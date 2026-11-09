# V2.0 Implementation Plan

Created 2026-11-08, at the start of the V2.0 work. Covers PA-001 to PA-009. The decision records are in [solution-log.md](solution-log.md); the issue states are in [issue-register.md](issue-register.md).

## Phase 0 baseline

| Item | Result |
|---|---|
| Branch / HEAD | `main` / `cd56107` |
| Pre-existing user changes | `M .env.example`, `?? prd_benchmark/`, `?? docs/product-audit/` (all kept, not touched) |
| pytest | 290 passed |
| vitest | 17 files, 194 passed |
| ruff format / ruff check / mypy | pass / pass / pass (21 files) |
| eslint / astro check | pass / 0 errors |
| prettier --check | 11 files already fail at baseline (see SL-001); files touched in V2.0 are formatted |
| e2e (Playwright, mock backend, `:memory:` DB) | see SL-001 |
| Code changes since the first audit | none (HEAD unchanged) |

## Module dependency order

```
rubric.py (pure data)
  └─ schemas.py (new optional fields, model-facing ReviewerOutput)
       ├─ scoring.py (role score, overall, gate status, finding normalisation, dedup, resolutions)
       ├─ prd_quality.py (Markdown structure + unsourced-number checks)
       ├─ prompts.py (generator / reviewer / optimizer rules)
       ├─ errors.py + retry policy
       ├─ providers/ (base, compatible, mock, scenario: new context objects)
       └─ workflow.py + run_manager.py (node guard, failure context, recovery runs)
            └─ main.py (recover + history + rubric endpoints)
                 └─ src/lib (types, contracts, reducer, api) → components
```

## Phases

| Phase | Issues | Core change | Exit criterion |
|---|---|---|---|
| 1 | PA-004, PA-009 | Truncation is never retried with the same request; structured RunError (stage, node, version, attempt, recovery_action, trace_id); per-node failure attribution; redacted exception logs; incomplete drafts are not selectable or downloadable as versions; recovery runs (new run, old run kept) | Reliability tests pass |
| 2 | PA-002, PA-008 | Budgeted, list/table-first generator prompt with P0/P1/P2 depth rules; fact/assumption labels and an assumptions table; deterministic structure and unsourced-number checks; optimizer receives the PRD plus de-duplicated findings; change types ADD/UPDATE/REMOVE/CONSOLIDATE/RETAIN | Prompt, quality-check and optimizer tests pass |
| 3 | PA-003 | Reviewers receive the user's requirements; structured findings with evidence and section; empty review allowed; caps (5 findings, 3 strengths, 2-sentence summary); severity guard; deterministic cross-role dedup; finding ids traced through plans and resolutions | Review tests pass |
| 4 | PA-006 | Per-role rubric in config, 1-5 dimension scores, backend-computed role and overall scores, gate status PASSED / NEEDS_REVISION / BLOCKED / UNSCORED, rubric and scoring versions, legacy marking | Scoring tests pass |
| 5 | PA-001, PA-005, PA-007 | Run header with title, summary and collapsible Markdown input; PRD table of contents and findings sidebar; single-column review list with filters; plan view with finding links; user-facing run timeline plus a collapsed developer view; history replay endpoint; design-token cleanup | vitest + browser check |
| 6 | all | Full regression (pytest, vitest, lint, typecheck, build, e2e), synthetic end-to-end and failure runs on the mock provider, document update | All green or documented |

## Compatibility rules

- Every new snapshot field is optional with a default, so the existing SQLite rows load unchanged. `extra="forbid"` stays on all models.
- `PRDVersion.content` stays the stored and downloaded Markdown. The structure model is derived from it and is not persisted as a replacement.
- Reviews without `dimension_scores` render as legacy scoring. Their stored scores are never recomputed.
- `contracts/v1` examples stay valid; new examples are added only for new fields.
- No database migration: the schema of the `runs` / `run_events` tables is unchanged.
- No real model calls and no reads of `.env`. The real-model smoke test is skipped (no approved safe test configuration exists).
