# V3.0 差距分析

- 日期：2026-11-08
- 产品依据：[product-definition.md](../product-definition.md)（V0.1）
- 代码基线：`main` @ `cd56107` 加上未提交的 V2.0 改动（见 [product-audit/solution-log.md](../product-audit/solution-log.md) SL-002 至 SL-007）
- 方法：逐文件阅读源码并追踪调用链；行号以当前工作区为准。没有调用模型，没有读取数据库和 `.env`。

## 1. 结论

现有系统是一个**单次运行的 PRD 生成与自动评审循环**：用户提交三段文本，LangGraph 执行"生成 → 三方评审 → 汇总评分 → 修订计划 → 再生成"，最多 5 版，结束后只能查看和下载。

V3.0 要的是一个**以项目为中心、由用户驱动的长期工作区**：多轮需求探索、结构化需求基线、用户确认的 Product Brief、按章节编辑的 PRD、用户处理 Finding、修改后的影响分析。

两者的差距集中在三处：

1. **没有"项目"和"需求基线"。** 顶层对象是 Run，用户输入只有三个字符串。V3.0 的大部分新能力（来源与状态、追溯、影响分析）都依赖一个持久的、可编辑的需求数据模型，这部分需要从零建立。
2. **控制权在工作流，而不在用户。** 现在的循环自动决定修改哪些问题、什么时候停止；用户只能暂停时写一段补充说明。V3.0 要求只有用户采纳的 Finding 才进入修改，人工修改不被覆盖。
3. **PRD 是整篇 Markdown 字符串，没有章节对象。** 人工编辑、章节级 Finding 定位、影响分析和"不覆盖人工修改"都需要章节级存储。

V2.0 做的可靠性、证据化评审、确定性去重、Rubric 评分、Markdown 结构检查、失败分类，基本都可以复用，但要从"自动循环的一环"改为"用户发起的一次动作"。

## 2. 总表

| # | 模块 | 处理 | 一句话理由 |
|---|---|---|---|
| 1 | 项目管理 | REBUILD | Run 是一次性任务，无法承载长期项目；新增 Project，Run 降级为项目内的一次 AI 任务 |
| 2 | 需求探索 | ADD | 不存在多轮对话、追问或抽取 |
| 3 | 需求数据模型 | ADD | 不存在任何结构化需求对象 |
| 4 | 产品分析（主动发现） | ADD（复用 Finding 结构） | 现有 Reviewer 只审 PRD 正文，不审需求基线 |
| 5 | Product Brief | ADD | 不存在 |
| 6 | PRD 生成 | MODIFY | Generator 可保留，输入从三段文本改为确认后的 Brief，增加大纲步骤和按章节输出 |
| 7 | PRD 编辑器 | REBUILD | 只有只读查看器；存储需改为章节模型 |
| 8 | Finding 管理 | MODIFY | 结构和去重可保留；需要新增用户处理状态和 API |
| 9 | 变更影响分析 | ADD | 不存在需求 ↔ 章节 ↔ 验收标准的关联 |
| 10 | 评分与质量 | MODIFY | 保留 Rubric 和后端计分；不再作为自动停止条件，拆成多个质量视角 |
| 11 | 可靠性与失败处理 | KEEP | `failures.py`、`_guard`、结构化 `RunError` 直接适用于每一次 AI 调用 |
| 12 | Provider 层 | KEEP + MODIFY | 接口保留，新增探索、分析、大纲、章节生成方法 |
| 13 | SSE 与事件存储 | KEEP | 机制通用，事件类型需扩展 |
| 14 | 前端 | REBUILD | 页面结构、视觉、状态模型全部改变；纯函数工具可复用 |
| 15 | 自动迭代循环 | DEPRECATE（作为默认路径） | 与"用户决定修改什么"冲突；保留为可选的"一键优化" |
| 16 | 运行记录 / 遥测页 | MODIFY | 降级为项目活动记录和开发者调试区 |

处理方式定义：KEEP 直接保留；MODIFY 现有能力需要调整；REBUILD 现有实现无法满足，需要重新设计；ADD 新增；DEPRECATE 不再需要或不属于 MVP。

## 3. 逐模块分析

### 3.1 项目管理 · REBUILD

