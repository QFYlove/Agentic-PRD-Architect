# Agentic PRD Architect 架构记录

> 最近更新：2026-08-21
>
> 范围：已确认的系统边界、实现基线和不可随意变更的架构决策

## 1. 系统组成

系统采用两个本地进程：Astro Node SSR 提供页面壳和 React Island，FastAPI
提供领域契约、REST 控制和 SSE 事件流。浏览器端工作台通过 URL 恢复
Run、快照校准、SSE 增量归并和结构化可视化消费同一套协议。

数据流固定为：浏览器以 REST 创建或控制 Run，以 GET SSE 接收单向业务事件；
FastAPI 中的 RunManager 驱动 LangGraph；Generator、三个独立 Reviewer 和
Optimizer 通过 Provider 接口调用 Mock 或真实模型；RunStore 与 EventStore
以 SQLite 为事实来源，进程内对象是活动运行的热缓存。

## 2. 不可变决策

- 当前版本是本地、单 Uvicorn Worker 的 Showcase；不支持水平扩展。
- 控制使用 REST，实时推送使用带递增 ID 的 SSE，不引入 WebSocket。
- Tech、UX、Business Reviewer 必须独立并行；总分由后端等权、确定性计算，
  模型自报的总分一律不采用。
- 质量门是两个独立条件的合取：`overall_score >= quality_threshold` 且
  `must_fix_count == 0`。任一不成立就继续迭代或以 `MAX_ITERATIONS_REACHED`
  收尾，不得以分数达标单独判定完成。
- 反馈 severity（`must_fix` / `should_fix` / `optional`）的计数按需从已存储的
  反馈推导，不作为总数持久化，避免同一份反馈在不同视图给出不同数字。
- 生成完整性由两个独立信号判定：Provider 的 `finish_reason` 与模型写在正文
  最后一行的 completion sentinel。任一不通过即拒绝该次尝试。
- Pydantic 模型是 API 数据契约的唯一事实来源；OpenAPI 和版本化 JSON 样本
  向 TypeScript 传播契约。
- 质量达标、最大轮次、取消和失败是不同终态，终态不可回到运行态。
- 缺少模型价格时费用必须是 `null`/不可用，不能按零费用展示。
- 持久化只使用本地 SQLite；不引入外部数据库、Redis、外部队列或全局前端
  状态框架。
- 密钥只从后端环境读取；模型原始 HTML 和隐藏思维链不得进入前端。

## 3. 契约与基线约束

共享 JSON Fixture 是前后端之间的可执行桥梁：每个样本先由 Pydantic 校验，
再由前端运行时解析器和 TypeScript 检查消费。契约集显式覆盖全部四个终态和
17 种事件，避免仅凭静态类型造成枚举漂移。

状态迁移集中在 `backend/state_machine.py`，领域数据集中在
`backend/schemas.py`。RunManager 只能调用该迁移边界，不能在路由或
LangGraph 节点中散落状态判断。OpenAPI 主动注册尚未被路由引用的核心
模型，保证契约随时可检查。

Astro 命令通过 `cross-env` 关闭遥测，使 Windows、CI 和受限执行环境使用同一
脚本。格式化脚本只扫描项目源文件和契约，避免访问虚拟环境与工具缓存。

Astro 4 和 Mermaid 10 的 Major 版本由现有技术栈文档固定，但其当前锁定依赖
树存在已公开安全告警。因此当前产物的安全边界是本地 Showcase；任何公网部署
都必须先把框架 Major 升级作为显式架构变更，并重新执行契约、SSR 和 E2E 门禁。

## 4. 运行时协调与工作流

`RunManager.commit()` 是普通状态修改的唯一提交入口；状态、对应业务事件和
`latest_event_sequence` 在同一把 Run 锁内完成。状态迁移使用同样的锁顺序：
先 Run 锁，后事件 Condition。EventStore 订阅者不会在持有 Condition 时读取
Run 快照，从而避免反向锁顺序导致死锁。

