# Solution Log

解决方案与开发过程日志。**只追加，不覆盖。** 已有记录中的决策不能修改；方案变更时追加一条新记录，并在"关联记录"中引用旧记录。

问题定义和状态见 [issue-register.md](issue-register.md)。

## 记录编号

格式：`SL-<三位序号>`，例如 `SL-001`。一条记录对应一个问题的一次方案决策；一个问题可以有多条记录。

## 记录模板

复制下面的模板，追加到文件末尾。

```markdown
### SL-XXX <标题>

- 日期：YYYY-MM-DD
- 对应问题：PA-XXX
- 关联记录：（被替代或相关的 SL 编号，没有就写"无"）
- 记录状态：PROPOSED / APPROVED / IN_PROGRESS / IMPLEMENTED / VERIFIED / REJECTED

1. **问题背景**：
2. **已确认的根因**：（引用台账中的 Root Cause 和证据）
3. **方案目标**：
4. **候选方案**：
   | 方案 | 做法 | 优点 | 缺点 | 成本 / 风险 |
   |---|---|---|---|---|
5. **最终选择及理由**：
6. **放弃其他方案的原因**：
7. **计划修改的文件**：
8. **实际修改的文件**：（实施后填写）
9. **代码修改摘要**：（实施后填写）
10. **测试用例**：（新增或修改的测试及其覆盖内容）
11. **测试结果**：（命令和结果原文摘要）
12. **修改前后对比**：（数据、截图或样例）
13. **是否引入新问题**：（如有，新增 PA 编号并记录）
14. **最终验收结果**：（通过 / 不通过，验收人，日期）
```

## 记录

暂无。第一阶段审计（2026-11-08）只做了问题定位，没有确定或实施任何方案。

---

### SL-001 V2.0 基线与实施计划（Phase 0）

- 日期：2026-11-08
- 对应问题：PA-001 至 PA-009
- 关联记录：无
- 记录状态：IMPLEMENTED

1. **问题背景**：第一阶段审计和数据库审计已确认 PA-001 至 PA-009，用户授权一次性实施 V2.0。
2. **已确认的根因**：见 issue-register.md 各条 Root Cause 与附录 A。
3. **方案目标**：在不破坏历史数据和现有契约的前提下，按"可靠性 → 生成质量 → 评审 → 评分 → 前端"的顺序实施。
4. **候选方案**：见 [implementation-plan.md](implementation-plan.md)。
5. **最终选择及理由**：按模块依赖顺序实施（rubric → schemas → scoring / prd_quality / prompts → providers → workflow / run_manager → API → 前端）。所有新字段均为可选字段，不做数据库迁移。
6. **放弃其他方案的原因**：不重写 LangGraph 图、不引入 checkpointer、不更换前端技术栈，均因为成本和回归风险超出问题本身。
7. **计划修改的文件**：见各 SL 记录。
8. **实际修改的文件**：见各 SL 记录。
9. **代码修改摘要**：无（本条只记录基线）。
10. **测试用例**：无。
11. **测试结果（修改前基线）**：pytest 290 passed；vitest 194 passed（17 个文件）；ruff format / ruff check / mypy 通过；eslint 通过；astro check 0 错误；Playwright e2e 18 passed；prettier --check 有 11 个文件在基线即不通过（见 PA-010）。
12. **修改前后对比**：见 SL-007。
13. **是否引入新问题**：记录 PA-010。
14. **最终验收结果**：不适用。

### SL-002 截断不再重试、结构化失败信息、恢复运行（PA-004、PA-009）

- 日期：2026-11-08
- 对应问题：PA-004、PA-009
- 关联记录：SL-001
- 记录状态：VERIFIED

