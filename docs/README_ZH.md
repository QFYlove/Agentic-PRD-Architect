# Agentic PRD Architect

[English](../README.md) | **简体中文**

Agentic PRD Architect 可以将产品创意转化为经过多轮评审、带版本记录的 PRD。FastAPI/LangGraph 后端依次运行生成器、三个并行评审器、确定性评分聚合器和优化器；Astro/React 前端通过支持重放的 SSE 实时展示进度。Mock 模式具有确定性，无需外部服务凭据。

## 环境要求与安装

- Node.js 24.15.0 和 npm 11.12.1
- Python 3.13.5

```powershell
npm ci
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item .env.example .env
npm run playwright:install
```

`.env` 已被 Git 忽略。请勿提交任何 API 密钥。

## Provider 配置

项目初始启用 Mock。仓库提供的 `.env.example` 默认选择 DeepSeek，并将 GLM 配置完整注释：

```env
ENABLE_MOCK_LLM=true
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# LLM_PROVIDER=glm
# GLM_API_KEY=
# GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
# GLM_MODEL=glm-5.2
```

使用 DeepSeek 时，请填写 `DEEPSEEK_API_KEY`，并设置 `ENABLE_MOCK_LLM=false`。使用 GLM 时，请注释 DeepSeek 的 Provider 选择，取消四行 GLM 配置的注释，填写 `GLM_API_KEY`，并保持 Mock 关闭。应用启动时会校验 Provider、密钥、Base URL 和模型配置，不会静默回退到 Mock。

## 本地运行

分别在两个终端中启动后端和前端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
npm run dev
```

访问 `http://127.0.0.1:4321`；健康检查地址为 `http://127.0.0.1:8000/api/health`。Uvicorn 应保持单 Worker 运行，因为 RunStore、EventStore 和控制信号都保存在进程内。Mock Podcast 场景的 v1 得分为 71，v2 得分为 88。

## 测试与构建

```powershell
npm run format:check
npm run lint
npm run typecheck
npm run test:run
npm run build
.\.venv\Scripts\ruff.exe format --check backend
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\mypy.exe backend
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
npm run test:e2e
npm run test:e2e:repeat
```

端到端测试启动器使用独立的 4331/8011 端口，支持仅限测试环境的故障注入，并始终清理其启动的服务进程。真实 Provider 的冒烟测试需要手动提供凭据并在发布前执行，不属于默认自动化流程。

## 常见问题

- 端口已被占用：停止占用 4321/8000 的进程；端到端测试还需使用 4331/8011。
- 缺少浏览器可执行文件：运行 `npm run playwright:install`。
- 启动时提示缺少密钥：启用 Mock，或者为当前 Provider 配置密钥。
- 前端无法访问 API：检查两个服务、`/api/health`、`PUBLIC_API_BASE_URL` 和 `FRONTEND_ORIGINS`。
- 上一次运行记录消失：后端重启时会按设计清除内存状态。