**当前实现**
- 顶层对象是 Run。`RunSnapshot`（`backend/schemas.py:773`）继承 `PRDRunState`（`schemas.py:687-764`），一次运行的输入、版本、评审、修订计划、遥测、错误全部放在一个对象里。
- 列表 `GET /api/runs`（`backend/main.py:356-367`）→ `RunManager.list_runs`（`run_manager.py:450`）→ 内存排序（`run_store.py:141-167`）。SQLite 只在启动时整体读入（`run_store.py:206-210`）。
- 没有改名、删除接口；CORS 只允许 GET / POST / OPTIONS（`main.py:275`）。`run_store.remove` 没有调用方。运行只会因 TTL（30 天，`config.py:63`）或数量上限（100，`config.py:62`）被清理。
- 运行之间唯一的关系是恢复链 `source_run_id`（`run_manager.py:325-381`）。
- 前端"对话记录"就是 `RunSummary[]`（`src/components/ConversationSidebar.tsx:7`）。

**新版目标**：项目可以创建、保存、继续、改名、删除；项目有当前阶段、待处理 Finding 数、待确认事项数、最近修改时间；关闭后重新打开可以恢复（定义 4.2 P0、5.1 A）。

**差距**
- 没有 Project 实体，也没有"一个项目内多次 AI 任务"的概念。
- 30 天 TTL 和 100 条上限会**自动删除**用户的长期工作，这与项目工作区直接冲突。
- 启动时把全部快照读进内存，项目数据变大后不可行。

**建议**：新增 `projects` 表和 Project API。Run 改名为"AI 任务"（Job），挂在项目下，表示一次生成、一次评审或一次优化。项目数据不设 TTL；删除必须由用户发起并二次确认（定义 10.5）。旧 Run 保留为只读的"历史运行"，不迁移成项目（见 [technical-impact.md](technical-impact.md) §5）。

**技术依赖**：新的存储层（按对象建表，不再整体序列化快照）；删除策略（Q-010）。

**风险**：如果直接在 `RunSnapshot` 上加字段扩展成项目，快照会继续膨胀，每次 `commit` 都整体写一次 JSON（`run_manager.py:453-485`），探索阶段每轮对话都会触发全量写。

### 3.2 需求探索 · ADD

**当前实现**
- 不存在多轮对话、消息历史、追问或聊天接口。仓库中的 "chat" 只出现在 Provider 调用 Chat Completions 的地方（`providers/compatible.py:53,204,285`）和侧栏文案（`ConversationSidebar.tsx:37,47`）。
- 唯一的中途输入是暂停后在 `RunControls.tsx:96-110` 填写的补充说明（`ResumeRunRequest.user_override`，≤2000 字，`schemas.py:217-226`）。
- `src/lib/prdOutline.ts:135` 的 `digestRequest` 只是把输入切句用于显示。

**新版目标**：解析输入 → 提取已知信息 → 识别缺口 → 每轮 1～3 个带目的说明的问题 → 用户回答、跳过或"不知道" → 更新基线 → 再评估（定义 3.3）。

**差距**：整套能力都需要新增，包括：对话存储、每轮的 AI 调用、抽取结果写入基线、问题状态（待回答 / 已回答 / 跳过 / 不知道）、P0/P1/P2 优先级、"不重复询问已明确信息"的判断依据。

**建议**
- 探索是请求—响应式的交互，不需要放进 LangGraph 长流程。每轮一次 `explore_turn` 调用，输入当前基线 + 最近几轮对话 + 本轮回答，输出结构化结果：本轮理解摘要、抽取的条目（新增 / 更新，带来源）、下一轮问题（带目的、优先级、目标分组）。
- 抽取结果一律以 Inferred / Proposed 状态写入，用户确认后才变成 Confirmed（定义 2.2、2.3）。
- 结构化输出复用 `_validated_structured`（`workflow.py:780-860`）的"一次传输重试 + 一次修复"策略，以及 `failures.classify`。

**技术依赖**：需求数据模型（3.3）；Provider 新方法；对话表。

**风险**
- 每轮都要把基线和历史发给模型，token 成本随项目增长。需要对话摘要或只发最近 N 轮。
- 模型可能把推断写成用户原话。必须在后端校验：`source=user` 的条目只能来自用户本轮或历史消息中的原文片段。

