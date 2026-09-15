# AI Coding Benchmark — Working Handoff

Last updated: 2026-09-15

## Project

Repository: `Agentic-PRD-Architect`

Benchmark baseline:

- Tag: `ai-coding-benchmark-v1`
- Commit: `0edc069`

## Goal

Evaluate real AI coding systems on a real repository across multiple task phases.

Core systems:

- Claude Code + Opus 5
- Codex + GPT-5.6 Sol
- Cursor + Grok 4.6 Medium
- Kimi Code + Kimi K2.6
- Kimi Code + Kimi K3

Post-freeze extension system:

- ZCode + GLM-5.3

The benchmark evaluates end-to-end system behavior rather than attempting to claim a pure harness-only or model-only comparison.

## Benchmark Structure

- `benchmark/README.md` — benchmark overview and round status
- `benchmark/methodology.md` — experimental methodology
- `benchmark/environment.md` — execution environment
- `benchmark/metrics.csv` — quantitative results
- `benchmark/prompts/` — exact prompts
- `benchmark/specs/` — frozen canonical specifications
- `benchmark/raw/` — raw outputs, patches, evaluator logs, manifests
- `benchmark/rounds/` — per-round analysis
- `benchmark/conclusions.md` — cross-round conclusions

## Round 1 — Complete / Frozen

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

Report: `benchmark/rounds/round-01-planning.md`.

### Round 1 extension — ZCode + GLM-5.3

Status: complete.

- ZCode Desktop App 3.11.2
- Model: GLM-5.3
- Reasoning UI: `最高`
- Permission mode: `变更前确认`
- Baseline: `0edc069`
- Duration: 188 sec
- Semantic manual interventions: 0
- Repository changes: 0
- Completion: completed
- Reference planning-quality position: between Claude and Cursor

This extension does not modify the frozen original Round 1 ranking.

## Round 2 — Complete / Frozen

Task: implementation of Run-level Provider / Model Selection from one shared canonical specification.

Frozen inputs:

- baseline: `0edc069`
- canonical spec: `benchmark/specs/round-02-canonical-spec.md`
- implementation prompt: `benchmark/prompts/round-02-implementation.md`
- canonical spec SHA-256: `4c6c7bc167262b80c1957362fe818934b4ff9e5a54e0fe2892e46b7184fd8a68`
- implementation prompt SHA-256: `c6ad086d4d153d5f55c4e85ef12b3f83abbc0966e3469b16574c4c7fd5ec1446`

Final ranking:

1. **Kimi Code + Kimi K3** — blocked; Canonical **Provisional PASS**
2. **Claude Code + Opus 5** — partial; Canonical **PARTIAL**
3. **Codex + GPT-5.6 Sol** — completed; Canonical **PARTIAL**
4. **Kimi Code + Kimi K2.6** — completed; Canonical **PARTIAL**
5. **Cursor + Grok 4.6 Medium** — blocked; **NOT IMPLEMENTED**

Key findings:

- green tests do not override substantive canonical gaps;
- completion status and final code quality are separate signals;
- quota/provider balance is part of end-to-end product reliability;
- K3 vs K2.6 provided the strongest partially controlled comparison.

Report: `benchmark/rounds/round-02-implementation.md`.

## Round 2 extension — ZCode + GLM-5.3

Status: **complete / archived; Canonical PASS**.

Configuration:

- ZCode Desktop App 3.11.2
- Model: GLM-5.3
- Thinking: `最高`
- Permission mode: `完全访问`
- Baseline: `0edc069`
- Same frozen canonical spec and exact Round 2 prompt
- Semantic manual interventions: 0

Timing / quota history:

- segment 1 active runtime: 850 sec → quota exhausted;
- segment 2 active runtime: 213 sec → quota exhausted again;
- segment 3 active runtime: not recorded → completed;
- known active runtime: at least 1063 sec;
- exact final active runtime: unavailable;
- quota waiting time is excluded and no missing duration is estimated.

Final implementation:

- final commit: `986929712107395062d71efc11270b50c607ae2d`
- commit message: `benchmark: freeze zcode round 2 extension`
- code delta: 35 files, +2581 / -109
- final patch: `benchmark/raw/round-02/zcode-glm53.patch`
- final patch SHA-256: `3a71df6936b2bdf8874e7da548a4dfd3fd688017f93801ed12e7636bdddddb3a`

Operator verification:

- Ruff format/check: PASS
- mypy: PASS
- backend pytest: **305 passed**
- frontend typecheck / ESLint / build: PASS
- Vitest: **204 passed**
- uniform `npx playwright test --project=chromium`: shared baseline `infra_error` from `.venvScriptspython.exe`
- project `npm run test:e2e`: **23 passed**

Canonical review: **PASS**.

The implementation satisfies the frozen semantics for safe backend catalog exposure, explicit selection/no fallback, Run-scoped binding, different-pair isolation, JSON snapshot persistence without DDL, old-run compatibility, unavailable historical selection failure, selected-model pricing, missing-price `null`, deterministic mocks, frontend catalog states, and contract/lifecycle preservation.

Archive:

- Git bundle: `~/Documents/ai-coding-benchmark-archives/round2-zcode/zcode-glm53-r2.bundle`
- bundle SHA-256: `f86bb69f5d4e7273e63a5b4417eb44a6b92d98ecedd3996746645fb724c6c942`
- bundle verification: complete history / okay
- report: `benchmark/rounds/round-02-zcode-extension.md`
- raw evidence record: `benchmark/raw/round-02/zcode-glm53.md`
- evaluator: `benchmark/raw/round-02/zcode-glm53-evaluator.md`

