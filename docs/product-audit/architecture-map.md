# Architecture Map

基线：`cd56107`，2026-11-08。代码结构变化时更新本文件。

## 1. 目录与职责

| 目录 / 文件 | 职责 |
|---|---|
| `backend/main.py` | `create_app()`：按配置选择 Provider（Mock / Scenario / OpenAI-compatible），组装存储、RunManager、AgentWorkflow；注册 REST 和 SSE 路由及统一错误处理 |
| `backend/run_manager.py` | 运行生命周期：创建、启动、暂停、恢复、取消、失败；`commit()` 是唯一的快照修改入口，同时追加事件；记录 token、耗时、费用 |
| `backend/workflow.py` | LangGraph 图和六个节点的实现；异常到错误码的映射 |
| `backend/schemas.py` | 全部 Pydantic 模型：请求、评审、评估、修订计划、版本、快照、事件 |
| `backend/prompts.py` | 所有系统 Prompt：评分锚点、严重度规则、文档写法规则、Generator / 三个 Reviewer / Optimizer |
| `backend/prd_document.py` | 生成完整性校验：`finish_reason` 分类和 `<!-- PRD_COMPLETE -->` 标记 |
| `backend/providers/` | `base.py` 接口；`compatible.py` DeepSeek/GLM 适配；`mock.py`、`scenario.py` 测试用 |
| `backend/errors.py` | `AppError`（HTTP 错误）和 `ProviderError` 层级（工作流错误码） |
| `backend/state_machine.py` | 运行状态转换表 |
| `backend/run_store.py` / `event_store.py` | 快照与事件的内存 / SQLite 存储，SSE 回放 |
| `backend/telemetry.py` / `observability.py` | token 累加和费用估算；结构化日志 |
| `src/components/AgentDashboard.tsx` | 主页面：侧栏、运行头部、标签页、运行控制 |
| `src/hooks/useAgentRun.ts` | 创建 / 恢复运行、SSE 连接与重连、控制操作 |
| `src/lib/runReducer.ts` | 快照 + 事件 → 视图状态（版本草稿、评审、分数、修订计划、结果） |
| `src/lib/*` | API 客户端、契约校验、错误文案、失败提示、轨迹映射、diff |
| `contracts/v1/` | 前后端共享的 JSON 契约样例 |

## 2. 后端调用关系

```
HTTP route (main.py)
  └─ RunManager (run_manager.py)
       ├─ RunStore / EventStore (SQLite)
       ├─ ProviderCatalog → LLMProvider (providers/)
       └─ AgentWorkflow (workflow.py, LangGraph)
            ├─ prompts.py（经 Provider 拼接）
            ├─ schemas.py（解析与校验）
            └─ prd_document.py（生成完整性）
```

## 3. LangGraph 工作流

`workflow.py:85-112`

```
START → generator ─┬→ tech_reviewer ─┐
                   ├→ ux_reviewer  ──┼→ aggregator ─(gate passed / budget used)→ END
                   └→ biz_reviewer ─┘        └─(otherwise)→ optimizer → generator
```

- 图状态只有 `run_id`，真实状态在 `RunSnapshot` 中，节点通过 `RunManager.commit` 读写。
- 没有使用 LangGraph checkpointer。失败后无法从节点恢复，`FAILED` 是终态（`state_machine.py:82`）。
- generator：流式生成，最多 2 次尝试（`workflow.py:245-309`），每次尝试受 `generator_timeout_seconds` 和剩余运行时间约束。
- reviewer / optimizer：`_validated_structured`（`workflow.py:565-620`），传输失败重试 1 次，校验失败修复 1 次。
- 第二版起，generator 以 `best_version` 的全文作为 `baseline_prd`（`workflow.py:442-455`），要求在其上"最小编辑"并整篇重新输出。

## 4. Prompt 与 Schema 关系

| 调用 | 系统 Prompt | 用户载荷 | 输出约束 |
|---|---|---|---|
| Generator | `GENERATOR_SYSTEM_PROMPT` + `COMPOSITION_RULES` | `user_idea`、`target_audience`、`user_constraints`、`iteration`、`revision_plan`、`baseline_prd`（`compatible.py:189-200`） | 无 Schema。自由 Markdown，末行写完成标记 |
| Reviewer ×3 | 角色描述 + `SCORING_ANCHORS` + `SEVERITY_RUBRIC` | `required_role`、`prd`、`iteration`（`compatible.py:312-316`） | `RoleReview` 的 strict JSON Schema 文本放在系统 Prompt 中，`response_format=json_object` |
| Optimizer | `OPTIMIZER_SYSTEM_PROMPT` | `evaluation`、`iteration`、`user_override`（`compatible.py:331-335`） | `RevisionPlan` 的 JSON Schema |
| Repair | 原 Prompt | 非法值 + 校验错误 | 同原 Schema |

