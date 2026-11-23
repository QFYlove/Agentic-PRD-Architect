# Repository Guidelines

## Project Structure & Module Organization

The product is the V3 project workspace: idea → exploration → requirement baseline → Product Analyst → Product Brief → outline → per-section PRD → four reviewers → targeted optimisation → versions → Markdown export.

Documentation:

- `PRD.md`: short English product summary; `docs/product-definition.md`: full product definition.
- `docs/v3-planning/`: V3 architecture, data model, interaction, design system, roadmap, open decisions.
- `docs/product-audit/`: architecture map, issue register, and solution log (append a record for every completed change).
- `memory-bank/progress.md`: current status. The other `memory-bank/` files describe the V1/V2 baseline and are kept for reference.

Code:

- `backend/v3/`: V3 domain models, SQLite store and migrations, `JobManager`, services (`explore`, `document`, `review`, `optimize`, `quality`), prompts, rubric, pure rules, mock gateway, and the `/api/v3` router.
- `backend/` (top level): V2 run pipeline (`RunManager`, LangGraph `workflow.py`, run/event stores) plus shared pieces V3 reuses (`failures.py`, `errors.py`, providers, `prd_document.py`, `prd_quality.py`, `observability.py`, `telemetry.py`).
- `src/v3/`: the V3 workspace UI; `src/pages/index.astro` mounts it, `src/pages/runs.astro` mounts the V2 dashboard (`src/components/`, `src/hooks/`, `src/lib/`).
- `backend/tests/`, `src/**/*.test.ts(x)`, `e2e/`: tests. `scripts/v3/walkthrough.mjs` drives the app for screenshots.
- `contracts/v1/`: frozen V2 contract examples. Do not change them.
- `design-preview/`: standalone visual prototypes, not part of the app.

Keep business workflow code out of HTTP handlers. V3 routes delegate to the services in `backend/v3/`, every model call runs as a Job through `JobManager`, and model access goes through the gateway (`backend/v3/llm.py`). V2 routes delegate to `RunManager`.

## Build, Test, and Development Commands

- `npm ci`: install frontend dependencies from the lockfile.
- `npm run dev`: start Astro on port 4321.
- `npm run build`: produce the SSR build.
- `npm run lint && npm run typecheck`: check frontend style and types.
- `npm run test:run`: run Vitest once (`npm run test` is watch mode).
- `npm run test:e2e`: run Playwright on isolated ports 4331/8011.
- `./.venv/bin/python -m pip install -r backend/requirements-dev.txt`: install backend
  dependencies (dev requirements include the runtime ones).
- `./.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`:
  start FastAPI locally. Keep it at one worker.
- `./.venv/bin/python -m pytest -p no:cacheprovider`: run backend tests.
- `./.venv/bin/ruff format --check backend && ./.venv/bin/ruff check backend && ./.venv/bin/mypy backend`:
  backend style and types.

Use `ENABLE_MOCK_LLM=true` for deterministic local development without API costs. V3 schema changes go into a new numbered entry in `MIGRATIONS` in `backend/v3/store.py`; never edit a shipped migration.

## Coding Style & Naming Conventions

Use two-space indentation in TypeScript/Astro and four spaces in Python. TypeScript must remain strict; Python functions should include type hints and use async APIs for I/O.

Use `PascalCase` for React components and Pydantic models, `camelCase` for TypeScript values, and `snake_case` for Python modules/functions. Format Python with Ruff and frontend files with Prettier; do not hand-format around tool output.

## Testing Guidelines

Name Python tests `test_*.py`, Vitest files `*.test.ts(x)`, and Playwright scenarios `*.spec.ts`. Shared V3 fixtures (`app`, `client`) are in `backend/tests/conftest.py`. For V3, cover: AI output never becomes confirmed, user-sourced quotes exist in user messages, findings need evidence, reviewers stay in their own domain and allow zero findings, cross-reviewer dedup, rejected findings stay rejected, only accepted findings reach the Optimizer, human sections are not overwritten, stale marking and format-only edits, single-section failure isolation, append-only versions, SSE replay, soft delete, and internal codes kept out of document text. Keep the V2 coverage (completeness signals, retries, pause/resume/cancel, SSE replay). Use the mock gateway or `MockLLMProvider`; real-provider tests are explicit manual smoke tests.

## Commit & Pull Request Guidelines

Use Conventional Commits such as `feat: add reviewer fan-out` or `fix: deduplicate SSE events`. Keep commits focused.

Pull requests should include a concise summary, affected architecture, test commands/results, linked issue when applicable, and screenshots for UI changes. Update the design or stack documents when changing APIs, dependencies, or workflow semantics.

## Security & Agent Rules

Never commit `.env`, API keys, the local SQLite database, or test artifacts. Do not render raw model HTML or expose hidden chain-of-thought; Mermaid runs in strict security mode with HTML labels disabled. Do not surface raw provider errors, stack traces, or keys to the frontend. The four V3 reviewers (Product, UX, Tech, Biz) remain independent; compute every score in backend code, never use a model's self-reported total, and never average the four into one score. The AI never confirms or rejects requirement items; only user actions do. Internal requirement and finding codes never appear in Brief, PRD, or exported text.