### 3.3 需求数据模型 · ADD

**当前实现**
- 用户输入只有三个字符串：`user_idea`（10–5000 字）、`target_audience`（≤1000）、`user_constraints`（≤2000），见 `CreateRunRequest`（`schemas.py:183-214`）。它们原样包进 `UserRequirements`（`providers/base.py:37-44`，由 `workflow.py:123-128` 构建）。
- 没有 User、Scenario、Pain Point、Requirement、Assumption、Decision、Open Question 任何对象，也没有来源和状态字段。
- "假设"和"待确认"只以 PRD 正文里的文本标签存在：`[用户输入] [假设] [待确认]` 等（`prompts.py:213-235` FACT_RULES），由正则检查（`prd_quality.py:75-97`），以及必需章节"假设与待确认事项"（`prd_quality.py:35-73`）。

**新版目标**：12 个分组（定位、目标、用户、问题、场景、现有方案、方案、功能、约束、假设、决策、待确认），每条有来源、状态（Confirmed / Inferred / Assumption / Proposed / Open / Rejected）和修改记录，用户可以直接编辑（定义 3.4、6.1）。

**差距**：完全没有。现有的文本标签是"写在 PRD 里的约定"，不是数据；无法查询、无法关联、无法追踪修改。

**建议**
- 用一张 `requirement_items` 表承载所有分组（`category` 字段区分），而不是 12 张表。Assumption、Decision、OpenQuestion 的专属字段（验证方式、影响、优先级）放在可空列或 JSON 扩展列里。这样基线面板、Brief 和追溯都只查一张表。
- 每次修改写一条 `item_revisions`（旧值、新值、来源：用户编辑 / AI 抽取 / 用户确认）。
- 关联关系用一张 `links` 表（from_id, to_id, kind），满足定义 6.2 "先用 ID 引用和关系表，暂不用图数据库"。
- ID 采用分组前缀 + 项目内序号（`USR-01`、`DEC-02`），人可读、可在对话和 PRD 中引用。

**技术依赖**：新存储层；ID 分配需在事务内完成，避免并发重号。

**风险**：分组边界不清（例如"免费不限速"既是决策又是功能规则）。建议允许一条目只属于一个分组，用 `links` 表达跨组关系，而不是复制条目。

### 3.4 产品分析（主动发现）· ADD，复用 Finding 结构

**当前实现**
- 三个 Reviewer（`workflow.py:661-680`，`_reviewer_node` `:698-778`）只读 PRD 正文，加上用户原始三段文本、结构检查结果、该角色上一轮的 findings（`ReviewContext`，`providers/base.py:47`；装配在 `workflow.py:711-723`）。
- Reviewer 的 `FindingCategory` 有 17 个值（`schemas.py:93-118`），偏向文档质量和实现，没有"产品机会"类。
- 没有任何环节在 PRD 生成**之前**分析需求。

**新版目标**：五个发现维度——A 需求完整性、B 逻辑一致性、C 场景遗漏、D 产品风险、E 产品机会；机会必须说明对应问题、现有方式不足、新价值、实现代价、待验证假设（定义 3.5）。

**差距**：分析对象不同（基线而不是 PRD）、维度不同、触发时机不同。

**建议**
- 新增 Product Analyst 调用，输入需求基线，输出 Finding。复用 V2.0 的 Finding 准入规则（问题、证据、影响、建议四项必填，允许 0 条，单次上限）和后端的确定性处理（`scoring.normalize_review` `:115` 的证据检查、置信度降级、ID 分配）。
- 证据字段引用基线条目 ID，而不是 PRD 原文。后端校验被引用的 ID 存在。
- 触发时机：用户点击"检查"或进入方案页时，以及基线变化超过阈值时；**不在每轮对话后自动调用**，避免成本和噪音。探索调用本身只负责追问，可以顺带标记明显冲突，但正式 Finding 由 Analyst 产出。

**技术依赖**：需求数据模型；统一的 Finding 表（3.8）。

**风险**：机会类发现容易变成"加个 AI 推荐"之类的泛化建议。Prompt 和后端都要强制机会的五个字段非空，并对没有关联用户问题的机会直接丢弃。

