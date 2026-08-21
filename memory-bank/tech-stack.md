# Agentic PRD Architect 技术栈说明

> 文档版本：1.0  
> 文档状态：技术选型基线  
> 需求来源：`PRD.md`、`memory-bank/design-document.md`  
> 适用范围：第一版本地 Showcase 实现

---

## 1. 文档目的

本文档定义 Agentic PRD Architect 第一版的技术栈、依赖边界、版本策略、开发工具和运行约束，作为项目初始化、依赖安装、代码评审和环境搭建的统一依据。

本文档不重复描述完整业务流程。业务状态机、API 数据结构和交互细节以 `memory-bank/design-document.md` 为准。除非特别说明，本文档中的文件路径均以仓库根目录为基准。

### 1.1 决策优先级

当文档之间出现差异时，按以下原则执行：

1. 产品目标和必须交付能力以 `PRD.md` 为准。
2. API、状态机和工程实现方式以 `memory-bank/design-document.md` 为准。
3. 具体框架、依赖和工具选型以本文档为准。
4. Patch 版本以项目初始化后提交的 lockfile 和 Python 依赖锁定文件为准。

---

## 2. 技术选型原则

第一版技术选型遵循：

- **展示优先**：突出多 Agent 并行评审、实时过程和版本演进。
- **前后端类型清晰**：TypeScript 与 Pydantic 分别约束浏览器和服务端数据。
- **异步优先**：LLM 调用、并行 Reviewer、SSE 和任务控制均使用异步模型。
- **协议标准化**：控制请求使用 REST，实时事件使用标准 SSE。
- **依赖克制**：不引入当前版本不需要的数据库、队列和全局状态框架。
- **可替换边界**：模型 Provider、RunStore 和 EventStore 通过接口隔离。
- **可重复演示**：Mock LLM 是正式运行模式，不是临时测试代码。
- **默认安全**：不展示隐藏思维链，不执行不可信 HTML，不把密钥发送到前端。

---

## 3. 技术栈总览

| 层级 | 技术 | 项目用途 | 第一版状态 |
|---|---|---|---|
| 前端页面框架 | Astro 4.x | 页面壳、路由、SSR 模式、React Island 承载 | 必选 |
| 交互框架 | React 18 | Dashboard、任务控制、流式状态和可视化组件 | 必选 |
| 前端语言 | TypeScript | 组件、事件协议和状态 Reducer 类型 | 必选 |
| 样式 | Tailwind CSS | 响应式布局、主题和组件样式 | 必选 |
| 图标 | Lucide React | 状态、按钮和提示图标 | 必选 |
| 工作流图 | Mermaid.js | Agent 状态机和活动节点高亮 | 必选 |
| 评分图表 | Recharts | 多版本 Tech/UX/Biz 雷达图 | 必选 |
| Markdown | react-markdown + remark-gfm | 安全渲染 PRD Markdown | 必选 |
| 前端状态 | React `useReducer` + 自定义 Hook | SSE 事件归并和任务控制 | 必选 |
| 后端语言 | Python 3.11+ | API、工作流、LLM 和任务管理 | 必选 |
| Web 框架 | FastAPI | REST API、校验、CORS 和生命周期 | 必选 |
| ASGI Server | Uvicorn | 本地后端服务 | 必选 |
| Agent 编排 | LangGraph | Generator/Reviewer/Optimizer 状态机 | 必选 |
| 数据校验 | Pydantic v2 | 请求、状态、结构化模型输出 | 必选 |
| 配置 | pydantic-settings | `.env` 与环境变量校验 | 必选 |
| LLM SDK | OpenAI Python SDK | DeepSeek/GLM OpenAI 兼容协议客户端 | 必选 |
| SSE | sse-starlette | 标准 EventSourceResponse | 必选 |
| 本地持久化 | Python `sqlite3` + SQLite WAL | Run 快照、对话列表、可回放事件 | 必选 |
| 运行时协调 | Python 内存 + asyncio primitives | Run 锁、SSE Condition、控制信号 | 必选 |
| 后端测试 | pytest + pytest-asyncio + HTTPX | 单元、异步、API 和 SSE 测试 | 必选 |
| 前端测试 | Vitest + Testing Library | Reducer、Hook 和组件测试 | 建议 |
| E2E | Playwright | Mock 模式完整流程验收 | 建议 |

---

## 4. 前端技术栈

### 4.1 Astro 4.x

Astro 作为页面和构建框架，负责：