LangGraph 定义真实的循环拓扑：Generator 扇出到三个 Reviewer，三个分支汇合
到 Aggregator，未通过质量门时经 Optimizer 回到 Generator。并行分支只写各自
角色字段；Aggregator 是唯一可以计算总分和判定质量门的位置。Optimizer 产出
结构化 Revision Plan，下一轮 Generator 必须逐条处理。

暂停不是任意中断。`PAUSE_REQUESTED` 允许当前 Generator/Reviewer 完成，只在
聚合完成且 Optimizer 尚未开始时进入 `PAUSED`。暂停时间从 Run 总超时中扣除，
但 Run 仍占并发槽。取消信号会与 Provider await 竞争；提交 Provider 结果前
在 Run 锁边界再次检查，避免晚到结果污染终态。

EventStore 的 Heartbeat 是订阅层信号，不创建 `RunEvent`、不分配 sequence、
不进入有界缓冲。业务事件才具有可回放 ID；恢复起点取 query 与
`Last-Event-ID` 的较大合法值。

Provider 重试分为两条互斥路径：没有收到响应的临时传输错误最多尝试两次；
已经收到但 Pydantic 校验失败时只做一次格式修复，不重复原请求。认证和模型
配置错误立即终止。

## 5. 生成完整性与失败保留

一次 Generator 尝试只有同时通过 `finish_reason` 与 completion sentinel 才被接受。
Sentinel 在进入状态之前就被剥离，因此不会出现在阅读界面或下载文件中。三种失败
原因——输出上限、模型提前结束、服务中断——映射到三个不同的错误码和三段不同的
用户文案，因为仅说「不完整」无法告诉用户该改什么。

`LLM_MAX_OUTPUT_TOKENS` 作为 `max_tokens` 显式发送，使 `finish_reason="length"`
指向一个已配置的上限，而不是随模型变化的 Provider 服务端默认值。

后续版本生成失败不回收已提交的版本：`versions` 中的每一版及其评审与修订计划都
保留，界面指名失败的是哪一版。只有 `versions` 为空、首版从未落地时才允许显示
「首版 PRD 生成失败」。

Per-node timing 记录每次节点调用的节点、版本、attempt、墙钟秒数与 Token，包括
消耗了 Token 却产出不可用文档的失败尝试——否则记录时间无法与总耗时对上。

## 6. 前端投影与恢复

URL 中的 `run_id` 是浏览器恢复身份的唯一事实来源。Hook 加载时必须先取原子
快照，再从 `latest_event_sequence` 建立 SSE；New Run 递增本地 session 并
关闭旧 EventSource，所以旧连接的晚到事件无法写入新 Run。

Reducer 是所有可视化的唯一事件投影层。每个版本保存 generation attempt；
`prd_stream_reset` 才能切换到更高 attempt，旧 attempt 的晚到 delta 被丢弃，
`prd_generated` 再以完整正文校准。`prd_delta` 只存在于实时路径，不做持久化。
自动选择跟随最新流式版本，用户手动选择旧版本后设置 pinned 标志，不会被后续
事件强制切回。severity 计数在事件 payload 缺少计数字段时由已收到的三份 review
重算，使实时路径与快照恢复路径给出同一组数字。

EventSource 保留浏览器原生的短暂重连能力。连续三次错误后才关闭旧连接、重新
拉取快照并用新游标订阅；一次成功 open 会清零错误计数。终态事件立即关闭连接。
API 传输、事件解析和 reducer 顺序检查分别承担不同错误边界。

界面由版本轨和五个工作区页签（`prd` / `review` / `plan` / `diff` / `trace`）
组成，只有 `prd` 永不禁用。模型正文只通过 `react-markdown` + GFM 且 `skipHtml`
渲染；Trace 由结构化事件白名单生成；`mermaid` 代码块按类型白名单、
`securityLevel: "strict"` 和 `htmlLabels: false` 渲染，首次用到时才加载，解析失败
降级为图表源码。图表同时提供文本表格，状态 Badge 同时提供文字，信息不依赖颜色
或 SVG。遥测列表读不懂的数据一律丢弃，不能因此让一份已完成的 PRD 无法渲染。