### 3.5 Product Brief · ADD

**当前实现**：不存在。生成器直接从三段文本写 PRD（`_generator_node`，`workflow.py:386-520`）。

**新版目标**：14 个部分的需求基线快照，可编辑、需用户确认；只有确认内容成为正式基线；推断、假设、建议保留原身份（定义 3.6）。

**建议**
- Brief 不是一份新的自由文本，而是**基线条目的一次带版本的快照**加少量叙述字段（背景、方案概述）。这样 Brief 的每一行都能追溯到条目 ID，修改 Brief 等于修改条目。
- 确认机制：用户逐组确认或整体确认；确认时生成 `brief_versions` 记录，冻结当时的条目 ID 和内容。PRD 生成只读已确认的 Brief 版本。
- 未确认的条目可以出现在 Brief 中，但必须带状态标记，并进入"假设与待确认事项"。

**技术依赖**：需求数据模型；Q-007（确认粒度）。

**风险**：如果 Brief 做成独立文档，会出现"基线和 Brief 不一致"的第二个事实来源。必须坚持 Brief 是基线的视图。

### 3.6 PRD 生成 · MODIFY

**当前实现**
- `_generator_node`（`workflow.py:386-520`，流式在 `:528-607`）一次输出整篇 Markdown，末行写完成标记，由 `prd_document.validate_generated_prd` 校验完整性。
- 输入：三段用户文本、迭代号、修订计划（或恢复时的 `seed_revision_plan`）、底稿 `baseline_prd`（最佳版本 → 最新版本 → `seed_prd`，`:610-624`）、输出语言、生成模式。
- Prompt：`generator_system_prompt(mode)`（`prompts.py:260-301`）+ `STRUCTURE_RULES`（`:164`起，8 个必需章节骨架）+ `FACT_RULES`（`:213-235`）+ `budget_rules`（标准 12k–18k 字，精简 7k–11k）。
- 生成后 `prd_quality.check_prd`（`prd_quality.py:227`）做结构检查，结果存入 `PRDVersion.quality`。

**新版目标**：三步——按 Brief 生成项目适用的大纲（每章说明目标、内容、关联需求、依赖章节、未定信息）→ 用户可改大纲 → 生成正文（P0 详细、P1 核心、P2 简述）→ 为核心功能生成流程、规则、状态、异常、权限、验收标准，且每项能追溯到用户问题或目标（定义 3.7）。

**差距**
- 没有大纲步骤，章节骨架写死在 Prompt 中。
- 输入是自由文本，模型无法引用条目 ID，所以追溯无从谈起。
- 整篇一次输出：截断风险高（PA-004 / PA-009 的根因），也无法只重写某一章。

**建议**
- 保留 Generator 的流式、完成标记、截断不重试、篇幅预算、事实标签规则。
- 改为"大纲调用（结构化 JSON）+ 逐章生成（流式 Markdown）"。每章输入：已确认 Brief 中与该章关联的条目 + 大纲 + 已生成章节的标题和摘要（用于一致性）。
- 要求模型在正文中用条目 ID 标注来源（原型中的 `[[FD-01|…]]` 锚点语法是 Finding 版本，需求引用可用类似语法），后端解析后写入章节 ↔ 条目关联。
- 逐章生成同时解决截断：单章失败只重做该章，已完成章节保留。

**技术依赖**：章节模型（3.7）；Brief（3.5）。

**风险**：逐章生成会增加调用次数和章节间不一致的概率。缓解：大纲阶段先确定术语和编号；全文生成后跑一次确定性一致性检查（`prd_quality` 扩展）和一次 Tech/UX/Biz 评审。

### 3.7 PRD 编辑器 · REBUILD

**当前实现**
- `PRDVersion`（`schemas.py:672-680`）：`content: str` 整篇 Markdown。版本号上限 5（schema 约束）。
- 章节只存在于解析时：`prd_quality.Heading`（`:123`）、`src/lib/prdOutline.ts:37 parseOutline`、`:73 locateSection`。
- 没有人工编辑的 API 或 UI。`PRDViewer.tsx` 用 react-markdown 只读渲染，带目录和问题侧栏。
- 版本对比：`src/lib/diff.ts:243 diffLines`（行级 LCS，上限 25 万单元格）和 `src/lib/readingDiff.ts:338 readingDiff`（块级、按章节分组），`VersionDiff.tsx:253` 提供阅读 / 源码两种模式。
- 导出：`src/lib/download.ts:6-16`，Markdown，文件名 `agentic-prd-{runId}-v{n}.md`。

