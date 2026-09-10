# AI Coding Benchmark — Working Handoff

Last updated: 2026-09-10

## Project

Repository: `Agentic-PRD-Architect`

Benchmark baseline:

- Tag: `ai-coding-benchmark-v1`
- Commit: `0edc069`

## Goal

Evaluate real AI coding systems on a real repository across multiple rounds.

Systems currently included:

- Claude Code + Opus 5
- Codex + GPT-5.6 Sol
- Cursor + Grok 4.6 Medium
- Kimi Code + Kimi K2.6
- Kimi Code + Kimi K3

The benchmark evaluates end-to-end system behavior rather than attempting to claim a pure harness-only or model-only comparison.

## Worktrees

Main:

`~/Documents/Agentic-PRD-Architect`

Experimental worktrees / branches:

| System | Worktree | Branch |
|---|---|---|
| Claude | `Agentic-PRD-Architect-claude` | `bench/provider-claude` |
| Codex | `Agentic-PRD-Architect-codex` | `bench/provider-codex` |
| Cursor | `Agentic-PRD-Architect-cursor` | `bench/provider-cursor` |
| Kimi K2.6 | `Agentic-PRD-Architect-kimi` | `bench/provider-kimi` |
| Kimi K3 | `Agentic-PRD-Architect-kimi-k3` | `bench/provider-kimi-k3` |

All experiments compare against `ai-coding-benchmark-v1` / `0edc069`.

## Benchmark Structure

- `benchmark/README.md` — benchmark overview and round status
- `benchmark/methodology.md` — experimental methodology
- `benchmark/environment.md` — execution environment
- `benchmark/metrics.csv` — quantitative results
- `benchmark/prompts/` — exact prompts
- `benchmark/specs/` — frozen canonical specifications
- `benchmark/raw/` — unedited agent outputs and run metadata
- `benchmark/rounds/` — per-round analysis
- `benchmark/conclusions.md` — cross-round conclusions

## Round 1 — Complete

Task: Run-level Provider / Model Selection — repository understanding and planning only. No code modification was allowed.

Planning-quality ranking:

1. Claude Code + Opus 5
2. Cursor + Grok 4.6 Medium
3. Codex + GPT-5.6 Sol
4. Kimi Code + Kimi K3
5. Kimi Code + Kimi K2.6

Key quantitative evidence:

- Cursor: 152 sec, 0 semantic interventions.
- Codex: 370 sec, 0 semantic interventions.
- Claude: 753 sec, displayed context 77.9k / 200k, 0 semantic interventions.
- Kimi K2.6: displayed context 126k / 256k, duration unavailable, 0 semantic interventions.
- Kimi K3: observed cost CNY 6.50, duration/tokens unavailable, 0 semantic interventions.

Round 1 report: `benchmark/rounds/round-01-planning.md`.

## Round 2 — Complete / Frozen

Task: implementation of Run-level Provider / Model Selection from one shared canonical specification.

Frozen inputs:

- baseline: `0edc069`
- canonical spec: `benchmark/specs/round-02-canonical-spec.md`
- implementation prompt: `benchmark/prompts/round-02-implementation.md`
- canonical spec SHA-256: `4c6c7bc167262b80c1957362fe818934b4ff9e5a54e0fe2892e46b7184fd8a68`
- implementation prompt SHA-256: `c6ad086d4d153d5f55c4e85ef12b3f83abbc0966e3469b16574c4c7fd5ec1446`

Frozen evaluation priority:

1. canonical correctness and critical safety/compatibility;
2. post-run regression/evaluation;
3. autonomy / semantic manual intervention;
4. scope discipline / reviewability;
5. efficiency: duration, code delta, measured cost/tokens.

Speed alone does not outrank correctness.

### Round 2 final ranking

1. **Kimi Code + Kimi K3** — blocked; Canonical **Provisional PASS**; strongest final implementation correctness, but heavy/slow and terminated by insufficient balance.
2. **Claude Code + Opus 5** — partial; Canonical **PARTIAL**; extremely strong backend/canonical implementation, but final frontend regressions and no clean completion.
3. **Codex + GPT-5.6 Sol** — completed; Canonical **PARTIAL**; smallest/reviewable meaningful patch and best completed convergence, but thinner canonical depth and required coverage.
4. **Kimi Code + Kimi K2.6** — completed; Canonical **PARTIAL**; all operator gates executable/green, but different-pair concurrency and true per-model pricing were not actually established.
5. **Cursor + Grok 4.6 Medium** — blocked; **NOT IMPLEMENTED**; free quota exhausted before any code change.

