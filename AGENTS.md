# Repository Guidelines

## Project Structure & Module Organization

Product requirements live in `PRD.md`; design, stack, implementation, architecture, and progress documents live in `memory-bank/`. Keep them aligned when changing scope or protocols.

The planned implementation is split into:

- `backend/`: FastAPI entry point, Pydantic schemas, LangGraph workflow, LLM providers, run/event stores, and `backend/tests/`.
- `src/`: Astro pages/layouts, React components, hooks, API helpers, and shared TypeScript types.
- `public/`: static assets.
- `.env.example`: documented, non-secret configuration.

Keep business workflow code out of HTTP handlers. API routes should delegate to `RunManager`; model access should go through the provider interface.

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

Use `ENABLE_MOCK_LLM=true` for deterministic local development without API costs.

## Coding Style & Naming Conventions

Use two-space indentation in TypeScript/Astro and four spaces in Python. TypeScript must remain strict; Python functions should include type hints and use async APIs for I/O.

Use `PascalCase` for React components and Pydantic models, `camelCase` for TypeScript values, and `snake_case` for Python modules/functions. Format Python with Ruff and frontend files with Prettier; do not hand-format around tool output.

## Testing Guidelines

Name Python tests `test_*.py`, Vitest files `*.test.ts(x)`, and Playwright scenarios `*.spec.ts`. Cover state transitions, iteration limits, parallel reviewers, the quality gate's two independent conditions, feedback severity derivation, generation completeness signals, preservation of committed versions when a later one fails, pause/resume/cancel behavior, SSE replay, reducer deduplication, and malformed model output. Prefer `MockLLMProvider`; real-provider tests should be explicit smoke tests.

## Commit & Pull Request Guidelines

Use Conventional Commits such as `feat: add reviewer fan-out` or `fix: deduplicate SSE events`. Keep commits focused.

Pull requests should include a concise summary, affected architecture, test commands/results, linked issue when applicable, and screenshots for UI changes. Update the design or stack documents when changing APIs, dependencies, or workflow semantics.

## Security & Agent Rules

Never commit `.env`, API keys, the local SQLite database, or test artifacts. Do not render raw model HTML or expose hidden chain-of-thought; Mermaid runs in strict security mode with HTML labels disabled. Do not surface raw provider errors, stack traces, or keys to the frontend. Tech, UX, and Business reviewers remain independent; aggregate scores deterministically in backend code and never use a model's self-reported total.
