# Agentic PRD Architect — Product Requirements

## 1. Objective

**Agentic PRD Architect** turns a brief product idea into a versioned, reviewed PRD,
showcasing a Generator–Evaluator–Optimizer agentic loop.

The application takes a product idea, generates a draft PRD, critiques it from three
independent agent perspectives (Tech Lead, UX Designer, Business Strategist), refines
it through an iterative loop until the quality gate passes or the iteration budget runs
out, and streams the structured loop progress to the frontend in real time. Hidden
model reasoning is never exposed.

---

## 2. Tech Stack & System Architecture

- **Frontend**: Astro 4.x (SSR) + React 18 + TailwindCSS + Lucide Icons + Mermaid.js
  (for diagrams inside the generated PRD) + Recharts (radar score chart).
- **Backend**: Python 3.11+ (pinned to 3.13.5 locally) + FastAPI + LangGraph +
  OpenAI-compatible SDK adapter. DeepSeek and GLM are supported through configurable
  Chat Completions endpoints.
- **Communication**: REST for control, Server-Sent Events for real-time streaming of
  structured agent events, loop iterations, and partial PRD output. SSE events carry
  incrementing ids and are replayable.
- **Persistence**: local SQLite (`data/agentic-prd.sqlite3`) for conversations,
  snapshots, and replayable events.

### Structure

```text
agentic-prd-architect/
├── backend/
│   ├── main.py              # FastAPI app: REST control APIs + SSE endpoint
│   ├── workflow.py          # LangGraph loop, Aggregator, quality gate
│   ├── prompts.py           # System prompts for Generator, Reviewers, Optimizer
│   ├── schemas.py           # Pydantic models for state, reviews, events
│   ├── prd_document.py      # Completion sentinel + finish_reason verdicts
│   ├── run_manager.py       # Atomic commits, control signals, concurrency
│   ├── run_store.py         # In-memory + SQLite snapshot stores
│   ├── event_store.py       # Replayable event log with a bounded hot buffer
│   └── providers/           # Provider protocol, DeepSeek/GLM adapter, Mock
├── src/
│   ├── layouts/Layout.astro
│   ├── pages/index.astro    # Loads the React workspace with client:only
│   ├── components/          # Workspace, version rail, panels, viewers, charts
│   ├── hooks/useAgentRun.ts # Snapshot-first restore + EventSource lifecycle
│   └── lib/                 # Reducer, contracts, diff, outcome/failure text
├── e2e/                     # Playwright specs
├── package.json
└── astro.config.mjs
```

---

## 3. Agentic Loop Architecture & State Machine

### 3.1 State Schema Definition (`backend/schemas.py`)

The shipped models are Pydantic and live in `backend/schemas.py`. Every reviewer
finding carries a severity, because completion depends on blocking findings and not
only on the score:

```python
class FeedbackSeverity(str, Enum):
    MUST_FIX = "must_fix"
    SHOULD_FIX = "should_fix"
    OPTIONAL = "optional"

class FeedbackItem(BaseModel):
    severity: FeedbackSeverity
    message: str

class RoleReview(BaseModel):
    role: ReviewRole                    # tech | ux | biz
    score: int                          # 0-100
    feedback: list[FeedbackItem]

class EvaluationResult(BaseModel):
    tech: RoleReview
    ux: RoleReview
    biz: RoleReview
    overall_score: float                # server-computed equal-weight average
    combined_feedback: list[FeedbackItem]

    def severity_counts(self) -> dict[str, int]: ...
    @property
    def must_fix_count(self) -> int: ...
```

`overall_score` is validated against the average the backend computes itself, so a
model that reports its own total cannot influence the gate. `severity_counts()` and
`must_fix_count` are derived on demand and never persisted as totals, so the reviewer
panel, the outcome summary, and the trace cannot disagree about one list of findings.

`PRDRunState` additionally tracks `versions` (each with its own content, evaluation,
revision plan, and token usage), `best_version` / `best_score` (the highest-scoring
version, not the newest), telemetry, and `node_timings`.

### 3.2 Loop Logic Diagram

```text
[User Input] --> (Node 1: Draft Generator vN)
                      |
                      v
               (Node 2: three independent Reviewers, in parallel)
                      |
                      +--- Tech Lead + UX Designer + Biz Strategist
                      |
                      v
            (Node 3: deterministic Aggregator)
                      |
                      v
            [Quality Gate: score >= target AND must_fix == 0]
                      |
       +--------------+--------------+
       | gate passed                 | gate not passed
       | OR iteration budget spent   | AND budget remains
       v                             v
   (Terminal: COMPLETED /     (Node 4: Optimizer -> Revision Plan)
    MAX_ITERATIONS_REACHED)          |
                                     +--- Revision Plan back to Generator ---+
                                                                             |
                                     +---------------------------------------+
                                     v
                           (Re-run Node 1: Regenerate Draft vN+1)
```