注意：
- Reviewer 看不到用户原始需求，也看不到上一轮评审和修订计划。
- Optimizer 看不到 PRD 正文。
- `to_strict_json_schema` 会把所有字段列为 required，包括 `strengths` 和 `feedback`。
- 结构化调用使用和生成相同的 `max_tokens`（`llm_max_output_tokens`，默认 16000）。

## 5. 评分机制

| 环节 | 由谁决定 | 代码 |
|---|---|---|
| 单角色分数（0-100 整数） | 模型直接输出，参考统一的 6 档锚点 | `schemas.py:183`，`prompts.py:13-24` |
| 每条意见的严重度 | 模型判断，参考 must_fix 准入规则 | `prompts.py:33-60` |
| 综合分 | 后端：三角色等权算术平均，保留 1 位小数 | `workflow.py:642`；`schemas.py:217-224` 校验 |
| must_fix 计数 | 后端统计 `combined_feedback` | `schemas.py:227-244`，`workflow.py:659-660` |
| 质量门槛 | 后端：`overall >= quality_threshold` 且 `must_fix == 0` | `workflow.py:661-662` |
| 最佳版本 | 后端：综合分严格高于历史最佳才替换 | `workflow.py:650-653` |

不存在：分维度评分、角色权重配置、Rubric 版本、评分依据字段、分数与意见的一致性校验。

## 6. 数据持久化

- `RunSnapshot`（`schemas.py:327-403`）整体序列化为 JSON，存入 SQLite `runs` 表（`run_store.py:189`）。
- 事件存入 `run_events` 表（`event_store.py:174`）。`prd_delta` 是瞬时事件，不落库、不写快照（`event_store.py:14`，`run_manager.py:398-405`）。
- 版本列表 `versions` 只追加完成的版本；失败的生成不会写入版本，也不会改动 `best_version`。
- 后端重启时，未结束的运行被标记为 `FAILED / RUN_INTERRUPTED`（`run_store.py:202-221`），不追加事件。

## 7. 核心 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/providers` | 可选 Provider / Model |
| GET | `/api/runs` | 运行列表（`RunSummary`） |
| POST | `/api/runs` | 创建运行（`CreateRunRequest`） |
| GET | `/api/runs/{id}` | 完整快照 |
| POST | `/api/runs/{id}/pause` / `resume` / `cancel` | 运行控制 |
| GET | `/api/runs/{id}/events` | SSE，支持 `after_sequence` 和 `Last-Event-ID` |

没有"失败后重试 / 从节点恢复"的接口。

错误响应统一为 `{error: {code, message, request_id}}`（`main.py:80-97`）。工作流内部失败写入快照的 `error: RunError{code, message, retryable}`，并发出 `run_failed` 事件。

## 8. 前端页面与组件

```
index.astro → Layout.astro → AgentDashboard (client:only)
  ├─ ConversationSidebar（历史运行）
  ├─ 无运行：Hero + ProductIdeaForm（ProviderModelSelector）
  └─ 有运行：运行头部
       ├─ StatusBadge、连接状态、user_idea、run_id
       ├─ OutcomePanel、失败提示、VersionRail、"目标 N"
       ├─ WorkspaceTabs
       │    ├─ PRD：PRDViewer（react-markdown + remark-gfm，MermaidBlock）
       │    ├─ 评审：ReviewPanel
       │    ├─ 修订计划：RevisionPlanPanel
       │    ├─ 对比：VersionDiff
       │    └─ 运行记录：WorkflowDiagram、AgentTrace、RadarScoreChart、TelemetryPanel
       └─ RunControls
```

## 9. 关键数据流

1. 创建：`ProductIdeaForm` → `api.createRun` → `POST /api/runs` → `CreateRunRequest` → `RunManager.create_run`（检测输出语言、绑定 Provider）→ `AgentWorkflow.run`。
2. 生成：`_generator_node` → `provider.stream_prd` → `prd_delta`（瞬时）→ `validate_generated_prd` → `PRDVersion` 追加 → `prd_generated`。
3. 评审：三个 `_reviewer_node` 并行 → `generate_review` → `RoleReview` 校验 / 修复 → `snapshot.reviews[role]` → `review_completed`。
4. 汇总：`_aggregator_node` → `EvaluationResult`（平均分、拼接意见）→ `scores_updated` → 门槛判断 → `run_completed` / `max_iterations_reached` / 进入 optimizer。
5. 优化：`_optimizer_node` → `generate_revision_plan` → `RevisionPlan` → `pending_revision_plan`，`current_iteration += 1` → `revision_planned` → 回到 generator。
6. 前端：`useAgentRun.hydrate` 拉快照 → `SNAPSHOT_LOADED`；非终态时 SSE 从 `latest_event_sequence` 之后续接 → `EVENT_RECEIVED` → `applyEvent`。终态运行不连接 SSE，`state.events` 为空。
7. 失败：节点异常 → `AgentWorkflow.run` 的 except 分支或 `RunManager._run_workflow` 的兜底 → `fail_run` → 快照 `error` + `run_failed` 事件 → 前端按 `error_code` 查 `errorMessages.ts`。

