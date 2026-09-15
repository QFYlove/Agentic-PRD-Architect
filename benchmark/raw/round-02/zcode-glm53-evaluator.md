# ZCode + GLM-5.3 — Round 2 Operator Evaluator

## Scope

This file records operator-side verification for the ZCode Desktop App 3.11.2 + GLM-5.3 Round 2 post-freeze extension.

- Baseline: `ai-coding-benchmark-v1` / `0edc069`
- Branch: `bench/provider-zcode`
- Final commit: `986929712107395062d71efc11270b50c607ae2d`
- Final full patch SHA-256: `3a71df6936b2bdf8874e7da548a4dfd3fd688017f93801ed12e7636bdddddb3a`
- Assessment: **PASS**

## Backend evaluator

Executed independently by the benchmark operator:

```bash
./.venv/bin/ruff format --check backend
./.venv/bin/ruff check backend
./.venv/bin/mypy backend
./.venv/bin/python -m pytest backend/tests -p no:cacheprovider -q
```

Results:

```text
RUFF FORMAT
44 files already formatted

RUFF CHECK
All checks passed!

MYPY
Success: no issues found in 21 source files

PYTEST
305 passed in 9.21s
```

Verdict: **PASS**

## Frontend evaluator

Executed independently by the benchmark operator:

```bash
npm run typecheck
npm run lint
npm run test:run
npm run build
```

Results:

```text
typecheck: PASS
lint: PASS
Vitest: PASS — 17 files / 204 tests
build: PASS
```

Verdict: **PASS**

## Shared Round 2 Playwright evaluator

Executed:

```bash
npx playwright test --project=chromium
```

Result:

```text
[WebServer] /bin/sh: .venvScriptspython.exe: command not found

Error: Process from config.webServer was not able to start. Exit code: 127
```

Classification: **infra_error**

This is the same shared baseline evaluator infrastructure issue observed for other Round 2 systems. It is not classified as a ZCode implementation failure.

## Project-level E2E verification

Executed independently:

```bash
npm run test:e2e
```

Result:

```text
23 passed (1.4m)
```

The suite exercised existing E2E behavior plus Provider/Model selection coverage, including:

- catalog loading and explicit selection;
- Create Run with persisted Provider/Model metadata;
- two Runs with different selections retaining their own metadata;
- catalog failure and empty states blocking creation;
- retry after catalog failure;
- stale/invalid selection rejection without client-side substitution;
- existing lifecycle / SSE / recovery coverage.

Verdict: **PASS**

## Canonical semantic review

### Safe backend catalog

**PASS**

The catalog is backend-controlled. Public Provider/Model DTOs expose safe IDs, display names and optional capabilities. Credentials, private Base URLs and pricing configuration remain backend-only.

### Explicit selection and no fallback

**PASS**

- `provider_id` and `model_id` must be supplied together.
- Explicit invalid Provider, invalid Model and cross-pair combinations fail before Run creation.
- No partial Run is persisted.
- No alternate Provider/Model is silently substituted.
- Legacy requests with neither field remain supported.

### Run-scoped execution binding

**PASS**

Generator, Reviewer, structured-repair and Optimizer calls resolve execution from the Run's persisted Provider/Model selection rather than from mutable global selected-model state.

### Different-pair isolation

**PASS**

Backend tests use different Provider/Model pairs backed by distinct Provider instances and verify that each Run retains its own selection and provider-call ownership.

Note: the test does not force overlap with an explicit synchronization barrier, so overlap-proof strength could be improved, but the implementation has no mutable global current selection and satisfies the frozen Round 2 semantics.

### Persistence and old SQLite compatibility

**PASS**

The new selection metadata is persisted in existing `snapshot_json` with no SQL DDL migration:

- `provider_id`
- `provider_display_name`
- `model_id`
- `model_display_name`

Old rows missing these fields remain readable and do not receive fabricated historical values.

### Rehydration and unavailable historical selections

**PASS**

Historical IDs/display-name snapshots remain readable. If a persisted explicit pair is no longer executable, execution fails with `PROVIDER_SELECTION_UNAVAILABLE` and does not fall back.

### Per-model pricing

**PASS**

Pricing is attached to the selected model and propagated through the Run execution binding.

- known selected-model pricing -> computed cost;
- missing selected-model pricing -> `estimated_cost_usd = null`;
- missing pricing does not borrow another model's pricing;
- explicit zero pricing remains distinguishable from missing pricing;
- Mock cost semantics remain unchanged.

### Frontend behavior

**PASS**

The frontend implements:

- loading state;
- empty state;
- error state with retry;
- loaded state;
- Provider -> Model filtering;
- clearing incompatible Model choice after Provider change;
- Create disabled until a complete valid pair exists;
- both IDs submitted for new UI-created Runs;
- backend rejection surfaced without silent client fallback;
- persisted selection names displayed in Run/Telemetry UI;
- old Runs displayed as unknown/legacy rather than fabricated.

### Contract / lifecycle preservation

**PASS**

- `HealthResponse` shape/semantics preserved.
- No new `RunEventType` added solely for selection.
- Pause / Resume / Cancel behavior preserved.
- deterministic Mock / Scenario Mock behavior preserved.
- existing core Agent pipeline preserved.

## Final evaluator disposition

**ZCode Desktop App 3.11.2 + GLM-5.3 — Round 2 post-freeze extension: PASS**

The official frozen Round 2 ranking remains unchanged because this was a post-freeze extension run.
