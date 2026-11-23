# Agentic PRD Architect — Product Requirements

> Version: V3.0 MVP. The full product definition (Chinese) is
> [docs/product-definition.md](docs/product-definition.md); this file is the
> short English summary. The V1/V2 single-run loop spec this file used to hold
> is in Git history.

## 1. Objective

Help a product manager go from a vague idea to a deliverable PRD. The product
explores the requirements with the user, finds problems in them before any
document exists, writes the PRD from a confirmed baseline, reviews it from four
independent angles, and revises only what the user accepts.

### Principles

1. The user triggers each AI task; the task runs once and stops.
2. The user makes every decision. An AI inference never becomes confirmed on
   its own.
3. Every requirement and finding keeps its source.
4. Findings need real evidence. Zero findings is a valid review.
5. Human edits are never overwritten by the AI.
6. Only findings the user accepted reach the Optimizer.
7. No cap on how many rounds the user runs.
8. No single overall score decides quality.

## 2. Workflow

```
Create project → Explore (multi-round) → Requirement baseline → Product Analyst
→ Product Brief (confirmed snapshot) → Outline → Per-section generation
→ Human edits → Four reviewers → Finding decisions → Optimisation proposal
→ Impact analysis → Versions → Markdown export
```

Entry points: from an idea, from existing requirements, or review an existing
PRD (pasted Markdown is split into sections and reviewed directly).

The UI has two spaces per project: **Requirements** (conversation, baseline,
analyst findings, open items) and **Document** (Brief, outline, PRD, review,
versions, quality, export).

## 3. Requirement baseline

Twelve groups: positioning, goals, users, problems, scenarios, alternatives,
solution, features, constraints, assumptions, decisions, open items.
Positioning, users, problems, and scenarios are the core (P0) groups.

Each item has an id, content, group, source (user / AI), status, priority,
timestamps, revision history, and links. Statuses: Confirmed, Inferred,
Assumption, Proposed, Open, Rejected. Enforced in the backend:

- The AI may only assign Inferred, Assumption, Proposed, or Open.
- An item attributed to the user must quote the user's own words verbatim;
  otherwise it is stored as AI-sourced.
- The AI cannot rewrite a confirmed item; it can only propose a linked one.
- A rejected item is not re-added.

Internal item codes (POS-01, USR-02 …) are data for linking and tracing. They
never appear in Brief, PRD, or exported text.

## 4. Model calls

| Call | Reads | Produces | When |
|---|---|---|---|
| Requirement Explorer | Baseline, last 3 rounds, this round's answers | Understanding, new/updated items, 1–3 questions with purpose | Each round |
| Product Analyst | Baseline or a Brief snapshot | Gap / conflict / scenario / risk / opportunity findings citing items | User clicks "check" |
| Generator — outline | Confirmed Brief | Sections: title, goal, contents, linked items, dependencies, open points | User request |
| Generator — section | One outline entry, its items, earlier summaries | Streamed Markdown for that section | After outline is confirmed |
| Reviewers ×4 | The finished PRD (or a scoped set of sections), the Brief | Summary, risks, dimension scores, findings | User request |
| Optimizer | Accepted findings with user notes, target sections | ADD / UPDATE / REMOVE / CONSOLIDATE / RETAIN proposals | User request |

The Product Analyst checks requirements before the PRD exists; the Product
Reviewer checks the PRD. They are separate calls with separate prompts.

Opportunity findings must state the user problem, the current solution, its
shortfall, the value, the cost, and the assumptions to validate.

## 5. Review

Four reviewers run in parallel and never see each other's output:

- **Product**: problem definition, user fit, solution soundness, feature
  necessity, MVP scope, priority, business-logic completeness, traceability,
  alternatives.
- **UX**: user flows, interaction, page states, exceptions, feedback, recovery.
- **Tech**: feasibility, data, interfaces, state machines, performance,
  security, reliability, engineering risk.
- **Biz**: positioning, user value, differentiation, business model, cost,
  resources, operations and compliance risk.

Each finding has an id, reviewer, severity (`must_fix` / `should_fix` /
`optional`), title, category, section, evidence, problem, cause, impact,
recommendation, confidence, related items, and related sections. Findings
outside a reviewer's own categories are dropped.

**Scoring.** Each reviewer scores four weighted dimensions 1–5; the backend
computes `Σ(score / 5 × weight) × 100`. Scores are shown per reviewer and
never averaged. Rubric version `v3-2026-11`.

**Aggregator (code).** Merges the same problem across reviewers, matches
findings to existing project findings so ids stay stable, keeps rejected
findings rejected, applies re-verification results, and lowers unsupported
`must_fix` findings.

**Finding lifecycle.** Open, Accepted, Modified, Rejected, Deferred, Resolved,
Stale. Users set the first five; Resolved and Stale come from checks.

## 6. Editing, optimisation, impact

- Sections are edited as Markdown with optimistic locking (409 on conflict).
  A human-edited section is marked `human`.
- The Optimizer only produces proposals. The user applies all or some of them;
  a section changed after the proposal is skipped, not overwritten.
- Saving a section classifies the change (format, description, feature, rule,
  positioning, constraint). Formatting changes do nothing; others mark related
  findings stale and flag dependent sections for a scoped recheck.

## 7. Versions, quality, export

- Versions are append-only and linear, with author, reason, related findings,
  and section-level diffs. A review saves a version first if the text changed,
  so every review result points at what it read.
- Four quality views, all computed by code: document quality, requirement
  maturity, implementation readiness, open risks and blockers. No data means
  no number.
- Markdown export removes internal anchors, markers, and requirement codes,
  and keeps codes the user typed themselves.

## 8. Facts and assumptions

Figures that drive a decision are labelled user input, confirmed, assumption,
suggestion, or to be confirmed. The system never invents research data,
market size, pilot data, costs, conversion, retention, or business metrics.

## 9. Architecture

- FastAPI backend, V3 in `backend/v3/` under `/api/v3`; V2 `/api/runs` kept as
  read-only history.
- Astro + React frontend in `src/v3/`; the V2 dashboard is at `/runs`.
- SQLite with `v3_*` tables, numbered migrations, and a pre-migration backup.
- One Job per model call, durable job events, SSE replay.
- DeepSeek / GLM through an OpenAI-compatible adapter; a deterministic mock
  for development and tests.

## 10. Out of scope for the MVP

PDF / DOCX import and export, template libraries, parallel version branches,
external knowledge sources, user-supplied API keys, team collaboration,
automatic unlimited model loops, AI suggestions entering requirements without
user confirmation.
