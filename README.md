# Agentic PRD Architect

**English** | [简体中文](docs/README_ZH.md)

Agentic PRD Architect turns a product idea into a versioned, reviewed PRD. A
FastAPI/LangGraph backend runs a Generator, three parallel Reviewers,
deterministic score aggregation, and an Optimizer. The Astro/React frontend
streams progress over replayable SSE. Mock mode is deterministic and needs no
external credentials.

## Prerequisites and installation

- Node.js 24.15.0 and npm 11.12.1
- Python 3.13.5

```powershell
npm ci
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item .env.example .env
npm run playwright:install
```

`.env` is ignored by Git. Never commit API keys.

## Provider configuration

Mock is enabled initially. The checked local `.env` layout keeps DeepSeek
active and GLM fully commented:

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

For DeepSeek, enter `DEEPSEEK_API_KEY` and set `ENABLE_MOCK_LLM=false`. To use
GLM, comment the DeepSeek provider selection, uncomment the four GLM lines,
enter `GLM_API_KEY`, and keep Mock disabled. Provider, key, base URL, and model
are validated at startup; the application never silently falls back to Mock.

## Run locally

Start one process per terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
npm run dev
```

Open `http://127.0.0.1:4321`; health is at
`http://127.0.0.1:8000/api/health`. Conversations, snapshots, and replayable
events are stored in `data/agentic-prd.sqlite3`. Keep Uvicorn at one worker
because active workflow tasks and control signals remain process-local. Mock
Podcast runs score 71 in v1 and 88 in v2.

## Test and build

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

The E2E launcher uses isolated ports 4331/8011, test-only failure injection,
and always cleans up its server processes. Real-provider smoke testing is a
manual, credentialed release check and is not part of default automation.

## Troubleshooting

- Port already in use: stop the process using 4321/8000; E2E separately needs
  4331/8011.
- Browser executable missing: run `npm run playwright:install`.
- Startup reports a missing key: either enable Mock or configure the key for
  the selected provider.
- Frontend cannot reach the API: verify both processes, `/api/health`,
  `PUBLIC_API_BASE_URL`, and `FRONTEND_ORIGINS`.
- A run was interrupted by a restart: its persisted snapshot is retained and
  marked failed with `RUN_INTERRUPTED`; start a new run to retry it.
