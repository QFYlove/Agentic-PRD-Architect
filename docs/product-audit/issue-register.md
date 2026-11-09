# Issue Register

问题台账。每个问题一条记录，ID 永不复用。更新时修改对应字段和 Last Updated，不删除历史记录；方案过程写在 [solution-log.md](solution-log.md)。

## 状态定义

台账状态（Status）：

| 状态 | 含义 |
|---|---|
| OPEN | 待分析 |
| INVESTIGATING | 分析中 |
| CONFIRMED | 根因已确认 |
| SOLUTION_PROPOSED | 已有解决方案 |
| APPROVED | 方案已确认 |
| IN_PROGRESS | 正在开发 |
| FIXED_PENDING_VERIFICATION | 已修改，待验证 |
| VERIFIED | 验收通过 |
| DEFERRED | 暂缓处理 |
| CLOSED | 已关闭 |

根因确认程度（Root Cause 字段中标注）：CONFIRMED、PARTIALLY_CONFIRMED、SUSPECTED、NOT_REPRODUCED、NOT_FOUND。

优先级：P0 影响结果正确性或用户无法完成任务；P1 影响产出质量或可信度；P2 影响体验和信息层级。

## 总览

| ID | Title | Status | 根因确认 | Priority | Solution Log | Last Updated |
|---|---|---|---|---|---|---|
| PA-001 | 用户输入完整展示，页面冗杂 | VERIFIED | CONFIRMED | P2 | SL-006 | 2026-11-08 |
| PA-002 | PRD 过长、大段文字、结构不清 | FIXED_PENDING_VERIFICATION | CONFIRMED | P1 | SL-003 | 2026-11-08 |
| PA-003 | 三方评审冗长、泛泛、重复 | FIXED_PENDING_VERIFICATION | CONFIRMED | P1 | SL-004 | 2026-11-08 |
| PA-004 | 工作流失败反馈不合理 | VERIFIED | CONFIRMED | P0 | SL-002 | 2026-11-08 |
| PA-005 | 运行记录缺乏实际作用 | VERIFIED | CONFIRMED | P2 | SL-006 | 2026-11-08 |
| PA-006 | 评分标准和综合评分机制不透明 | VERIFIED | CONFIRMED | P1 | SL-005 | 2026-11-08 |
| PA-007 | 前端视觉效果和信息架构不佳 | FIXED_PENDING_VERIFICATION | PARTIALLY_CONFIRMED | P2 | SL-006 | 2026-11-08 |
| PA-008 | PRD 事实、假设及跨章节一致性风险 | FIXED_PENDING_VERIFICATION | CONFIRMED | P1 | SL-003、SL-004 | 2026-11-08 |
| PA-009 | 输出截断后用相同请求重试 | VERIFIED | CONFIRMED | P0 | SL-002 | 2026-11-08 |
| PA-010 | 11 个前端文件在基线即不符合 Prettier | OPEN | CONFIRMED | P2 | — | 2026-11-08 |

VERIFIED 的依据：根因对应的代码已修改，对应单元测试、e2e 和浏览器截图通过（Mock 模型）。FIXED_PENDING_VERIFICATION 的项目依赖真实模型的输出质量或用户对视觉方向的确认，Mock 无法证明。

---|---|---|---|---|---|
| PA-001 | 用户输入完整展示，页面冗杂 | CONFIRMED | CONFIRMED | P2 | 2026-11-08 |
| PA-002 | PRD 过长、大段文字、结构不清 | INVESTIGATING | PARTIALLY_CONFIRMED | P1 | 2026-11-08 |
| PA-003 | 三方评审冗长、泛泛、重复 | INVESTIGATING | PARTIALLY_CONFIRMED | P1 | 2026-11-08 |
| PA-004 | 工作流失败反馈不合理 | CONFIRMED | CONFIRMED（数据库已确认：v2 两次尝试均触达 16000 输出 token 上限） | P0 | 2026-11-08 |
| PA-005 | 运行记录缺乏实际作用 | CONFIRMED | CONFIRMED | P2 | 2026-11-08 |
| PA-006 | 评分标准和综合评分机制不透明 | CONFIRMED | CONFIRMED | P1 | 2026-11-08 |
| PA-007 | 前端视觉效果和信息架构不佳 | INVESTIGATING | PARTIALLY_CONFIRMED | P2 | 2026-11-08 |
| PA-008 | PRD 事实、假设及跨章节一致性风险 | CONFIRMED | CONFIRMED（数据库已追溯：评审要求补数字 → 计划转述 → 生成器自行填值） | P1 | 2026-11-08 |
| PA-009 | 输出截断后用相同请求重试，必然再次失败并重复计费 | CONFIRMED | CONFIRMED | P1 | 2026-11-08 |

---

## PA-001 用户输入完整展示，页面冗杂

| 字段 | 内容 |
|---|---|
| ID | PA-001 |
| Title | 用户输入完整展示，页面冗杂 |
| Observation | 结果页完整展示原始 Prompt；长输入占据大量空间；与 PRD 层级不清；Markdown 格式未渲染 |
| Status | VERIFIED（2026-11-08，见 SL-006） |
| Priority | P2 |
| Root Cause | **CONFIRMED。前端展示问题为主，数据结构缺少摘要为辅，不是 Markdown 渲染器故障。** ① `user_idea` 在运行头部用普通 `<p>` 原样输出，没有折叠、行数限制或展开（`AgentDashboard.tsx:374-376`）。输入上限 5000 字（`schemas.py:102`），会把标签页推到首屏以下。② 该 `<p>` 没有 `whitespace-pre-wrap`，换行被合并成一段；也没有经过 Markdown 渲染，所以标题和列表显示为 `#`、`-` 原文。PRD 使用的 `ReactMarkdown` 工作正常，只是没有用于用户输入。③ 数据结构只有原文：`RunSnapshot` / `RunSummary` 没有 title、summary 或标签字段（`schemas.py:333-335, 406-416`），也没有生成摘要的节点。④ `target_audience`、`user_constraints` 提交后在任何组件中都不显示（类型存在于 `types.ts:68-69`，没有组件读取）。⑤ 原始输入不在 PRD 正文中：两份样例都从 H1 标题开始。"混在一起"是页面布局问题：输入紧贴在标签页上方，且使用和正文接近的字号（`text-sm text-ink`）|
| Evidence | `src/components/AgentDashboard.tsx:374-376`；`src/components/ConversationSidebar.tsx:101-108`（侧栏单行截断，title 显示全文）；`backend/schemas.py:101-108, 327-335, 406-416`；样例 v1/v2 第 1 行均为 H1 |
| Related Files | `src/components/AgentDashboard.tsx`，`src/components/ConversationSidebar.tsx`，`backend/schemas.py`，`src/lib/types.ts` |
| Impact | 长输入时首屏被原始需求占满，PRD 和结果被推到下方；多行输入可读性差；受众和约束信息丢失，用户无法确认系统是按什么输入生成的 |
| Proposed Direction | 低成本优先：① 运行头部默认只显示 2-3 行（line-clamp）加"展开原始需求"，展开后保留换行（`whitespace-pre-wrap`），可选用现有 `ReactMarkdown` + `skipHtml` 渲染；② 折叠区内一并展示受众和约束；③ 运行标题先用前端规则生成（取首行或首个标题，截断），暂不新增模型调用；④ 若后续需要真正的摘要，再评估在 generator 输出或单独节点中生成 title/summary，这需要改 Schema 和契约 |
| Acceptance Criteria | 5000 字输入时首屏可见标签页和 PRD 开头；默认折叠，可展开查看全文；换行保留；受众和约束可见；侧栏和头部标题一致；Vitest 和 `e2e/layout.spec.ts` 增加长输入用例 |
| Related Tests | 现有：`e2e/layout.spec.ts`（只覆盖 PRD 宽度，不覆盖长输入）。缺失：长输入折叠、换行保留、受众和约束展示 |
| DB Evidence | 2026-11-08 只读查询运行 `9fa59292`：`user_idea` 为 4993 字（上限 5000），444 行，包含 29 个 Markdown 标题和 228 个列表行；`target_audience`、`user_constraints` 为空，受众和约束都写在 `user_idea` 正文中。按 `AgentDashboard.tsx:374-376` 的渲染方式，这 444 行会合并成一个不分行的段落，标题和列表符号原样显示。详见附录 A |
| Solution Log | SL-006 |
| Last Updated | 2026-11-08 |

