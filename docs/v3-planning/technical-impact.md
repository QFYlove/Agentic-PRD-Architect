# V3.0 技术影响分析

本文件说明 V3.0 对现有代码、数据结构和接口的影响。所有改动均**尚未实施**。现状依据见 [gap-analysis.md](gap-analysis.md)。

## 1. 数据模型建议

当前所有数据存在两张表：`runs(run_id, snapshot_json, updated_at)`（`run_store.py:193`）和 `run_events(run_id, sequence, event_json)`（`event_store.py:192`），快照整体序列化。V3.0 改为按对象建表，仍使用 SQLite（WAL），不引入图数据库（定义 6.2）。

| 表 | 主要字段 | 说明 |
|---|---|---|
| `projects` | id, code（P-0007）, name, entry_mode（idea / requirement / review）, stage, created_at, updated_at, deleted_at | 不设 TTL；软删除后由用户确认清理 |
| `messages` | id, project_id, round, role（user / ai）, content, created_at | 对话记录 |
| `questions` | id（Q-06）, project_id, round, priority, text, purpose, target_category, finding_id, state（pending / answered / skipped / unknown）, answer_message_id | 每轮问题与处理结果 |
| `requirement_items` | id（USR-01）, project_id, category, content, status, source_kind（user / ai）, source_round, source_quote, priority, extra_json, updated_at | 一张表承载 12 个分组；Assumption / Decision / OpenQuestion 的专属字段在 extra_json |
| `item_revisions` | id, item_id, before, after, before_status, after_status, actor（user / ai）, reason, created_at | 修改与确认记录（定义 8.2"查看信息修改历史"） |
| `links` | from_id, to_id, kind（derives / implements / verifies / conflicts / affects）, origin（ai / user / rule） | 需求 ↔ 条目 ↔ 章节 ↔ 规则 ↔ 验收 |
| `briefs` | id, project_id, version, narrative_json, item_snapshot_json, confirmed_at, confirmed_by | 基线快照，冻结条目 ID 与内容 |
| `prd_sections` | id, project_id, parent_id, position, level, num, title, body_md, origin（ai / optimized / human）, locked, updated_at, row_version | 当前草稿的章节；`row_version` 做乐观锁 |
| `prd_versions` | id, project_id, label（v3）, source（ai_generate / ai_optimize / human）, note, created_at, sections_json | 版本快照（章节 id、标题、正文、来源） |
| `findings` | id（F-01 / FD-03）, project_id, scope（baseline / prd）, kind, reviewer, severity, title, evidence, problem, impact, recommendation, confidence, status, verification, user_note, related_items_json, related_sections_json, first_seen_version, last_checked_version, decided_at | 项目级、跨版本稳定 ID |
| `jobs` | id, project_id, kind（explore / analyze / outline / section / review / optimize / impact）, status, input_ref, error_json, tokens_json, cost, started_at, finished_at, trace_id | 每次 AI 调用一条，替代 Run 作为执行单元 |
| `job_events` | job_id, sequence, event_json | 与现有 `run_events` 同构，复用 SSE 回放 |

### 状态定义

- `requirement_items.status`：confirmed / inferred / assumption / proposed / open / rejected（定义 3.4）。只有用户操作能把非 confirmed 变为 confirmed；后端在服务层强制，不依赖前端。
- `findings.status`（用户）：open / accepted / modified / rejected / deferred / resolved / stale。
- `findings.verification`（AI 复查）：resolved / partially_resolved / unresolved / not_checked，沿用现有 `FindingStatus`（`schemas.py:121-132`）的值。

### 关键约束

1. `source_kind=user` 的条目必须带 `source_quote`，后端检查该片段出现在某条用户消息中，否则降为 `inferred`。
2. Optimizer 写入 `origin=human` 或 `locked` 的章节时，只能生成提案，不能直接更新。
3. Brief 确认后，`briefs.item_snapshot_json` 不可修改；之后的基线修改需要新的 Brief 版本。
4. 版本快照只追加，不覆盖（定义 6.3）。

## 2. 对现有后端代码的影响