Astro 仅渲染文档壳，React 工作台使用 `client:only`。Markdown、Recharts 和
Mermaid 作为独立延迟加载块，避免阻塞首屏；Vite 开发代理只把 `/api` 转发给
本地 FastAPI，公开 Base URL 仍由 `PUBLIC_API_BASE_URL` 统一配置。

## 7. 真实 Provider 与测试控制面

真实模型边界由一个 `OpenAICompatibleLLMProvider` 承担。DeepSeek 与 GLM
共享异步 Chat Completions、流式 Usage、JSON Object、Pydantic 校验和统一错误
映射；Provider 特有差异只在应用工厂注入。DeepSeek 显式关闭 thinking，任何
`reasoning_content` 都不进入状态、事件或前端；GLM 使用同一公共契约。

E2E 故障注入是测试控制面，不是生产 API。只有 `APP_ENV=test` 且
`E2E_TEST_MODE=true` 时才创建 Scenario Provider 和 `/api/test/scenario`。
Playwright 使用独立端口 4331/8011；Node 启动器负责探活和按已记录 PID 清理
子进程，避免测试结束后污染开发端口。

取消是用户意图优先的终态：Cancel API 在设置取消信号后立即原子提交
`CANCELLED`，节点提交边界仍检查同一信号并拒绝晚到结果。超时、Provider
错误或未知异常与取消竞态时也必须保留 CANCELLED，不能覆盖成 FAILED。

日志仅记录请求 ID、Run ID、节点、Provider 类型、耗时、状态和重试次数等
结构化元数据。Prompt、PRD 正文、模型原始响应、隐藏推理和 API Key 均不进入
日志。并发容量检查与创建在同一锁内，保证超出上限的请求确定返回 429。

## 8. 文件职责

### 仓库与运行时

| 文件 | 作用 |
| --- | --- |
| `PRD.md` | 产品目标、功能范围和验收要求的最高层需求来源。 |
| `AGENTS.md` | 面向贡献者和 AI 开发者的仓库工作规范。 |
| `README.md` | 英文安装、Provider 配置、启动、测试、能力、限制和排障说明。 |
| `docs/README_ZH.md` | 与 `README.md` 对应的简体中文版本。 |
| `.nvmrc` | 固定 Node.js 24.15.0。 |
| `.python-version` | 固定 Python 3.13.5。 |
| `.env.example` | 不含密钥的后端配置模板，含 `PUBLIC_API_BASE_URL` 与 `LLM_MAX_OUTPUT_TOKENS`。 |
| `.env` | Git 忽略的本地配置；DeepSeek 选择生效、GLM 整段注释、Mock 默认开启。 |
| `.gitignore` | 排除依赖、构建产物、缓存、虚拟环境和本地密钥文件。 |
| `package.json` | 前端精确依赖版本及开发、检查、单元测试、E2E、浏览器安装和构建脚本。 |
| `package-lock.json` | npm 唯一 lockfile，保证可复现安装。 |
| `pyproject.toml` | pytest、Ruff、strict mypy 和已知 LangGraph 依赖告警过滤配置。 |

### 前端配置与源码

