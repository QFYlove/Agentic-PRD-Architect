# AI Coding Benchmark — Working Handoff

Last updated: 2026-09-11

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

Status: **incomplete / blocked; continuation pending if desired**.

Configuration:

- ZCode Desktop App 3.11.2
- Model: GLM-5.3
- Thinking: `最高`
- Round 2 permission mode: `完全访问`
- Same frozen baseline and Round 2 prompt
- Do not switch to GLM-5.3-Flash mid-run

Observed execution:

- first active segment: 850 sec, then quota exhausted;
- second active segment: 213 sec, then quota exhausted again;
- cumulative active execution observed so far: 1063 sec;
- original first blocker T1 remains 850 sec;
- waiting time for quota reset is excluded.

Current modified files in the unfinished ZCode worktree:

- `backend/config.py`
- `backend/errors.py`
- `backend/run_manager.py`
- `backend/schemas.py`
- `backend/telemetry.py`
- `backend/workflow.py`
- `backend/provider_catalog.py` (new)

Checkpoint evidence:

- `~/Desktop/zcode-glm53-r2-blocked-at-850s.patch`
- `~/Desktop/zcode-glm53-r2-blocked-2-active-1063s-full.patch`

The second checkpoint includes the untracked `backend/provider_catalog.py`.

Do not delete or reset the ZCode worktree until this extension is either completed and archived or explicitly abandoned.

This extension does not modify the frozen original Round 2 ranking.

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

## Round 3 Temporary Repositories

Independent Round 3 repositories:

- `~/Documents/Agentic-PRD-Architect-r3-claude`
- `~/Documents/Agentic-PRD-Architect-r3-codex`
- `~/Documents/Agentic-PRD-Architect-r3-kimi-k26`
- `~/Documents/Agentic-PRD-Architect-r3-seed`

Do not delete these until the Round 3 evidence has been committed/tagged in the main repository and any desired final Git bundles have been created.

## Operational Notes

- Permission approvals/mode changes used only to unblock tool execution are operational and do not count as semantic manual interventions.
- Do not estimate missing duration/token/cost values.
- Do not selectively rerun frozen systems to improve rankings.
- Do not merge the Round 3 buggy seed into production.
- Kimi's unrelated `test_node_timings.py` Ruff cleanup is preserved as delivered evidence and treated as minor scope creep.
- The first Kimi frontend evaluator attempt was contaminated by a temporary `node_modules.round3-backup` directory inside the repository. That attempt is discarded; the clean rerun passed.

## Current Next Actions

### 1. Freeze Round 3 evidence in the main repository

After the updated benchmark documents and `metrics.csv` are in place:

```bash
git add benchmark
git diff --cached --stat
git status --short
```

Then commit and tag:

```bash
git commit -m "benchmark: freeze round 3 results and evidence"
git tag -a ai-coding-benchmark-round3 -m "Freeze Round 3 debugging and repair benchmark"
```

Push the commit and tag after verification.

### 2. Finish or explicitly abandon the ZCode Round 2 extension

If continuing, use the same ZCode task, worktree, GLM-5.3 model, and configuration. Do not mix models inside the existing run.

Once complete, archive it strictly as a post-freeze Round 2 extension.

### 3. Archive and remove temporary Round 3 repositories

After freeze/tag and optional Git-bundle creation, the temporary Round 3 repositories can be deleted.

### 4. Move to production integration

The competitive benchmark is finished after Round 3.

Do not merge a benchmark “winner” wholesale. Instead:

1. compare candidate diffs by module;
2. select the strongest semantics and regression tests;
3. port/cherry-pick/reimplement selectively;
4. run a fresh non-benchmark product acceptance pass;
5. merge only the production-ready result into the formal project branch.