- `src/pages/index.astro` 页面入口。
- `src/layouts/Layout.astro` HTML 外壳、Meta 和全局样式。
- SSR 模式配置。
- 加载 React Dashboard Island。
- 开发服务器和生产构建。

配置基线：

```javascript
// astro.config.mjs
export default defineConfig({
  output: "server",
  integrations: [react(), tailwind()],
  adapter: node({ mode: "standalone" }),
});
```

如果项目仅运行开发服务器，可以暂时不使用生产 Adapter；正式执行 SSR build 时使用 `@astrojs/node`。

### 4.2 React 18

React 负责全部高交互区域：

- 创建 PRD 任务。
- 订阅和消费 SSE。
- Pause、Resume、Cancel。
- PRD 流式内容和版本历史。
- Reviewer 状态。
- Mermaid 和 Recharts。
- 下载 Markdown。

Dashboard 使用：

```astro
<AgentDashboard client:only="react" />
```

原因：

- Mermaid 依赖浏览器 DOM。
- Recharts 依赖浏览器布局。
- EventSource 只存在于浏览器环境。
- 避免 Astro SSR 阶段出现 `window is not defined`。

### 4.3 TypeScript

所有 `.tsx`、Hook、API Client 和 Reducer 使用 TypeScript，并启用严格模式。

最低要求：

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true
  }
}
```

核心类型包括：

- `RunSnapshot`
- `RunStatus`
- `NodeStatus`
- `RunEvent<T>`
- `PRDVersion`
- `RoleReview`
- `EvaluationResult`
- `RevisionPlan`

第一版手工维护与 Pydantic 一致的 TypeScript 类型。后续可以从 OpenAPI 自动生成 Client 和类型，但不作为首版依赖。

### 4.4 Tailwind CSS

Tailwind 用于：

- 双列与移动端单列布局。
- 状态色和可访问的焦点样式。
- PRD 阅读区排版。
- Skeleton、Badge、Tabs 和控制按钮。
- 深色界面或展示型视觉主题。

不引入额外大型 UI 组件库，避免视觉同质化和无用依赖。常用组件在项目内以轻量 React 组件实现。

如果需要 Markdown Typography，可选择加入 `@tailwindcss/typography`；该依赖是推荐项，不是必选项。

### 4.5 Lucide React

`lucide-react` 用于：

- Generate、Pause、Resume、Cancel、Download。
- Agent 状态和连接状态。
- 成功、警告和错误反馈。

图标必须配合文字或 `aria-label`，不能作为唯一状态信息。

### 4.6 Mermaid.js

Mermaid 用于渲染 PRD 正文里模型写出的 ` ```mermaid ` 代码块。

支持的图表类型是一份白名单：`flowchart`（含 Mermaid 旧别名 `graph`）、
`sequenceDiagram`、`stateDiagram-v2`、`mindmap`、`erDiagram`。白名单之外的类型
不进入渲染路径，直接按代码块显示源码。

使用约束：

- `await import("mermaid")` 放在 effect 内：不含图表的 PRD 永远不会下载这个库。
- `startOnLoad: false`，由组件显式调用 `mermaid.render`。
- `securityLevel: "strict"` 且 `htmlLabels: false`：标签里的 HTML 是文本，不是标记。
  模型输出不得被当作 HTML 或 JS 执行。
- 每次渲染使用唯一 DOM ID。
- 先 `parse` 再 `render`：定义无法解析时降级显示图表源码，而不是让 Mermaid 往文档里
  插入一张红色 "Syntax error" 图，也不能影响 PRD 其余部分的渲染。

### 4.7 Recharts

Recharts（`RadarScoreChart`）用于展示版本评分：

- 三个轴：Technical、UX、Business。
- 每个 PRD 版本一条数据系列。
- 固定量程 0–100。

图表只是可视化，具体分值还必须以文本形式展示，保证移动端和无障碍可读性。

### 4.8 Markdown 渲染

使用：

```text
react-markdown
remark-gfm
```

安全规则：

- 不启用 `rehype-raw`；`skipHtml` 打开。
- 不渲染模型输出中的原始 HTML。
- `remark-gfm` 提供表格支持，PRD 中的表格按 GFM 渲染。
- 链接使用安全属性。
- 代码块作为文本显示，不执行；`mermaid` 块交由 §4.6 的白名单路径处理。
- 下载使用原始 UTF-8 Markdown，而不是渲染后的 HTML；completion sentinel 在展示与
  下载前都已剥离。

### 4.9 前端状态管理

第一版使用：

- `useReducer`：统一归并快照和 SSE 事件。
- `useEffect`：SSE 生命周期。
- 自定义 `useAgentRun` Hook：封装连接、控制和重连。