**新版目标**：修改正文、增删章节、调整顺序、改优先级、编辑表格 / 规则 / 验收标准、保存版本、查看和对比历史版本；AI 不得覆盖人工修改；人工与 AI 修改可区分（定义 3.8、8.3）。

**差距**
- 无编辑能力；整篇字符串无法标记"哪一章是人工改的"。
- 版本上限 5 不适合长期编辑（定义 3.10 "不设置固定迭代上限"）。
- 无保存反馈、无自动保存、无并发保护。

**建议**
- 存储改为 `prd_documents`（项目内一份）+ `prd_sections`（id、顺序、层级、编号、标题、正文 Markdown、来源 origin：ai / optimized / human、锁定标记、关联条目）+ `prd_versions`（版本快照：章节 id 与内容哈希列表）。
- 人工保存的章节标记 `origin=human`。Optimizer 修改 human 章节必须走"提出修改 → 用户确认"，不能直接写入。
- 编辑器 MVP 采用"按章节编辑 Markdown 源码 + 渲染预览"，不做富文本所见即所得（成本高、与 Markdown 导出不一致）。原型即按此实现。
- 复用：`readingDiff`（块级对比可直接用于章节内对比）、`prdOutline.parseOutline`（导入已有 PRD 时切章节）、`prd_quality.sections_matching`（`:455-482`）、`download.ts`。

**技术依赖**：章节存储；版本快照；乐观锁（`updated_at` 或版本号）防止两个标签页互相覆盖。

**风险**：导入外部 PRD（入口 C）时，标题层级不规范会导致切分错误。需要导入后让用户确认章节划分。

### 3.8 Finding 管理 · MODIFY

**当前实现**
- `FeedbackItem`（`schemas.py:245-272`）：severity、issue、recommendation、finding_id、title、category、section、evidence、user_impact、source_role(s)、merged_from、observations、confidence、severity_adjusted_from。
- ID：`v{版本}-{角色}-{序号}`（`scoring.py:159`），每角色最多 5 条（`:47`）。无证据丢弃（`:126-131`）；quantification 类或置信度 < 0.5 的 must_fix 降级（`:95-112`）。
- 去重 `deduplicate`（`scoring.py:271`）只合并不同角色的问题。
- 处理状态 `FindingStatus`（`schemas.py:121-132`）：resolved / partially_resolved / unresolved / declined / not_checked，由 `resolve_previous_findings`（`scoring.py:391-446`）根据下一轮 Reviewer 的复查或 Optimizer 的拒绝自动得出。
- **用户无法采纳、拒绝或暂缓任何 Finding**。`ReviewPanel.tsx` 的按钮只做筛选和定位（`:411-415, 663-686, 750-753`）；`RevisionPlanPanel` 只读。

**新版目标**：Finding 状态 Open / Accepted / Modified / Rejected / Deferred / Resolved / Stale；只有用户采纳的进入定向优化；修改后历史 Finding 标记为已解决、部分解决、不受影响或需重新验证（定义 3.5、3.10、3.11）。

**差距**
- 缺少"用户处理状态"这一层。现有状态全是"AI 复查结果"，两者应分开：`status`（用户决定）和 `verification`（AI 复查结果）。
- ID 带版本号，同一问题在下一版会换 ID，无法长期追踪。
- Finding 只挂在某个版本的评审上，不是项目级对象；探索阶段的发现无处存放。

**建议**
- 新建项目级 `findings` 表，同时承载探索发现（A–E）和评审发现（TECH / UX / BIZ）。ID 改为项目内递增 `F-01`、`FD-01`（或统一前缀），不随版本变化。
- 字段在 `FeedbackItem` 基础上增加：`scope`（baseline / prd）、`kind`（A–E 或评审类别）、`status`（用户）、`verification`（AI）、`related_items`、`related_sections`、`decided_by`、`decided_at`、`user_note`（"修改后采纳"时的修改内容）。
- 保留：证据准入、置信度降级、跨角色去重、`resolve_previous_findings` 的"多评审取最差、未复查不算解决"规则，改为写入 `verification`。
- 新增 API：`PATCH /findings/{id}`（状态 + 备注）。Optimizer 只读取 `status in (accepted, modified)` 的 Finding。

