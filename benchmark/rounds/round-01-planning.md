# Round 1 — Repository Understanding & Planning

## Objective

Round 1 evaluates how well each AI coding system can understand a real, non-trivial repository and design a safe implementation plan before writing code.

The task was to design **Run-level Provider / Model Selection** for Agentic PRD Architect.

This round specifically evaluates:

- repository understanding
- architecture reasoning
- requirement adherence
- backward-compatibility awareness
- security awareness
- testing strategy
- scope discipline
- implementation planning

No code modification was allowed.

---

## Experimental Setup

### Baseline

- Git tag: `ai-coding-benchmark-v1`
- Commit: `0edc069`

### Prompt

All systems received the exact prompt stored at:

`../prompts/round-01-planning.md`

The prompt required the systems to inspect repository documentation and real source code, while explicitly prohibiting:

- file modification
- commits
- dependency changes
- state-changing commands

### Isolation

Each system used an independent Git worktree based on the same baseline.

Systems were not given access to other systems' answers.

Manual interventions during all five runs: **0**.

---

## Systems

| System | Model | Harness / Interface | Provider |
|---|---|---|---|
| Claude Code | Opus 5 | Claude Code 2.1.251.1 | internal |
| Codex | GPT-5.6 Sol | Codex CLI 0.153.4 | internal OpenAI-compatible gateway |
| Cursor | Grok 4.6 Medium | Cursor Coding Agent | Cursor |
| Kimi Code | Kimi K2.6 | Kimi Code 0.41.0 | internal OpenAI-compatible gateway |
| Kimi Code | Kimi K3 | Kimi Code 0.41.0 | Kimi Open Platform |

---

## Quantitative Results

| System | Duration | Displayed Context | Token Usage | Measured Cost | Manual Interventions |
|---|---:|---:|---:|---:|---:|
| Cursor + Grok 4.6 Medium | 2m32s | unavailable | unavailable | unavailable | 0 |
| Codex + GPT-5.6 Sol | 6m10s | unavailable | unavailable | unavailable | 0 |
| Claude Code + Opus 5 | 12m33s | 77.9k / 200k | unavailable | unavailable | 0 |
| Kimi Code + K2.6 | unavailable | 126k / 256k | unavailable | unavailable | 0 |
| Kimi Code + K3 | unavailable | unavailable | unavailable | ¥6.50 | 0 |

Context occupancy is not treated as total token consumption.

Missing measurements are intentionally left unavailable rather than estimated.

---

# Evaluation

## 1. Claude Code + Opus 5

### Strengths

Claude produced the deepest repository-specific analysis in this round.

It correctly identified that the current architecture constructs one Provider in `create_app()` and injects that singleton into `RunManager`. More importantly, it inspected the actual consumption sites rather than stopping at the architectural description.

It identified the relevant `self.manager.provider` usages in workflow and manager code, including generation, review, structured repair, optimizer, logging and `run_started`, and explicitly checked that `run_id` was available at the relevant call sites.

This made its proposed migration to `provider_for(run_id)` especially concrete rather than conceptual.

Claude also identified several constraints that could easily be missed during implementation:

- the SQLite schema stores the complete Run snapshot as JSON and therefore requires no DDL migration
- `CreateRunRequest` uses `extra="forbid"`, making optional defaults important for compatibility
- the existing `HealthResponse` shape has an exact-equality test and should not be casually extended
- the current pricing implementation is global and would silently calculate incorrect cost for a different per-Run model
- the existing event type set is contract-sensitive and does not need a new `provider_selected` event

Its frontend behavior was also strict: loading, empty and catalog-error states disable creation instead of silently reverting to a backend default.

### Weaknesses

The response is the longest and slowest measured result in Round 1.

Some implementation detail goes beyond what is strictly necessary for a planning round, although most of that detail remained relevant to the requested feature.

### Assessment

**Planning quality: strongest in Round 1.**