不引入 Redux、Zustand、MobX 或其他全局状态库。当前页面只有一个主要运行上下文，React 内置状态足够。

Reducer 需要：

- 依据事件 `sequence` 去重。
- 忽略旧事件。
- 拼接 `prd_delta`。
- 用 `prd_generated` 完整内容进行校准。
- 独立更新三个 Reviewer 状态。
- 结束后拒绝非终态回退。

### 4.10 前端请求方式

- REST 请求使用原生 `fetch`。
- SSE 使用浏览器原生 `EventSource`。
- 不引入 Axios。
- EventSource 自动重连依赖 SSE `id` 和 `Last-Event-ID`。
- 页面刷新恢复使用 `GET /api/runs/{run_id}` 快照和 `after_sequence` 查询参数。

---

## 5. 后端技术栈

### 5.1 Python 3.11+

项目最低运行版本为 Python 3.11。

使用的语言能力：

- 原生 `async` / `await`。
- `asyncio.TaskGroup` 或等价并发机制。
- `typing.Protocol` 定义 Provider 和 Store 接口。
- `StrEnum`、`Literal`、现代联合类型。

开发环境应锁定同一个 Python minor 版本，避免本地和 CI 行为差异。

### 5.2 FastAPI

FastAPI 负责：

- 创建任务和控制接口。
- 任务快照查询。
- SSE 订阅入口。
- Pydantic 请求/响应校验。
- CORS。
- 全局异常转换。
- 应用启动与关闭生命周期。
- OpenAPI 文档。

接口基线：

```text
POST /api/runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/events
POST /api/runs/{run_id}/pause
POST /api/runs/{run_id}/resume
POST /api/runs/{run_id}/cancel
GET  /api/health
```

### 5.3 Uvicorn

Uvicorn 作为 ASGI Server。

第一版运行限制：

- 使用单 Worker。
- 不允许启动多个独立 Worker 共享内存任务。
- 开发模式可以启用 reload。
- 生产式本地运行关闭 reload。

示例：

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 5.4 Pydantic v2

Pydantic 用于：

- API 请求和响应。
- LangGraph 状态相关模型。
- Reviewer 结构化输出。
- Revision Plan。
- 配置校验。
- 事件 Payload。

规则：

- 集合字段统一使用 `Field(default_factory=...)`。
- 外部输入使用严格长度和数值边界。
- `overall_score` 使用 `float`，由服务端计算。
- Enum/`Literal` 约束状态和 Reviewer 角色。
- 对外响应不得直接暴露内部异常对象。

### 5.5 pydantic-settings

使用 `BaseSettings` 加载：

- 应用 Host 和 Port。
- CORS Origin。
- Mock 模式。
- LLM Provider、模型和密钥。
- 默认阈值和轮次。
- 并发、TTL、SSE Buffer。
- 节点超时和任务总超时。

`.env` 只用于本地开发，必须提供 `.env.example`，真实 `.env` 不提交版本库。

### 5.6 LangGraph

LangGraph 负责 Agentic Loop 的节点和条件路由：

- `generate_draft`
- `review_tech`
- `review_ux`
- `review_biz`
- `aggregate_reviews`
- `quality_gate`
- `wait_for_resume`
- `optimize_plan`
- `complete_run`

三个 Reviewer 必须并行执行。Aggregator 和 Quality Gate 使用确定性 Python 代码，不调用 LLM。

LangGraph 只负责业务工作流，不负责：

- HTTP 生命周期。
- SSE 连接管理。
- 任务持久化。
- CORS。
- 浏览器控制。

这些能力由 FastAPI、RunManager 和 Store 层负责。

### 5.7 OpenAI Python SDK 与兼容协议

OpenAI SDK 在第一版中作为异步 OpenAI 兼容协议客户端，用于接入 DeepSeek 和 GLM：

- Generator Markdown 流式输出。
- Reviewer Structured Output。
- Optimizer Structured Output。
- Token Usage 获取。
- 每次调用的 `finish_reason`。

`finish_reason` 不是可选的诊断信息，而是判定生成是否完整的两个独立信号之一（另一个
是模型写在正文最后一行的 completion sentinel，见 design-document §6.8）。因此适配器
必须把它随文本一起返回，而不是只返回 content。`max_tokens` 由
`LLM_MAX_OUTPUT_TOKENS` 显式发送，使 `finish_reason="length"` 报告的是一个已配置的
上限。

具体模型名称不写死在业务代码中：