## PA-002 PRD 过长、大段文字、结构不清

| 字段 | 内容 |
|---|---|
| ID | PA-002 |
| Title | PRD 过长、大段文字、结构不清 |
| Observation | PRD 很长；大量连续段落；缺少分点和层级；内容重复；功能描述过度展开 |
| Status | FIXED_PENDING_VERIFICATION（2026-11-08，见 SL-003） |
| Priority | P1 |
| Root Cause | **PARTIALLY_CONFIRMED。主要由 Generator Prompt 和迭代方式造成，其次是 PRD 没有结构化 Schema；渲染和后处理不是原因。** ① **Prompt 明确要求段落**：`COMPOSITION_RULES` 规定背景、方案、业务逻辑、技术设计等"Prose by default…connected paragraphs"，并禁止把推理拆成列表，列表"only for real enumerations"（`prompts.py:74-94`）。样例 v1、v2 的列表行数都是 0，超过 300 字的段落从 5 个增加到 17 个，最长 530 字。② **没有内容预算**：Generator Prompt 没有总篇幅、章节字数、章节清单或 MVP 与远期的详略要求（`prompts.py:110-138`）。唯一的上限是 `max_tokens=16000`（`config.py:34`），而且模型并不知道这个值，触顶就是失败（见 PA-004）。③ **迭代只增不减**：第二版起要求在最佳版本上"最小编辑"，保持其他内容逐字不变，并且"never delete content"（`prompts.py:116-127`）。修订计划只会补充内容，没有任何环节要求删减。样例从 44KB 增长到 67KB（+52%）。④ **PRD 没有 Schema**：整份 PRD 是一个 `content: str`（`schemas.py:316`），没有章节结构，所以无法按章节控制篇幅，也无法做跨章节校验。⑤ **没有跨章节一致性检查**：代码中没有这一步，只依赖 reviewer 把"需求互相矛盾"判为 must_fix（`prompts.py:39`）。⑥ 后处理只移除完成标记（`prd_document.py:55-63, 108`）；`react-markdown` + `remark-gfm` 能正确渲染标题、列表和表格，不存在格式丢失 |
| Evidence | `backend/prompts.py:70-138`；`backend/schemas.py:314-320`；`backend/config.py:34`；`backend/workflow.py:442-455`（baseline 取最佳版本）；`backend/providers/compatible.py:189-200`（baseline 以 JSON 字符串传入，整篇重新输出）；样例统计：v1 439 行 / 9 个表格 / 0 列表行，v2 497 行 / 11 个表格 / 0 列表行；重复规则如回收站计入配额出现在 v2:178、210、248、298 |
| Related Files | `backend/prompts.py`，`backend/schemas.py`，`backend/workflow.py`，`backend/providers/compatible.py`，`backend/config.py` |
| Impact | 阅读成本高；每轮输出越来越长，逼近输出上限并导致 v2 失败（PA-004）；评审输入变长，耗时和费用增加；重复描述成为跨章节矛盾的来源（PA-008） |
| Proposed Direction | 先改 Prompt，暂不改 Schema：① 在 Generator Prompt 中加入篇幅预算（例如总字数区间、单段上限约 150-200 字）和推荐章节骨架；② 规定 MVP 详写、后续阶段只写一张路线图表格；③ 放宽"Prose by default"，允许规则、约束、验收条件使用列表；④ 修订时允许"合并重复、删除冗余"，Optimizer 可以提出删减项；⑤ 加一个确定性的后端检查（长度、超长段落数），超出预算时记录告警，先不阻断。中期再评估章节级结构（例如按章节输出 JSON 后再拼成 Markdown），这一步改动大，需要单独决策 |
| Acceptance Criteria | 用固定 Mock 和真实模型冒烟样例对比：总长度、超长段落数下降到约定阈值；v2 相对 v1 的增长受控；MVP 外的功能不再按 MVP 深度展开；不出现新的截断失败 |
| Related Tests | 现有：`backend/tests/test_node_timings.py` 中 `test_the_generator_is_told_to_write_a_document_not_a_checklist` 断言 Prompt 包含 "Prose by default"，修改 Prompt 会使其失败，需要同步更新；`test_generation_reliability.py:483`（在最佳版本上编辑）。缺失：篇幅和段落长度的确定性检查 |
| DB Evidence | 2026-11-08 只读查询运行 `9fa59292`：v1 为 17162 字、10314 个输出 token；修订计划有 18 项，覆盖约 10 个章节，每一项都要求补充内容，没有任何删减项。v2 输入 18225 token（含 v1 全文作为 baseline），两次尝试都在输出 16000 token 时被截断，截断时已生成 25988 字（比 v1 多 51%），仍停在第 12.3 节，第 13、14 章和计划 P3、P4 要求写入第 13 章的内容都还没有输出。这证实了"整篇重写 + 只增不减"会直接把输出推过上限，篇幅问题与 PA-004 是同一根因。详见附录 A |
| Solution Log | SL-003 |
| Last Updated | 2026-11-08 |

## PA-003 三方评审冗长、泛泛、重复