| 文件 | 作用 |
| --- | --- |
| `astro.config.mjs` | 启用 React/Tailwind/Node SSR、可配置 `/api` 代理、E2E 工具栏开关和懒加载阈值。 |
| `playwright.config.ts` | Chromium、单 Worker、失败证据和内置/外部 E2E 服务模式。 |
| `scripts/run-e2e.mjs` | 启动 E2E 前后端、探活、转发 Playwright 参数并清理测试进程树。 |
| `tailwind.config.mjs` | 定义 Tailwind 扫描范围和主题扩展入口。 |
| `tsconfig.json` | 启用 Astro strictest、React JSX 和额外严格检查。 |
| `vitest.config.ts` | 配置 jsdom 前端测试发现范围和统一测试环境初始化。 |
| `.eslintrc.cjs` | TypeScript、Astro、React Hooks 的 Lint 规则。 |
| `.eslintignore` | 排除构建目录及 Astro 生成的 `src/env.d.ts`。 |
| `.prettierrc.json` | 前端与 Astro 的统一格式规则。 |
| `.prettierignore` | 排除依赖、缓存、虚拟环境和设计文档。 |
| `src/env.d.ts` | Astro 自动生成/维护的环境类型引用。 |
| `src/pages/index.astro` | 根路由、无脚本说明和 client-only React Island 挂载点。 |
| `src/layouts/Layout.astro` | HTML 文档壳、元数据和全局样式入口。 |
| `src/components/AgentDashboard.tsx` | 主工作台；组合页面状态、运行头部、控制区、版本轨、五个工作区页签和延迟加载可视化。 |
| `src/components/ProductIdeaForm.tsx` | 创建 Run 的输入、边界校验、质量设置和重复提交隔离。 |
| `src/components/RunControls.tsx` | 按 Run 状态提供 Pause/Resume/Cancel/New Run 和补充要求输入。 |
| `src/components/StatusBadge.tsx` | 将全部 Run 状态映射为带文字的非纯颜色状态标识。 |
| `src/components/VersionRail.tsx` | 版本列表、分数、最佳版本标识和当前选择。 |
| `src/components/WorkspaceTabs.tsx` | `prd` / `review` / `plan` / `diff` / `trace` 页签及可用性规则。 |
| `src/components/ReviewPanel.tsx` | 三位 Reviewer 的分数与按 severity 分组的反馈。 |
| `src/components/RevisionPlanPanel.tsx` | Optimizer 输出的结构化 Revision Plan。 |
| `src/components/VersionDiff.tsx` | 版本对比的「阅读对比」与「源码」两种视图。 |
| `src/components/OutcomePanel.tsx` | 终态与失败展示；未达成目标、最佳版本和失败版本指名。 |
| `src/components/AgentTrace.tsx` | 按 sequence 显示安全时间线与 per-node timing，并暴露不含内容的 sequence 测试标记。 |
| `src/components/PRDViewer.tsx` | 安全 GFM（含表格、`skipHtml`）、流式标识、分数摘要和 Markdown 下载入口。 |
| `src/components/MermaidBlock.tsx` | Mermaid 类型白名单、懒加载、strict 安全模式与解析失败降级为源码。 |
| `src/components/RadarScoreChart.tsx` | 多版本 Recharts 雷达图及可访问文本分数表。 |
| `src/components/WorkflowDiagram.tsx` | 本地静态节点拓扑与运行状态高亮（不使用 Mermaid）。 |
| `src/components/TelemetryPanel.tsx` | 原样显示后端轮次、耗时、Token、估算费用、per-node timing 和 Mock 状态。 |
| `src/hooks/useAgentRun.ts` | URL 身份、快照优先恢复、EventSource 生命周期和 REST 控制协调。 |
| `src/styles/global.css` | Tailwind 组件类、响应式页面、Markdown、图形和焦点/减弱动画样式。 |
| `src/lib/config.ts` | 校验并规范化唯一公开 API Base URL，缺失时回退本地 FastAPI。 |
| `src/lib/api.ts` | 类型化 REST Client、正确绑定的浏览器 fetch、事件 URL 及统一网络/HTTP/契约错误。 |
| `src/lib/runReducer.ts` | sequence 幂等、attempt 隔离、快照/事件投影、版本固定选择和终态锁定。 |
| `src/lib/contracts.ts` | JSON 契约的最小运行时解析、枚举守卫和反馈 severity 归一化。 |
| `src/lib/diff.ts` | 两个版本源码的行级差异计算。 |
| `src/lib/readingDiff.ts` | 面向阅读的段落/章节级差异计算。 |
| `src/lib/outcomeSummary.ts` | 由快照推导终态摘要：达标情况、阻塞反馈数和最佳版本。 |
| `src/lib/failureNotice.ts` | 由失败快照推导提示文案，指名失败版本并保留已有版本。 |
| `src/lib/nodeTimings.ts` | Per-node timing 的容错解析与展示归一化。 |
| `src/lib/errorMessages.ts` | 错误码到用户文案的映射，不透出原始 Provider 响应。 |
| `src/lib/trace.ts` | 将允许的结构化事件映射为 Trace 文案，忽略未知敏感 payload。 |
| `src/lib/download.ts` | 创建原始 UTF-8 Markdown Blob、确定性文件名并回收对象 URL。 |
| `src/lib/types.ts` | 与后端契约对应的 TypeScript 类型、枚举联合与终态工具。 |
| `src/lib/contracts.test.ts` | 用版本化 Fixture 检查前端契约及全部终态/事件。 |
| `src/lib/smoke.test.ts` | 证明 Vitest 可真实发现并执行测试。 |
| `src/lib/api.test.ts` | 默认/自定义配置及 REST 成功、错误、网络和非法响应测试。 |
| `src/lib/runReducer.test.ts` | 顺序、终态、attempt/reset、评审、版本选择和完全重置测试。 |
| `src/lib/runFailures.test.ts` | 失败提示的版本指名与已有版本保留测试。 |
| `src/lib/outcomeSummary.test.ts` | 质量门两个条件、最佳版本和 severity 计数推导测试。 |
| `src/lib/diff.test.ts` | 源码与阅读两种差异计算测试。 |
| `src/lib/helpers.test.ts` | Markdown Blob/文件名/URL 回收和 Trace 敏感字段过滤测试。 |
| `src/hooks/useAgentRun.test.tsx` | URL 恢复、三次错误校准、终态、New Run、未知 Run 和卸载测试。 |
| `src/components/components.test.tsx` | 表单、控制、Markdown 安全、图表降级和遥测测试。 |
| `src/components/mermaid.test.tsx` | Mermaid 白名单、懒加载、安全选项和解析失败降级测试。 |
| `src/components/panels.test.tsx` | 评审、Revision Plan、终态面板和版本轨测试。 |
| `src/components/versionDiff.test.tsx` | 版本对比两种视图的切换与内容测试。 |
| `src/components/AgentDashboard.test.tsx` | 空、创建、运行、暂停请求、暂停、完成和失败主状态测试。 |
| `src/components/ConversationSidebar.tsx` | SQLite 对话摘要列表、新建对话和历史 Run 切换入口。 |
| `src/components/ConversationSidebar.test.tsx` | 对话摘要、得分显示和选择行为测试。 |
| `src/test/setup.ts` | Testing Library 清理和 jsdom 的 ResizeObserver/视口测试替身。 |
| `src/test/fixtures.ts` | 前端单元测试共享的类型正确快照、评审、评分和事件工厂。 |
| `public/.gitkeep` | 保留当前为空的静态资源目录。 |