### Round 2 code delta

| System | Files | Added | Deleted | Completion |
|---|---:|---:|---:|---|
| Claude Opus 5 | 23 | 2320 | 96 | partial |
| Codex GPT-5.6 Sol | 15 | 563 | 18 | completed |
| Cursor Grok 4.6 | 0 | 0 | 0 | blocked |
| Kimi K2.6 | 31 | 1639 | 94 | completed |
| Kimi K3 | 34 | 2551 | 59 | blocked |

### Round 2 observable efficiency notes

- Kimi K3: total T0-T1 unavailable. One frontend subagent alone used 49m35s, 132k tokens and 122 tool calls. Exact Round 2 monetary cost unavailable. Run stopped on insufficient provider balance.
- Claude: reliable T0-T1 unavailable. Final visible context was 98.2k / 200k. Transcript ended before normal completion.
- Codex: 21m35s; 15 files; +563/-18; normal completion.
- Kimi K2.6: reliable T0-T1 unavailable; relatively large 31-file patch and extensive validation; exact time/cost unavailable.
- Cursor: implementation duration is not meaningfully comparable because quota exhaustion occurred before code changes.

Do not estimate missing duration/token/cost values.

### Uniform post-run evaluator

The same operator-controlled gates were applied to all final worktrees:

```bash
./.venv/bin/ruff format --check backend
./.venv/bin/ruff check backend
./.venv/bin/mypy backend
./.venv/bin/python -m pytest backend/tests -p no:cacheprovider -q
npm run typecheck
npm run lint
npm run test:run
npm run build
npx playwright test --project=chromium
```

| Gate | Claude | Codex | Cursor baseline | Kimi K2.6 | Kimi K3 |
|---|---|---|---|---|---|
| Ruff format | FAIL baseline | FAIL baseline | FAIL baseline | PASS | FAIL format |
| Ruff check | FAIL baseline I001 | FAIL baseline I001 | FAIL baseline I001 | PASS | PASS |
| mypy | PASS | PASS | PASS | PASS | PASS |
| pytest | 308 passed | 279 passed | 276 passed | 300 passed | 307 passed |
| frontend typecheck | FAIL (2) | PASS | PASS | PASS | PASS |
| ESLint | FAIL | PASS | PASS | PASS | PASS |
| Vitest | FAIL (2 failed / 182 passed) | 184 passed | 184 passed | 193 passed | 204 passed |
| build | FAIL | PASS | PASS | PASS | PASS |
| Playwright | infra_error | infra_error | infra_error | 23 passed | infra_error |

Shared evaluator facts:

- Cursor baseline reproduced the `backend/tests/test_node_timings.py` Ruff problem, so matching Claude/Codex failures are baseline-attributed rather than feature regressions.
- Cursor, Codex, Claude and K3 all hit the same Playwright web-server path problem: `.venvScriptspython.exe`. Record these as `infra_error`, not implementation test failures.
- K2.6 changed the Playwright configuration and was the only worktree where the uniform operator E2E gate executed, passing 23 tests.
- Temporary evaluator dependency symlinks used for the Cursor baseline rerun were removed afterward; Cursor returned to a clean unchanged worktree.

### Key Round 2 findings

- Green tests are not sufficient evidence of requirement correctness: K2.6's strongest visible gate result still missed the intended semantics of different-pair concurrency and per-model pricing.
- Completion status and final code quality are separate signals: K3 was blocked but left the strongest canonical implementation; Claude was partial but left a very strong backend; Codex completed normally with thinner canonical coverage.
- Product limits matter in end-to-end evaluation: Cursor free quota and K3 provider balance both affected the ability to finish.
- K3 vs K2.6 is the strongest partially controlled comparison. The K3 advantage in Provider/Model interpretation, concurrency, and pricing appeared in both Round 1 planning and Round 2 implementation.

Round 2 report: `benchmark/rounds/round-02-implementation.md`.

## Operational Notes

- Permission approvals/mode changes used only to unblock tool execution are operational and do not count as semantic manual interventions.
- Codex switched from Ask to “Approve for me” during the run; record as a runtime configuration deviation, not a semantic intervention.
- Do not selectively repair or rerun Round 2 systems after T1. The frozen worktrees/results are the Round 2 evidence.

## Current Next Action

Round 2 is complete. Do not modify the frozen Round 2 spec/protocol to improve these results.

Before starting a new benchmark round:

1. commit/archive the updated benchmark documentation and raw evidence;
2. choose a genuinely new task/phase for Round 3;
3. freeze the next round's baseline, prompt, and evaluation procedure before the first run.
