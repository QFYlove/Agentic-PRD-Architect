# Round 2 Canonical Specification — Run-level Provider / Model Selection

Status: **Frozen for Round 2**
Benchmark baseline: `ai-coding-benchmark-v1` / `0edc069`
Task type: implementation + testing

## 1. Purpose

Implement **Run-level Provider / Model Selection** in Agentic-PRD-Architect.

A user creating a new Run must be able to select one allowed Provider and one allowed Model for that Run. The available choices are controlled by the backend. The resolved selection is immutable for the lifetime of the Run, persists with the Run, is visible in safe Run/Telemetry metadata, and must never leak backend credentials or internal connection details.

This specification is authoritative for Round 2. Round 1 proposals are not implementation instructions. Where Round 1 agents disagreed, all Round 2 systems must follow this document instead of their own prior plan.

## 2. Baseline and implementation constraints

The implementation MUST:

- start from Git tag `ai-coding-benchmark-v1`, commit `0edc069`;
- preserve existing repository conventions and contracts unless this specification explicitly changes them;
- avoid unrelated refactors;
- avoid dependency additions/upgrades unless the baseline is genuinely incapable of implementing the feature without them;
- preserve the existing core Agent pipeline and execution semantics;
- preserve existing REST control, SSE streaming, Pause, Resume, and Cancel behavior;
- preserve SQLite as the source of truth;
- preserve deterministic Mock and Scenario Mock behavior;
- keep all credentials and private Provider configuration on the backend.

The following core behavior MUST NOT be redesigned as part of this task:

- Generator → three independent Reviewers → Aggregator → Optimizer;
- parallel Reviewer execution;
- deterministic Aggregator behavior;
- quality-gate behavior;
- existing Run lifecycle semantics unrelated to Provider/Model selection.

Existing contract constraints that MUST remain stable unless strictly required by this feature:

- the existing `HealthResponse` field shape and semantics;
- the existing `RunEventType` set — do not add a new event type solely for Provider/Model selection.

## 3. Canonical terminology

### Provider

A backend-configured model Provider. It has:

- a stable `provider_id` used by APIs and persistence;
- a safe `provider_display_name` shown to users;
- backend-only execution configuration such as credentials and Base URL;
- one or more allowed Models.

### Model

A selectable model under a Provider. It has:

- a stable `model_id` used by APIs and persistence;
- a safe `model_display_name` shown to users;
- optional safe capability metadata;
- optional backend-only model-specific pricing metadata.

`model_id` only needs to be unique within its Provider. The canonical identity of a selection is the pair `provider_id + model_id`.

### Run selection

The immutable Provider/Model pair resolved when a new Run is created.

## 4. Backend-controlled safe catalog

The backend MUST expose a read-only catalog of currently selectable Providers and Models.

Use the repository's existing API prefix/routing convention and add a catalog endpoint at relative path:

`GET /providers`

The response MUST be structurally equivalent to:

```json
{
  "providers": [
    {
      "provider_id": "provider-a",
      "provider_display_name": "Provider A",
      "models": [
        {
          "model_id": "model-a1",
          "model_display_name": "Model A1",
          "capabilities": null
        }
      ]
    }
  ]
}
```

Requirements:

- The catalog MUST be generated from backend-controlled configuration/registry data, not from frontend constants.
- Only entries that are valid selectable choices for a new Run may appear.
- The frontend MUST NOT be able to add or override a Provider, Model, credential, Base URL, header, or other private execution setting.
- The response MUST NOT contain API keys, tokens, secrets, private Base URLs, auth headers, raw environment values, arbitrary backend configuration passthrough, or actual model pricing values.
- `capabilities` may be `null` or contain only safe public metadata.
- Model pricing configuration remains backend-only. The frontend may display the Run's computed Telemetry cost, but it must not receive the configured per-token/per-million model price table through this catalog.
- A valid but empty catalog returns an empty `providers` array.
- A catalog configuration/loading failure MUST be surfaced as an error rather than converted into a fabricated/default catalog.

The implementation MAY choose its internal config schema, registry classes, factories, and dependency-injection pattern, provided the externally observable behavior above is preserved.

## 5. Create Run API semantics