```env
LLM_PROVIDER=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

GLM 使用同一适配器和 `https://open.bigmodel.cn/api/paas/v4`，模型由 `GLM_MODEL` 配置。第一版不直接调用 OpenAI，也不宣称支持未实现、未测试的 Anthropic 等其他 Provider。

### 5.8 sse-starlette

使用 `EventSourceResponse` 输出标准 SSE：

```text
id: 17
event: review_completed
data: {...}

```

后端需要同时控制：

- 事件 ID。
- Event name。
- JSON data。
- Heartbeat。
- 连接断开检测。
- 任务结束后的正常关闭。

### 5.9 asyncio

Python 标准库 `asyncio` 用于：

- 三个 Reviewer 并行调用。
- 后台任务。
- 每个 Run 的锁。
- Pause/Resume 信号。
- Cancel 信号。
- EventStore 条件变量。
- 超时控制。

不引入 Celery、RQ 或外部消息队列。

---

## 6. LLM Provider 与 Mock 技术

### 6.1 Provider 抽象

统一定义：

```python
class LLMProvider(Protocol):
    async def generate_markdown(...) -> LLMTextResult:
        ...

    async def generate_structured(
        ...,
        schema: type[T],
    ) -> LLMStructuredResult[T]:
        ...
```

第一版实现：

| Provider | 用途 | 是否访问网络 |
|---|---|---|
| `OpenAICompatibleLLMProvider` | DeepSeek/GLM 真实生成、评审和优化 | 是 |
| `MockLLMProvider` | 演示、开发和自动测试 | 否 |
| `ScenarioMockLLMProvider` | E2E 确定性故障注入，仅测试环境启用 | 否 |

### 6.2 Mock LLM

Mock Provider 使用：

- 固定测试数据。
- 异步生成器模拟 PRD delta。
- 可配置延迟。
- 可注入超时、非法 JSON 和节点失败。
- 测试模式下关闭 sleep。

Mock 模式必须走与真实 Provider 相同的 LangGraph、RunManager、EventStore 和 SSE 路径，不能在 API 层直接返回假结果。

### 6.3 Structured Output

Reviewer 和 Optimizer 优先使用 Provider 原生结构化输出能力，并使用 Pydantic 二次校验。

失败策略：

1. 原始结构化请求。
2. Pydantic 校验。
3. 一次格式修复请求。
4. 再次校验。
5. 仍失败则节点失败。

不使用宽松正则猜测评分。

### 6.4 思维过程处理

前端可以展示：

- 当前节点。
- Reviewer 最终反馈。
- 评分。
- 修订摘要。
- 结构化运行日志。

前端不展示：

- 模型隐藏思维链。
- Provider 原始内部推理字段。
- 系统 Prompt。
- API Key 或原始异常敏感信息。

---

## 7. 通信与数据协议

### 7.1 REST

REST 用于短生命周期操作：

- 创建 Run。
- 获取快照。
- Pause。
- Resume。
- Cancel。
- Health Check。

请求和响应统一使用 UTF-8 JSON。

### 7.2 Server-Sent Events

SSE 用于服务端到浏览器的单向实时事件：

- 节点开始/完成。
- PRD delta。
- Reviewer 结果。
- 聚合分数。
- Revision Plan。
- 遥测。
- 暂停、恢复、结束和错误。

选择 SSE 而不是 WebSocket 的原因：

- 本项目实时数据主要是服务端单向推送。
- 控制操作已经通过 REST 完成。
- 原生 EventSource 支持自动重连。
- 协议和服务端实现更简单。

### 7.3 SSE 可靠性

- 每条事件带递增 `id`。
- EventStore 保存有界事件缓冲。
- 同一连接使用 `Last-Event-ID` 自动补发。
- 页面刷新使用快照的 `latest_event_sequence`。
- `prd_generated` 完整事件校准之前的 delta。
- 每 15 秒发送 heartbeat。

### 7.4 CORS 与同源策略

开发环境允许：

```text
http://localhost:4321
http://127.0.0.1:4321
```

推荐开发端口：

| 服务 | 地址 |
|---|---|
| Astro | `http://localhost:4321` |
| FastAPI | `http://127.0.0.1:8000` |

生产式部署可使用反向代理将 `/api` 转发给 FastAPI，从而保持同源；反向代理不属于第一版必须交付项。

---

## 8. 状态与存储技术

### 8.1 前端状态

使用 React 内存状态：

- 当前 Run 快照。
- SQLite 对话摘要列表。
- 连接状态。
- 最后事件序号。
- 当前选中的 PRD 版本。
- 正在生成的 Markdown delta。
- 暂停弹窗输入。

