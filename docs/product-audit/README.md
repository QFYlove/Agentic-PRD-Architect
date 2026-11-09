# Product Audit

长期维护的产品质量审计记录。问题台账、解决方案日志和架构图都放在这个目录，后续每次修改都要同步更新。

## 第一阶段审计（只读）

- 审计日期：2026-11-08
- 基线提交：`cd56107`（main）
- 审计方式：静态阅读源码、Prompt、Schema 和测试；运行已有确定性单元测试；分析用户导出的两份云盘 PRD 样例（`~/Downloads/agentic-prd-9fa59292-…-v1.md` / `-v2.md`）。
- 没有修改业务代码、Prompt、Schema、配置或依赖，没有调用模型，没有产生费用。
- 本地 SQLite（`data/agentic-prd.sqlite3`）未读取。按本轮限制，需要读取数据库的验证列为待验证项。

### 审计目标

逐项定位 PA-001 至 PA-008 的根因，区分已确认和待确认的部分，并建立可持续维护的问题台账。

### 审计范围

| 范围 | 内容 |
|---|---|
| 后端 | `backend/`：FastAPI 入口、Schema、Prompt、LangGraph 工作流、RunManager、Provider、事件与快照存储、错误类型 |
| 前端 | `src/`：Dashboard、各标签页组件、reducer、SSE hook、错误文案、样式与 Tailwind 配置 |
| 测试 | `backend/tests/`、`src/**/*.test.ts(x)`、`e2e/*.spec.ts` |
| 样例 | 一次真实模型运行导出的 v1 / v2 PRD |
| 不在范围 | `prd_benchmark/`、`benchmark/`（独立评测工程，本轮未审计） |

### 架构摘要

一次运行由 `POST /api/runs` 创建，`RunManager` 建立快照并启动 `AgentWorkflow`（LangGraph）。图结构为 generator → 三个 reviewer 并行 → aggregator →（未达门槛）optimizer → generator 循环。每一步通过 `RunManager.commit` 修改快照并追加事件，事件经 SSE 推送到前端 `runReducer`。详见 [architecture-map.md](architecture-map.md)。

## 问题总览

| ID | 问题 | 状态 | 优先级 |
|---|---|---|---|
| PA-001 | 用户输入完整展示，页面冗杂 | CONFIRMED | P2 |
| PA-002 | PRD 过长，大段文字，结构不清 | PARTIALLY_CONFIRMED | P1 |
| PA-003 | 三方评审冗长、泛泛、重复 | PARTIALLY_CONFIRMED | P1 |
| PA-004 | 工作流失败反馈不合理 | CONFIRMED（v2 两次尝试均触达 16000 输出 token 上限） | P0 |
| PA-005 | 运行记录缺乏实际作用 | CONFIRMED | P2 |
| PA-006 | 评分标准与综合评分不透明 | CONFIRMED | P1 |
| PA-007 | 前端视觉与信息架构不佳 | PARTIALLY_CONFIRMED | P2 |
| PA-008 | PRD 事实、假设与跨章节一致性风险 | CONFIRMED（数据库追溯） | P1 |
| PA-009 | 输出截断后用相同请求重试，必然再次失败并重复计费 | CONFIRMED（数据库审计中新发现） | P1 |

台账状态值（OPEN、CONFIRMED、SOLUTION_PROPOSED 等）见 [issue-register.md](issue-register.md)。上表的"状态"是第一阶段审计时的根因确认程度。

## 问题总览（V2.0 实施后，2026-11-08）

| ID | 问题 | 台账状态 | 优先级 | 方案 |
|---|---|---|---|---|
| PA-001 | 用户输入完整展示，页面冗杂 | VERIFIED | P2 | SL-006 |
| PA-002 | PRD 过长，大段文字，结构不清 | FIXED_PENDING_VERIFICATION（需真实模型验证） | P1 | SL-003 |
| PA-003 | 三方评审冗长、泛泛、重复 | FIXED_PENDING_VERIFICATION（需真实模型验证） | P1 | SL-004 |
| PA-004 | 工作流失败反馈不合理 | VERIFIED | P0 | SL-002 |
| PA-005 | 运行记录缺乏实际作用 | VERIFIED | P2 | SL-006 |
| PA-006 | 评分标准与综合评分不透明 | VERIFIED | P1 | SL-005 |
| PA-007 | 前端视觉与信息架构不佳 | FIXED_PENDING_VERIFICATION（需用户确认视觉方向） | P2 | SL-006 |
| PA-008 | PRD 事实、假设与跨章节一致性风险 | FIXED_PENDING_VERIFICATION（需真实模型验证） | P1 | SL-003、SL-004 |
| PA-009 | 输出截断后用相同请求重试 | VERIFIED | P0 | SL-002 |
| PA-010 | 11 个前端文件在基线即不符合 Prettier | OPEN | P2 | — |