## 10. V2.0 变更（2026-11-08）

上文第 3–9 节描述的是基线 `cd56107`。V2.0 之后的差异：

| 范围 | 变化 |
|---|---|
| 新模块 | `rubric.py`（维度、权重、锚点、版本）、`scoring.py`（评审归一化、角色分 / 综合分、去重、门槛状态、问题处理状态、修订计划构建）、`prd_quality.py`（Markdown 结构与数字标注检查）、`failures.py`（重试与错误分类表） |
| 模型侧契约 | Reviewer 输出 `ReviewerOutput`（dimension_scores、findings、resolutions，无总分）；Optimizer 输出 `OptimizerOutput`（change_type、source_finding_ids、target/affected_sections、must_preserve、declined_findings）。存储仍为 `RoleReview` / `RevisionPlan`，新增字段均可选 |
| Reviewer 输入 | user_requirements + automated_checks + previous_findings + prd |
| Optimizer 输入 | user_requirements + 基线 PRD（超过 60,000 字时为目录 + 相关章节）+ 去重后的 findings（每条一次）+ role_scores + quality_report |
| 评分 | 后端：`RoleScore = Σ(dim/5 × weight) × 100`，`Overall = 三角色平均`；门槛状态 PASSED / NEEDS_REVISION / BLOCKED / UNSCORED |
| 重试 | 只重试 transient（网络、5xx、429、单次超时、未完成流），最多 2 次，带退避；截断不重试；结构化修复最多 1 次 |
| 失败 | 节点 `_guard` 标注节点、阶段、版本、尝试；`RunError` 带 stage / node / version / attempt / recovery_action / category / trace_id；`incomplete_draft` 记录半成品 |
| API | 新增 `POST /api/runs/{id}/recover`、`GET /api/runs/{id}/history`、`GET /api/rubric`；`CreateRunRequest.generation_mode` |
| 前端 | RunRequest（需求概览）、FailurePanel、RunTimeline（用户视图 + 开发者折叠区）、PRD 目录与问题侧栏、单列评审列表、修订计划状态；草稿 `interrupted` 状态 |
| 持久化 | 表结构不变；快照 JSON 增加可选字段，旧行原样加载 |

## V3 项目工作台（2026-11-08 新增）

V2 的 `/api/runs`、`RunSnapshot` 存储、`contracts/v1` 不变，只读历史在前端 `/runs`。V3 是独立的一套：

| 模块 | 职责 |
|---|---|
| `backend/v3/store.py` | `v3_*` 表；`MIGRATIONS` 编号迁移，记录在 `v3_schema_migrations`；迁移前备份；`rollback_v3` |
| `backend/v3/jobs.py` | `JobManager`：每次 AI 调用一个 Job；复用 `failures.py` 的重试 / 截断不重试 / 分类；JobEvent 持久化（`section_delta` 只走内存）；重启时把未完成 Job 标为 `JOB_INTERRUPTED` |
| `backend/v3/explore.py` | 项目、对话、问题、需求条目与修改记录、Requirement Explorer、Product Analyst |
| `backend/v3/document.py` | Brief 快照、大纲、逐章流式生成、章节编辑（乐观锁）、确定性影响分析、版本、diff、导出、入口 C 导入 |
| `backend/v3/review.py` | Product / UX / Tech / Biz 四个 Reviewer 并行；Aggregator：准入、跨角色合并、与项目 Finding 匹配、复查结论、评分 |
| `backend/v3/optimize.py` | 只对已采纳 Finding 生成提案；用户选择后按 row_version 应用并生成新版本 |
| `backend/v3/quality.py` | 文档质量、需求成熟度、实施就绪度、风险与阻塞，分开计算 |
| `backend/v3/mock.py` | 读取真实 payload 的确定性网关，开发和测试用 |
| `src/v3/` | 前端工作台；`store.ts` 加载项目数据并跟随 Job SSE，`useJob.ts` 断线后按序号续传 |

```
POST /api/v3/... → service (explore/document/review/optimize) → JobManager.start → gateway (Mock / Compatible)
                                                              ↘ 规则校验后写入 v3_* 表 → JobEvent → SSE
```