页面刷新后从 FastAPI 快照恢复。

### 8.2 后端 RunStore

本地运行使用 `SQLiteRunStore`：

- SQLite JSON 快照保存完整 Run、版本、评分和遥测。
- `dict[UUID, PRDRunState]` 作为进程内热缓存。
- 每个任务独立 `asyncio.Lock`。
- 完成任务按 TTL 清理。
- 服务重启后恢复历史终态；中断任务标记为 `RUN_INTERRUPTED`。

测试可使用 `InMemoryRunStore`。Store 边界仍允许未来替换为 PostgreSQL。

### 8.3 EventStore

使用 SQLite 事件表和进程内有界热缓冲：

- 每个 Run 独立事件序列。
- 所有业务事件写入 SQLite。
- 默认最多 1000 条事件。
- 使用 `asyncio.Condition` 通知 SSE 订阅者。
- 支持跨重启按 sequence 补发。
- 完成后保留到 Run TTL 到期。

### 8.4 SQLite 运行约束

使用 Python 标准库 `sqlite3`，不引入 ORM。数据库默认位于
`data/agentic-prd.sqlite3`，启用 WAL 和 5 秒 busy timeout。SQLite 只负责
持久化；活动 Task、Pause/Resume/Cancel 信号和 SSE Condition 仍属于单进程，
因此不能直接增加 Uvicorn Worker。

---

## 9. 可观测性与日志

### 9.1 应用日志

使用 Python 标准 `logging`，输出结构化字段：

- `request_id`
- `run_id`
- `iteration`
- `node`
- `status`
- `duration_ms`
- `retry_count`
- `provider`
- `model`
- Token Usage

禁止记录：

- API Key。
- 完整系统 Prompt。
- 用户完整 PRD 内容。
- Provider 原始敏感响应。

第一版不强制引入第三方日志库；如果 JSON 日志实现明显简化，可选择 `structlog`，但它不是基础依赖。

### 9.2 前端遥测展示

展示：

- 当前耗时。
- 总 Token。
- 输入/输出 Token。
- Estimated Cost。
- 当前轮次。
- 三个 Reviewer 状态。
- Per-node timing：每次节点调用的节点名、版本、attempt、墙钟秒数与 Token。

Per-node timing 也记录失败的尝试——一次消耗了 Token 却产出不可用文档的 Generator
尝试必须出现在列表里，否则记录时间无法与总耗时对上。`node_timings` 不是快照的必需
字段：早于它的历史快照没有这一项，遥测列表读不懂的数据一律丢弃，不能因此让一份已
完成的 PRD 无法渲染。

模型价格通过后端配置维护，前端不自行计算。

### 9.3 暂不引入

第一版不引入：

- OpenTelemetry Collector。
- Prometheus。
- Grafana。
- Sentry。

代码应保留统一日志和事件出口，方便后续接入。

---

## 10. 测试技术栈

### 10.1 后端

| 工具 | 用途 |
|---|---|
| pytest | 单元和集成测试框架 |
| pytest-asyncio | 异步节点、Store 和 RunManager 测试 |
| HTTPX | FastAPI ASGI API 测试 |
| MockLLMProvider | 确定性的 Agent 流程测试 |

重点覆盖：

- LangGraph 路由。
- Reviewer 并行。
- 分数聚合与质量门（`score >= target` 与 `must_fix == 0` 两个条件各自成立才通过）。
- 反馈 severity 计数按需推导，不作为总数持久化。
- 最大轮次。
- Pause/Resume/Cancel。
- Structured Output 重试。
- 生成完整性判定：`finish_reason` 与 completion sentinel 两个信号，及三种失败原因对应
  的错误码。
- 后续版本生成失败时保留已提交的版本。
- Per-node timing 记录（含失败尝试）。
- SSE 格式、事件补发和快照重校准。
- SQLite 快照 / 事件的 JSON 往返。

### 10.2 前端

| 工具 | 用途 |
|---|---|
| Vitest | TypeScript 单元测试 |
| React Testing Library | 组件和 Hook 行为 |
| user-event | 用户交互 |
| Mock EventSource | SSE 重连与事件测试 |

重点覆盖：

- Reducer 去重和状态迁移。
- PRD delta 拼接与流重置。
- 版本选择、版本对比（阅读 / 源码两种视图）。
- 控制按钮状态。
- 终态展示：质量门未通过的原因、最佳版本、severity 计数。
- 失败提示指名失败的版本，而不是宣称整个任务失败。
- Markdown 安全渲染（GFM 表格、`skipHtml`、Mermaid 白名单与降级）。