### 后端源码与测试

| 文件 | 作用 |
| --- | --- |
| `backend/__init__.py` | 声明后端 Python 包。 |
| `backend/requirements.txt` | 精确锁定后端运行依赖。 |
| `backend/requirements-dev.txt` | 在运行依赖之上锁定测试、Lint 和类型工具。 |
| `backend/config.py` | Pydantic Settings、环境解析、边界校验、密钥、输出上限和价格语义。 |
| `backend/schemas.py` | 请求/响应、反馈 severity、评审、修订来源、版本、遥测、per-node timing、Run 快照和事件模型。 |
| `backend/state_machine.py` | 唯一的 Run 合法迁移表和终态规则。 |
| `backend/errors.py` | 业务、容量、事件过期、生成完整性和 Provider 错误的安全类型体系。 |
| `backend/prompts.py` | Generator、三 Reviewer 和 Optimizer 的隔离系统 Prompt，含文档编排规则与 completion sentinel 要求。 |
| `backend/prd_document.py` | completion sentinel 剥离与 `finish_reason` 判定，输出 complete/truncated/interrupted/filtered 结论。 |
| `backend/language.py` | 统一输出语言约束。 |
| `backend/telemetry.py` | Token 确定性累加、per-node timing 记录和已知/未知/Mock 费用计算。 |
| `backend/run_store.py` | 内存/SQLite 快照 Store、独立 Run 锁、历史列表、恢复和终态 TTL。 |
| `backend/event_store.py` | SQLite 事件日志、递增序号、有界热回放、多订阅者通知和 Heartbeat。 |
| `backend/run_manager.py` | API/Graph 协调层；原子提交、任务引用、控制信号、并发和关闭。 |
| `backend/workflow.py` | LangGraph 循环、节点执行、并行评审、确定性聚合与质量门、生成完整性重试、暂停取消。 |
| `backend/providers/__init__.py` | 导出 Provider 公共接口与 Mock 实现。 |
| `backend/providers/base.py` | 流式/结构化 Provider 抽象及统一结果信封。 |
| `backend/providers/mock.py` | 1–5 轮确定性 Generator、Reviewer、Optimizer 和模拟 Usage。 |
| `backend/providers/compatible.py` | DeepSeek/GLM 流式与 JSON Object 兼容调用、Usage、取消和安全错误映射。 |
| `backend/providers/scenario.py` | 仅测试环境可用的非法结构、超时和 Reviewer 失败注入。 |
| `backend/observability.py` | 输出白名单字段的结构化 JSON 日志。 |
| `backend/main.py` | 应用工厂、生命周期、CORS、统一异常、REST/SSE 路由和 OpenAPI。 |
| `backend/tests/__init__.py` | 声明后端测试包。 |
| `backend/tests/helpers.py` | 创建隔离 Settings、Store、Provider 和 LangGraph Manager 的测试工厂。 |
| `backend/tests/test_api.py` | 创建/快照/控制、错误、CORS、SSE 回放和恢复游标测试。 |
| `backend/tests/test_config.py` | 配置默认值、环境覆盖、边界、价格和密钥测试。 |
| `backend/tests/test_schemas.py` | 领域模型、聚合、边界和独立默认集合测试。 |
| `backend/tests/test_state_machine.py` | 正常、暂停、取消、非法和终态迁移测试。 |
| `backend/tests/test_contracts.py` | Pydantic Fixture 和 OpenAPI 组件契约测试。 |
| `backend/tests/test_dependencies.py` | 所有直接运行依赖的导入冒烟测试。 |
| `backend/tests/test_event_store.py` | 并发序号、缓冲淘汰、回放、订阅和 Heartbeat 测试。 |
| `backend/tests/test_mock_provider.py` | 1–5 轮稳定输出、评分趋势、去重来源和 Prompt 边界测试。 |
| `backend/tests/test_compatible_provider.py` | DeepSeek/GLM 请求差异、流式、Usage、错误、结构化和修复契约测试。 |
| `backend/tests/test_observability_security.py` | 注入/HTML/脚本/伪指令、日志和安全错误泄漏测试。 |
| `backend/tests/test_performance_resources.py` | 四 Run 容量、事件上限、TTL 引用清理和长 PRD 完整性测试。 |
| `backend/tests/test_provider_retries.py` | 传输重试、单次格式修复、修复失败和认证失败测试。 |
| `backend/tests/test_run_manager.py` | 原子提交、唯一任务、并发槽、关闭回收和订阅唤醒测试。 |
| `backend/tests/test_run_store.py` | 深拷贝、容量和终态 TTL 测试。 |
| `backend/tests/test_generation_reliability.py` | `finish_reason`、completion sentinel、三种失败原因和失败保留测试。 |
| `backend/tests/test_node_timings.py` | Per-node timing 记录（含失败尝试）与快照往返测试。 |
| `backend/tests/test_prd_delta_persistence.py` | `prd_delta` 仅存在于实时路径、不进入持久化测试。 |
| `backend/tests/test_smoke.py` | 使用 HTTPX ASGI Transport 的异步健康接口测试。 |
| `backend/tests/test_telemetry.py` | Token 累加、价格舍入、未知价格和 Mock 费用测试。 |
| `backend/tests/test_workflow.py` | 多轮/最大轮次、并行、质量门两个条件、severity 计数、暂停恢复、取消、重试和超时测试。 |