1. **问题背景**：运行 9fa59292 的 v2 两次发送相同的 18,225 token 请求，两次都在 16,000 token 处截断，68,450 token 没有产出版本；失败页只显示"v2 生成失败"，半成品显示为"正在生成"且可以下载。
2. **已确认的根因**：`ProviderOutputTruncatedError` 继承可重试错误；重试由类继承关系隐式决定；`run_failed` 不带节点和阶段；并行 reviewer 失败按"最后启动的节点"归属；未知异常不写日志；前端只看草稿是否完成，不看运行状态。
3. **方案目标**：截断只发生一次；每个失败都有错误码、阶段、节点、版本、尝试次数、是否可重试、下一步、trace_id；半成品不能被当作版本；失败后有安全的恢复入口。
4. **候选方案**：
   | 方案 | 做法 | 优点 | 缺点 | 成本 / 风险 |
   |---|---|---|---|---|
   | A 自动续写 | 截断后发一次"从断点继续"请求 | 可能自动救回 | 续写边界不可靠，容易重复或缺章节；仍是一次付费调用 | 中 / 中 |
   | B 截断后提高 max_tokens 重试 | 同请求，上限加大 | 简单 | 需要知道每个模型的上限和价格；仍可能截断 | 低 / 中 |
   | C 不自动重试，提供"精简模式重新生成 / 从最佳版本继续"，由用户发起新运行 | 新运行使用精简预算 | 不产生无效费用；不改动原运行；可预测 | 需要用户点一次 | 低 / 低 |
   | D LangGraph checkpointer 节点续跑 | 引入持久化 checkpoint | 真正的断点续跑 | 需要改图结构和状态存储，超出范围 | 高 / 高 |
5. **最终选择及理由**：C。用户明确要求"续写不可靠就不要自动继续"，且不允许不受控的多轮调用。
6. **放弃其他方案的原因**：A 续写边界无法可靠验证；B 依赖模型参数且不解决根因；D 改动面过大。
7. **计划修改的文件**：errors.py、新增 failures.py、workflow.py、run_manager.py、run_store.py、event_store.py、schemas.py、observability.py、config.py、main.py；前端 errorMessages.ts、failureNotice.ts、runReducer.ts、useAgentRun.ts、api.ts、PRDViewer.tsx、VersionRail.tsx、AgentDashboard.tsx，新增 FailurePanel.tsx。
8. **实际修改的文件**：同上，另有 providers/scenario.py（新增 `output_truncated`、`optimizer_failure` 场景）。
9. **代码修改摘要**：
   - `ProviderOutputTruncatedError` 改为不可重试，不再继承 `RetryableProviderError`。
   - `backend/failures.py`：一张表决定重试和报告。`is_transient`（网络、5xx、429、未完成流、单次调用超时可重试；截断、整次运行超时、认证、参数错误不可重试）；`backoff_seconds`（优先 Retry-After，否则指数退避，上限 20 秒）；`classify` 输出错误码、可重试、类别（transient / permanent / output_limit / interrupted）和下一步（continue_from_best / regenerate_compact / retry / check_configuration / edit_input）。
   - 区分 `NODE_TIMEOUT`（单次调用）和 `RUN_TIMEOUT`（整次运行）。
   - 每个 LangGraph 节点包一层 `_guard`，把节点名、阶段、版本写到异常上；并行 reviewer 的失败归属到真正抛出异常的节点，其他仍在运行的兄弟节点标为 SKIPPED。
   - `RunError` 增加 stage、node、version、attempt、recovery_action、category、trace_id、occurred_at；`run_failed` 事件携带完整 error 和 node_statuses。
   - 每次运行生成 `trace_id`；未知异常用 `log_exception` 记录异常类型和脱敏后的堆栈（Bearer、sk-、api_key/password 等被遮蔽，长度上限 6000）。
   - 失败时如果有未完成的流式文本，记录 `incomplete_draft`；后端重启中断的运行同样记录。
   - 新接口 `POST /api/runs/{id}/recover`（restart / regenerate_compact / continue_from_best），创建新运行，原运行不变；`continue_from_best` 以原运行最佳完整版本为底稿、精简模式，并沿用由该版本产生的修订计划。
   - 新接口 `GET /api/runs/{id}/history`，返回持久化事件。
   - 前端：草稿增加 `interrupted` 状态，`isUsableDraft` 决定能否下载、对比、默认选中；失败后自动选中最佳完整版本；失败面板回答"发生了什么 / 失败步骤 / 仍可使用 / 下一步"，并提供恢复按钮；配置类错误只给说明不给重试按钮。
