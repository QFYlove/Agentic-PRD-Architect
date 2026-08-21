# Agentic PRD Architect

[English](../README.md) | **简体中文**

Agentic PRD Architect 可以将产品创意转化为经过多轮评审、带版本记录的 PRD。FastAPI/LangGraph 后端运行 Generator、三个并行 Reviewer、确定性 Aggregator 和 Optimizer，循环直到通过质量门或迭代预算耗尽；Astro/React 前端通过支持重放的 SSE 实时展示进度。Mock 模式具有确定性，无需外部服务凭据。

## 功能说明

**Agentic Loop.** Generator 生成 `vN` → Tech、UX、Biz 三个 Reviewer 并行评分 → Aggregator 在后端代码中确定性计算总分（模型自己给出的总分一律不采用）→ 如果需要继续，Optimizer 输出结构化 Revision Plan，下一轮 Generator 必须逐条处理。

**质量门（Quality Gate）.** 只有同时满足 `overall_score >= quality_threshold` **且** `must_fix_count == 0` 时任务才是 `COMPLETED`。这是两个互相独立的事实：目标 85 分的任务可以拿到 91 分，却仍被一条阻塞性反馈拦住。迭代预算用尽时任务以 `MAX_ITERATIONS_REACHED` 结束，这是正常终态而非失败——此时终态面板会同时说明未达到的目标分数和实际最佳版本，而最佳版本经常不是最后一版。

**反馈严重程度（severity）.** 每条评审反馈都属于 `must_fix`、`should_fix` 或 `optional`。只有 `must_fix` 会阻塞完成，另外两级作为建议与已完成的 PRD 共存。计数始终由存储的反馈按需推导，不作为总数持久化，因此评审面板、终态摘要和运行记录对同一份反馈的数量语义不可能互相矛盾。

**多版本.** 每个版本各自保存正文、评审结果、修订计划和 Token 用量。`best_version` / `best_score` 跟踪的是分数最高的版本，而不是最新版本。

**阅读输出.** PRD 使用 GFM 渲染（含表格），禁用原始 HTML。Mermaid 的 `flowchart` / `sequenceDiagram` / `stateDiagram-v2` / `mindmap` / `erDiagram` 在首次使用时才延迟加载，使用 `securityLevel: "strict"` 与 `htmlLabels: false` 渲染；定义无法解析时降级显示图表源码。版本对比提供渲染后的“阅读对比”和“源码”两种视图。任意版本都可下载为原始 UTF-8 Markdown。

**生成可靠性.** 一份生成完成的 PRD 必须同时通过两个独立的完整性信号：Provider 的 `finish_reason`，以及模型在最后一行写入的 completion sentinel（展示前会被剥离，因此不会进入阅读界面或下载文件）。任一信号不通过即拒绝该次尝试；三种原因——输出长度上限、模型提前结束、服务中断——映射到三个不同的错误码和三段不同的中文文案，因为仅说“不完整”无法告诉用户该改什么。后续版本生成失败时，已提交的所有版本都会保留，界面会指名失败的是哪一版，而不是让用户以为整个任务都没了。

**可观测性.** Per-node timing 记录每次节点调用的节点名、版本、attempt、墙钟耗时和 Token，包含那些消耗了 Token 却产出不可用文档的失败尝试。SSE 重连按 `Last-Event-ID` 补发，不重复也不丢事件；落后过多的客户端改用原子快照重新校准。对话、快照和可回放事件持久化在 SQLite 中，重启后历史仍可浏览。

## 环境要求与安装

- Node.js 24.15.0 和 npm 11.12.1
- Python 3.13.5

```bash
npm ci
python3 -m venv .venv
./.venv/bin/python -m pip install -r backend/requirements-dev.txt
cp .env.example .env
npm run playwright:install
```

`.env` 已被 Git 忽略。请勿提交任何 API 密钥。

## Provider 配置

项目初始启用 Mock。仓库提供的 `.env.example` 默认选择 DeepSeek，并将 GLM 配置完整注释：