| 字段 | 内容 |
|---|---|
| ID | PA-003 |
| Title | 三方评审冗长、泛泛、重复 |
| Observation | 三个 Reviewer 都输出较长的整体评价；部分意见没有依据；建议泛泛；不同角色重复指出同一问题；数量过多 |
| Status | FIXED_PENDING_VERIFICATION（2026-11-08，见 SL-004） |
| Priority | P1 |
| Root Cause | **PARTIALLY_CONFIRMED。Schema 和 Prompt 缺少证据与数量约束，聚合器只做拼接。** ① **Schema 没有证据字段**：`FeedbackItem` 只有 `severity`、`issue`、`recommendation`（`schemas.py:145-150`），没有章节、原文引用、影响或置信度。② **长度约束很宽**：`summary`、`issue`、`recommendation` 各允许 2000 字；`strengths` 和 `feedback` 列表没有数量上限（`schemas.py:149-150, 184-186`）。③ **Schema 引导模型填写内容**：strict JSON Schema 把 `strengths` 和 `feedback` 列为 required（已用 `to_strict_json_schema` 验证），Prompt 却没有说明可以为空。Prompt 写了"Most reviews of a solid document have zero must_fix"，但这只针对 must_fix，没有约束 should_fix 和 optional 的数量（`prompts.py:33-60`）。④ **没有准入标准**：Prompt 只要求"issue states the concrete gap"，没有要求指明章节、引用原文，或说明不改会造成什么后果；也没有"无依据则不提"的规则。⑤ **角色边界只有一句话**（`prompts.py:140-171`），没有说明哪些问题归其他角色，所以三个角色会重复指出同一问题。⑥ **聚合器只拼接**：`combined_feedback=[*tech, *ux, *biz]`（`workflow.py:643-647`），不去重、不合并、不排序。去重只在 Optimizer Prompt 中由模型完成（`prompts.py:174-176`），结果只体现在修订计划里，评审页仍显示全部原始意见。⑦ **Reviewer 缺少上下文**：载荷只有 `prd` 和 `iteration`（`compatible.py:312-316`），看不到用户需求、受众、约束，也看不到上一轮意见，无法判断"是否偏离需求"或"上轮问题是否已解决"，只能泛泛评论。"没话找话"是否确实存在，需要真实评审样本统计才能量化 |
| Evidence | `backend/schemas.py:145-194`；`backend/prompts.py:33-60, 140-171, 173-195`；`backend/workflow.py:638-648`；`backend/providers/compatible.py:251-270, 301-318`；前端完整展示每条意见，没有折叠（`src/components/ReviewPanel.tsx:96-188`） |
| Related Files | `backend/schemas.py`，`backend/prompts.py`，`backend/workflow.py`，`backend/providers/compatible.py`，`src/components/ReviewPanel.tsx` |
| Impact | 真正的阻塞问题被大量建议淹没；重复意见放大某一类问题；Optimizer 接收大量低价值意见，导致 PRD 膨胀（PA-002）；无法验证意见是否成立 |
| Proposed Direction | ① Prompt：明确允许空结果；每个角色最多 N 条（例如 5 条），按影响排序；每条必须给出章节和原文依据，没有依据就不提；写明角色边界。② Schema：`FeedbackItem` 增加 `section`、`evidence`（短引用）字段，收紧长度和列表数量上限；`summary` 限制在约 200 字。③ 聚合器：在后端做确定性的去重（同一章节 + 文本相似度），先只合并展示，不改变评分。④ 前端：默认只展开 must_fix，其他按严重度折叠。新增字段属于契约变更，需要同步 `contracts/v1`、前端类型和旧快照兼容 |
| Acceptance Criteria | 评审页每个角色的意见数不超过上限；每条意见都有章节和依据；同一问题被多个角色提出时合并显示并标注来源；空结果能正常展示和通过校验；旧快照仍能读取 |
| Related Tests | 现有：`test_provider_retries.py:65, 79`（结构修复）；`test_compatible_provider.py:327`（JSON 模式和 Schema 提示）。缺失：去重、数量上限、空评审、证据字段校验 |
| DB Evidence | 2026-11-08 只读查询运行 `9fa59292` 的 v1 评审：共 24 条意见（技术 9、体验 9、商业 6），其中 must_fix 4、should_fix 14、optional 6；另有 19 条"做得好"；summary 258-377 字；每条意见（问题 + 建议）108-380 字，平均 226 字。① **跨角色重复**：容量和配额数值（tech-1 / ux-3 / biz-1）、首发市场（tech-2 / biz-4）、磁力回退（tech-7 / biz-2）、提取码错误上限（tech-5 / ux-8）。评审页逐条显示全部 24 条；Optimizer 合并了其中一部分（计划 P1、P3、P4、P7 带有多个来源角色）。② **严重度升级违反 Rubric**：biz-1（要求单位经济模型）属于 Rubric 明确排除在 must_fix 之外的"more detailed business modelling"；tech-1 要求给出配额数值，接近"a metric that could be quantified further"。4 条 must_fix 中有 3 条是在要求补数字或补决策。③ **建议本身包含新规则和数字**：例如 ux-2 提出"<10s 骨架屏""可取消并保留已获取分片"，tech-2 提出"仅内地可用、海外仅访问分享"，这些内容后来被写进 v2（见 PA-008）。④ Optimizer 载荷中每条意见出现两次：各角色的 `feedback` 一次，`combined_feedback` 又一次；后者占载荷 16260 字中的 6916 字（43%）。详见附录 A |
| Solution Log | SL-004 |
| Last Updated | 2026-11-08 |

## PA-004 工作流失败反馈不合理