10. **测试用例**：`test_v2_reliability.py`（24 个）、`test_generation_reliability.py` 中替换原第 220 行的 `test_truncation_is_never_retried_with_the_same_request` 及 3 个恢复测试、`test_workflow.py` 超时测试、前端 `runFailures.test.ts`、`v2.test.tsx`、e2e `failures.spec.ts` 新增截断 + 恢复场景和 optimizer 失败场景。
11. **测试结果**：见 SL-007。
12. **修改前后对比**：截断请求次数 2 → 1；失败节点从"最后启动的节点"改为实际节点；失败页从一行标题改为原因 + 步骤 + 可用结果 + 恢复按钮；半成品从"正在生成 + 可下载"改为"未完成 · 已中断 + 下载禁用"。截图：`test-results/layout/desktop-failed-truncation.png`。
13. **是否引入新问题**：恢复运行是新运行，会再次消耗 token（由用户主动点击，属于预期）。
14. **最终验收结果**：通过（Mock + e2e + 浏览器截图），2026-11-08。真实模型截断场景未实测。

### SL-003 生成质量：篇幅预算、结构规则、事实与假设、修订计划（PA-002、PA-008）

- 日期：2026-11-08
- 对应问题：PA-002、PA-008
- 关联记录：SL-001
- 记录状态：IMPLEMENTED（待真实模型验证）

1. **问题背景**：样例 PRD 无列表、长段落增多、v2 增长 51%；64 个新增数字无来源，出现编造的"内部试点观测值"；修改一处规则后其他章节保留旧规则。
2. **已确认的根因**："Prose by default"；无篇幅预算；修订只增不减；评分锚点鼓励量化；Optimizer 看不到 PRD；`target_section` 只有一个；无一致性检查。
3. **方案目标**：结构清晰、篇幅受控、数字有标签、修改能删能合并、改规则时同步所有出现处。
4. **候选方案**：
   | 方案 | 做法 | 优点 | 缺点 | 成本 / 风险 |
   |---|---|---|---|---|
   | A 只改 Prompt | | 低成本 | 无法验证 | 低 / 中 |
   | B Prompt + 确定性检查 + 修订计划结构化 + Optimizer 上下文 | | 可测试、兼容 | 不能保证模型遵守 | 中 / 低 |
   | C 整份 PRD 改为 JSON 章节输出再渲染 | | 结构最强 | 模型输出稳定性风险大，改动下载、对比、渲染全链路 | 高 / 高 |