**技术依赖**：项目存储；章节模型（`related_sections`）。

**风险**：跨版本"同一问题"的识别。新一轮评审产生的 Finding 需要先和项目内已有的 open / deferred Finding 做 `is_same_problem`（`scoring.py:231`）匹配，命中则更新原记录而不是新建，否则用户会反复看到被拒绝过的问题（定义 1.2 第 8 点）。

### 3.9 变更影响分析 · ADD

**当前实现**
- 不存在需求 ↔ 规则 ↔ 章节 ↔ 验收标准的关联。
- 唯一相关的是 V2.0 修订计划中的 `affected_sections`（`RevisionItem`，`schemas.py:425-450`），由模型填写，只在一次修订内使用。
- 每次生成新版都会重新调用全部三个 Reviewer（`workflow.py:213-215`），与"不允许每次编辑都重新调用全部 Agent"（定义 3.11）相反。

**新版目标**：按修改类型（格式 / 描述 / 功能 / 业务规则 / 用户定位 / 核心约束）决定检查范围；更新历史 Finding 状态。

**建议**
- **第一层：确定性。** 保存章节时计算 diff（复用 `readingDiff`），判断是否只有格式变化（空白、标点、顺序）；通过 `links` 表找出关联条目和下游章节；把关联的 open Finding 标为 Stale。原型中"已保存。修改可能影响 §7 验收标准"即这一层。
- **第二层：按需的语义检查。** 用户点击"检查影响"时，只把被改章节 + 下游章节 + 关联条目发给**一个**范围受限的检查调用（复用 Reviewer Prompt，限定章节），输出对受影响 Finding 的复查结论和新的冲突。
- 修改类型的判定：先用规则（改动落在"业务规则"表格、验收标准列表、定位章节等）粗分，再由检查调用确认，不单独增加一个分类 Agent。

**技术依赖**：章节模型、`links` 表、Finding 表。

**风险**：关联关系的质量决定影响分析的质量。关联主要来自生成时的 ID 标注，模型漏标会导致漏检。缓解：生成后用确定性规则补齐（章节正文中出现的条目 ID、业务规则编号 BR-xx、验收标准编号 AC-xx）。

### 3.10 评分与质量管理 · MODIFY

**当前实现**
- `backend/rubric.py:59-160`：三角色各 4 维度、权重、1–5 锚点，`RUBRIC_VERSION=2026-11-v2`；`GET /api/rubric`（`main.py:462`）。
- `scoring.py`：`role_score`（`:62`）= Σ(分/5×权重)×100；`overall_score`（`:77`）三角色平均；`evaluate_gate`（`:326-352`）门槛 PASSED / NEEDS_REVISION / BLOCKED / UNSCORED。
- 门槛决定自动循环是否停止（`_route_after_aggregate`，`workflow.py:997-999`）。`best_version` 只在分数严格更高时更新（`workflow.py:890-893`）。

**新版目标**：不以单一综合分为唯一标准；分别展示 PRD 文档质量、需求成熟度、实施就绪度、未解决风险和阻塞项（定义 7.7）。

**建议**
- **保留**：Rubric 维度与锚点、后端计分、模型不得自报总分、版本号记录。这些满足定义 10.3"评分需要提供维度和理由"。
- **重新定位**：综合分从"自动停止条件"改为"文档质量"一个视角。
- **新增**两个确定性指标，不需要模型：
  - 需求成熟度：P0 分组中已确认条目占比、未处理的 P0 待确认事项数、未处理的 must_fix 探索发现数。
  - 实施就绪度：P0 功能是否都有流程、业务规则、异常处理、验收标准章节（从章节关联和结构检查得出）。
- **未解决风险与阻塞**：直接来自 Finding 表（open / deferred 且 severity=must_fix 或 kind=D）。
- `best_version` 概念不再适用（用户编辑的版本没有"最高分"之说），由用户选择当前版本。