| 字段 | 内容 |
|---|---|
| ID | PA-004 |
| Title | 工作流失败反馈不合理 |
| Observation | v2 生成失败；页面显示失败但没有具体原因；不知道失败在哪个节点；不清楚能否安全重试；已完成和失败的部分区分不清 |
| Status | VERIFIED（2026-11-08，见 SL-002） |
| Priority | P0 |
| Root Cause | **CONFIRMED。本次失败的原因已由数据库确认：v2 生成两次尝试都触达 16000 输出 token 上限（`PROVIDER_OUTPUT_TRUNCATED`），不是超时或 JSON 解析失败（见 DB Evidence）。** 以下为源码审计确认的失败处理机制问题。后端：① 已知 Provider 错误有独立错误码（`errors.py`，`workflow.py:139-175`），但其他异常（聚合器 / 优化器的 `ValueError`、未映射的 HTTP 状态、解析异常等）在 `RunManager._run_workflow` 中统一变成 `WORKFLOW_FAILED`（`run_manager.py:333-342`），并且整个后端没有任何 `LOGGER.exception` / `exc_info`，原始异常连开发者日志里都没有。② 节点超时和整次运行超时都映射为 `RUN_TIMEOUT`（`workflow.py:162-168, 198-199, 218-220`），提示"请缩小需求范围"，对节点超时有误导。③ `run_failed` 载荷只有 `error_code`、`message`、`retryable`（`run_manager.py:603`），没有节点、阶段、版本和尝试次数。④ 失败节点靠单个 `active_node` 字段标记（`run_manager.py:589-590`）。三个 reviewer 并行时它只记录最后启动的那个，所以失败可能记在错误的 reviewer 上，其余 reviewer 停留在 RUNNING。⑤ `FAILED` 是终态（`state_machine.py:82`），没有 checkpointer，也没有重试接口，无法从失败节点恢复。⑥ 后端重启时会把运行标记为 `RUN_INTERRUPTED`（`run_store.py:213-217`），但前端文案表里没有这个码，显示的是兜底文案"操作失败，请稍后重试。"；`PROVIDER_SELECTION_UNAVAILABLE` 同样缺失（`errorMessages.ts:1-41`）。⑦ 时间和长度预算偏紧：整次运行 600 秒，生成每次尝试 240 秒，输出上限 16000 tokens（`config.py:34, 69-72`）。v2 必须整篇重新输出一份已有约 44KB 的文档再加上修改（PA-002），很容易触发 `PROVIDER_OUTPUT_TRUNCATED` 或 `RUN_TIMEOUT`。前端：⑧ 具体原因只出现在可关闭的顶部横幅中（`AgentDashboard.tsx:264-293`）；失败提示只写"v2 生成失败"和保留了哪些版本，不写原因和节点（`failureNotice.ts:122-125`）；运行记录中的失败条目是固定文案（`trace.ts:142-148`）。⑨ **失败后的半成品草稿仍显示为"正在生成"**：失败版本的流式草稿保留为 `complete:false`，页面自动选中它（`runReducer.ts:650-652, 832-847`）；`PRDViewer` 只看草稿是否完成，不看运行状态，所以继续显示"正在生成"和光标，下载按钮也可用，下载的是半成品（`PRDViewer.tsx:93, 111-122, 127, 160-162`）。⑩ 实时视图收到 `run_failed` 后不会把节点标成 FAILED，工作流图上失败节点仍显示运行中，直到刷新。⑪ `retryable` 字段前端没有使用（只出现在 `types.ts:138`）；失败后只有"新建任务"（`RunControls.tsx:78-86`），需要重新填写并从 v1 全部重跑 |
| Evidence | 上述文件行号；样例 v2 在 497 行句子中间结束，且没有完成标记。由于 `validate_generated_prd` 要求有标记才能写入版本（`prd_document.py:106-107`），这份 v2 是失败后的半成品草稿（用户已确认，2026-11-08）。测试 `test_node_timings.py:216` 确认失败的 v2 不影响 v1、评审、计划和 best_version |
| Related Files | `backend/workflow.py`，`backend/run_manager.py`，`backend/errors.py`，`backend/run_store.py`，`backend/state_machine.py`，`backend/config.py`，`src/lib/errorMessages.ts`，`src/lib/failureNotice.ts`，`src/lib/trace.ts`，`src/lib/runReducer.ts`，`src/components/PRDViewer.tsx`，`src/components/AgentDashboard.tsx`，`src/components/RunControls.tsx` |
| Impact | 用户不知道失败原因和下一步怎么做；可能把半成品当作 v2 阅读或下载；重试需要从头执行，重复花费 v1 和评审的费用；开发者无法从日志定位未知异常 |
| Proposed Direction | 分两步。第一步（低风险）：在 `run_failed` 载荷和 `RunError` 中增加 `node`、`stage`、`version`、`attempt`；未知异常用 `log_event` 记录异常类型（不记录原文）；区分 `NODE_TIMEOUT` 和 `RUN_TIMEOUT`；补全前端文案（RUN_INTERRUPTED 等）；失败提示中直接写原因和是否可重试；运行失败时把未完成草稿标记为"未完成 / 已中断"，禁用或明确标注下载；`run_failed` 时把节点标成 FAILED；并行阶段按节点记录失败。第二步（需要决策）：增加"从最佳版本继续"接口，复用已有版本和修订计划，从 generator 重新开始，不重跑已完成的节点；同时调整超时和输出预算，或配合 PA-002 降低 v2 输出量 |
| Acceptance Criteria | 每种失败（截断、未完成、超时、结构化失败、未知异常、重启中断）在 UI 上显示原因、节点、版本和是否可重试；失败的半成品不再显示"正在生成"；有可用的重试入口且不重复执行已完成节点；best_version 不变 |
| Related Tests | 现有：`test_generation_reliability.py:220, 276`；`test_workflow.py:445, 469`；`test_provider_retries.py:203`；`test_run_store.py:81`；`test_node_timings.py:216`；`src/lib/runFailures.test.ts`；`e2e/failures.spec.ts`。缺失：未知异常记录、并行 reviewer 失败归属、失败后草稿状态、RUN_INTERRUPTED 文案、失败后重试 |
| Pending Verification | 已完成（2026-11-08）。原待验证项"只读查询运行 `9fa59292` 的快照以确认失败原因"已在用户批准后执行，结果见 DB Evidence。按用户说明，v2 是半成品这一点不再通过数据库验证 |
| DB Evidence | 2026-11-08 只读查询（`mode=ro`，`query_only=ON`）运行 `9fa59292`：① `status=FAILED`，`error={code: PROVIDER_OUTPUT_TRUNCATED, message: "The provider hit its output limit before finishing.", retryable: true}`。② 节点状态：`generator=FAILED`，三个 reviewer、aggregator、optimizer 均为 SUCCEEDED，`current_iteration=2`，所以失败节点是 v2 的 generator。这次失败发生在串行阶段，没有触发上文 ④ 的并行误判。③ 节点耗时：v2 generator 第 1 次 76.31 秒，失败，输入 18225 / 输出 16000 token；第 2 次 78.15 秒，失败，输入 18225 / 输出 16000 token。两次输出都恰好等于 `llm_max_output_tokens=16000`。④ 自动重试发生了 1 次：`prd_stream_reset`（seq 1385，attempt 2），结果相同。⑤ 整次运行用时 261.9 秒，低于 600 秒的运行上限，每次尝试也低于 240 秒的单次上限，排除超时。⑥ 结构化输出：三个 reviewer 和 optimizer 都是一次成功，没有修复调用，排除 JSON 解析失败。⑦ `run_failed` 事件（seq 2069）的载荷只有 `error_code`、`message`、`retryable`，不含节点和版本，与上文 ③ 一致。⑧ 已保留：v1（76.0 分，`best_version=1`）、v1 评审、v1 修订计划（`pending_revision_plan`，18 项）。⑨ 两次失败尝试共消耗输入 36450 + 输出 32000 token，占整次运行 137120 token 的 50%，没有产出任何版本（见 PA-009）。⑩ 快照中的 `current_prd` 是第 2 次尝试的半成品，25988 字，以"第三方解析"结尾、没有完成标记；页面正是用这份内容生成"正在生成"草稿和下载文件（机制见 ⑨） |
| Solution Log | SL-002 |
| Last Updated | 2026-11-08 |

## PA-005 运行记录缺乏实际作用

| 字段 | 内容 |
|---|---|
| ID | PA-005 |
| Title | 运行记录缺乏实际作用 |
| Observation | 显示大量节点事件、事件编号和技术指标；对普通用户价值低；更像调试界面 |
| Status | VERIFIED（2026-11-08，见 SL-006） |
| Priority | P2 |
| Root Cause | **CONFIRMED。运行记录直接展示原始事件流，没有按"用户想知道什么"组织，也没有用户视图和调试视图之分。** ① 事件来自 `RunManager.commit` 追加的每一个状态变化（`run_manager.py:390-398`），前端把每条事件都放进 `state.events`（`runReducer.ts:595`）。`AgentTrace` 用 `toTraceItem` 一对一渲染，每条都带 `#sequence` 编号（`AgentTrace.tsx:76-78`，`trace.ts:29-152`），大部分是"已开始处理"这类过程信息。② 标签页角标 = `state.events.length`（`AgentDashboard.tsx:196-197`），其中包括数百条不显示的 `prd_delta` 和 `telemetry_updated`，所以与面板中的"N 条事件"不一致。③ **历史运行的运行记录是空的**：打开已结束的运行时只加载快照，不连接 SSE、不回放事件（`useAgentRun.ts:268-274`，`runReducer.ts:811-881` 不加载事件），面板显示"结构化工作流事件将在这里实时显示"。中途重连也只能看到重连之后的事件。④ 业务结果没有进入记录：评审条目只有条数（`trace.ts:55-79`），失败条目是固定文案，不含原因（`trace.ts:142-148`）。⑤ 指标面板展示输入 / 输出 / 总 token、费用、Provider/Model、每个节点耗时和 token（`TelemetryPanel.tsx:17-134`），节点名使用英文（`nodeTimings.ts:4-11`），与轨迹中的中文名不一致。⑥ 对照六个问题：执行了什么——部分回答（只有实时会话中有）；哪些已完成——工作流图回答；哪些失败、为什么——不回答（PA-004）；消耗多少资源——回答，但偏技术；下一步怎么做——不回答 |
| Evidence | 上述文件行号；`e2e/recovery.spec.ts:67-74` 只验证事件编号不重复 |
| Related Files | `src/components/AgentTrace.tsx`，`src/lib/trace.ts`，`src/components/TelemetryPanel.tsx`，`src/lib/nodeTimings.ts`，`src/components/WorkflowDiagram.tsx`，`src/components/AgentDashboard.tsx`，`src/hooks/useAgentRun.ts`，`src/lib/runReducer.ts`，`backend/run_manager.py`，`backend/event_store.py` |
| Impact | 运行记录占一个标签页却回答不了用户的问题；历史运行无法回看过程；角标数字误导 |
| Proposed Direction | ① 用快照（`versions`、`node_statuses`、`node_timings`、`error`、`total_tokens`）生成"运行摘要"作为默认视图：按版本列出 生成 → 评审 → 汇总 → 优化 的结果、分数、失败原因和下一步。快照已经持久化，历史运行也能显示，不依赖事件回放。② 原始事件流和 token 明细放到"开发者详情"折叠区。③ 角标改为只统计可见条目或去掉。④ 统一节点中文名。若需要回看历史事件，可在打开终态运行时调用一次 `after_sequence=0` 的回放，`prd_delta` 不落库，事件数量可控 |
| Acceptance Criteria | 打开历史运行能看到完整运行摘要；默认视图不显示事件编号和 token 明细；失败时显示原因和下一步；角标数字与内容一致；节点名称统一 |
| Related Tests | 现有：`e2e/recovery.spec.ts:67-74`；`src/components/panels.test.tsx`。缺失：终态运行的运行记录、角标计数、摘要视图 |
| DB Evidence | 2026-11-08 只读查询运行 `9fa59292`：事件序号从 1 到 2069，但只落库 28 条，其余约 2041 个序号是瞬时的 `prd_delta`。28 条中有 5 条 `status_changed` 和 7 条 `telemetry_updated` 不在轨迹中显示，可见条目只有 16 条。在实时会话里，标签角标会显示约 2000，面板只列出 16 条。快照中 `estimated_cost_usd=null`、`cost_available=false`（未配置模型单价），因此指标面板的费用显示"暂不可用"，用户看不到这次运行的花费，包括两次失败尝试浪费的 token |
| Solution Log | SL-006 |
| Last Updated | 2026-11-08 |