5. **最终选择及理由**：B。保留 `content: str` 为存储和展示格式；结构由 `prd_quality.py` 从 Markdown 确定性解析，结果作为可选的 `PRDVersion.quality` 存储。
6. **放弃其他方案的原因**：C 风险最大，且用户要求不要把 PRD 设计成复杂 JSON；A 无法验收。
7. **计划修改的文件**：prompts.py、新增 prd_quality.py、schemas.py、scoring.py、workflow.py、providers/base.py、providers/compatible.py。
8. **实际修改的文件**：同上，另有 language.py（新字段名加入语言指令）。
9. **代码修改摘要**：
   - Generator Prompt 删除 "Prose by default"，改为：短段落写理由，列表写功能/规则/异常/验收，有序步骤写流程，表格写多属性信息，段落不超过 300 字；8 个必需章节骨架；P0/P1/P2/暂不纳入的差异化详略；标准模式 12,000–18,000 字、精简模式 7,000–11,000 字预算。
   - 事实规则：数字必须标注 [用户输入] / [已验证事实] / [假设] / [建议] / [待确认]；禁止"内部试点""调研显示"等用户未提供的来源；"假设与待确认事项"表格（事项、类型、为什么需要、影响的决策、验证方式、阶段/负责人）。
   - 修订：Generator 按 change_type 执行 ADD / UPDATE / REMOVE / CONSOLIDATE / RETAIN，改规则时同步 affected_sections，保留 must_preserve，修订不得超出预算。
   - `prd_quality.check_prd`：必需章节、标题层级跳级、空章节、重复标题、重复章节编号、超长段落、段落内编号枚举、未标注数字、编造来源、超预算。只告警，不让生成失败；缺必需章节时 `structure_complete=false`。
   - Optimizer 输入改为：用户原始需求 + 基线 PRD 全文（超过 60,000 字时给目录 + 相关章节全文）+ 去重后的 findings（每条一次）+ 角色分 + 结构检查摘要。不再发送 `evaluation` 全量（消除 43% 的重复）。
   - Optimizer 输出 `OptimizerOutput`：每项含 change_type、source_finding_ids、target_sections、affected_sections、reason、expected_result、must_preserve；`declined_findings` 记录不采纳原因。后端 `build_revision_plan` 从 finding id 推导来源角色，丢弃不存在的 id，未计划也未拒绝的 must_fix 自动补入。
   - 评审拿到结构检查结果（automated_checks），用于确认或排除编造来源等问题。
10. **测试用例**：`test_node_timings.py` 中替换 "Prose by default" 测试为结构规则、篇幅预算、事实规则、长段落检查 4 个测试；`test_v2_quality.py` 中质量检查 6 个、修订计划 4 个；`test_compatible_provider.py` 中 Optimizer 载荷测试（含 PRD、每个 finding 只出现一次）。
11. **测试结果**：见 SL-007。
12. **修改前后对比**：Optimizer 载荷从"无 PRD + 双份意见"改为"有 PRD + 单份意见"；修订计划从只能 ADD/改写改为五种变更类型。真实模型输出的篇幅和数字标注效果未测。
13. **是否引入新问题**：Optimizer 输入会变大（加入 PRD 全文），但去掉了重复意见；超长 PRD 有截断到 60,000 字的保护。
14. **最终验收结果**：Mock 与单元测试通过；生成质量需要一次真实模型冒烟验证（未执行，见 README 剩余工作）。

### SL-004 评审有效性：原始需求上下文、证据、数量上限、去重、可追踪（PA-003）

- 日期：2026-11-08
- 对应问题：PA-003
- 关联记录：SL-001
- 记录状态：IMPLEMENTED（待真实模型验证）