The key advantage was not simply greater length, but discovery of repository-specific invariants that materially affect implementation correctness.

---

## 2. Cursor + Grok 4.6 Medium

### Strengths

Cursor produced a highly compact plan while still understanding the central architecture correctly.

It identified:

- process-level Provider configuration
- the global `RunManager.provider`
- JSON snapshot persistence in SQLite
- the `extra="forbid"` contract behavior
- injected Provider tests
- Mock / Scenario behavior
- frontend contract boundaries

Its proposed public API used explicit `provider_id` and `model_id`, with new clients always submitting both fields while old clients could omit both.

Cursor also handled historical data conservatively: old Runs without model metadata remain unrecorded rather than being retroactively assigned the current default model.

Its frontend error behavior was appropriately strict: catalog loading, empty and error states prevent creation, avoiding accidental execution with a model the user did not knowingly select.

It also explicitly preserved `HealthResponse`, the Run event contract and the current core Agent loop.

### Weaknesses

The analysis is less exhaustive than Claude's.

It did not surface as many hidden implementation details, particularly around global pricing and exact individual Provider access sites.

Several design choices are stated correctly but with less evidence from individual source locations.

### Assessment

**Very strong planning with exceptional time-to-plan.**

Cursor's most notable Round 1 property is the combination of high architectural accuracy and the fastest measured completion time: **2m32s**.

---

## 3. Codex + GPT-5.6 Sol

### Strengths

Codex showed strong system-design reasoning.

It explicitly separated:

- allowed Provider/Model combinations
- currently available combinations
- safe public metadata
- internal runtime configuration

It proposed explicit `provider_id + model_id` selection and rejected invalid combinations without falling back to another model.

Its Run-level architecture also correctly addressed concurrency: Provider state must belong to a Run or immutable `(provider_id, model_id)` instance rather than a mutable global Provider.

Codex paid particular attention to security and persistence. It recommended storing stable IDs and display names while excluding API keys, Base URLs, authorization headers, raw upstream errors and internal request data.

It also correctly argued that historical Runs must not be rewritten using the current environment's model configuration.

Testing coverage was broad, including:

- concurrent Runs with different Providers
- Provider consistency throughout one workflow
- persistence across restart
- old Snapshot compatibility
- secret leakage
- Mock behavior
- frontend catalog failure
- contract tests

### Weaknesses

The proposed impact surface is somewhat broader than necessary.

For example, it considered modifications across `base.py`, `compatible.py`, `mock.py`, `scenario.py`, observability and several UI surfaces. Some of these may ultimately be unnecessary if the existing Provider abstraction is left intact and the selection logic is concentrated in a Registry/Catalog layer.

Its error model also introduced more categories than the feature strictly requires.

### Assessment

**Architecturally strong, but somewhat more expansive than necessary.**

Codex is close to Cursor in overall planning quality, with better discussion of lifecycle/security in some areas but weaker scope discipline.

---

## 4. Kimi Code + Kimi K3

### Strengths

K3 represents a clear improvement over the K2.6 run.

It correctly adopted separate Provider and Model concepts rather than designing the first version around only one `model_key`.

It correctly identified:

- process-level singleton Provider architecture
- a new Provider Registry
- Run-scoped Provider binding
- SQLite JSON persistence requiring no SQL migration
- Provider instance caching
- secret isolation
- Mock / Scenario preservation
- per-model pricing risk
- frontend Provider → Model linkage
- old API compatibility
- concurrent Run isolation

The pricing observation is particularly important: the existing global price must not be reused for a different Run-level model. K3 proposed returning `None` when a trustworthy price is unavailable instead of fabricating a cost.

Its repository understanding was substantially more specific than the previous K2.6 output.

### Weaknesses

Several choices remain less strict than the strongest plans.

First, it proposed that if the catalog request fails, the new frontend may hide the model selector and submit the old request format, thereby using the server default.

That is a defensible backward-compatibility strategy, but it creates ambiguity in the new UI: a user entering a product idea may believe model selection is part of the product while a catalog failure silently removes that decision.