### 10.3 E2E

使用 Playwright 启动前后端（独立端口 8011/4331），并在 Mock 模式下验证：

- Podcast 微订阅案例从 v1 迭代到 v2。
- 三个 Reviewer 并行可见。
- 雷达图更新。
- 暂停、补充要求和恢复。
- 下载最终 Markdown。
- SSE 断线后的恢复。
- 版本轨 + 五个工作区页签的布局。
- Mermaid 渲染与解析失败降级。
- 运行记录中的 per-node timing。
- 仅测试环境启用的故障注入路径。

---

## 11. 代码质量工具

### 11.1 Python

推荐：

| 工具 | 用途 |
|---|---|
| Ruff | Lint、import 排序和格式检查 |
| mypy | Provider、Store 和状态类型检查 |

建议命令：

```bash
./.venv/bin/ruff check backend
./.venv/bin/ruff format --check backend
./.venv/bin/mypy backend
./.venv/bin/python -m pytest -p no:cacheprovider
```

### 11.2 TypeScript

推荐：

| 工具 | 用途 |
|---|---|
| ESLint | React、Hooks 和 TypeScript 规则 |
| Prettier | 格式化 TS/TSX/Astro/Markdown |
| TypeScript Compiler | 严格类型检查 |

建议命令：

```bash
npm run lint
npm run typecheck
npm run test:run
npm run build
npm run test:e2e
```

`npm run test` 是 watch 模式，单次执行用 `test:run`。

格式化工具不应自动重写模型生成的 PRD 内容。

---

## 12. 包管理与版本策略

### 12.1 前端包管理

使用 npm，与 PRD 中的 `npx astro add ...` 路径保持一致。

要求：

- 提交 `package-lock.json`。
- CI 使用 `npm ci`。
- 不混用 npm、pnpm 和 Yarn lockfile。
- Astro 保持 4.x、React 保持 18.x，除非先更新需求和兼容性验证。

### 12.2 Python 包管理

第一版使用标准虚拟环境、pip 和 `requirements.txt`：

```text
backend/requirements.txt
backend/requirements-dev.txt
```

要求：

- 本地开发使用独立 `.venv`。
- 提交确定的依赖版本。
- 运行依赖和开发依赖分开。
- 不把全局 Python 环境作为项目依赖来源。

如果后续需要发布 Python Package 或更严格的锁定，可以迁移到 `pyproject.toml`，但不作为第一版前置条件。

### 12.3 版本兼容策略

- PRD 指定的 Major 版本优先，不在实现过程中自动升级 Major。
- Patch/Minor 版本在初始化时选择兼容组合并锁定。
- Node.js 使用与 Astro 4.x 兼容且仍受支持的 LTS 版本，并通过 `.nvmrc` 或等价文件固定。
- Python 使用同一个 3.11+ Minor 版本，并在 README 中明确。
- 模型名称和价格属于运行配置，不与代码版本绑定。

---

## 13. 本地开发环境

### 13.1 进程拓扑

```text
Browser
  ├── Astro dev server :4321
  └── FastAPI/Uvicorn  :8000
        ├── LangGraph
        ├── RunManager
        ├── SQLiteRunStore（继承 InMemoryRunStore，热缓存 + SQLite 快照）
        ├── SQLiteEventStore（可回放事件）
        └── Mock/DeepSeek/GLM Provider
```

Uvicorn 必须保持单 Worker：Task 句柄、Run 锁、Pause/Resume/Cancel 信号和 SSE 订阅
Condition 都在进程内。

### 13.2 环境变量

基础配置：

```env
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
FRONTEND_ORIGINS=http://localhost:4321,http://127.0.0.1:4321
PUBLIC_API_BASE_URL=http://127.0.0.1:8000

ENABLE_MOCK_LLM=true
LLM_PROVIDER=deepseek
LLM_REQUEST_TIMEOUT_SECONDS=90
LLM_MAX_OUTPUT_TOKENS=16000
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# GLM provider (currently disabled)
# LLM_PROVIDER=glm
# GLM_API_KEY=
# GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
# GLM_MODEL=glm-5.2

DEFAULT_QUALITY_THRESHOLD=85
DEFAULT_MAX_ITERATIONS=3
MAX_CONCURRENT_RUNS=4
MAX_RETAINED_RUNS=100
RUN_TTL_SECONDS=2592000
EVENT_BUFFER_SIZE=1000
SSE_HEARTBEAT_SECONDS=15
DATABASE_PATH=data/agentic-prd.sqlite3
```