## V2.0 剩余工作

1. 用一条合成的短需求做一次真实模型冒烟测试（需要用户批准费用和配置），验证 PA-002 / PA-003 / PA-008 的输出质量：篇幅、列表与表格比例、数字标注、评审条数。
2. 用户确认 PA-007 的视觉方向（截图见 `test-results/layout/`）。
3. 单独提交一次格式化，关闭 PA-010。

## 文档入口

| 文档 | 用途 |
|---|---|
| [implementation-plan.md](implementation-plan.md) | V2.0 实施计划与 Phase 0 基线 |
| [issue-register.md](issue-register.md) | 问题台账。每个问题一条记录，持续更新状态 |
| [solution-log.md](solution-log.md) | 解决方案与开发过程日志，只追加，不覆盖 |
| [architecture-map.md](architecture-map.md) | 模块关系、工作流、Prompt/Schema、评分、持久化、API 和数据流 |

## 第一阶段执行记录

| 项目 | 内容 |
|---|---|
| 开始时工作区 | `M .env.example`、`?? prd_benchmark/`（均为审计前已有的用户改动，未触碰） |
| 结束时工作区 | 在上述基础上只新增 `?? docs/product-audit/` |
| 阅读的核心文件 | `backend/` 的 schemas、prompts、workflow、run_manager、providers/compatible、providers/base、prd_document、errors、config、state_machine、main、run_store（部分）、event_store（部分）；`src/` 的 AgentDashboard、PRDViewer、ReviewPanel、AgentTrace、TelemetryPanel、RunControls、runReducer（部分）、useAgentRun（部分）、errorMessages、failureNotice、trace、nodeTimings、download；其他前端组件和 `e2e/layout.spec.ts` 由子代理阅读，关键行号已抽查 |
| 运行的检查 | `pytest`（Mock、`DATABASE_PATH=:memory:`）：290 passed；`vitest run`：17 个文件、194 个测试通过；用本地 Python 打印 `RoleReview` / `RevisionPlan` 的 strict JSON Schema（无网络） |
| 模型调用 / 费用 | 无 / 无 |
| 未完成的检查 | 读取本地 SQLite 中运行 `9fa59292-…` 的快照（被权限拒绝，按本轮限制列为待验证）；启动前端截图；`npm run test:e2e`（需要启动服务）；`.env` 内容未读取 |

## 数据库只读审计记录（2026-11-08）

| 项目 | 内容 |
|---|---|
| 授权 | 用户在第一阶段审计后明确批准，范围限定为运行 `9fa59292-af6e-44d1-aacc-aff10e4a4024` |
| 方式 | Python `sqlite3`，URI `file:…/data/agentic-prd.sqlite3?mode=ro`，`PRAGMA query_only=ON`（返回 1）；先查 `sqlite_master` 表结构，再执行带 `WHERE run_id = ?` 的 SELECT |
| 读取内容 | `runs` 表中该运行的快照：状态、错误、节点状态、耗时、token、v1 正文和评审、修订计划、`current_prd` 统计；`run_events` 表中该运行的 28 条事件 |
| 未做的事 | 没有写操作，没有复制或导出数据库，没有读取 `.env`，没有调用模型或外部服务；用户输入只输出统计数字和简短片段 |
| 第一次尝试 | 被权限分类器拒绝一次，用户批准后重试成功 |
| 结果 | 已写入 [issue-register.md](issue-register.md)：PA-001 / 002 / 003 / 004 / 005 / 008 的 DB Evidence 行、新增的 PA-009，以及附录 A |
| 结束时工作区 | 与本轮开始时相同，只有 `docs/product-audit/` 下的文档变化 |

## 维护约定

1. 确定方案后，在 `solution-log.md` 追加一条记录，并在台账中更新状态和引用。
2. 实施时记录实际修改的文件、测试和结果。
3. 验收通过后才能标记 VERIFIED 或 CLOSED。
4. 不删除、合并或覆盖已有问题。新问题从 PA-009 开始编号。
5. 代码结构变化时同步更新 `architecture-map.md`。