The gate is a conjunction, not a single score check: a run can reach 91 against a
target of 85 and still be held by one `must_fix` finding. Exhausting the iteration
budget ends the run as `MAX_ITERATIONS_REACHED`, which is a normal ending and not a
failure; the outcome panel then reports the unmet target alongside the best version,
which is frequently not the last one.

---

## 4. Prompts Specification (`backend/prompts.py`)

### Generator Agent Prompt

> You are a Principal Product Manager. Generate a structured, professional PRD in
> Markdown for the given idea.
> If a Revision Plan is provided, address every item in it explicitly.
> Structure required:
>
> 1. Product Overview & Core Goal
> 2. Key User Stories & Happy Path
> 3. Technical Constraints & API Contracts
> 4. Edge Cases, Failures, and Recovery Flows (Loading, Empty, Error, Timeout)
> 5. Success Metrics (North Star Metric & Counter-metrics)

Document Composition Rules are part of the Generator prompt: GFM tables for
comparisons and contracts, and `mermaid` blocks limited to the diagram types the
renderer supports (`flowchart`, `sequenceDiagram`, `stateDiagram-v2`, `mindmap`,
`erDiagram`). The final line of the document must be the completion sentinel; it is
stripped before display and download, and its absence rejects the attempt.

### Reviewer Agent Prompts (structured output, one prompt per role)

The three reviewers run as independent nodes with isolated prompts, not as one
"panel" call:

> 1. **Tech Lead**: missing API details, concurrency risks, scaling bottlenecks, data
>    sync issues.
> 2. **UX Designer**: missing empty states, network latency handling,
>    reverse/cancellation flows, error messaging.
> 3. **Biz Strategist**: unclear KPIs, missing guardrail metrics, undefined user value.

Each returns a score (0-100) and a list of findings, where every finding is tagged
`must_fix`, `should_fix`, or `optional`. Only `must_fix` gates completion. A reviewer
does not report an overall score; the Aggregator computes it.

### Optimizer Agent Prompt

Consumes the combined findings and emits a structured Revision Plan (issue, required
change, target section, priority, source roles) that the next Generator pass must
work through item by item. It does not rewrite the document itself.

---

## 5. Implementation Notes

### Backend (`backend/`)

1. `requirements.txt` pins `fastapi`, `uvicorn`, `langgraph`, `openai`, `pydantic`,
   `pydantic-settings`, `sse-starlette`, `python-dotenv`. The OpenAI SDK is used as an
   OpenAI-compatible client for DeepSeek and GLM.
2. `workflow.py` builds the LangGraph workflow: Generator, three independent Reviewer
   nodes, deterministic Aggregator, Optimizer.
3. Control and streaming are separate surfaces, not one streaming POST:
   - `POST /api/runs` creates a run and returns `202` with the run id and events URL.
   - `GET /api/runs/{run_id}` returns an atomic snapshot.
   - `POST /api/runs/{run_id}/pause` | `/resume` | `/cancel` control it.
   - `GET /api/runs/{run_id}/events` is the SSE stream, with incrementing event ids
     replayable via `Last-Event-ID`.
   - `GET /api/runs` lists conversation summaries; `GET /api/health` reports health
     without exposing keys.

### Frontend (`src/`)

Astro renders the document shell; the React workspace loads with `client:only`. The
layout is a version rail plus five workspace tabs (`prd` / `review` / `plan` / `diff`
/ `trace`), of which only `prd` is never disabled:

- Version rail: every version with its score, and the best version marked.
- `prd`: streamed Markdown via `react-markdown` + `remark-gfm` with `skipHtml`,
  lazily-loaded Mermaid, and Markdown download.
- `review`: the three reviewers' scores and findings grouped by severity.
- `plan`: the Revision Plan for the selected version.
- `diff`: version comparison in a rendered reading view or a source view.
- `trace`: the structured event timeline plus per-node timings.

Telemetry (iteration, elapsed time, tokens, estimated cost, Mock status) comes from
the backend as-is; the frontend does not compute cost.

### Guardrails

1. **Structured output**: a malformed reviewer/optimizer response gets one format
   repair request; a second failure fails the node rather than guessing scores from
   loose regex.
2. **Iteration budget**: a hard stop that ends the run as `MAX_ITERATIONS_REACHED`
   even when the score is below target.
3. **Generation completeness**: `finish_reason` and the completion sentinel are both
   required; output cap, early stop, and service interruption map to three distinct
   error codes and three distinct messages.