完整键列表见 `.env.example`。`LLM_MAX_OUTPUT_TOKENS` 会作为 `max_tokens` 显式发送，
使 `finish_reason="length"` 指向一个已配置的上限而不是随模型变化的 Provider 默认值。

前端只允许读取公开配置，例如 API Base URL；任何密钥必须只存在于后端环境。

### 13.3 推荐启动方式

后端：

```bash
./.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```bash
npm run dev
```

第一版可以提供根目录启动脚本同时启动两个进程，但脚本不是框架依赖。

---

## 14. 安全技术基线

### 14.1 浏览器侧

- React 默认转义文本。
- `react-markdown` 不启用原始 HTML。
- 不使用 `dangerouslySetInnerHTML` 渲染模型内容。
- EventSource URL 只由可信 API Base URL 和 UUID 构造。
- 下载文件通过 Blob 创建。

### 14.2 API 侧

- Pydantic 校验输入长度和取值范围。
- CORS 使用明确 Origin。
- API Key 只从后端环境读取。
- Provider 错误转换为安全错误码。
- Run 使用 UUID 隔离。
- 限制同时运行任务数。
- 所有 LLM 调用设置超时和有限重试。

### 14.3 Prompt 层

- 系统 Prompt 和用户输入分离。
- 用户内容使用明确边界包裹。
- Reviewer 只输出最终评价，不输出隐藏推理。
- Generator 生成 Markdown，不生成可执行代码。
- Optimizer 只生成 Revision Plan。

---

## 15. 明确不选用的技术

| 技术/方案 | 第一版不使用的原因 |
|---|---|
| WebSocket | 当前主要是服务端单向推送，REST + SSE 更简单 |
| Redux/Zustand | 单页面运行状态可由 Hook + Reducer 管理 |
| Celery/RQ | 本地单进程 Showcase 不需要外部 Worker |
| Redis/PostgreSQL | SQLite 已满足本地持久化，外部服务不属于当前范围 |
| ORM | SQLite 直接使用标准库 `sqlite3` 和 JSON 快照，规模不需要 ORM |
| Docker/Kubernetes | 不属于核心交付要求 |
| 完整 LangChain 包 | LangGraph + Provider SDK 已满足需求 |
| Anthropic SDK | Provider 接口预留，但第一版不要求实现 |
| 原始 Chain-of-Thought 流 | 安全和产品表达上均不应展示 |
| Axios | 原生 fetch 与 EventSource 已满足需求 |
| UI 组件库 | Tailwind + 项目内组件足够，便于定制 Showcase 视觉 |

---

## 16. 依赖清单基线

### 16.1 `package.json` 运行依赖

```text
astro
react
react-dom
@astrojs/react
@astrojs/tailwind
@astrojs/node
tailwindcss
lucide-react
mermaid
recharts
react-markdown
remark-gfm
```

可选：

```text
@tailwindcss/typography
```

开发依赖：

```text
typescript
eslint
prettier
prettier-plugin-astro
vitest
@testing-library/react
@testing-library/user-event
playwright
```

### 16.2 `backend/requirements.txt`

```text
fastapi
uvicorn
langgraph
openai
pydantic
pydantic-settings
sse-starlette
python-dotenv
```

开发依赖：

```text
pytest
pytest-asyncio
httpx
ruff
mypy
```

是否需要单独安装 LangGraph 所依赖的底层包，由锁定后的依赖解析结果决定，不在 requirements 中重复声明传递依赖。

---

## 17. 技术栈与源码目录映射

| 源码路径 | 主要技术 |
|---|---|
| `src/pages/index.astro` | Astro |
| `src/layouts/Layout.astro` | Astro、Tailwind |
| `src/components/*.tsx` | React、TypeScript、Tailwind |
| `src/components/WorkflowDiagram.tsx` | React、Lucide（本地静态流程图，不用 Mermaid） |
| `src/components/MermaidBlock.tsx` | Mermaid.js 懒加载、白名单与降级 |
| `src/components/RadarScoreChart.tsx` | Recharts |
| `src/components/PRDViewer.tsx` | react-markdown、remark-gfm、`skipHtml` |
| `src/components/VersionRail.tsx` / `WorkspaceTabs.tsx` | 版本轨与五个工作区页签 |
| `src/components/ReviewPanel.tsx` / `RevisionPlanPanel.tsx` | 评审反馈与 Revision Plan 展示 |
| `src/components/VersionDiff.tsx` | 阅读对比 / 源码两种视图 |
| `src/components/OutcomePanel.tsx` | 终态与失败展示 |
| `src/components/TelemetryPanel.tsx` / `AgentTrace.tsx` | 运行指标与运行记录 |
| `src/hooks/useAgentRun.ts` | EventSource、fetch、React Hooks |
| `src/lib/runReducer.ts` | TypeScript、React Reducer |
| `src/lib/contracts.ts` | 快照与事件 payload 解析、severity 归一化 |
| `src/lib/diff.ts` / `readingDiff.ts` | 版本对比计算 |
| `src/lib/outcomeSummary.ts` / `failureNotice.ts` | 终态摘要与失败提示文案 |
| `src/lib/nodeTimings.ts` | Per-node timing 归一化 |
| `src/lib/errorMessages.ts` | 错误码到中文文案映射 |
| `backend/main.py` | FastAPI、CORS、SSE |
| `backend/config.py` | pydantic-settings |
| `backend/schemas.py` | Pydantic |
| `backend/workflow.py` | LangGraph、asyncio、Aggregator 与质量门 |
| `backend/prd_document.py` | completion sentinel 与 `finish_reason` 完整性判定 |
| `backend/language.py` | 输出语言约束 |
| `backend/state_machine.py` | Run 状态迁移合法性 |
| `backend/telemetry.py` | Token、耗时与 per-node timing |
| `backend/errors.py` | 应用错误码 |
| `backend/run_manager.py` | asyncio、RunStore/EventStore |
| `backend/run_store.py` | InMemoryRunStore / SQLiteRunStore |
| `backend/event_store.py` | asyncio.Condition、SSE event buffer、SQLiteEventStore |
| `backend/providers/base.py` | Provider Protocol 与统一结果类型 |
| `backend/providers/compatible.py` | DeepSeek/GLM OpenAI 兼容适配器 |
| `backend/providers/mock.py` | 异步生成器、确定性 Fixture |
| `backend/providers/scenario.py` | E2E 故障注入 |
| `backend/observability.py` | 结构化安全日志 |
| `backend/tests/` | pytest、pytest-asyncio、HTTPX |
| `e2e/` | Playwright（含 `layout.spec.ts`、`failures.spec.ts`、`recovery.spec.ts`） |

---

## 18. 技术验收标准

技术栈实现完成后应满足：

- Astro 4.x SSR 项目可以启动和构建。
- React 18 Dashboard 通过 `client:only="react"` 加载。
- TypeScript strict 检查通过。
- FastAPI 在 Python 3.11+ 单 Worker 模式运行。
- LangGraph 可以执行三个并行 Reviewer。
- DeepSeek/GLM 兼容 Provider 与 Mock Provider 使用相同接口。
- Pydantic 能校验所有 Reviewer 和 Optimizer 输出。
- REST 控制与 GET SSE 订阅可以独立工作。
- EventSource 可以重连并按事件 ID 补发。
- Mermaid 和 Recharts 只在客户端渲染；Mermaid 首次用到时才加载。
- Markdown 渲染不允许原始 HTML，GFM 表格可用。
- Mock 模式无需外部 API Key。
- 对话、快照和可回放事件在 SQLite 中持久化，重启后历史可浏览。
- 后端 pytest 通过。
- 前端单元测试和 build 通过。
- Podcast 微订阅场景的 Playwright E2E 通过。
- 项目不依赖外部数据库、Redis、WebSocket 或外部任务队列（本地 SQLite 除外）。

---

## 19. 最终技术栈结论

第一版采用：

```text
Frontend
Astro 4.x SSR
  + React 18
  + TypeScript
  + Tailwind CSS
  + Lucide React
  + Mermaid.js
  + Recharts
  + react-markdown / remark-gfm

Backend
Python 3.11+
  + FastAPI
  + Uvicorn
  + LangGraph
  + Pydantic v2 / pydantic-settings
  + OpenAI Python SDK（DeepSeek/GLM 兼容客户端）
  + sse-starlette
  + asyncio

State and Transport
SQLiteRunStore / SQLiteEventStore（进程内热缓存 + SQLite 持久化）
  + REST control APIs
  + Native EventSource SSE

Testing
pytest / pytest-asyncio / HTTPX
  + Vitest / React Testing Library
  + Playwright
```

该组合满足 `PRD.md` 的核心技术要求，并落实 `memory-bank/design-document.md` 中的并行 Reviewer、任务控制、SSE 重连、Mock 模式和存储抽象设计，同时避免在第一版引入与 Showcase 目标无关的基础设施。