| 文件 | 影响 | 处理 |
|---|---|---|
| `schemas.py` | `RunSnapshot`、`PRDVersion` 等 V1/V2 模型保留，供旧运行只读加载；新增 V3 模型放在新模块 | 不改旧模型，避免破坏 `contracts/v1` |
| `run_store.py` / `event_store.py` | 存储模式不适合项目数据 | 保留给旧运行；新增 `project_store.py`（按表读写，不在启动时全量加载） |
| `run_manager.py` | `commit()` 是唯一修改入口、带事件追加，这一模式值得保留 | 新增 `JobManager`，沿用"修改 + 追加事件"的单入口设计；`RunManager` 只保留读取旧运行 |
| `workflow.py` | LangGraph 自动循环 | 循环本身不再是默认路径。节点内部逻辑（`_validated_structured`、流式生成、`_guard`、质量检查）抽成可单独调用的函数，供各 Job 使用 |
| `prompts.py` | Generator / Reviewer / Optimizer Prompt | Reviewer、Optimizer 基本复用（输入改为章节）；Generator 拆为大纲和单章两个 Prompt；新增 Explorer、Analyst Prompt |
| `scoring.py` | 评分、去重、复查、修订计划构建 | 复用；`deduplicate` / `is_same_problem` 增加"与项目已有 Finding 匹配"；`resolve_previous_findings` 改为写 `verification` |
| `rubric.py` | | KEEP |
| `prd_quality.py` | 整篇 Markdown 检查 | 增加按章节检查的入口；必需章节检查改为按大纲检查 |
| `failures.py` / `errors.py` | | KEEP；新增 Job 类型到 `NODE_STAGES` |
| `providers/*` | | 接口新增 4 个方法；Mock、Scenario 同步 |
| `state_machine.py` | Run 状态 | 保留给旧运行；Job 状态更简单，新建小状态表 |
| `main.py` | 路由 | 新增 `/api/v3/...` 路由组；CORS 增加 PATCH / DELETE |
| `config.py` | `run_ttl_seconds`、`max_retained_runs` | 不作用于项目 |

## 3. API 建议