4. **Failure preservation**: when a later version fails, the versions already
   committed remain available and the notice names the version that failed.
5. **Pause**: pausing lets the current node finish and stops after aggregation, before
   the Optimizer runs, where the user can add supplementary requirements. There is no
   manual PRD editing.

---

## 6. Verification & Test Plan

Test prompt:

> _"Build a micro-subscription feature for a podcast app that lets listeners pay
> $0.10 per episode."_

Expected behaviour in Mock mode (deterministic):

1. **Iteration 1**: Generator drafts v1; the reviewers score it to an overall 71.0 and
   each raise one `must_fix`, so the gate holds the run on both counts.
2. **Iteration 2**: the Optimizer's Revision Plan feeds the next Generator pass; v2
   scores 88.0 with no `must_fix` remaining, and the gate passes.
3. **Completion**: the run ends `COMPLETED`; the radar chart and version rail show the
   v1 → v2 progression, and v2 is the best version.

Automated gates: `pytest`, Vitest, Playwright E2E (isolated ports 4331/8011),
`astro check`, ESLint, Prettier, Ruff, mypy, and the Astro SSR production build. Real
provider smoke testing is a manual, credentialed release check.

---

## 7. Deliverables Checklist

- [x] FastAPI backend with REST control APIs and a replayable SSE stream.
- [x] Astro + React frontend with responsive Tailwind design.
- [x] Live visual rendering of the loop (node status, radar score comparison, version
      rail, trace).
- [x] Quality gate on score **and** blocking findings, with the score computed in
      backend code.
- [x] Generation completeness protection and preservation of committed versions.
- [x] SQLite persistence for conversations, snapshots, and replayable events.
- [x] Markdown export.
- [ ] Manual real-provider release smoke run (requires credentials).

---

## 8. Critical Implementation Details

### 8.1 Backend CORS & Structured Output

- **CORS**: only the configured local origins (`http://localhost:4321` and
  `http://127.0.0.1:4321` by default) are allowed.
- **Structured output**: reviewers and the optimizer use the provider's JSON object
  mode plus Pydantic validation, with a single format repair on failure.
- **Mock mode**: `ENABLE_MOCK_LLM` selects the Mock provider, which runs through the
  same LangGraph, RunManager, EventStore and SSE path as a real provider. Startup
  validates provider, key, base URL and model; the application never silently falls
  back to Mock.
- **Output cap**: `LLM_MAX_OUTPUT_TOKENS` is sent explicitly as `max_tokens`, so
  `finish_reason="length"` reports a configured ceiling rather than an unknown
  provider default.

### 8.2 Frontend Dependencies & SSR Directives

- `package.json` includes `react-markdown`, `remark-gfm`, `mermaid`, `recharts`,
  `lucide-react`.
- `src/pages/index.astro` mounts the workspace with `client:only="react"` so
  browser-only code never runs during SSR.
- Mermaid is imported inside the effect that renders a diagram, so a PRD without
  diagrams never downloads it. It runs with `startOnLoad: false`,
  `securityLevel: "strict"` and `htmlLabels: false`, and falls back to the diagram
  source when a definition does not parse.

### 8.3 SSE Wire Format

The backend emits standard SSE frames with an id, an event name, and JSON data:

```text
id: 17
event: review_completed
data: {"run_id": "...", "version": 1, "role": "tech", ...}
```

Heartbeats are a subscription-layer signal: they carry no id and are not replayable.
Business events do carry replayable ids; a client resumes from the larger of its query
cursor and `Last-Event-ID`, and a client that has fallen too far behind recalibrates
from an atomic snapshot instead. `prd_delta` exists only on the live path and is never
persisted; `prd_generated` carries the full body.

---

## 9. Out of Scope

- Horizontal scaling. The backend runs as a single Uvicorn worker: task handles, run
  locks, pause/resume/cancel signals, and SSE subscriber conditions are process-local.
- External datastores. Persistence is local SQLite only — no external database, Redis,
  or queue. Active workflows are not checkpointed: a non-terminal run found at startup
  is marked `RUN_INTERRUPTED` and is not resumed.
- Continuing a terminal run. Terminal states do not return to a running state; start a
  new run instead.
- Manual PRD editing. Content is only produced by the loop; the user influences it
  through the idea, the quality settings, and the supplementary requirements available
  while paused.
- Export formats beyond Markdown. No PDF or DOCX.
- Deterministic quality or latency with a real provider. Scores, document length,
  wall-clock time, and cost are properties of the configured model service. Only Mock
  mode is deterministic.
- Public deployment on the current dependency tree. The pinned Astro 4 / Mermaid 10
  tree carries known upstream advisories, so a public deployment requires those major
  upgrades as an explicit change first.