```env
ENABLE_MOCK_LLM=true
LLM_PROVIDER=deepseek
LLM_MAX_OUTPUT_TOKENS=16000
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# LLM_PROVIDER=glm
# GLM_API_KEY=
# GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
# GLM_MODEL=glm-5.2
```

使用 DeepSeek 时，请填写 `DEEPSEEK_API_KEY`，并设置 `ENABLE_MOCK_LLM=false`。使用 GLM 时，请注释 DeepSeek 的 Provider 选择，取消四行 GLM 配置的注释，填写 `GLM_API_KEY`，并保持 Mock 关闭。应用启动时会校验 Provider、密钥、Base URL 和模型配置，不会静默回退到 Mock。

`LLM_MAX_OUTPUT_TOKENS` 会作为 `max_tokens` 显式发送。不发送它意味着沿用 Provider 服务端默认值，该默认值随模型而变且小到足以把一份完整 PRD 截断在中途；显式发送后上限就是一个已配置的值，`finish_reason="length"` 报告的是触达*这个*上限，Generator 会重试而不是提交半份文档。

## 本地运行

分别在两个终端中启动后端和前端：

```bash
./.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
npm run dev
```

访问 `http://127.0.0.1:4321`；健康检查地址为 `http://127.0.0.1:8000/api/health`。对话、快照和可回放事件保存在 `data/agentic-prd.sqlite3`。Uvicorn 必须保持单 Worker 运行，因为活动工作流任务和控制信号仍保存在进程内。Mock Podcast 场景 v1 得分 71.0、v2 得分 88.0，其中 v1 为每个 Reviewer 各带一条 `must_fix`，使质量门有真实的阻塞项可以拦住任务。

## 测试与构建

```bash
npm run format:check
npm run lint
npm run typecheck
npm run test:run
npm run build
./.venv/bin/ruff format --check backend
./.venv/bin/ruff check backend
./.venv/bin/mypy backend
./.venv/bin/python -m pytest -p no:cacheprovider
npm run test:e2e
npm run test:e2e:repeat
```

`npm run test` 是 watch 模式，单次执行请用 `test:run`。端到端测试启动器使用独立的 4331/8011 端口，支持仅限测试环境的故障注入，并始终清理其启动的服务进程。真实 Provider 的冒烟测试需要手动提供凭据并在发布前执行，不属于默认自动化流程。

## 当前限制

- 后端必须以**单 Uvicorn Worker** 运行。Task 句柄、Run 锁、Pause/Resume/Cancel 信号和 SSE 订阅 Condition 都在进程内，因此不支持水平扩展。
- 当前版本的持久化方案是 **SQLite**，不引入外部数据库、Redis 或队列。活动工作流不做 checkpoint：启动时发现的非终态 Run 会被标记为 `RUN_INTERRUPTED`，不会自动续跑。
- **终态任务不能继续优化。** 终态不可回到运行态，需要继续请新建任务。
- **不支持手工编辑 PRD。** 正文只由 Loop 产出；用户通过创意描述、质量设置和暂停时的补充优化要求施加影响。
- **导出只支持 Markdown**，没有 PDF / DOCX。
- **真实 Provider 的质量与延迟取决于模型服务。** 分数、篇幅、耗时和费用是所配置 Provider 的属性，不是本应用的属性。只有 Mock 模式具有确定性。
- 当前构建面向本地 Showcase。其锁定的 Astro 4 / Mermaid 10 依赖树存在已公开的上游安全告警，公网部署前必须先把这些 Major 升级作为显式变更完成。

## 常见问题

- 端口已被占用：停止占用 4321/8000 的进程；端到端测试还需使用 4331/8011。
- 缺少浏览器可执行文件：运行 `npm run playwright:install`。
- 启动时提示缺少密钥：启用 Mock，或者为当前 Provider 配置密钥。
- 前端无法访问 API：检查两个服务、`/api/health`、`PUBLIC_API_BASE_URL` 和 `FRONTEND_ORIGINS`。
- 后端重启中断了任务：历史快照仍会保留，并以 `RUN_INTERRUPTED` 标记为失败；请新建对话重试。
- 生成后续版本时失败：已提交的版本仍可选择查看，提示会指名失败的是哪一版。