Extend the existing Create Run request without renaming or replacing the existing Create Run endpoint.

The request accepts two new fields:

- `provider_id`
- `model_id`

### 5.1 Explicit selection

For the new frontend flow, both fields MUST be sent together.

When both are present, the backend MUST verify that:

1. `provider_id` exists in the current backend catalog;
2. `model_id` exists under that exact Provider;
3. the pair is currently selectable/available.

If any check fails:

- Run creation MUST fail with a clear 4xx error using the repository's existing error-envelope conventions;
- no Run may be created or partially persisted;
- no Provider or Model may be substituted;
- no retry may silently change the selection.

A request containing only one of `provider_id` or `model_id` MUST fail validation.

### 5.2 Legacy Create Run compatibility

A request containing neither field is a legacy request and MUST remain accepted.

For this legacy path only:

- preserve the baseline's existing default Provider/Model resolution behavior;
- resolve that default to a concrete Provider/Model pair before execution;
- persist the resolved pair on every newly created Run;
- if the legacy default cannot be resolved to a valid available pair, fail explicitly rather than starting a Run with an unknown or silently substituted model.

The legacy compatibility path is not permission to fall back when an explicit pair was supplied.

### 5.3 Response compatibility

Existing response fields and meanings MUST remain compatible. New safe Provider/Model metadata may be added in a backward-compatible way.

## 6. Run-scoped binding and concurrency isolation

Provider/Model execution configuration MUST be bound to the Run, not to mutable global "current Provider/current Model" state.

For a newly created Run:

- resolve `provider_id + model_id` once at creation/start;
- bind the resulting backend execution configuration to that Run;
- keep the selection immutable for the rest of that Run;
- every Generator/Reviewer/Optimizer model call belonging to that Run MUST use that Run's bound selection.

The implementation MUST support two or more concurrent Runs using different Provider/Model pairs without cross-talk.

Changing, creating, pausing, resuming, or cancelling one Run MUST NOT mutate the Provider/Model selection of another Run.

A shared read-only catalog/registry is allowed. A shared mutable selected Provider/Model is not.

## 7. Persistence and old SQLite compatibility

No SQL DDL migration is allowed for Round 2.

The Run's serialized snapshot/payload stored through the existing SQLite persistence path MUST gain nullable fields equivalent to:

- `provider_id`
- `provider_display_name`
- `model_id`
- `model_display_name`

Requirements:

- Every new Run created after Round 2 implementation MUST persist all four resolved values.
- The display names MUST be snapshots of the names at Run creation time, not dynamically re-derived from the current catalog when old Runs are displayed.
- Service restart or page refresh MUST NOT lose the stored selection metadata.
- Existing SQLite databases and existing Run rows created before Round 2 MUST remain readable without schema migration.
- When an old snapshot lacks these fields, deserialize them as `null`/missing-compatible values; do not invent historical values.
- Existing APIs/UI MUST not crash when reading an old Run with no stored selection.

If an old pre-Round-2 Run with no persisted selection must perform additional model execution, preserve the baseline legacy Provider resolution behavior for that old Run. This compatibility behavior MUST NOT be used for new Runs or explicit selections.

## 8. Rehydration and unavailable historical selections

When a persisted new-format Run contains a Provider/Model selection, any execution path that needs to reconstruct Provider access MUST use the persisted IDs.

If the persisted explicit selection is no longer available in backend configuration:

- fail that model-execution operation clearly;
- do not switch to another Provider/Model;
- preserve the historical IDs/display names for inspection.

The system MUST distinguish "historical metadata is readable" from "the historical Provider/Model is currently executable".

## 9. Telemetry, Run information, and contract preservation

Safe Run/Telemetry information MUST make the Run's selected model inspectable.

For new Runs, expose at least:

- `provider_id`
- `provider_display_name`
- `model_id`
- `model_display_name`

The values MUST come from the Run snapshot, not from a mutable current catalog lookup.

For old Runs, these fields may be `null` or represented by a non-fabricated legacy/unknown UI state.

Telemetry, Run APIs, SSE payloads, logs returned to the frontend, and error payloads MUST NOT expose:

- API keys;
- bearer tokens;
- auth headers;
- private/internal Base URLs;
- secret environment variables;
- raw backend Provider config objects.

This task does not require adding Provider/Model metadata to every individual SSE event if existing Run-level Telemetry already provides a stable place to expose it.

Contract preservation rules:

- Keep the existing `HealthResponse` shape and semantics unchanged.
- Do not add a new `RunEventType` solely to represent Provider/Model selection.
- Prefer persisted Run/Telemetry metadata for exposing the selected Provider/Model.

## 10. Per-model pricing semantics

Any pricing/cost logic affected by this feature MUST be model-scoped.

Requirements:

- pricing belongs to a specific Model, not merely to a Provider or one global default;
- pricing configuration remains backend-only;
- if a cost estimate is computed, it MUST use the selected Run's Model pricing;
- pricing from a different Model MUST never be used as fallback;
- if pricing for the selected Model is not configured/known, the resulting cost/price value MUST be `null`/unknown, not `0`, and not a guessed value;
- an explicitly configured zero price remains distinct from missing pricing;
- missing pricing MUST NOT prevent the Run itself from executing unless the baseline already requires pricing for execution.

Do not invent a new pricing unit/currency schema if the baseline already has one. Preserve existing pricing units and public Telemetry contract where possible while changing lookup semantics to be per-model.

## 11. Frontend behavior

The new Create Run UI MUST obtain all Provider/Model choices from the backend catalog.

Required behavior:

1. Load the catalog when the Create Run flow needs it.
2. Show a Provider selector using safe display names.
3. Show a Model selector containing only Models belonging to the selected Provider.
4. Do not enable new Run creation until a valid Provider/Model pair is selected.
5. Submit both `provider_id` and `model_id` in the new UI flow.
6. When Provider changes, clear/reset a Model selection that is not valid for the newly selected Provider.
7. Do not silently replace an invalid/stale selection if the backend rejects it.
8. Show a clear failure state and let the user choose again.

### Catalog states

- **Loading:** selectors/Create action are not usable yet.
- **Empty:** explain that no Provider/Model is available and disable Create.
- **Error:** explain that the catalog could not be loaded and disable Create; allow retry.
- **Loaded:** enable Create only after a valid pair exists.

The frontend MUST NOT contain Provider credentials, private Base URLs, or a parallel hard-coded authoritative catalog.

### Existing Run display

Run details/Telemetry UI MUST show the persisted Provider and Model display names for new Runs.

Old Runs with no metadata MUST render safely without fabricating a selection.

## 12. Mock and Scenario Mock requirements

Existing Mock and Scenario Mock behavior MUST remain deterministic.

The Provider/Model selection feature MUST NOT:

- introduce network access into deterministic mock tests;
- make mock outputs depend on nondeterministic catalog ordering;
- change the logical Agent pipeline;
- make Scenario Mock behavior depend on a real external Provider.

Test fixtures may supply a deterministic backend catalog. If Mock/Scenario Mock selections are represented in that catalog, their IDs/display names MUST also be deterministic.

Existing mock golden/contract behavior should remain unchanged except where backward-compatible Provider/Model metadata is intentionally added.

## 13. No silent fallback — canonical rule

The following cases MUST fail explicitly and MUST NOT silently fall back:

- unknown `provider_id`;
- unknown `model_id`;
- a Model that exists, but under a different Provider;
- an unavailable/disabled pair;
- a persisted explicit selection that can no longer be resolved for execution;
- catalog configuration/loading failure.

The only compatibility resolution allowed is the legacy behavior described in Sections 5.2 and 7 for requests/Runs that genuinely predate the new explicit selection fields.

## 14. Required test coverage

Round 2 is incomplete without tests. These are implementation requirements for the coding systems; the benchmark operator does not need to build a separate large hidden-test suite before starting Round 2.

### 14.1 Backend pytest

At minimum cover:

- safe catalog success response;
- catalog never serializes credentials/private Base URLs or actual model pricing configuration;
- valid explicit selection creates a Run;
- selection persists IDs + display names;
- unknown Provider fails with no Run created;
- unknown Model fails with no Run created;
- Provider/Model cross-pair mismatch fails;
- only one of the two selection fields fails validation;
- legacy Create Run request with neither field remains compatible;
- old Run snapshot/database row without new fields still loads;
- no SQL DDL migration is required;
- persisted new Run survives repository/service re-open and retains metadata;
- concurrent Runs with different selections remain isolated;
- unavailable persisted explicit selection fails rather than falling back;
- per-model pricing is selected correctly;
- missing selected-model pricing yields `null`/unknown rather than `0`/fallback;
- Mock/Scenario Mock determinism remains intact;
- existing Pause/Resume/Cancel behavior remains intact for selected Runs;
- existing `HealthResponse` contract remains unchanged.

### 14.2 Contract tests

At minimum cover:

- `GET /providers` safe response shape;
- backward-compatible Create Run request/response schema;
- explicit `provider_id + model_id` request fields;
- nullable Provider/Model metadata for old Runs;
- non-null persisted metadata for new Runs;
- existing SSE/REST contracts do not regress;
- no new `RunEventType` is required solely for this feature.

### 14.3 Vitest

At minimum cover:

- catalog loading state;
- empty state;
- error state and retry behavior;
- Provider selection filters Models;
- Provider change invalidates an incompatible Model selection;
- Create disabled without a complete valid pair;
- Create request sends both IDs;
- backend selection error is surfaced without client-side fallback;
- new Run metadata renders in Run/Telemetry UI;
- old Run with null/missing metadata renders safely.

### 14.4 Playwright E2E

At minimum cover:

- load catalog → select Provider → select Model → create Run → observe the same persisted selection in Run/Telemetry UI;
- create two Runs with different selections and verify each Run keeps its own metadata/behavior;
- empty or failed catalog prevents new Run creation;
- legacy/existing Run navigation remains functional.

Playwright tests SHOULD use deterministic local/mock fixtures and MUST NOT require billable external model calls.

### 14.5 Static/type/build checks

Run all relevant existing backend/frontend static, type, and build checks required by repository conventions.

## 15. Acceptance criteria

The implementation is functionally complete only if all of the following are true:

- [ ] New UI-created Runs always submit an explicit `provider_id + model_id` pair.
- [ ] Backend catalog is authoritative and safe.
- [ ] No credential/private Base URL or actual model pricing configuration reaches the frontend catalog.
- [ ] Invalid or unavailable explicit selections fail with no fallback and no partial Run.
- [ ] Selection is bound per Run and isolated across concurrent Runs.
- [ ] New Run snapshots persist IDs + display names.
- [ ] Old APIs remain compatible.
- [ ] Old SQLite data remains readable with no SQL DDL migration.
- [ ] Persisted historical selections do not silently change when catalog config changes.
- [ ] Per-model pricing semantics are correct; missing price is `null`/unknown.
- [ ] Mock and Scenario Mock remain deterministic.
- [ ] Core Agent loop and lifecycle behavior remain unchanged.
- [ ] Existing `HealthResponse` and `RunEventType` contracts remain stable.
- [ ] Catalog loading/empty/error states prevent new UI Run creation.
- [ ] Backend pytest, contract, Vitest, Playwright, and static/type/build coverage is added or updated and relevant suites pass.

## 16. Explicit non-goals

Round 2 does NOT require:

- editing Provider credentials from the frontend;
- user-supplied arbitrary Base URLs or API keys;
- exposing backend model price tables in the catalog;
- changing the Provider/Model of an already-created Run;
- adding a database column or SQL DDL migration;
- redesigning the Agent pipeline;
- redesigning REST/SSE transport;
- redesigning Pause/Resume/Cancel;
- adding a new `RunEventType` solely for Provider/Model selection;
- broad Provider abstraction refactors unrelated to Run-scoped binding;
- adding new external Providers beyond what is needed to represent the backend-controlled configured catalog;
- making live paid-provider calls in E2E tests.

## 17. Implementation freedom

This benchmark evaluates whether the system can understand the baseline repository and implement this behavior cleanly. Therefore internal implementation choices are intentionally not prescribed beyond the invariants above.

Agents may choose repository-appropriate module boundaries, types, factories, dependency injection, and helper abstractions. They MUST NOT weaken or reinterpret the externally observable requirements to match their preferred architecture.