## PA-006 评分标准和综合评分机制不透明

| 字段 | 内容 |
|---|---|
| ID | PA-006 |
| Title | 评分标准和综合评分机制不透明 |
| Observation | 三个角色各有分数，页面显示综合分；用户不知道评分标准、计算方式，以及分数与意见、门槛之间的关系 |
| Status | VERIFIED（2026-11-08，见 SL-005） |
| Priority | P1 |
| Root Cause | **CONFIRMED。** 实际机制：① **角色分数由模型直接给出**，是 0-100 的整数（`schemas.py:183`），没有维度分，也不要求评分依据。三个角色共用同一套 6 档锚点（`prompts.py:13-24`），没有各自的维度和权重。② **综合分由后端计算**：三个分数等权算术平均，保留 1 位小数（`workflow.py:642`）；`EvaluationResult` 校验综合分必须等于这个平均值（`schemas.py:217-224`），所以模型无法自报总分。权重写死在代码里，不可配置。③ **门槛由后端判定，包含两个独立条件**：`overall >= quality_threshold` 且 `must_fix == 0`（`workflow.py:659-662`）。阈值由用户在表单中设置，默认 85，范围 50-100（`schemas.py:105`）。但 must_fix 的认定本身是模型给出的严重度（`prompts.py:33-60`）。④ **最佳版本**：综合分严格高于历史最佳时才替换（`workflow.py:650-653`）。⑤ **没有一致性校验**：模型可以给 95 分同时列出 must_fix，也可以给 60 分却没有任何意见，后端不做检查。⑥ **没有 Rubric 版本**：锚点在代码常量中，快照不记录用的是哪一版。⑦ **前端不解释**：没有任何地方说明"综合分 = 三项平均"、锚点含义或扣分依据（全仓 `src/` 搜索"平均 / 权重 / 评分标准"无结果）。`OutcomePanel` 会显示"已达到评分目标，但质量门禁未通过"并列出目标分和 must_fix 数（`outcomeSummary.ts:35-98`），门槛的两个条件是展示了的，但计算方式没有说明 |
| Evidence | `backend/schemas.py:181-244`；`backend/prompts.py:13-60`；`backend/workflow.py:638-662, 702-719`；`src/lib/outcomeSummary.ts`；`src/components/ReviewPanel.tsx:225-244`（只显示分数和与上一版的差值）；`src/components/RadarScoreChart.tsx` |
| Related Files | `backend/prompts.py`，`backend/schemas.py`，`backend/workflow.py`，`src/components/ReviewPanel.tsx`，`src/components/OutcomePanel.tsx`，`src/lib/outcomeSummary.ts`，`src/components/RadarScoreChart.tsx` |
| Impact | 用户无法判断分数是否可信；分数波动（同一文档不同轮次）无法解释；门槛未通过时不知道该改什么 |
| Proposed Direction | ① 先做说明（只改前端）：在评审页显示"综合分 = (技术 + 体验 + 商业) / 3"、六档锚点、两个门槛条件及当前状态。② 后端增加确定性的一致性检查，例如有 must_fix 时分数不应高于某一档，或者无意见时不应低于某一档，先只记录警告。③ 中期（需要改 Schema 和 Prompt）：每个角色定义 3-5 个维度和锚点，模型输出维度分和依据，后端按配置的权重计算角色分，并在快照中记录 `rubric_version`。改变评分方式会让新旧运行的分数不可直接比较，需要标注版本 |
| Acceptance Criteria | 用户在页面上能看到评分标准、综合分公式和门槛条件；分数与意见明显矛盾时有标记；如实施维度评分，快照包含 rubric 版本，角色分可由维度分复算 |
| Related Tests | 现有：`test_workflow.py:134`（门槛等号边界）、`:552`（达到阈值且无阻塞问题时通过）；`test_generation_reliability.py:340, 362, 390`；`test_schemas.py`（综合分校验）。缺失：分数与意见一致性、前端公式展示 |
| Solution Log | SL-005 |
| Last Updated | 2026-11-08 |

## PA-007 前端视觉效果和信息架构不佳