### 端到端测试

| 文件 | 作用 |
| --- | --- |
| `e2e/helpers.ts` | Podcast 输入、场景切换、快照、事件和终态轮询公共工具。 |
| `e2e/fixtures/longPrd.ts` | 长 PRD 与图表内容的确定性 E2E 输入。 |
| `e2e/happy-path.spec.ts` | 两轮评分、三 Reviewer、修订、图表、事件顺序和下载验收。 |
| `e2e/controls.spec.ts` | 安全暂停/恢复要求及生成、评审阶段取消验收。 |
| `e2e/layout.spec.ts` | 版本轨与五页签布局、Mermaid 渲染与降级、per-node timing 展示验收。 |
| `e2e/recovery.spec.ts` | 三次 SSE 失败快照降级及客户端断开后的无重复恢复。 |
| `e2e/failures.spec.ts` | 结构、超时、Reviewer、最大轮次、生成不完整和并发上限故障验收。 |

### 版本化契约与 Memory Bank

| 文件 | 作用 |
| --- | --- |
| `contracts/v1/create_run_request.json` | 创建 Run 的有效请求样本。 |
| `contracts/v1/run_snapshot.json` | 包含 Reviewer、节点 Usage、费用状态和耗时的初始快照。 |
| `contracts/v1/terminal_snapshots.json` | 四种终态的完整契约样本集。 |
| `contracts/v1/run_event.json` | 带结构化 payload 的代表性事件样本。 |
| `contracts/v1/run_events.json` | 全部 17 种业务事件类型样本集。 |
| `contracts/v1/error_response.json` | 统一错误信封样本。 |
| `memory-bank/design-document.md` | 详细系统设计、协议和交互行为。 |
| `memory-bank/tech-stack.md` | 技术选型、依赖边界与运行约束。 |
| `memory-bank/implementation-plan.md` | 小步实施和逐步验证指令。 |
| `memory-bank/progress.md` | 当前能力、验证结果、已知限制。 |
| `memory-bank/architecture.md` | 本文件；维护稳定边界、决策和文件职责。 |

