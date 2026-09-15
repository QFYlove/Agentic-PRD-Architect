# ZCode + GLM-5.3 — Round 2 Run Evidence Record

> Evidence note: a complete exportable ZCode transcript was not captured as one standalone raw file. This record preserves the operator-observed configuration, quota-continuation history, final agent report, frozen identifiers, and validation facts. It must not be described as a verbatim full transcript, and missing duration/token/cost data are not reconstructed.

## Run identity

- Product: ZCode Desktop App
- Version: 3.11.2
- Model: GLM-5.3
- Thinking setting: `最高`
- Permission mode: `完全访问`
- Branch: `bench/provider-zcode`
- Baseline: `ai-coding-benchmark-v1` / `0edc069`
- Canonical spec SHA-256: `4c6c7bc167262b80c1957362fe818934b4ff9e5a54e0fe2892e46b7184fd8a68`
- Exact implementation prompt SHA-256: `c6ad086d4d153d5f55c4e85ef12b3f83abbc0966e3469b16574c4c7fd5ec1446`
- Semantic manual interventions: 0
- Final completion status: completed
- Canonical acceptance after operator review: **PASS**

## Quota / continuation timeline

### Segment 1

- active runtime: 850 sec
- stop reason: quota exhausted
- checkpoint: `~/Desktop/zcode-glm53-r2-blocked-at-850s.patch`

### Segment 2

- additional active runtime: 213 sec
- cumulative known active runtime: 1063 sec
- stop reason: quota exhausted again
- checkpoint: `~/Desktop/zcode-glm53-r2-blocked-2-active-1063s-full.patch`

### Segment 3

- continued with the same ZCode task/worktree/model
- active runtime: `not_recorded`
- result: completed

Final timing record:

- segment 1: 850 sec
- segment 2: 213 sec
- segment 3: not recorded
- known active runtime: `>=1063 sec`
- exact total active runtime: unavailable
- quota waiting time excluded
- no missing value estimated

No GLM-5.3-Flash or other model was mixed into this run.

## Final agent-reported implementation

The final ZCode report stated that the implementation:

- added a backend-controlled safe Provider/Model catalog;
- added explicit `provider_id + model_id` Create Run fields with both-or-neither validation;
- rejected invalid explicit selections before persistence with no fallback;
- persisted Provider/Model IDs and display-name snapshots in existing `snapshot_json`;
- used Run-level Provider/Model execution binding for Generator, Reviewers, Optimizer and structured repair;
- failed persisted selections that were no longer executable instead of silently switching models;
- changed cost calculation to selected-model pricing;
- represented missing pricing as unknown/null and distinguished explicit zero pricing;
- added frontend Provider/Model selectors and catalog loading/empty/error/retry states;
- displayed persisted Provider/Model names on Run/Telemetry UI and rendered old runs as unknown;
- preserved HealthResponse, RunEventType, lifecycle controls and deterministic mock behavior;
- updated tests/contracts/documentation.

The agent also reported that real paid DeepSeek/GLM smoke testing was not performed because credentials/network access were not part of the local deterministic test path.

## Final frozen implementation

- commit: `986929712107395062d71efc11270b50c607ae2d`
- commit message: `benchmark: freeze zcode round 2 extension`
- files changed: 35
- insertions: 2581
- deletions: 109

Final full patch:

- repository archive path: `benchmark/raw/round-02/zcode-glm53.patch`
- SHA-256: `3a71df6936b2bdf8874e7da548a4dfd3fd688017f93801ed12e7636bdddddb3a`

An earlier tracked-only patch omitted seven untracked files and is not the final evidence artifact.

## Final validation evidence

Agent-side final report claimed all relevant gates green.

Operator-side verification subsequently established:

- Ruff format: PASS
- Ruff check: PASS
- mypy: PASS
- backend pytest: 305 passed
- frontend typecheck: PASS
- ESLint: PASS
- Vitest: 204 passed
- build: PASS
- project E2E: 23 passed

The uniform Round 2 command `npx playwright test --project=chromium` hit the same shared baseline web-server path infrastructure error seen in several original Round 2 worktrees:

`.venvScriptspython.exe: command not found`

This is recorded as `infra_error`, not as an implementation failure.

See `zcode-glm53-evaluator.md` for the operator evaluation and semantic review.

## Bundle archive

External Git bundle:

`~/Documents/ai-coding-benchmark-archives/round2-zcode/zcode-glm53-r2.bundle`

- contains `refs/heads/bench/provider-zcode`
- final commit: `986929712107395062d71efc11270b50c607ae2d`
- verification: complete history / okay
- SHA-256: `f86bb69f5d4e7273e63a5b4417eb44a6b92d98ecedd3996746645fb724c6c942`

## Benchmark interpretation

This is a **post-freeze Round 2 extension**. It does not alter the official frozen five-system Round 2 ranking.

Final implementation quality is top-tier and achieved a fully verified PASS, but the end-to-end product experience was materially affected by repeated quota exhaustion. ZCode also received a continuation opportunity after quota recovery that was not uniformly applied to the original frozen systems, so any cross-system reference placement must remain explicitly non-official.