This is a post-freeze extension and does **not** modify the official frozen Round 2 ranking. Its final implementation quality is top-tier, but that comparison is reference-only because ZCode received a different continuation opportunity after quota recovery.

The ZCode benchmark run is closed. After this archive update is committed and pushed in the main repository, the ZCode worktree may be removed.

## Round 3 — Complete / Frozen

Task: existing-code debugging and repair across Run lifecycle, persistence recovery, and resource/event cleanup.

Original baseline: `0edc069`

Buggy seed:

- commit: `07445c45d3a28692524f6cd53676f004523b0424`
- tree: `06938442d66bb9f04b904cdb2306e2dbb19a2cef`
- tag: `ai-coding-benchmark-round3-seed`
- ground-truth patch SHA-256: `ca3d9165274afd5dd1931d2654480c321fdd9339a5d40cee60adff63d61d5a1e`

Exact prompt:

- file: `benchmark/prompts/round-03-debugging-repair.md`
- SHA-256: `a51fbf395e28854b9babd49cf87148d52ce52284bc1ac8d5853c01f9199c1f71`

History isolation:

The Claude, Codex, and Kimi Round 3 agent repositories were created from the buggy seed tree and re-initialized with one baseline commit so agents could not inspect the parent diff that injected the regressions.

Final ranking:

1. **Claude Code + Opus 5**
2. **Codex + GPT-5.6 Sol**
3. **Kimi Code + Kimi K2.6**

Timing / code delta:

| System | Duration | Files | Added | Deleted |
|---|---:|---:|---:|---:|
| Claude Opus 5 | 533 sec | 4 | 142 | 5 |
| Codex GPT-5.6 Sol | 361 sec | 3 | 27 | 2 |
| Kimi K2.6 | not recorded | 5 | 111 | 8 |

Final commits:

- Claude: `c506509864f81930ad610b538c1e82f58d47f677`
- Codex: `9ab849866ba2b8cf31d5303876c4daa2956454ac`
- Kimi K2.6: `adfebd76d917411dbdafa37031b00df1c78066b5`

Final patch SHA-256:

- Claude: `e6d48a10b1bcd066b817f05fe4376aca4eb4bf3685b3bf153eee0b45b92002a1`
- Codex: `af4ff0335cc2a735a3b24a42b75f5814fc254c12c252dad39c82c064cbffe674`
- Kimi K2.6: `adc15584b92ae770a7e30f974c5a19fa74dc4d0f57d7bfda8d2467694139903e`

Buggy-seed backend baseline:

- Ruff format: baseline fail
- Ruff check: baseline fail
- mypy: pass
- pytest: 3 failed / 273 passed

Final operator backend evaluator:

| Gate | Claude | Codex | Kimi K2.6 |
|---|---|---|---|
| Ruff format | baseline fail | baseline fail | pass |
| Ruff check | baseline fail | baseline fail | pass |
| mypy | pass | pass | pass |
| pytest | 279 passed | 277 passed | 279 passed |

Final frontend/project gates:

| Gate | Claude | Codex | Kimi K2.6 |
|---|---|---|---|
| typecheck | pass | pass | pass |
| ESLint | pass | pass | pass |
| Vitest | 184 passed | 184 passed | 184 passed |
| build | pass | pass | pass |

Independent repeated-restart acceptance:

- SHA-256: `425ea1e8fd824f460b9edf8b7fb7e5c681b35771176a8fbf3e8d0d9be0cf3e5a`
- Claude: pass
- Codex: pass
- Kimi K2.6: pass

Important methodology limitation:

The buggy seed already produced three backend failures, including direct signals for the TTL and event-cleanup regressions. Round 3 is therefore a regression-repair benchmark rather than a fully hidden fault-discovery benchmark.

The repeated-restart probe was authored after the runs and is recorded as an independent acceptance check, not a pre-frozen hidden test.

Report: `benchmark/rounds/round-03-debugging-repair.md`.

## Archive State

Round 3 evidence has already been frozen, tagged, pushed, bundled, verified, and its temporary Round 3 repositories removed.

ZCode Round 2 now also has a frozen implementation commit, full patch hash, operator evaluator evidence, and verified Git bundle. Once this documentation/evidence update is committed and pushed, its worktree can be removed.

## Operational Notes

- Permission approvals/mode changes used only to unblock tool execution are operational and do not count as semantic manual interventions.
- Do not estimate missing duration/token/cost values.
- Do not selectively rerun frozen systems to improve rankings.
- Do not merge the Round 3 buggy seed into production.
- ZCode's exact final active runtime is unavailable; preserve `>=1063s known active runtime` rather than fabricating a total.
- ZCode is a post-freeze extension and must not retroactively modify the original Round 2 ranking.

## Current Next Actions

1. Apply this final ZCode archive batch to the main repository.
2. Review `git diff`, then commit and push the benchmark archive update.
3. Remove the ZCode worktree after confirming the main-repository archive and external Git bundle.
4. Start production integration from a clean branch/worktree based on formal `main`.
5. Compare Round 2 candidate implementations module-by-module and selectively port/reimplement the strongest semantics and tests.
6. Run a fresh non-benchmark product acceptance pass before merging production integration.

The competitive benchmark is finished. **Do not start Round 4.**