| 字段 | 内容 |
|---|---|
| ID | PA-007 |
| Title | 前端视觉效果和信息架构不佳 |
| Observation | 观感差；信息密度不合理；部分区域留白多；评审卡片文字密集；正文宽度与布局不协调；视觉层级不清；技术信息与用户信息混杂 |
| Status | FIXED_PENDING_VERIFICATION（2026-11-08，见 SL-006） |
| Priority | P2 |
| Root Cause | **PARTIALLY_CONFIRMED（代码层面已定位，像素数值是根据 CSS 推算，未在浏览器中实测）。** ① **正文右侧大块留白**：PRD 正文限宽 `78ch`（`tailwind.config.mjs:33`，约 690-710px），左对齐，没有 `mx-auto`（`PRDViewer.tsx:146`）；外层 `.panel` 却占满工作区（最大 1600px 容器，左侧固定 15rem 侧栏，`AgentDashboard.tsx:224, 242`）。1440px 宽时正文右侧约 370px 空白，1600px 以上约 530px。`e2e/layout.spec.ts:268, 293, 299` 只要求正文 ≤ 960、工作区 > 900，允许这种情况。② **评审卡片拥挤**：从 `lg` 起三列（`ReviewPanel.tsx:337`），1024px 时每张卡约 210px 宽，正文 12px / 20px 行高（`ReviewPanel.tsx:111, 173, 177, 258`）。意见全部展开，不折叠。每条意见有一个带边框的严重度标签。③ **边框层级过多**：评审页为 panel > 3 张 inset 卡片 > 每条意见的边框标签；对比页三层（panel > 边框框体 > 分隔线）；运行记录页 4 个 panel，工作流图内还有 7 个边框节点。`global.css:92-94` 的注释说面板内部改用"plain bordered block"以避免卡片嵌套，但视觉上仍是边框盒子套在边框面板里。④ **字号层级**：大量 9-11px 的任意值字号（如 `ConversationSidebar.tsx:129`、`RevisionPlanPanel.tsx:134`、`AgentDashboard.tsx:377`）；Tailwind 没有扩展字号体系；字体栈写了 Inter，但没有加载字体文件，实际回退到系统字体（`global.css:30-37`）。⑤ **技术信息默认外露**：运行头部显示 run UUID（`AgentDashboard.tsx:377-379`）和连接状态（349-360）；标签角标是事件总数；修订计划条目显示等宽字体的 `target_section`；侧栏行显示迭代、版本和一位小数的分数。⑥ **操作位置**：`RunControls` 放在标签内容之后（`AgentDashboard.tsx:432-441`），长 PRD 时暂停 / 取消在很远的下方；标签栏不吸顶。⑦ **移动端**：`lg` 以下侧栏历史列表没有高度限制，整列表排在工作区下方（`ConversationSidebar.tsx:38, 59`）。⑧ 同一屏用户原始输入过长（PA-001）。⑨ 评审建议可能出现"建议：建议：…"：前端固定加"建议："前缀（`ReviewPanel.tsx:178`），e2e fixture 中的文本本身也以"建议："开头（`layout.spec.ts:36`）；真实模型输出是否如此未确认 |
| Evidence | 上述文件行号；`src/styles/global.css:14-27`（深色 token）、`64-123`（组件类）、`125-241`（`.prd-markdown`） |
| Related Files | `src/components/AgentDashboard.tsx`，`PRDViewer.tsx`，`ReviewPanel.tsx`，`RevisionPlanPanel.tsx`，`VersionDiff.tsx`，`WorkflowDiagram.tsx`，`ConversationSidebar.tsx`，`RunControls.tsx`，`src/styles/global.css`，`tailwind.config.mjs`，`e2e/layout.spec.ts` |
| Impact | 页面不像成品；关键信息（结论、阻塞问题）不突出；宽屏留白和窄卡片同时存在 |
| Proposed Direction | 本轮不设计。建议的顺序：先确定信息架构（默认视图只放结论、版本、PRD，技术信息收进运行记录或详情）；再做低成本样式调整（正文居中或右侧加目录 / 评审摘要栏，评审卡片在 `xl` 才分三列或改为单列，减少一层边框，统一字号档位）；最后再考虑设计系统级别的改动。每一步都附截图对比 |
| Acceptance Criteria | 需要和用户一起确认目标布局后再定义；至少包括 1024 / 1440 / 1920 宽度下的截图对比、正文与留白比例、评审卡片最小宽度、默认视图不显示 run UUID |
| Related Tests | 现有：`e2e/layout.spec.ts`（宽度、表格滚动）；`src/components/components.test.tsx`。缺失：视觉回归截图基线 |
| Pending Verification | 需要启动前端并截图（本轮未启动服务）；`test-results/layout/*.png` 是否存在及其内容未检查 |
| Solution Log | SL-006 |
| Last Updated | 2026-11-08 |

## PA-008 PRD 事实、假设及跨章节一致性风险

| 字段 | 内容 |
|---|---|
| ID | PA-008 |
| Title | PRD 事实、假设及跨章节一致性风险 |
| Observation | 云盘 PRD 样例中有无依据的具体数值、推测写成事实、假设标记不全、同一规则在不同章节不一致、MVP 范围冲突、指标无来源、成本计算错误、评审意见优化后未解决 |
| Status | FIXED_PENDING_VERIFICATION（2026-11-08，见 SL-003、SL-004） |
| Priority | P1 |
| Root Cause | **CONFIRMED。没有单一来源，是多个环节共同造成的。数据库追溯确认了因果链：v1 本来把未知数值标为"待成本测算"（这正是用户输入要求的"对无法确认的信息建立明确的假设和待验证清单"）；Reviewer 把这些标记当作缺陷，并要求"数值可标注为假设…但必须存在"（biz-1）；Optimizer 把要求原样写进修订计划（P1、P2、P15、P16）；Generator 没有任何数据来源，只能自己填值。** ① **Generator Prompt 没有事实规则**：只有"without inventing requirements"（`prompts.py:114`），没有要求数值注明来源或标为假设，也没有要求维护假设和待确认清单。v1 的假设标记相对一致（例如 v1:189、197、213 标"假设 / 待定"），这是模型自身的表现，不是 Prompt 约束的结果。② **评分锚点鼓励量化**：90-100 档要求"quantified"，70-79 档写"key claims left unquantified"（`prompts.py:16-19`）；商业 Reviewer 要评估"market assumptions, monetization"（`prompts.py:163-164`）。没有真实数据时，模型满足"量化"的办法就是编造数字。v2 新增的大部分无来源数字（v2:33、445、449、467-471 等）出现在评审和修订之后，符合这个机制，已由数据库逐项确认（见 DB Evidence）。③ **最小编辑规则直接造成跨章节矛盾**：Optimizer 每一项只能指定一个 `target_section`（`prompts.py:179-180`）；Generator 被要求其他章节逐字不变（`prompts.py:120-123`）；Optimizer 的载荷里没有 PRD 正文（`compatible.py:331-335`），不知道同一规则还出现在哪里。结果是改了一处、其他地方保留旧规则。例如第三方分享：v2:150、483 已改为不进 MVP，同一节 v2:204 仍写"MVP 仅支持 1—2 个平台"，v2:206 却写"不进入 MVP 范围"；v2:9 仍写"以单轮方式完成"。④ **没有跨章节或计算校验**：代码中没有任何一致性检查或数值复核环节；成本计算由模型自己完成，v2:440、445、449 有算术错误（冷存储按 100% 计价且重复累加、付费档成本约为售价 25 倍、滥用损失套用付费档配额）。⑤ **评审无法确认问题是否解决**：Reviewer 只收到 PRD 正文（`compatible.py:312-316`），看不到上一轮意见和修订计划；系统不追踪每个计划项是否已落实。⑥ **v2 缺失第 13、14 章（假设、开放问题、竞品）**：已确认是输出截断造成的（PA-004 DB Evidence），不是 Optimizer 有意删除。计划 P3、P4 要求写入第 13 章的内容也因此没有输出 |
| Evidence | `backend/prompts.py:13-24, 110-138, 162-171, 173-195`；`backend/providers/compatible.py:189-200, 312-316, 331-335`；`backend/schemas.py:247-269`（`RevisionItem.target_section` 为单个字符串）；样例分析：无来源数值约 12 处（v2:33、230、302、445、449、466-471）；跨章节冲突约 9 组（v2:200/176、258/424、254/420、260/375、186/370、238/302、485/8/80、445/449、204/206）；v2 重复的 5.5 节编号（v2:202、250）|
| Related Files | `backend/prompts.py`，`backend/schemas.py`，`backend/workflow.py`，`backend/providers/compatible.py` |
| Impact | PRD 中的数字和规则不能直接相信；修订轮次越多，矛盾可能越多；用户需要逐行核对，PRD 的价值下降 |
| Proposed Direction | 按成本从低到高：① Generator Prompt 增加事实规则：没有用户提供的数据时不写具体市场、转化、价格数字，如需估算必须标注"假设"，并维护一个"假设与待确认"章节；修订时同一规则要在所有出现的章节一起改。② 锚点中的"quantified"改为"可验证的验收标准"，并说明编造的数字应扣分。③ Optimizer 载荷加入 PRD 章节标题列表（或全文），`target_section` 允许多个章节。④ Reviewer 载荷加入上一轮修订计划，增加"计划项是否落实"的检查。⑤ 中期：加一个专门的一致性检查节点或确定性检查（重复编号、MVP 范围关键词、数值复算），需要单独评估成本 |
| Acceptance Criteria | 在固定样例上：无来源数值都带假设标记；修改一条规则后，所有出现处一致；修订后的评审能指出哪些计划项已落实；没有重复章节编号 |
| Related Tests | 现有：无事实或一致性相关测试。缺失：Prompt 包含事实规则的断言；确定性检查（重复标题编号等）的单元测试 |
| Pending Verification | 已完成（2026-11-08）。原待验证项"把 v2 新增数字对应到评审意见和计划项"已在用户批准后执行，结果见 DB Evidence 和附录 A。按用户说明，v2 是否为半成品不再验证 |
| DB Evidence | 2026-11-08 只读查询运行 `9fa59292`，对象为 `user_idea`、v1 正文、v1 三方评审、v1 修订计划和 v2 半成品（`current_prd`）。① **数字来源**：v2 中有 65 个带单位的数字在 v1 中不存在（如 70%、30—50 元、0.10—0.15 元/GB、1.8 元、6 秒、8 Mbps、3%—8%、D7 ≥20%）。这 65 个数字中，只有 v2:200 的"10 秒"能对应到 ux-2 / 计划 P10 的"<10s 骨架屏"；其余 64 个在用户输入、评审和修订计划中都没有出现。评审和计划中出现的数字总共只有 10s、3s、5 秒、24 小时 4 个。用户输入只给了指标名称（D1/D7/D30 留存、会员转化率、单用户存储和带宽成本），没有给任何数值。结论：除这一个之外，新增数值都是模型自行补充的；评审和计划只要求"要有数值"，并没有提供数值。② **标为"内部试点观测值"的来源是编造的**（v2:33、473）：用户输入、v1、评审、计划中都没有"内部试点"。③ **规则来源**：v2:485"仅中国内地可用、海外仅可访问分享"来自 tech-2 建议中的举例，经计划 P3 原样传递，和用户输入"面向中国及海外市场"相矛盾。v2:200"已获取的分片会保留"来自 ux-2 /计划 P10 的"可取消并保留已获取分片"，和 v1 原有的 v2:176"取消后清理已下载分片"相冲突，后者因为最小编辑规则保持不变。v2:232 的续播冲突规则直接来自 ux-1 / P9。v2:445 的毛利目标和"免费档成本 ≤ X 元"硬约束的框架来自 biz-1 / P2，具体数值（2 元、≥60%、30—50 元）是模型自填的。"冷热分层"的计价要求来自 biz-1 / P2，冷存储计算错误发生在模型自填的部分。④ **Optimizer 的输入**：载荷只有 `evaluation`、`iteration=1`、`user_override=null`，没有 PRD 正文（代码 `compatible.py:331-335`；记录的输入 10119 token 少于每个 reviewer 的输入 11954 token，后者包含 PRD 正文，两者一致）。⑤ **Optimizer 的输出**：18 项计划，high 4 / medium 12 / low 2；保留了全部 4 条 must_fix 和 14 条 should_fix，6 条 optional 中删除 4 条、保留 2 条；`objective` 写着"少量、可执行的定点修订"，实际有 18 项。⑥ **评审意见是否得到解决**：v2 生成失败，没有 v2 评审，系统无法判断，代码中也没有逐项核对计划是否落实的机制（上文 ⑤） |
| Solution Log | SL-003、SL-004 |
| Last Updated | 2026-11-08 |