## 9. SQLite 对话持久化

SQLite 是历史事实来源，进程内对象是活动运行的热缓存与协调层。每次
`RunManager.commit()` 或状态迁移都先追加业务事件，再持久化包含最新 sequence
的快照；如果两次写入之间进程退出，重启后的 SSE 可以从较旧快照 sequence
补发事件。`SQLiteEventStore` 保留全部业务事件，同时只把最近
`EVENT_BUFFER_SIZE` 条加载为热回放缓冲。

活动工作流不做进程级 checkpoint。重启时非终态快照统一转为
`RUN_INTERRUPTED`，历史 PRD、评分和事件仍可浏览。SQLite 不改变单 Worker
约束，因为 Task、Run 锁、取消/恢复信号和订阅 Condition 仍在进程内。

## 10. 当前限制

- 单 Uvicorn Worker：Task 句柄、Run 锁、Pause/Resume/Cancel 信号和 SSE 订阅
  Condition 都在进程内，不支持水平扩展。
- 持久化只有本地 SQLite；活动工作流不做 checkpoint，启动时发现的非终态 Run 标记为
  `RUN_INTERRUPTED` 且不自动续跑。
- 终态任务不能继续优化，需要继续请新建任务。
- 不支持手工编辑 PRD 正文；用户通过创意描述、质量设置和暂停时的补充要求施加影响。
- 导出只支持 Markdown，没有 PDF / DOCX。
- 真实 Provider 的质量与延迟是所配置模型服务的属性，只有 Mock 模式具有确定性。
- 锁定的 Astro 4 / Mermaid 10 依赖树存在已公开上游告警，公网部署前必须先完成这些
  Major 升级。

## 11. 维护规则

每完成实施步骤都更新 `progress.md`。只有系统边界、协议、状态机、事实来源或
模块职责发生变化时才更新本文件；不要把逐次测试日志复制到架构记录中。
