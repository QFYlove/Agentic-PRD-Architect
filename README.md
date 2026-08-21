# Agentic PRD Architect

**English** | [简体中文](docs/README_ZH.md)

Agentic PRD Architect turns a product idea into a versioned, reviewed PRD. A
FastAPI/LangGraph backend runs a Generator, three parallel Reviewers, a
deterministic Aggregator, and an Optimizer, looping until the quality gate
passes or the iteration budget runs out. The Astro/React frontend streams
progress over replayable SSE. Mock mode is deterministic and needs no external
credentials.

## What it does

**The loop.** Generator drafts `vN` → Tech, UX, and Biz Reviewers score it in
parallel → the Aggregator computes the overall score in backend code (the
model's own total is never used) → if the run continues, the Optimizer emits a
structured Revision Plan that the next Generator pass must address item by item.

**Quality gate.** A run is only `COMPLETED` when
`overall_score >= quality_threshold` **and** `must_fix_count == 0`. Those are two
independent facts: a run can reach 91 against a target of 85 and still be held by
one blocking finding. Exhausting the iteration budget instead ends the run as
`MAX_ITERATIONS_REACHED`, which is a normal ending, not a failure — the outcome
panel then reports the target that was not met alongside the best version, which
is frequently not the last one.

**Feedback severity.** Every reviewer finding is `must_fix`, `should_fix`, or
`optional`. Only `must_fix` gates completion; the other two survive a finished
PRD as advice. Counts are derived from the stored findings on demand, never
persisted as totals, so the Reviewer panel, the outcome summary, and the trace
can never disagree about one list.

**Versions.** Every version keeps its own content, evaluation, revision plan, and
token usage. `best_version` / `best_score` track the highest-scoring version, not
the newest one.

**Reading the output.** PRDs render as GFM (tables included) with raw HTML
disabled. Mermaid `flowchart` / `sequenceDiagram` / `stateDiagram-v2` / `mindmap`
/ `erDiagram` blocks are lazily loaded on first use, rendered with
`securityLevel: "strict"` and `htmlLabels: false`, and fall back to the diagram
source when a definition does not parse. Version comparison offers a rendered
reading view and a source view. Any version downloads as raw UTF-8 Markdown.

**Reliability.** A generated PRD must satisfy two independent completeness
signals: the provider's `finish_reason`, and a completion sentinel the model
writes as its final line (stripped before display, so it never reaches a reader
or a download). Either one failing rejects the attempt, and the three causes —
output cap, early stop, service interruption — map to three distinct error codes
and three distinct messages, because "incomplete" alone cannot tell a user what
to change. When a later version fails to generate, every version already
committed is preserved and the UI names the version that died rather than
implying the run was lost.

**Observability.** Per-node timings record each call's node, version, attempt,
wall-clock seconds, and tokens — including attempts that burned tokens and then
produced an unusable document. SSE reconnects replay from `Last-Event-ID` without
duplicates or gaps; a client that has fallen too far behind recalibrates from an
atomic snapshot. Conversations, snapshots, and replayable events persist in
SQLite, so history survives a restart.

## Prerequisites and installation

- Node.js 24.15.0 and npm 11.12.1
- Python 3.13.5

```bash
npm ci
python3 -m venv .venv
./.venv/bin/python -m pip install -r backend/requirements-dev.txt
cp .env.example .env
npm run playwright:install
```

`.env` is ignored by Git. Never commit API keys.

## Provider configuration

Mock is enabled initially. `.env.example` keeps DeepSeek selected and GLM fully
commented:

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

For DeepSeek, enter `DEEPSEEK_API_KEY` and set `ENABLE_MOCK_LLM=false`. To use
GLM, comment the DeepSeek provider selection, uncomment the four GLM lines,
enter `GLM_API_KEY`, and keep Mock disabled. Provider, key, base URL, and model
are validated at startup; the application never silently falls back to Mock.

`LLM_MAX_OUTPUT_TOKENS` is sent explicitly as `max_tokens`. Omitting it leaves
the provider's server-side default in force, which is model-dependent and small
enough to truncate a full PRD mid-document; sending it makes the ceiling a
configured value, so `finish_reason="length"` reports hitting _this_ limit and
the generator retries instead of committing a partial document.

## Run locally

Start one process per terminal:

```bash
./.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
npm run dev
```

Open `http://127.0.0.1:4321`; health is at
`http://127.0.0.1:8000/api/health`. Conversations, snapshots, and replayable
events are stored in `data/agentic-prd.sqlite3`. Keep Uvicorn at one worker
because active workflow tasks and control signals remain process-local. Mock
Podcast runs score 71.0 in v1 and 88.0 in v2, with v1 carrying one `must_fix`
per reviewer so the quality gate has something real to hold the run for.

## Test and build

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

`npm run test` is watch mode; use `test:run` for a single pass. The E2E launcher
uses isolated ports 4331/8011, test-only failure injection, and always cleans up
its server processes. Real-provider smoke testing is a manual, credentialed
release check and is not part of default automation.

## Current limitations

- The backend must run as a **single Uvicorn worker**. Task handles, run locks,
  pause/resume/cancel signals, and SSE subscriber conditions are process-local,
  so the application does not scale horizontally.
- **SQLite is the persistence layer** for this release — no external database,
  Redis, or queue. Active workflows are not checkpointed: a non-terminal run
  found at startup is marked `RUN_INTERRUPTED` and is not resumed.
- **A terminal run cannot be optimized further.** Terminal states do not return
  to a running state; start a new run instead.
- **No manual PRD editing.** Content is only produced by the loop; the user
  influences it through the idea, the quality settings, and the supplementary
  requirements available while paused.
- **Export is Markdown only.** No PDF or DOCX.
- **Real-provider quality and latency depend on the model service.** Scores,
  document length, wall-clock time, and cost are properties of the configured
  provider, not of this application. Only Mock mode is deterministic.
- This build targets local showcase use. Its pinned Astro 4 / Mermaid 10
  dependency tree carries known upstream advisories, so a public deployment
  requires those major upgrades as an explicit change first.

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
- A run failed while generating a later version: the versions already committed
  are still selectable, and the notice names the version that failed.