---

## PA-009 输出截断后用相同请求重试，必然再次失败并重复计费

| 字段 | 内容 |
|---|---|
| ID | PA-009 |
| Title | 输出截断后用相同请求重试，必然再次失败并重复计费 |
| Observation | 2026-11-08 数据库审计时发现：v2 两次生成尝试的输入完全相同（18225 token），都在输出 16000 token 时被截断 |
| Status | VERIFIED（2026-11-08，见 SL-002） |
| Priority | P1 |
| Root Cause | **CONFIRMED。** `ProviderOutputTruncatedError` 继承自 `RetryableProviderError`（`errors.py:93-117`），generator 的重试循环对它重试一次（`workflow.py:275-307`）。第二次请求的 Prompt、baseline、计划和 `max_tokens` 与第一次完全相同（`workflow.py:248-273`），文档需要的长度没有变化，所以截断几乎必然再次发生。错误还被标记为 `retryable: true`（`workflow.py:146-152`）。前端文案让用户"精简需求描述或降低目标篇幅后重新运行"（`errorMessages.ts:21-22`），但界面上没有控制篇幅的选项；重新运行仍然是同样的输入和同样的上限。注释（`errors.py:96-98`）假设"a second attempt can succeed"，这对模型提前停止（UNFINISHED）或服务中断（INTERRUPTED）成立，对输出上限截断（TRUNCATED）不成立 |
| Evidence | 运行 `9fa59292` 的 `node_timings`：generator v2 attempt 1：76.31 秒，18225 / 16000 token，失败；attempt 2：78.15 秒，18225 / 16000 token，失败。两次失败共消耗 68450 token，占整次运行 137120 token 的 50%。`test_generation_reliability.py:220`（`test_repeated_truncation_fails_the_run_without_reviewing`）断言截断时恰好尝试 2 次且 `retryable is True`，说明当前行为是有意设计并由测试固定的，修改时需要同步更新这个测试 |
| Related Files | `backend/errors.py`，`backend/workflow.py`，`backend/prd_document.py`，`backend/config.py`，`src/lib/errorMessages.ts` |
| Impact | 每次截断多花一倍的生成时间和 token；用户看到"可重试"却无法通过重试成功；没有配置单价时（本次即如此）用户看不到这笔花费 |
| Proposed Direction | ① 截断时不再用相同请求重试：改为不重试，或在重试时改变条件（例如提高 `max_tokens` 到模型允许的范围内，或要求只输出被修改的章节）。② `PROVIDER_OUTPUT_TRUNCATED` 的 `retryable` 改为 false，或换成更准确的"需要调整后重试"的类型。③ 根本办法与 PA-002 相同：控制篇幅预算，或改为按章节增量修改，避免整篇重新输出。要提高 `max_tokens`，需先确认所用模型的输出上限和价格 |
| Acceptance Criteria | 截断后不会出现两次相同输入的请求；错误的 `retryable` 与实际可恢复性一致；前端文案给出用户能执行的下一步 |
| Related Tests | 现有：`test_generation_reliability.py:220`（会随方案变化而需要更新）、`test_workflow.py:352`。缺失：截断时不重复相同请求的断言 |
| Solution Log | SL-002 |
| Last Updated | 2026-11-08 |

---

## PA-010 11 个前端文件在基线即不符合 Prettier