旧接口（`/api/runs/*`、`/api/rubric`）保持不变。新接口放在 `/api/v3` 前缀下。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/api/v3/projects` | 列表 / 创建（含入口方式与初始输入） |
| GET / PATCH / DELETE | `/api/v3/projects/{id}` | 详情（含阶段与计数）/ 改名 / 删除 |
| GET | `/api/v3/projects/{id}/conversation` | 消息与问题 |
| POST | `/api/v3/projects/{id}/turns` | 提交一轮回答（回答、跳过、不知道），返回 job_id |
| GET | `/api/v3/projects/{id}/items` | 基线 |
| PATCH | `/api/v3/items/{id}` | 编辑内容 / 改状态（确认、拒绝、恢复） |
| GET | `/api/v3/items/{id}/revisions` | 修改记录 |
| POST | `/api/v3/projects/{id}/analyze` | 触发 Analyst |
| GET / POST | `/api/v3/projects/{id}/briefs` | Brief 版本列表 / 生成草稿 |
| POST | `/api/v3/briefs/{id}/confirm` | 确认 Brief |
| POST | `/api/v3/projects/{id}/outline` | 生成大纲 |
| GET / PUT | `/api/v3/projects/{id}/sections` | 章节列表 / 批量调整顺序 |
| POST / PATCH / DELETE | `/api/v3/sections/{id}` | 新增 / 保存（带 row_version）/ 删除 |
| POST | `/api/v3/projects/{id}/generate` | 按大纲逐章生成 |
| POST | `/api/v3/projects/{id}/reviews` | 触发三方评审（可限定章节） |
| GET | `/api/v3/projects/{id}/findings` | Finding 列表（筛选 scope / reviewer / status） |
| PATCH | `/api/v3/findings/{id}` | 用户处理（status、user_note） |
| POST | `/api/v3/projects/{id}/optimize` | 对采纳的 Finding 生成修改提案 |
| POST | `/api/v3/proposals/{id}/apply` | 用户确认提案（可部分应用） |
| POST | `/api/v3/projects/{id}/impact` | 对未检查的修改做语义检查 |
| GET / POST | `/api/v3/projects/{id}/versions` | 版本列表 / 保存版本 |
| GET | `/api/v3/projects/{id}/versions/{a}/diff/{b}` | 对比 |
| GET | `/api/v3/projects/{id}/export.md` | 导出 |
| GET | `/api/v3/jobs/{id}` / `/events` | 任务状态 / SSE |

## 4. 工作流编排

| 场景 | 现在 | V3.0 |
|---|---|---|
| 一轮探索 | 不存在 | 同步 HTTP + 短任务：提交回答 → Job（explore）→ 写消息、条目、问题 → 推送 `turn_completed`。单轮预期较短，前端显示"正在整理回答" |
| 生成 PRD | 一个 Run 内循环最多 5 版 | Job（outline）→ 用户确认 → Job（section）× N，按大纲顺序逐章执行，每章一个 `section_delta` 流 |
| 评审 | 每版自动执行 | Job（review）：三个 Reviewer 并行（可继续用 LangGraph 的 fan-out / join，或 `asyncio.gather`），Aggregator 代码汇总 |
| 优化 | 自动执行 | Job（optimize）只产出提案；应用提案是普通 API 调用，不调用模型 |

LangGraph 在 V3.0 中的价值变小：只有评审的 fan-out / join 和逐章生成有图结构。建议保留依赖但不强制，评估 `asyncio.gather` 是否足够；不引入 checkpointer（逐章生成已经提供了断点）。

## 5. 历史数据兼容

- 不修改 `runs`、`run_events` 表，也不迁移旧运行到项目。旧运行在工作台底部以"历史运行（只读）"列出，可查看、下载，不可编辑。
- 如果用户希望把某次旧运行转成项目：提供"从历史运行创建项目"，把最佳版本按入口 C 导入（切章节、进入审查）。这是复制，不改原记录。
- 新表放在同一个 SQLite 文件中，使用 `CREATE TABLE IF NOT EXISTS`；建表前备份数据库文件。是否单独建库见 [open-decisions.md](open-decisions.md) D-06。
- `contracts/v1/` 不变；V3 契约放 `contracts/v3/`。

## 6. 前端影响

| 现有 | 处理 |
|---|---|
| `AgentDashboard.tsx` 单页 + 标签页 | 替换为项目路由：`/`（工作台）、`/p/{id}/explore`、`/p/{id}/solution`、`/p/{id}/brief`、`/p/{id}/prd`、`/p/{id}/review`、`/p/{id}/versions` |
| `runReducer.ts`（快照 + 事件 → 视图） | 模式保留（快照 + 事件去重），按对象拆分：项目、基线、章节、Finding 各自缓存，避免定义 10.4"面板因每次对话整体重新加载" |
| `useAgentRun.ts` SSE 重连 | 抽出通用的 `useJobEvents`，复用重连、`after_sequence`、序号去重 |
| `global.css` / `tailwind.config.mjs` 深色变量 | 新建 V3 设计变量（见 [design-system.md](design-system.md)）。Tailwind 可继续使用，但颜色、圆角、阴影全部换成新 token；建议新页面用 CSS 变量 + 少量组件类，和原型一致 |
| `PRDViewer`、`ReviewPanel`、`VersionDiff` 等 | 视觉与结构重做；`readingDiff`、`diff`、`prdOutline`、`download`、`errorMessages`、`failureNotice` 纯函数直接复用 |
| `lucide-react`、`recharts`、`mermaid` | 原型没有使用图标库和图表库。V3 页面建议不用 recharts（定义 9.8 第 11 条）；Mermaid 保留用于 PRD 正文中的流程图 |

## 7. 测试影响

- 继续有效：`test_v2_quality.py`（评分、去重、复查）、`test_v2_reliability.py`（失败分类）、事件存储与 SSE 回放、Provider 适配、`readingDiff` / `diff` 测试。
- 需要重写：工作流循环、暂停 / 恢复、最大迭代相关测试（自动循环降级后）；e2e happy-path。
- 新增重点（对应定义 12.2）：
  1. AI 抽取的条目不能以 confirmed 写入。
  2. `source=user` 条目必须有原文片段。
  3. Optimizer 不能直接修改 human 章节。
  4. 只有 accepted / modified Finding 进入优化输入。
  5. 被拒绝的 Finding 在下一次评审中不重复出现（匹配后保持 rejected）。
  6. 保存章节后关联 Finding 变为 stale；格式修改不触发。
  7. 单章生成失败不影响已完成章节。
  8. 乐观锁冲突返回 409，不覆盖。
  9. 删除项目需要确认，删除后不可通过 API 读取。

## 8. 主要技术风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 探索每轮的上下文成本随项目增长 | 费用、延迟 | 只发压缩基线 + 最近 3 轮；记录每轮 token |
| 模型抽取把推断写成用户原话 | 违反定义 2.3 | 原文片段校验；默认 inferred |
| 逐章生成导致章节间不一致 | PRD 质量 | 大纲先定术语与编号；生成后跑一致性检查和评审 |
| 跨版本 Finding 匹配不准 | 重复提问或误判已处理 | 保守匹配（V2.0 阈值）+ 用户可手动合并 |
| 关联关系漏标 | 影响分析漏检 | 规则补齐 ID 引用；用户可在追溯面板补关联 |
| 两套存储并存 | 维护成本 | 旧运行只读，冻结代码路径；设定移除时间点 |

