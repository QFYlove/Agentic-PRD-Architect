# Round 3 — Debugging & Repair: Run Lifecycle / Persistence / Cleanup Regressions

Status: **Final / Frozen**

Repository: `Agentic-PRD-Architect`

Original baseline: `ai-coding-benchmark-v1` / `0edc069`

Buggy seed: `ai-coding-benchmark-round3-seed` / `07445c45d3a28692524f6cd53676f004523b0424`

Buggy seed tree: `06938442d66bb9f04b904cdb2306e2dbb19a2cef`

Task type: debugging + repair + regression testing

Frozen inputs:

- Exact prompt SHA-256: `a51fbf395e28854b9babd49cf87148d52ce52284bc1ac8d5853c01f9199c1f71`
- Ground-truth seed patch SHA-256: `ca3d9165274afd5dd1931d2654480c321fdd9339a5d40cee60adff63d61d5a1e`
- Independent restart acceptance SHA-256: `425ea1e8fd824f460b9edf8b7fb7e5c681b35771176a8fbf3e8d0d9be0cf3e5a`

## 1. Objective

Round 3 evaluates how well three AI coding-system configurations diagnose and repair regressions in an existing codebase rather than implement a new feature from scratch.

The intended workflow is:

`fault reproduction → root-cause localization → minimal correct repair → regression tests → validation → task closure`

The three user-visible regression areas were:

1. terminal Run TTL incorrectly reflecting creation age instead of the most recent meaningful update;
2. interrupted Run recovery after SQLite restart not being durably persisted, allowing repeated interruption recovery on later restarts;
3. Run removal through TTL or retention leaving event/runtime state behind after the Run itself had disappeared.

The prompt described symptoms and required semantics but did not reveal the exact modified lines.

## 2. Seed baseline evaluation

| Gate | Buggy seed |
|---|---|
| Ruff format | FAIL — existing `test_node_timings.py` formatting debt |
| Ruff check | FAIL — existing import-order issue |
| mypy | PASS |
| pytest | **3 failed / 273 passed** |

The existing suite directly exposed the TTL and event-cleanup regressions. This means Round 3 is a valid repair benchmark, but **not a fully hidden fault-discovery benchmark**. The repeated-restart persistence semantic was checked independently after the runs.

## 3. Final ranking

| Rank | System | Completion | Acceptance | Final assessment |
|---:|---|---|---|---|
| 1 | **Claude Code + Opus 5** | completed | **PASS** | Best overall debugging-and-repair result: all roots correct, strong regression coverage, good cleanup ownership, and strong autonomous backend validation. |
| 2 | **Codex + GPT-5.6 Sol** | completed | **PASS** | Cleanest and smallest production repair, fastest recorded run, but weaker autonomous validation closure because its own pytest environment was unavailable. |
| 3 | **Kimi Code + Kimi K2.6** | completed | **PASS** | Correct repair with broad validation, but event cleanup ownership is less centralized and the patch contains minor unrelated formatting scope creep. |

## 4. Quantitative summary

| System | Duration | Code delta | Manual interventions | Completion |
|---|---:|---:|---:|---|
| Claude Opus 5 | **533s (8m53s)** | 4 files, **+142 / -5** | 0 | completed |
| Codex GPT-5.6 Sol | **361s (6m01s)** | 3 files, **+27 / -2** | 0 | completed |
| Kimi K2.6 | not recorded | 5 files, **+111 / -8** | 0 | completed |

Kimi's duration was not reliably recorded and is intentionally excluded from speed comparison.

Final frozen commits:

- Claude: `c506509864f81930ad610b538c1e82f58d47f677`
- Codex: `9ab849866ba2b8cf31d5303876c4daa2956454ac`
- Kimi K2.6: `adfebd76d917411dbdafa37031b00df1c78066b5`

Final patch hashes:

- Claude: `e6d48a10b1bcd066b817f05fe4376aca4eb4bf3685b3bf153eee0b45b92002a1`
- Codex: `af4ff0335cc2a735a3b24a42b75f5814fc254c12c252dad39c82c064cbffe674`
- Kimi K2.6: `adc15584b92ae770a7e30f974c5a19fa74dc4d0f57d7bfda8d2467694139903e`

## 5. Operator evaluation

### Backend

| Gate | Claude | Codex | Kimi K2.6 |
|---|---|---|---|
| Ruff format | baseline FAIL | baseline FAIL | PASS |
| Ruff check | baseline FAIL | baseline FAIL | PASS |
| mypy | PASS | PASS | PASS |
| pytest | **279 passed** | **277 passed** | **279 passed** |

Claude and Codex retain exactly the Ruff problem already present in the buggy seed, so it is baseline-attributed. Kimi reformatted the unrelated `backend/tests/test_node_timings.py`; this is not credited as task correctness.

### Frontend / project-level gates

| Gate | Claude | Codex | Kimi K2.6 |
|---|---|---|---|
| typecheck | PASS | PASS | PASS |
| ESLint | PASS | PASS | PASS |
| Vitest | **184 passed** | **184 passed** | **184 passed** |
| build | PASS | PASS | PASS |

The first Kimi frontend-evaluator attempt was invalid because a temporary `node_modules.round3-backup` directory was left inside the repository tree and Astro scanned it. That contaminated attempt is discarded. After restoring the repo, Kimi passed all four gates normally.

## 6. Independent repeated-restart acceptance

A separate post-run acceptance probe verified that interrupted-run recovery remains stable across a second restart.

| System | Result |
|---|---|
| Claude Opus 5 | PASS |
| Codex GPT-5.6 Sol | PASS |
| Kimi K2.6 | PASS |

Probe SHA-256: `425ea1e8fd824f460b9edf8b7fb7e5c681b35771176a8fbf3e8d0d9be0cf3e5a`

The probe was authored after the agent runs, so it is not presented as a pre-frozen hidden test. It was derived only from the already-frozen durable-recovery requirement and was never fed back to an agent for repair.

## 7. Per-system assessment

### Claude Code + Opus 5

Strengths:

- fixed all three regressions;
- centralized event cleanup in `_release_run_resources`;
- persisted interrupted recovery;
- accounted for retention survivors before persistence;
- added strong targeted regression tests;
- reproduced failures and reached 279 passing backend tests;
- recognized unrelated Ruff debt instead of editing it.

Trade-off: larger-than-minimal patch and heavier comments/defensive logic.

### Codex + GPT-5.6 Sol

Strengths:

- smallest and most reviewable patch;
- production repair closely matches the minimal semantic inverse of the planted bugs;
- centralized cleanup ownership;
- fastest recorded Round 3 completion at 361s;
- passed operator backend/frontend evaluation and independent restart acceptance.

Weakness: its own environment could not run the backend pytest suite, so autonomous task closure was weaker than Claude/Kimi.

### Kimi Code + Kimi K2.6

Strengths:

- fixed all three regressions;
- broad autonomous validation;
- backend/frontend gates all green;
- passed independent restart acceptance.

Weaknesses:

- event cleanup was added separately at TTL/retention callers instead of being centralized;
- unrelated `test_node_timings.py` Ruff debt was reformatted, which is minor scope creep;
- duration was not recorded.

## 8. Cross-system findings

- All three systems achieved semantic acceptance; differentiation shifted to minimality, ownership, test quality, validation closure, scope discipline, and efficiency.
- Codex produced the best minimal production patch; Claude produced the strongest end-to-end debugging/verification package.
- Kimi shows why “make every check green” can cause unnecessary edits to baseline debt.
- Existing test failures reduced diagnosis difficulty, so Round 3 should be described as a regression-repair benchmark rather than a fully hidden production-bug hunt.
- The three-round progression is complete: **Planning → Implementation → Debugging & Repair**.