For the canonical implementation, disabling creation and offering an explicit retry is safer.

More importantly, its `provider_for(run_id)` discussion allowed an unknown Run to fall back to the default Provider. A Run-scoped Provider resolver should fail loudly if its Run binding cannot be resolved; falling back risks exactly the type of cross-model execution the feature is intended to prevent.

K3 also persisted primarily Provider/Model IDs. Persisting display names as part of the Run snapshot would make historical Runs more self-contained if catalog names later change or entries are removed.

### Assessment

**Strong core architecture with several weaker fallback/history semantics.**

K3 is materially closer to the leading plans than K2.6.

---

## 5. Kimi Code + Kimi K2.6

### Strengths

K2.6 correctly understood several important pieces:

- global Provider state must become Run-specific
- Provider configuration and public metadata must be separated
- secrets cannot appear in frontend responses
- SQLite Snapshot JSON allows zero-DDL compatibility
- Provider instances need lifecycle management
- Mock behavior must remain deterministic
- backend, contract, Vitest and Playwright coverage all need updates

The answer was not fundamentally off-track: its overall Provider Factory concept could support the feature.

### Weaknesses

The most important weakness was requirement interpretation.

The task explicitly describes Provider and Model selection, but K2.6 proposed using a single `model_key` as the primary create-Run selection and suggested that the first version could use a one-level model selector, leaving true Provider → Model linkage for later.

That reduces an explicit current requirement into a future enhancement.

Its frontend failure handling was also ambiguous. For catalog failure it stated that submission could either fall back to the default model **or** be disabled, instead of selecting one strict behavior.

This is particularly weak in a requirement containing an explicit no-silent-fallback constraint.

The plan was also less precise about repository-specific invariants than Claude, Cursor and Codex.

### Assessment

**Understood the architectural direction but missed important product-contract details.**

The K2.6 result is useful as a baseline because K3 subsequently improved several of these exact weaknesses under the same Kimi Code harness.

---

# Qualitative Comparison

| Dimension | Claude + Opus 5 | Cursor + Grok 4.6 | Codex + GPT-5.6 Sol | Kimi + K3 | Kimi + K2.6 |
|---|---|---|---|---|---|
| Repository understanding | Excellent | Very good | Very good | Good–very good | Good |
| Requirement adherence | Excellent | Excellent | Very good | Very good | Fair |
| Architecture correctness | Excellent | Very good | Excellent | Very good | Good |
| Compatibility / security | Excellent | Very good | Excellent | Good | Good |
| Testing / risk coverage | Excellent | Very good | Excellent | Very good | Good |
| Scope discipline | Very good | Excellent | Good | Very good | Good |
| Measured speed | Slowest measured | Fastest measured | Middle | unavailable | unavailable |

This table is qualitative rather than a statistically calibrated score.

---

# Controlled / Partially Controlled Comparison

## Kimi Code: K2.6 vs K3

This is the most controlled comparison currently available in Round 1 because both runs used:

- Kimi Code 0.41.0
- the same repository baseline
- the same task prompt
- independent worktrees
- zero manual interventions

However, the provider path and reasoning configuration differed, so the result should not be interpreted as a perfectly isolated model-only experiment.

### Observed improvement

K2.6 centered the create-Run API and UI around a single `model_key` and deferred true two-level Provider/Model selection.

K3 moved to an explicit Provider + Model architecture and described a linked Provider/Model UI.

K3 also surfaced more repository-specific risks:

- global pricing becoming incorrect under multiple models
- run-scoped Provider consistency
- concurrent Run isolation
- Registry instance caching
- exact Mock / Scenario implications

This provides evidence that the K3 configuration followed the architectural intent of the task more closely than the K2.6 configuration in this round.

### Remaining issue

K3 still retained fallback-oriented behavior in some paths, especially catalog failure and unresolved `provider_for(run_id)` behavior.