| 字段 | 内容 |
|---|---|
| ID | PA-010 |
| Title | 11 个前端文件在基线即不符合 Prettier |
| Observation | V2.0 Phase 0 运行 `npm run format:check`，基线（cd56107）有 11 个文件不通过 |
| Status | OPEN |
| Priority | P2 |
| Root Cause | CONFIRMED。provider/model 选择相关提交（cd56107、ce8f1cd）未格式化：ProductIdeaForm.tsx、ProviderModelSelector(.test).tsx、TelemetryPanel.tsx、useProviderCatalog(.test).ts(x)、api.ts、types.ts、AgentDashboard(.test).tsx、components.test.tsx |
| Evidence | Phase 0 的 prettier --check 输出；V2.0 改动过的 4 个文件（api.ts、types.ts、AgentDashboard.tsx、AgentDashboard.test.tsx）已格式化，其余 7 个仍不通过 |
| Related Files | 上述文件 |
| Impact | `npm run format:check` 失败；不影响运行 |
| Proposed Direction | 单独一个 `style:` 提交运行 `npm run format`，不与功能改动混合 |
| Acceptance Criteria | `npm run format:check` 通过 |
| Related Tests | 无 |
| Solution Log | 暂无 |
| Last Updated | 2026-11-08 |

---

## 附录 A 运行 9fa59292 数据库证据（2026-11-08）

查询方式：`sqlite3.connect("file:data/agentic-prd.sqlite3?mode=ro", uri=True)`，执行 `PRAGMA query_only=ON`（返回 1）。先查 `sqlite_master` 确认表结构（`runs(run_id, snapshot_json, updated_at)`、`run_events(run_id, sequence, event_json)`），然后只执行 `WHERE run_id = '9fa59292-af6e-44d1-aacc-aff10e4a4024'` 的 SELECT。没有写操作，没有复制或导出数据库，用户输入只输出了统计数字和不超过 40 字的片段。

### A.1 运行概况

| 项 | 值 |
|---|---|
| Provider / Model | deepseek / deepseek-flash（真实调用，`is_mock=false`） |
| 时间 | 2026-11-08 06:46:48 → 06:51:10 UTC，有效运行 261.9 秒 |
| 状态 | FAILED，`current_iteration=2/3`，阈值 85 |
| 错误 | `PROVIDER_OUTPUT_TRUNCATED`，`retryable=true` |
| 最佳版本 | v1，76.0 分（技术 78 / 体验 76 / 商业 74） |
| v1 严重度 | must_fix 4，should_fix 14，optional 6 |
| token 合计 | 输入 86874，输出 50246，总计 137120；费用未配置（`cost_available=false`） |
| 落库事件 | 28 条（序号 1-2069，其余为瞬时 `prd_delta`） |

### A.2 节点耗时

| 节点 | 版本 | 尝试 | 秒 | 成功 | 输入 / 输出 token |
|---|---|---|---|---|---|
| generator | 1 | 1 | 75.45 | 是 | 4441 / 10314 |
| tech_reviewer | 1 | 1 | 12.37 | 是 | 11954 / 1398 |
| biz_reviewer | 1 | 1 | 14.41 | 是 | 11955 / 1575 |
| ux_reviewer | 1 | 1 | 16.86 | 是 | 11955 / 2153 |
| optimizer | 1 | 1 | 14.72 | 是 | 10119 / 2806 |
| generator | 2 | 1 | 76.31 | 否 | 18225 / 16000 |
| generator | 2 | 2 | 78.15 | 否 | 18225 / 16000 |

### A.3 v2 新增内容的来源追溯

数字识别方法：对 v2（`current_prd`）逐行提取"数字（含范围）+ 单位"（%、元、GB、TB、Mbps、秒、分钟、天、次、个百分点等），去掉 v1 中已有的，再分别在用户输入、三方评审、修订计划中查找。这个方法没有覆盖不带单位的数字，所以 65 个是下限；其中部分是由其他自填数字推算出来的（如 1.25 元 = 10 GB × 0.125）。

| v2 位置 | 内容 | 用户输入 | 评审 | 修订计划 | 判断 |
|---|---|---|---|---|---|
| 33 | 完成率 ≥70%、转化 ≥40%、高出下限 10 个百分点，来源写"内部试点观测值" | 只有指标名 | biz-3 要求"≥ X%"阈值 | P15 要求判定阈值 | 框架来自评审 / 计划；数值和"内部试点"来源是模型编造的 |
| 200 | 等待分级 10 秒 / 60 秒；取消后分片"保留 7 天" | 无 | ux-2："<10s""可取消并保留已获取分片" | P10 同 | 10 秒和"保留分片"规则来自评审；60 秒是模型补的；与 v2:176 冲突 |
| 206 | 80% | 无 | 无 | 无 | 无法追溯，模型自行补充 |
| 230 | 分片 2—4 秒、1—4 Mbps、>8 Mbps、2 Mbps、4K 首帧 8 秒，"必然突破 3 秒" | 无 | tech-4 要求"码率与分片时长假设" | P6 同 | 要求来自评审；数值是模型补的，并写成了确定的事实 |
| 238-240 | 提取码 10 次 / 5 次、15 分钟、30 次、1—2 次 | 无 | tech-5 / ux-8 要求上限和锁定时长 | P7、P17 | 要求来自评审；数值是模型补的 |
| 256-260 | 10 GB / 2 TB / 50 GB，单价 0.10—0.15 元、0.20—0.30 元、0.05—0.10 元，1.8 元/日，5 / 300 分钟 | 无 | tech-1 要求"初始值（待校准）"，biz-1 要求单价 | P1、P2 | 要求来自评审；数值是模型补的（v2:252 标注了"待校准"） |
| 414 | 重试 5 次，间隔到 25 分钟 | 无 | tech-6 要求"重试上限" | P8 | 要求来自评审；数值是模型补的 |
| 439-445 | 1.25 元、256 元、冷存储 0.03—0.05 元 / 90 天、0.40 元、80 元、13 元、505 元、2 元约束、毛利 ≥60%、月费 30—50 元 | 无 | biz-1："冷热分层""目标毛利率""免费档成本不超过 X 元" | P2 | 框架来自评审；所有数值和计算是模型完成的，其中有算术错误 |
| 449 | 滥用率 3%—8%、0.25 元、15 元、400 元、损失压到 10% 以内、激活率下降 5—10 个百分点 | 无 | biz-5 要求滥用假设和激活折损 | P16 | 要求来自评审；数值是模型补的 |
| 457-468 | 500 次、50%、95%、1000 次、10 分钟、25%、D7 ≥20%、会员转化 ≥1.5% | 只有指标名 | biz-3 要求阈值 | P15 | 指标名来自用户；阈值是模型补的 |
| 485 | 默认方案"仅中国内地可用、海外仅可访问分享"（海外用户不能提交下载任务） | 用户写的是"面向中国及海外市场" | tech-2 举例"仅内地可用、海外仅访问分享" | P3 原样转述 | 来自评审的举例，与用户输入矛盾 |
| 232 | 续播冲突："最近一次有实际播放行为的一端胜出" | 无 | ux-1 原句 | P9 原句 | 来自评审 |

### A.4 无法从数据库确认的事项

- Optimizer 和 Generator 实际发送给模型的完整请求文本没有被记录（代码只记录元数据）。载荷内容是根据代码（`compatible.py:189-200, 331-335`）和存储的 evaluation、计划推定的，记录下来的 token 数与推定一致。
- v2 如果完整生成，是否还会补上第 13、14 章，以及会有多长，无法确认。
- v2 没有评审，所以无法确认修订后评审意见是否解决。
- 同一请求在其他模型或更高 `max_tokens` 下是否能完整生成，本轮没有测试（需要调用模型）。