1. **问题背景**：v1 有 24 条意见，跨角色重复，4 条 must_fix 中 3 条是要求补数字。
2. **已确认的根因**：无证据字段、无数量上限、strict schema 强制列表、Prompt 未允许空结果、聚合只拼接、reviewer 看不到用户需求。
3. **方案目标**：只输出有依据、可执行的问题；允许 0 条；跨角色合并；每条有稳定 ID 并能追踪处理结果。
4. **候选方案**：只改 Prompt（不可验证）；Prompt + 模型侧契约 + 后端确定性处理（选中）；增加一个 LLM 语义聚合节点（增加调用和费用，放弃）。
5. **最终选择及理由**：模型侧使用 `ReviewerOutput`（findings 含 title、severity、category、section、evidence、problem、user_impact、recommendation、confidence；resolutions），后端 `normalize_review` 做确定性处理，存为原有 `RoleReview`（`FeedbackItem` 增加可选字段），兼容历史数据。
6. **放弃其他方案的原因**：新增 LLM 聚合节点违反"不引入不必要的新 Agent"。
7. **计划修改的文件**：prompts.py、schemas.py、scoring.py、workflow.py、providers/*。
8. **实际修改的文件**：同上。
9. **代码修改摘要**：
   - Reviewer 输入加入 `user_requirements`（原始需求、受众、约束）、`automated_checks`、上一轮该角色的 findings。
   - Prompt：四项准入（问题、证据、影响、建议）；最多 5 条；0 条是正确答案；总结不超过 2 句；优点最多 3 条；角色边界；must_fix 条件收紧，"缺少用户未提供的数字"最多 should_fix，禁止要求编造数字。
   - 后端：无证据的 finding 丢弃并计数；按严重度排序截断到 5 条；生成稳定 ID `v{版本}-{角色}-{序号}`；`quantification` 类或置信度 < 0.5 的 must_fix 降为 should_fix 并记录原级别；`nice_to_have` 映射为 optional。
   - 聚合器 `deduplicate`：只合并不同角色的问题；同章节号 + 标题二元组重叠 ≥ 0.5，或同类别 + 文本重叠 ≥ 0.75；保留每个角色的 observations 和 merged_from。
   - `resolve_previous_findings`：上一轮每个 finding 在新版本中的状态（resolved / partially_resolved / unresolved / declined / not_checked），多个评审取最差结论，没人复查的标为未复查，不当作已解决。
10. **测试用例**：`test_v2_quality.py` 中评审处理 6 个、聚合 5 个、处理状态 1 个；`test_mock_provider.py` 中 Tech/UX 同一问题被合并；`test_v2_quality.py` 中工作流接线测试（reviewer 收到用户约束、第二轮收到上轮 findings）。
11. **测试结果**：见 SL-007。
12. **修改前后对比**：Mock 首轮意见 12 条合并为 11 条；评审页从三列长文改为单列列表 + 筛选 + 展开详情 + 定位章节。
13. **是否引入新问题**：确定性去重可能漏合并措辞差异大的同一问题（保守设计，宁可不合并）。
14. **最终验收结果**：Mock、单元测试和 e2e 通过；真实模型下的意见数量与质量待验证。

### SL-005 评分透明化：角色 Rubric、后端计分、门槛状态、版本（PA-006）

- 日期：2026-11-08
- 对应问题：PA-006
- 关联记录：SL-001
- 记录状态：VERIFIED

1. **问题背景**：角色分由模型自由给出，页面不说明计算方式。
2. **已确认的根因**：只有一个 0–100 分，没有维度、权重、依据和版本。
3. **方案目标**：模型判断维度，后端计算分数和门槛，页面完整展示规则。
4. **候选方案**：只在前端写说明（不解决模型自由打分）；维度评分 + 后端计算（选中）。
5. **最终选择及理由**：`backend/rubric.py` 集中定义三角色各 4 个维度和权重（与需求文档一致）、1–5 锚点、`RUBRIC_VERSION=2026-11-v2`、`SCORING_VERSION=weighted-mean-v1`；模型输出 `dimension_scores`（每个维度 1–5 + 依据），schema 拒绝缺维度、重复维度、越界分数和模型自带的 `score` 字段；后端 `role_score = Σ(分/5×权重)×100`，`overall = 三角色平均`（半入，1 位小数）。
6. **放弃其他方案的原因**：前端说明无法改变"模型决定分数"的事实。
7. **计划修改的文件**：新增 rubric.py、scoring.py、contracts/v1/rubric.json、src/lib/rubric.ts；schemas.py、prompts.py、workflow.py、ReviewPanel.tsx。
8. **实际修改的文件**：同上。
9. **代码修改摘要**：门槛状态 PASSED / NEEDS_REVISION / BLOCKED（存在 constraint_violation 类 must_fix）/ UNSCORED（无评估）；评估记录 rubric_version、scoring_version、gate_status、findings_before_dedup；历史评审无维度时标记为"历史评分"，不伪造维度；`contracts/v1/rubric.json` 由后端生成，契约测试保证与后端一致；前端评审页展示综合分公式、各角色分、维度分、权重、依据、门槛结果和"评分规则"折叠区。
10. **测试用例**：`test_v2_quality.py` 中评分 8 个、门槛状态 1 个、可复算 1 个；`test_contracts.py` rubric 一致性；前端 `panels.test.tsx` 维度与规则展示。
11. **测试结果**：见 SL-007。
12. **修改前后对比**：评审页从"76/100"变为"90.7 = (92 + 88 + 92) / 3 · 目标 85 · 门槛：通过"，并显示维度条和依据。截图：`test-results/layout/desktop-review-v2-findings.png`。
13. **是否引入新问题**：新旧评分不可直接比较，已通过 rubric_version 和"历史评分"标签区分。
14. **最终验收结果**：通过，2026-11-08。

### SL-006 前端：需求概览、运行时间线、PRD 目录、评审列表、视觉规范（PA-001、PA-005、PA-007）

- 日期：2026-11-08
- 对应问题：PA-001、PA-005、PA-007
- 关联记录：SL-001
- 记录状态：IMPLEMENTED

1. **问题背景**：原始输入全文铺在页首；运行记录是原始事件流且历史运行为空；正文右侧大块留白，评审三列拥挤，边框层层嵌套。
2. **已确认的根因**：见台账。
3. **方案目标**：首屏只放结论、版本和文档；技术信息折叠；历史运行可完整回看。
4. **候选方案**：引入 UI 组件库（新依赖，放弃）；在现有 Tailwind + CSS 变量上调整（选中）。
5. **最终选择及理由**：不新增依赖，不调用模型生成摘要。
6. **放弃其他方案的原因**：组件库会改变整体风格和构建体积。
7. **计划修改的文件**：新增 RunRequest.tsx、RunTimeline.tsx、prdOutline.ts、runTimeline.ts；修改 AgentDashboard.tsx、PRDViewer.tsx、ReviewPanel.tsx、RevisionPlanPanel.tsx、VersionRail.tsx、global.css、tailwind.config.mjs、useAgentRun.ts、runReducer.ts。
8. **实际修改的文件**：同上。
9. **代码修改摘要**：
   - PA-001：标题和两句摘要由确定性规则从原文提取（跳过"你是……"角色设定）；受众、精简模式、恢复来源和原文标题作为标签；原文折叠在"查看原始需求"里，用 react-markdown + skipHtml 渲染，并显示受众和约束。
   - PA-005：默认视图为"执行摘要 + 按版本的阶段时间线（生成 / 评审 / 聚合评分 / 修订计划）+ 最终质量检查"，全部从快照构建；Provider、Token、节点耗时、Trace ID、原始事件、错误码放在"开发者调试信息"折叠区；打开运行时调用 history 接口合并持久化事件，按序号去重；运行记录标签不再显示事件总数。
   - PA-007：PRD 页左侧目录（xl 以上）、正文居中、可选右侧待处理问题栏（2xl 以上）；正文宽度从 78ch 改为 46rem；评审页改为评分摘要 + 三张评分卡 + 单列问题列表（筛选、展开、定位章节）；修订计划改为单列，显示变更类型、原因、同步修改章节、必须保留项、对应问题的处理状态；面板内用 `surface-sunken` 底色替代嵌套边框；提高 ink-muted / ink-faint 对比度；9–11px 字号统一到 12px（text-xs）；重复的"建议："前缀去除。
10. **测试用例**：`v2.test.tsx`（目录锚点、未完成草稿、结构提示、需求摘要、原文 Markdown 渲染、时间线重建、开发者区折叠、修订计划字段、恢复按钮）；e2e 中 happy-path、recovery、layout 更新。
11. **测试结果**：见 SL-007。
12. **修改前后对比**：浏览器截图 `test-results/layout/desktop-prd.png`、`desktop-review.png`、`desktop-failed-truncation.png`、`desktop-failed-timeline.png`。
13. **是否引入新问题**：无已知新问题。目录和右侧栏只在 xl / 2xl 宽度出现，较窄桌面不显示。
14. **最终验收结果**：PA-001、PA-005 截图与测试符合预期；PA-007 视觉方向需要用户确认（FIXED_PENDING_VERIFICATION）。

### SL-007 全链路回归（Phase 6）

- 日期：2026-11-08
- 对应问题：PA-001 至 PA-009
- 关联记录：SL-002 至 SL-006
- 记录状态：IMPLEMENTED

1. **测试结果（修改后）**：
   | 检查 | 修改前 | 修改后 |
   |---|---|---|
   | pytest | 290 passed | 360 passed，0 failed，0 skipped |
   | vitest | 194 passed / 17 文件 | 209 passed / 18 文件 |
   | Playwright e2e（Mock，内存库） | 18 passed | 20 passed |
   | ruff format / ruff check / mypy | 通过 | 通过（25 个源文件） |
   | eslint | 通过 | 通过 |
   | astro check / build | 0 错误 | 0 错误，build Complete |
   | prettier --check（本次改动和新增的前端文件） | — | 通过 |
2. **全链路**：e2e happy-path 跑通 生成 → 三方评审 → 去重聚合 → 后端评分 → 门槛 → Optimizer（含 PRD 正文）→ v2 → 再评审（含上轮问题处理状态）→ 版本对比 → 最佳版本；失败场景覆盖 Provider 超时（NODE_TIMEOUT）、输出截断 + 从最佳版本恢复、单个 Reviewer 失败、结构化输出错误、Optimizer 失败、刷新后历史运行恢复。
3. **真实模型调用**：未执行。仓库没有经批准的安全测试配置，且读取 `.env` 和付费调用都在限制范围内。
4. **最终验收结果**：见各 SL。

### SL-008 V3.0 MVP P0 正式实现（Batch 1–7）

- 日期：2026-11-08
- 对应规划：`docs/v3-planning/` 全部文档；V4 视觉方案
- 记录状态：IMPLEMENTED（真实模型冒烟未执行，见第 6 条）

1. **实际修改**：
   - 新增后端包 `backend/v3/`：`models`（领域对象）、`store`（SQLite 新表 + 编号迁移 + 备份 + 回滚）、`jobs`（Job / JobEvent / SSE 回放）、`llm`（五类调用的结构化输出 + 网关）、`prompts`、`rubric`（Product Reviewer 新维度，其余三个沿用 V2）、`rules`（纯函数：证据校验、去重匹配、修改分类、导出清理、PRD 切分）、`explore`（项目、对话、基线、Analyst）、`document`（Brief、大纲、逐章生成、编辑、影响分析、版本、导出、入口 C 导入）、`review`（四个 Reviewer + 聚合 + Finding 生命周期）、`optimize`（修改提案与应用）、`quality`（四项独立指标）、`mock`（确定性网关）、`api`（`/api/v3` 路由）。
   - `backend/main.py`：挂载 `/api/v3`，CORS 增加 PUT/PATCH/DELETE；V2 组装不变。
   - `backend/providers/compatible.py`：抽出 `_stream_messages`，新增 `stream_call` / `structured_call` 供 V3 使用；V2 方法行为不变（37 个原测试通过）。
   - 前端：新增 `src/v3/`（App、Home、Explore、Requirements、Brief、Outline、Document、Review、store、api、useJob、ui、styles）；`/` 改为 V3 工作台，V2 仪表盘移到 `/runs`（只读历史入口，原功能保留）。
2. **设计决策**：两个空间（需求 / 文档）；Brief、大纲、PRD 在文档空间内切换；审查、来源、质量放在按需打开的右侧栏；四个 Reviewer 的结论默认折叠；移除"原型"标识、头像、Logo 图形和装饰性图标；顶栏只在模拟模式下显示"模拟模型"。
3. **技术决策**：
   - 新表放在同一 SQLite 文件（D-06），首次迁移前用 SQLite backup API 复制到 `data/backups/`；`rollback_v3()` 只删 V3 表。
   - 不使用 LangGraph；评审 fan-out 用 `asyncio.gather`（D-12）。
   - 每个项目同时只允许一个 AI 任务（409），避免并发写入同一项目。
   - Brief 由代码从基线组装（每行带条目编号），不是模型生成，确保可追溯。
   - 删除为软删除，没有自动永久清理（D-07 待用户决定保留期）。
3a. **后端强制的规则**：模型输出的 confirmed / rejected 降为 inferred；`source=user` 的原话必须在用户消息中逐字出现，否则改为 `ai`；模型不能改写已确认条目，只能新增关联建议；被拒绝条目不会被再次加入；Analyst 发现必须引用存在的条目编号，机会类必须带六项说明；Reviewer 发现无证据丢弃、超出本角色类别丢弃、引用在正文中找不到则标记且不能是"必须修改"；被拒绝的 Finding 匹配后保持拒绝且不计入本轮；只有 accepted / modified 进入 Optimizer；提案应用时按 row_version 校验，期间被改过的章节跳过；格式修改不标 Stale、不触发检查。
4. **测试结果**：
   | 检查 | 结果 |
   |---|---|
   | pytest | 388 passed（新增 `test_v3_workflow.py` 28 个） |
   | ruff format / ruff check / mypy | 通过（41 个源文件） |
   | vitest | 215 passed / 19 文件（新增 `src/v3/v3.test.tsx`） |
   | Playwright e2e | 28 passed（原 20 个 + 新增 `v3-workspace.spec.ts` 8 个） |
   | eslint / astro check | 0 错误 |
   | 浏览器走查 `scripts/v3/walkthrough.mjs` | 全流程无控制台错误；三页在 1440/1280/1024/390 无横向溢出；截图在 `docs/v3-screenshots/` |
5. **相关 Finding**：PA-007 被 V3 视觉取代；PA-002/003/008 并入 V3 真实模型冒烟。
6. **未解决问题**：真实模型冒烟未执行（需批准配置与费用）；Explorer/Analyst/Reviewer Prompt 只在 Mock 下验证；软删除没有清理任务；移动端未做键盘和读屏测试；V2 旧运行"转为项目"未实现。

### SL-009 V3 修复：想法入口无法审查、正文出现内部编号

- 日期：2026-11-09
- 记录状态：IMPLEMENTED（Mock 验证）

1. **根因一**：审查只支持 PRD 章节（`Reviews.start_review` 读取 `v3_sections`），前端审查入口只在 PRD 编辑器的侧栏里。"从想法 / 已有需求开始"的项目在 Brief 阶段没有章节，文档空间显示 Brief 页，页面上没有审查入口，直接调接口返回 `DOCUMENT_EMPTY`。"审查已有 PRD"在创建时就导入了章节，所以能审查。另外，章节没生成完时也能发起全文审查，审查结果关联的是最近保存的版本，而不一定是实际读到的正文。
2. **修复一**：Brief 页新增"检查 Brief"，复用 Product Analyst，对指定 Brief 版本的冻结条目做检查，发现记录 `brief_version`（迁移 2 新增列）；已有的同一问题复用原 Finding，不重复。全文审查要求所有章节完成（`DOCUMENT_INCOMPLETE`），只复查已完成章节不受限制；审查前正文与最新版本不同时先自动保存版本，结果的 `version_number` 指向实际审查的文本。
3. **根因二**：编号由后端拼接，不是模型生成：`document._item_line` 写入 `内容（POS-01）`，风险行写入 `（F-01）`；生成章节时 Brief 文本连同编号一起发给模型，模型照抄进正文。导出用固定前缀正则清理，会误删用户自己写的同格式编号。
4. **修复二**：Brief 正文不再拼接编号，关联只存在 `item_codes` / `finding_codes`；发给大纲步骤的编号只放在结构化字段里，正文步骤不再收到编号；Prompt 明确禁止写编号；生成、优化、导出时只移除"本项目系统分配、且用户输入里没有出现过"的编号（`strip_internal_refs` + `Base.internal_codes`）；旧 Brief 快照在读取时清理，存储的快照不改。
5. **测试**：pytest 399（新增 `test_v3_fixes.py` 11 个），vitest 215，e2e 29（新增 1 个），浏览器走查 Brief 与导出均无内部编号。
