# ZCode + GLM-5.3 — Round 2 Post-Freeze Extension Report

## Status

**Assessment: PASS**

This run is a post-freeze extension to Round 2 and does **not** alter the official frozen Round 2 ranking.

## System

- Product: ZCode Desktop App
- Version: 3.11.2
- Model: GLM-5.3
- Reasoning: highest
- Branch: `bench/provider-zcode`
- Baseline: `ai-coding-benchmark-v1` / `0edc069`
- Manual interventions: `0`

## Timing

- Segment 1 active runtime: `850 s`
- Segment 2 active runtime: `213 s`
- Segment 3 active runtime: `not_recorded`
- Known active runtime before final segment: `>=1063 s`
- Exact total active runtime: `unavailable`

Quota waiting time is excluded from active runtime. No unrecorded duration is estimated.

## Final implementation

- Final commit: `986929712107395062d71efc11270b50c607ae2d`
- Commit message: `benchmark: freeze zcode round 2 extension`
- Files changed: `35`
- Insertions: `2581`
- Deletions: `109`

### Final patch

- File: `zcode-glm53-r2-final-full.patch`
- SHA-256: `3a71df6936b2bdf8874e7da548a4dfd3fd688017f93801ed12e7636bdddddb3a`

Note: an earlier tracked-only patch was incomplete because `git diff --binary` did not include untracked files. The hash above is the complete final patch including all 35 changed files.

## Operator verification

### Backend

- Ruff format: PASS — 44 files already formatted
- Ruff check: PASS
- mypy: PASS — no issues found in 21 source files
- pytest: PASS — `305 passed`

### Frontend

- Typecheck: PASS
- Lint: PASS
- Vitest: PASS — `204 passed`
- Build: PASS

### E2E

Shared Round 2 command:

`npx playwright test --project=chromium`

Result: **infra_error**

Reason:

`.venvScriptspython.exe: command not found`

This is the same shared baseline evaluator infrastructure issue observed for other Round 2 systems and is not classified as a ZCode implementation failure.

Project-level deterministic E2E command:

`npm run test:e2e`

Result: **PASS — 23 passed**

The executed suite included Provider/Model selection, persistence, catalog failure/empty handling, stale selection rejection, lifecycle controls, SSE recovery, and existing regression coverage.

## Canonical review

### Backend-controlled safe catalog — PASS

`GET /api/providers` is backed by a backend `ProviderCatalog`. Public DTOs expose safe Provider/Model IDs, display names, and optional capabilities. Provider credentials, private Base URLs, and pricing remain backend-only.

### Explicit Provider/Model selection — PASS

Create Run accepts `provider_id + model_id`.

- Both supplied: resolve exact pair.
- Only one supplied: validation failure.
- Neither supplied: legacy compatibility path.
- Invalid Provider, invalid Model, and cross-pair mismatch fail before Run creation.
- No partial Run is persisted and no fallback is performed.

### Run-scoped execution binding — PASS

Provider/Model execution is derived from each Run's persisted selection rather than a mutable global current Provider/Model.

Generator, Reviewer, structured repair, and Optimizer model calls use the Run-specific `RunExecution`.

### Different-pair isolation — PASS

Backend tests create Runs using distinct Provider/Model pairs backed by distinct Provider instances and verify call ownership and persisted metadata remain isolated.

Test-strength note: the test does not force a barrier proving overlapping model calls at a precise instant, but the implementation contains no mutable global selected Provider/Model and the different-pair execution semantics are correct.

### Persistence / old SQLite compatibility — PASS

The following fields are persisted inside existing `snapshot_json`:

- `provider_id`
- `provider_display_name`
- `model_id`
- `model_display_name`

No SQL DDL migration is introduced. Old rows without these fields remain readable and deserialize to null/missing-compatible values.

Display names are stored as creation-time snapshots rather than re-derived from the current catalog.

### Historical unavailable selection — PASS

A persisted explicit selection that is no longer present in the current catalog remains readable as historical metadata.

Any later execution requiring that selection fails with `PROVIDER_SELECTION_UNAVAILABLE`; it does not fall back to another Provider/Model.

### Per-model pricing — PASS

Pricing belongs to the selected `CatalogModel` and flows through `RunExecution` into telemetry cost estimation.

- selected model with pricing → model-specific estimate
- selected model without pricing → `estimated_cost_usd = null`, `cost_available = false`
- no other model's pricing is used as fallback
- explicit zero pricing is distinct from missing pricing
- Mock cost behavior remains zero as before

### Frontend behavior — PASS

The frontend:

- loads Provider/Model choices from the backend catalog
- handles loading / empty / error+retry / loaded states
- disables Create until a complete valid pair exists
- filters Models by selected Provider
- clears incompatible Model selection when Provider changes
- always submits both IDs in the new UI flow
- surfaces backend selection rejection without silently replacing the user's choice
- displays persisted Provider/Model display names on Run and Telemetry UI
- displays a non-fabricated unknown/legacy state for old Runs

### Contract and lifecycle preservation — PASS

- existing `HealthResponse` shape preserved
- no new `RunEventType` added solely for selection
- Pause / Resume / Cancel behavior preserved
- deterministic Mock / Scenario Mock behavior preserved
- core Agent pipeline preserved

## Minor notes

These do not reduce the result below PASS:

1. The different-pair concurrency test could be stronger by deliberately forcing overlapping execution with a barrier or delay.
2. `RunExecution` is reconstructed from persisted IDs and a read-only catalog rather than stored in a separate per-run runtime binding map. This satisfies the frozen Round 2 semantics while the catalog remains read-only.
3. `capabilities` is a flexible dictionary and relies on backend construction discipline to remain safe public metadata. A production-hardening pass could add stricter recursive validation.

## Qualitative placement

Official frozen Round 2 ranking remains unchanged:

1. Kimi Code + K3
2. Claude Code + Opus 5
3. Codex + GPT-5.6 Sol
4. Kimi Code + K2.6
5. Cursor + Grok 4.6 Medium

ZCode is a **post-freeze extension** and should not be inserted into that official ranking.

For final implementation quality only, ZCode + GLM-5.3 belongs in the top tier and is stronger than the frozen K3 result on final acceptance status because ZCode reached a fully verified PASS. This comparison is non-official because ZCode received a different continuation opportunity after quota restoration.

## Product-level observation

The final implementation quality is strong, but the execution experience exposed a significant product reliability issue:

- quota exhausted after 850 s
- quota exhausted again after an additional 213 s
- completion only after a later continuation
- exact final active runtime unavailable

This is relevant to an end-to-end coding-agent benchmark even though it does not reduce the correctness of the final code.

## Bundle archive

- Bundle: `zcode-glm53-r2.bundle`
- Branch contained: `refs/heads/bench/provider-zcode`
- Final commit in bundle: `986929712107395062d71efc11270b50c607ae2d`
- Bundle verification: complete history / okay
- SHA-256: `f86bb69f5d4e7273e63a5b4417eb44a6b92d98ecedd3996746645fb724c6c942`

## Final disposition

**ZCode Desktop App 3.11.2 + GLM-5.3 — Round 2 post-freeze extension: PASS**

The ZCode benchmark run is closed. No further benchmark modification should be made to the frozen ZCode implementation. Production integration should proceed separately from the benchmark branch.
