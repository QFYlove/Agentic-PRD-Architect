# Agentic PRD Architect

**English** | [简体中文](docs/README_ZH.md)

Agentic PRD Architect is a workspace for product managers. It starts from a
vague idea, explores the requirements with the user round by round, checks them,
turns them into a confirmed Product Brief, writes the PRD section by section,
reviews it from four independent angles, and applies only the fixes the user
accepts. The output is a versioned Markdown PRD.

The user drives every step. Each AI task runs once and stops; nothing the AI
infers counts as agreed until the user confirms it.

## Workflow

Each project has two spaces: **Requirements** and **Document**.

1. **Create a project** from an idea, from existing requirements (meeting
   notes, a rough spec), or by pasting an existing PRD for review. A pasted PRD
   is split into sections and goes straight to step 7.
2. **Explore.** Each round the Requirement Explorer reads the user's answers,
   updates the requirement baseline, and asks 1–3 new questions, each with the
   reason it matters. Questions can be answered, skipped, or marked "not sure";
   the last two become open items. Depth is "brief" (2 questions) or
   "detailed" (3).
3. **Requirement baseline.** Twelve groups: positioning, goals, users,
   problems, scenarios, current alternatives, solution, features, constraints,
   assumptions, decisions, open items. Every item keeps its source, status,
   priority, and revision history. The AI can only mark items as inferred,
   proposed, assumption, or open; only the user confirms or rejects.
4. **Check requirements.** The Product Analyst looks for gaps, conflicts,
   missing scenarios, risks, and opportunities. Every finding cites baseline
   items. Accepted findings become questions in the next round.
5. **Product Brief.** Assembled by code from the baseline, editable, and
   confirmed once; a confirmed Brief is frozen as a version. "Check Brief" runs
   the Product Analyst on that snapshot.
6. **Outline and sections.** The Generator proposes an outline for this product
   (no fixed template). The user adds, removes, renames, and reorders sections,
   then confirms. Sections are generated one at a time with streaming; a failed
   section is retried alone.
7. **Four-way review.** Product, UX, Tech, and Biz reviewers run in parallel
   and independently on the finished document. Findings appear as highlights in
   the text. The user accepts, accepts with changes, defers, or rejects each.
8. **Targeted optimisation.** The Optimizer proposes edits only for accepted
   findings. The user picks which edits to apply; applying creates a new
   version. Sections the user wrote are never changed without that choice.
9. **Edit and recheck.** Saving a section runs a deterministic impact check:
   related findings become stale and dependent sections are flagged, so only
   those need a recheck. Formatting-only edits trigger nothing.
10. **Versions, quality, export.** Append-only versions with section-level
    diffs, four quality views, and Markdown export with internal markers and
    requirement codes removed.

Steps 4–10 can be revisited in any order.

## Scoring

Reviewers never produce a total. Each reviewer scores its four rubric
dimensions from 1 to 5 with a reason, and the backend computes
`score = Σ(dimension / 5 × weight) × 100`. A missing dimension means "not
scored", not a guess. The four reviewer scores are shown separately and never
averaged.

| Reviewer | Dimensions (weight) |
|---|---|
| Product | Problem definition and user fit 30% · Solution soundness 25% · Completeness and consistency 25% · MVP scope and priority 20% |
| UX | Fit to needs and scenarios 25% · Core task flows 30% · Interaction clarity 25% · State feedback and recovery 20% |
| Tech | Feasibility 30% · Architecture, interfaces and data 25% · Reliability and failure handling 25% · Security and constraints 20% |
| Biz | User value 30% · Positioning 25% · MVP scope and priority 20% · Business model and cost 25% |

Findings are `must_fix`, `should_fix`, or `optional`. A finding without
evidence is dropped; one whose quote cannot be found in the document is marked
and cannot be `must_fix`; "needs a number" findings are capped at `should_fix`.

The quality panel shows four separate, rule-based views: document quality,
requirement maturity, implementation readiness, and open risks and blockers. A
view with nothing to measure shows no number.

## Architecture

- **Frontend:** Astro 4 + React 18 (`src/v3/`). `/` is the V3 workspace;
  `/runs` is the V2 dashboard, kept as read-only history.
- **Backend:** FastAPI. V3 lives in `backend/v3/` under `/api/v3`; the V2 run
  pipeline (`/api/runs`, LangGraph loop) is unchanged.
- **Model calls:** five kinds — Explorer, Analyst, Generator (outline and
  section), four Reviewers, Optimizer. Each call is one Job with durable events
  and SSE replay. Retry rules are shared with V2: transient failures retry once,
  output-cap truncation never retries.
- **Storage:** SQLite (`data/agentic-prd.sqlite3`). V3 uses its own `v3_*`
  tables with numbered migrations; the file is copied to `data/backups/` before
  the first migration runs.
- **Rules in code, not prompts:** status limits on AI output, verbatim checks
  for quotes attributed to the user, evidence checks on findings, cross-reviewer
  dedup and matching against existing findings, optimistic locking on sections,
  impact analysis, scores, and quality views.

Details: [docs/product-definition.md](docs/product-definition.md),
[docs/v3-planning/](docs/v3-planning/),
[docs/product-audit/architecture-map.md](docs/product-audit/architecture-map.md).

## Install

- Node.js 24.15.0 and npm 11.12.1
- Python 3.13

```bash
npm ci
python3 -m venv .venv
./.venv/bin/python -m pip install -r backend/requirements-dev.txt
cp .env.example .env
npm run playwright:install
```

`.env` is ignored by Git. Never commit API keys.

## Provider configuration

Mock mode is on by default and needs no credentials. Its answers are fixed
rules for development and testing, and the top bar shows "模拟模型" while it is
on.

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

To use a real model, set `ENABLE_MOCK_LLM=false` and fill in the key for the
selected provider. Configuration is validated at startup and never falls back
to Mock silently. Set `MODEL_INPUT_PRICE_PER_MILLION` and
`MODEL_OUTPUT_PRICE_PER_MILLION` to see cost estimates.

## Run locally

```bash
./.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
npm run dev
```

Open `http://127.0.0.1:4321`. Health is at `http://127.0.0.1:8000/api/health`.
Keep Uvicorn at one worker: running jobs and SSE subscribers are process-local.

## Test

```bash
npm run lint && npm run typecheck
npm run test:run
npm run test:e2e
./.venv/bin/ruff format --check backend && ./.venv/bin/ruff check backend
./.venv/bin/mypy backend
./.venv/bin/python -m pytest -p no:cacheprovider
```

All automated tests use the mock model. E2E runs on isolated ports 4331/8011
with an in-memory database. A real-model smoke test is a manual check that
needs an approved key and budget.

## Limitations

- Prompts have only been verified with the mock model.
- Single worker, local SQLite, no external queue. A job interrupted by a
  restart is marked `JOB_INTERRUPTED` and is not resumed.
- One AI task per project at a time.
- Deleted projects are soft-deleted; there is no automatic cleanup.
- Old V2 runs cannot be converted into V3 projects.
- Markdown export only; no PDF or DOCX import or export.
- The pinned Astro 4 / Mermaid 10 dependencies carry known upstream advisories;
  this build is for local use.

## Troubleshooting

- Port in use: free 4321/8000 (E2E also needs 4331/8011).
- Frontend cannot reach the API: check both processes, `/api/health`,
  `PUBLIC_API_BASE_URL`, and `FRONTEND_ORIGINS`.
- "This project already has an AI task running": wait for it to finish; each
  project runs one task at a time.
- A section failed to generate: the others are kept; retry that section from
  the document page.