Therefore the improvement is substantial but incomplete.

### Cost

The K3 Round 1 planning run incurred an observed API cost of **¥6.50**.

Duration and token consumption were not exposed or recorded, so no cost-per-token or speed comparison can be made.

---

# Round 1 Ranking

For **planning quality only**:

1. **Claude Code + Opus 5**
2. **Cursor + Grok 4.6 Medium**
3. **Codex + GPT-5.6 Sol**
4. **Kimi Code + Kimi K3**
5. **Kimi Code + Kimi K2.6**

Cursor and Codex are close and optimize for different qualities:

- Cursor produced the strongest speed / concision trade-off.
- Codex produced broader architecture, security and lifecycle analysis.

Claude ranks first because it found the largest number of repository-specific constraints that materially affect implementation correctness.

This ranking is not a pure model ranking or a pure harness ranking. It represents the observed end-to-end system configurations used in this round.

---

# Canonical Design Decisions Derived from Round 1

Round 2 should not ask any system to implement its own Round 1 proposal directly.

Instead, all systems should implement one shared canonical specification derived from the best ideas across Round 1.

The canonical specification should include:

1. Creation API uses **`provider_id + model_id`**.
   - both specified, or both omitted for old-client compatibility
   - new frontend always submits both

2. Backend exposes a safe Provider/Model catalog.
   - no API key
   - no Base URL
   - no internal headers
   - no sensitive routing information

3. Provider selection is resolved through a backend Registry/Catalog.
   - invalid combinations fail explicitly
   - no model fallback

4. Each Run is permanently bound to one Provider/Model selection.
   - all Generator / Reviewer / Optimizer calls use that selection
   - concurrent Runs may use different selections without shared mutable model state

5. RunSnapshot stores:
   - provider ID
   - model ID
   - provider display name
   - model display name

6. Existing SQLite schema remains unchanged.
   - fields live inside `snapshot_json`
   - historical rows with missing fields remain readable
   - old Runs display “unrecorded / unknown”
   - current defaults are never retroactively assigned to old Runs

7. Pricing becomes Run/model-specific.
   - if trustworthy pricing is unavailable, estimated cost is `null`
   - never apply another model's global price

8. Mock and Scenario Mock remain deterministic.

9. Existing HealthResponse and Run event type contracts remain unchanged unless implementation proves a change is necessary.

10. New frontend catalog states:
    - Loading → creation disabled
    - Empty → creation disabled
    - Error → creation disabled + retry
    - Success → explicit linked Provider/Model selectors

11. Testing must cover:
    - invalid combination without fallback
    - secret leakage
    - concurrent Runs using different models
    - old request compatibility
    - old SQLite compatibility
    - restart persistence
    - missing pricing → null
    - Mock determinism
    - frontend catalog states
    - reload preserving model identity

---

# Limitations

Round 1 contains several important confounders:

- different underlying models
- different coding products / harnesses
- different reasoning configurations
- different context-management implementations
- different provider paths
- incomplete timing / token / cost observability

Therefore:

- end-to-end product behavior can be compared
- planning outputs can be qualitatively evaluated
- speed can only be compared where duration was measured
- token efficiency cannot currently be compared
- differences must not automatically be attributed to the harness or model alone

A larger number of rounds is required before drawing durable cross-round conclusions.

---

# Round Conclusion

Round 1 demonstrated meaningful differences in repository comprehension and implementation planning even though all systems received the same task and baseline.

Claude produced the most repository-specific and constraint-aware plan.

Cursor delivered the best measured speed-to-quality trade-off.

Codex produced strong architecture and security reasoning but with a broader proposed change surface.

Kimi K3 substantially improved on K2.6 in requirement interpretation and system design, while still retaining several weaker fallback semantics.

K2.6 understood the general architectural direction but deviated most clearly from the requested Provider/Model interaction model.

Round 2 should therefore use a **single canonical implementation specification**, rather than allowing each system to implement its own Round 1 plan.