**风险**：如果继续显示单一"90.7 分"，用户会把它当成完成标准。建议 MVP 页面上不突出综合分。

### 3.11 其他模块

| 模块 | 当前实现 | 处理 | 说明 |
|---|---|---|---|
| 失败处理 | `failures.py`：`is_transient`（`:58`）、`backoff_seconds`（`:74`）、`classify`（`:88-170`）；节点 `_guard`；`RunError` 结构化字段 | KEEP | 每一次 AI 调用（探索、分析、大纲、逐章、评审、优化）都沿用"截断不重试、只重试瞬时错误、结构化修复最多 1 次" |
| 状态机 | `state_machine.py:14-83`，暂停只在聚合 / 优化边界生效 | MODIFY | 自动循环取消后，AI 任务的状态简化为 queued / running / succeeded / failed / cancelled；暂停不再需要 |
| Provider | `LLMProvider`（`providers/base.py:82-132`）：`stream_prd`、`generate_review`、`generate_revision_plan`、`repair_structured` | KEEP + MODIFY | 新增 `explore_turn`、`analyze_baseline`、`generate_outline`、`stream_section`；Mock / Scenario Provider 同步扩展 |
| SSE 与事件 | `GET /api/runs/{id}/events`（`main.py:466`），`after_sequence` / `Last-Event-ID` 回放；`run_events` 表；`prd_delta` 瞬时不落库 | KEEP | 改为按 AI 任务订阅；事件类型扩展（turn_extracted、section_delta、findings_created 等） |
| 自动迭代循环 | generator → 3 reviewer → aggregator → optimizer → generator（`workflow.py:212-225`） | DEPRECATE（默认路径） | 改为用户逐步触发："评审"一次、"按采纳的问题优化"一次。可以保留"一键评审并优化一轮"作为快捷操作，但每轮结束都停下等用户 |
| 运行记录 / 遥测 | `RunTimeline.tsx`、`TelemetryPanel.tsx`、`AgentTrace.tsx` | MODIFY | 用户视图改为项目活动记录（原型工作台 C 区）；Token、耗时、Trace ID 保留在开发者折叠区 |
| 前端 | 单页 `AgentDashboard`，深色主题（`global.css:15-32`），Tailwind 映射 CSS 变量 | REBUILD | 页面结构、视觉、状态模型全部改变。可复用：`readingDiff`、`diff`、`prdOutline`、`download`、`errorMessages`、`failureNotice`、`useAgentRun` 的 SSE 重连逻辑 |
| 测试 | 后端约 258 个测试函数 / 23 文件；前端约 192 个 / 18 文件；e2e 14 个 / 5 文件（Mock） | MODIFY | 评分、去重、失败分类、SSE 回放等测试继续有效；运行循环相关的 e2e 需要按新流程重写 |
| 评测工程 | `prd_benchmark/`、`benchmark/` | 不在本次范围 | 可用于定义 11.3 的对照实验，需单独评估 |

## 4. 可以保留的旧功能

1. 失败分类与重试策略（`failures.py`），以及失败面板"发生了什么 / 失败步骤 / 仍可使用 / 下一步"的信息结构。
2. 截断不重试、半成品不当版本（`incomplete_draft`、`isUsableDraft`）。
3. Finding 的证据准入、上限、置信度降级、跨角色去重、复查取最差。
4. Rubric 维度、锚点、后端计分、版本号。
5. Markdown 结构检查 `prd_quality.check_prd`：必需章节、长段落、未标注数字、编造来源。
6. 生成 Prompt 中的事实标签规则和篇幅预算。
7. 块级阅读对比 `readingDiff`、Markdown 导出。
8. SSE 回放与重连、事件持久化。
9. Provider 抽象、Mock / Scenario Provider、e2e 隔离端口与内存库。

## 5. 必须重构或新增

- **重构**：项目与存储层、PRD 存储（章节化）、Finding 存储（项目级 + 用户状态）、前端全部页面、工作流编排（自动循环 → 用户触发的任务）。
- **新增**：对话与探索调用、需求基线（条目、修改记录、关联）、Product Analyst、Product Brief（快照与确认）、大纲生成、逐章生成、PRD 编辑与版本、影响分析、质量的多视角展示。

