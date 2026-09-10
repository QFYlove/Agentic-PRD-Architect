# Round 2 — Implementation: Run-level Provider / Model Selection

Status: **Final / Frozen**
Repository: `Agentic-PRD-Architect`
Baseline: `ai-coding-benchmark-v1` / `0edc069`
Task type: implementation + testing

Frozen inputs:

- Canonical spec SHA-256: `4c6c7bc167262b80c1957362fe818934b4ff9e5a54e0fe2892e46b7184fd8a68`
- Exact implementation prompt SHA-256: `c6ad086d4d153d5f55c4e85ef12b3f83abbc0966e3469b16574c4c7fd5ec1446`

## 1. Objective

Round 2 evaluates how well five AI coding-system configurations implement the same non-trivial full-stack feature from the same repository baseline and the same frozen canonical specification.

The target feature is **Run-level Provider / Model Selection**. A correct implementation must support an explicit `provider_id + model_id` pair, a backend-controlled safe catalog, strict no-fallback behavior, Run-scoped binding and concurrent isolation, persisted IDs/display names, old API and SQLite compatibility, per-model pricing, deterministic Mock/Scenario Mock behavior, stable lifecycle/contracts, correct frontend catalog states, and the required backend/contract/Vitest/Playwright/static coverage.

Round 2 is an **end-to-end system comparison**, not a pure model or pure harness benchmark. Product behavior, model behavior, provider path, reasoning configuration, tool use, context management, quotas, and execution reliability may all affect the observed outcome.

## 2. Evaluation order

The frozen protocol evaluates results in this order:

1. Canonical correctness and critical safety/compatibility requirements.
2. Post-run regression/evaluation results.
3. Autonomy and manual interventions.
4. Scope discipline and reviewability.
5. Efficiency: duration, code delta, and measured cost/tokens where available.

Speed or low cost does **not** outrank correctness. Missing duration, token, context, or cost values are not estimated.

## 3. Final ranking

| Rank | System | Run status | Canonical acceptance | Final assessment |
|---:|---|---|---|---|
| 1 | **Kimi Code + Kimi K3** | blocked | **Provisional PASS** | Strongest final implementation in canonical-correctness terms, but heavy/slow and terminated by insufficient balance before a clean normal finish. |
| 2 | **Claude Code + Opus 5** | partial | **PARTIAL** | Extremely strong backend/canonical reasoning and implementation, but failed to finish full-stack cleanup and left real frontend regressions. |
| 3 | **Codex + GPT-5.6 Sol** | completed | **PARTIAL** | Best convergence/scope discipline among completed implementations; stable final repo, but canonical depth and required coverage were thinner. |
| 4 | **Kimi Code + Kimi K2.6** | completed | **PARTIAL** | Strongest observed gate-completion result, but key concurrency and pricing semantics were not actually established despite green tests. |
| 5 | **Cursor + Grok 4.6 Medium** | blocked | **NOT IMPLEMENTED** | Free quota was exhausted before implementation; final worktree remained identical to baseline. |

The ranking reflects the protocol priority above. In particular, a green test suite does not override a substantive canonical gap, while an incomplete run is still penalized even if the code it left behind is strong.

## 4. Quantitative / observable summary

| System | Duration / latency evidence | Observable usage / cost | Code delta | Completion |
|---|---|---|---:|---|
| Kimi K3 | Total T0–T1 unavailable. Frontend subagent alone: **49m35s** | Frontend subagent alone: **132k tokens / 122 tools**. Round 2 CNY cost unavailable. Final agent terminated on insufficient balance. | **34 files, +2551 / -59** | blocked |
| Claude Opus 5 | Reliable T0–T1 unavailable | Final visible context: **98.2k / 200k**. Cost unavailable. | **23 files, +2320 / -96** | partial |
| Codex GPT-5.6 Sol | **21m35s** | Cost/token unavailable | **15 files, +563 / -18** | completed |
| Kimi K2.6 | Reliable T0–T1 unavailable | Cost/token unavailable | **31 files, +1639 / -94** | completed |
| Cursor Grok 4.6 | Stopped after quota exhaustion | Free quota exhausted | **0 files, +0 / -0** | blocked |

### Efficiency interpretation

**Kimi K3** produced the strongest implementation, but the result was expensive in execution resources and latency. The only directly exposed subtask already consumed 49m35s, 132k tokens, and 122 tool calls; that is not the whole run. The run then terminated because the provider account had insufficient balance. The exact Round 2 CNY cost was not captured, so no monetary value is inferred.

**Claude Opus 5** also behaved as a heavyweight system. It performed extensive repository exploration and produced a large implementation, reaching 98.2k/200k visible context before the transcript ended without a normal completion response. Its exact wall-clock duration is unavailable, so the report treats “slow convergence” qualitatively rather than inventing a number.

**Kimi K2.6** was also a relatively heavy implementation: 31 changed files and a much larger patch than Codex. It spent substantial effort on broad validation and ultimately achieved the cleanest observed gate result. Reliable T0/T1 timing was not preserved, so it is not assigned a numeric duration.

**Codex** had the clearest efficiency advantage among systems that produced meaningful code: 21m35s, only 15 changed files, +563/-18 lines, a normal completion response, and a stable post-run repository. Its weakness was not convergence but insufficient depth against the full canonical test/behavior matrix.

**Cursor** cannot be evaluated for implementation efficiency because no implementation was produced. The quota exhaustion itself is still a negative end-to-end product-reliability result.

## 5. Uniform post-run evaluator results

The operator applied the same regression/static/type/build command set to every final worktree. No post-T1 failures were fed back to the agents for repair.

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

| Gate | Kimi K3 | Claude Opus 5 | Codex GPT-5.6 Sol | Kimi K2.6 | Cursor baseline |
|---|---|---|---|---|---|
| Ruff format | FAIL (minor formatting issue) | FAIL (baseline issue) | FAIL (baseline issue) | **PASS** | FAIL (baseline issue) |
| Ruff check | **PASS** | FAIL (baseline import-order issue) | FAIL (baseline import-order issue) | **PASS** | FAIL (baseline issue) |
| mypy | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** |
| pytest | **307 passed** | **308 passed** | **279 passed** | **300 passed** | **276 passed** |
| frontend typecheck | **PASS** | **FAIL — 2 errors** | **PASS** | **PASS** | **PASS** |
| ESLint | **PASS** | **FAIL** | **PASS** | **PASS** | **PASS** |
| Vitest | **204 passed** | **FAIL — 2 failed / 182 passed** | **184 passed** | **193 passed** | **184 passed** |
| build | **PASS** | **FAIL** | **PASS** | **PASS** | **PASS** |
| Playwright | infra_error | infra_error | infra_error | **23 passed** | infra_error |

### Shared evaluator/baseline issues

The baseline worktree itself reproduced the Ruff issue in `backend/tests/test_node_timings.py`, so matching Ruff failures in Codex/Claude are not attributed as feature regressions.

The uniform Playwright command also failed before test execution on Cursor, Codex, Claude, and K3 because the baseline web-server command resolved to the invalid path `.venvScriptspython.exe`. These results are recorded as `infra_error`, not functional E2E failures. K2.6 modified the Playwright configuration to a POSIX-compatible path and was the only implementation for which the uniform operator Playwright suite actually executed, passing all 23 tests.

K3's own/subagent run reported E2E success before the provider-balance termination, but the operator-controlled uniform Playwright command could not independently re-establish that result, so K3 remains `infra_error` at the operator-evaluation layer rather than being credited with an operator E2E pass.

## 6. Canonical acceptance review

### 6.1 Kimi Code + Kimi K3 — Provisional PASS

K3 is the strongest Round 2 implementation in canonical-correctness terms.

Key strengths:

- explicit `provider_id + model_id` selection and backend-controlled safe catalog;
- strict invalid/cross-pair/unavailable selection failure;
- Run-scoped provider/model binding;
- **real different-pair concurrent isolation** using distinct Provider/Model fixtures and concurrent execution;
- persisted provider/model IDs and display names;
- restart persistence and old SQLite compatibility without DDL;
- historical unavailable selections fail instead of silently changing;
- **true per-model pricing**, including different model prices and missing-price → `null` behavior;
- deterministic Mock/Scenario behavior;
- stable Pause/Resume/Cancel, HealthResponse, and event contracts;
- frontend loading/empty/error/retry and linked Provider → Model behavior;
- strong backend and frontend test coverage.

Why it is only “Provisional” rather than an unqualified PASS:

- the full coding-agent run ended on provider `429` / insufficient balance before a normal final completion;
- the operator-controlled Playwright gate could not run because of the shared evaluator path issue;
- Ruff format still had a minor issue.

These are not evidence of a canonical functional defect, but they prevent a perfectly clean end-to-end completion result.

### 6.2 Claude Code + Opus 5 — PARTIAL

Claude produced one of the strongest backend implementations in the benchmark.

Key strengths:

- deep multi-provider catalog/runtime separation;
- strict no-fallback resolution;
- Run-specific bindings throughout generator/reviewer/repair/optimizer paths;
- real different-provider concurrency tests;
- detailed SQLite reopen/legacy-row/no-DDL coverage;
- historical unavailable-selection handling;
- true model-scoped pricing with behavior-level tests;
- strong lifecycle and compatibility coverage.

However, the final worktree was not cleanly shippable. `ProductIdeaForm` gained new required catalog props without all existing test call sites being updated, leaving:

- 2 TypeScript errors;
- ESLint failure;
- 2 Vitest failures;
- build failure.

It also did not finish the intended Round 2 Playwright/frontend coverage before the run ended. The result demonstrates excellent repository understanding and backend correctness, but weak final convergence/cleanup.

### 6.3 Codex + GPT-5.6 Sol — PARTIAL

Codex produced the smallest and most reviewable meaningful implementation.

Strengths:

- safe catalog;
- explicit selection and validation;
- persisted IDs/display names;
- Run lookup through persisted selection;
- model-scoped pricing representation and cost calculation;
- frontend catalog states and linked selectors;
- normal agent completion;
- clean typecheck/lint/Vitest/build and 279 backend tests.

Main limitations:

- the default production wiring effectively registers only the currently configured Provider/Model pair, so real multi-pair capability is not established as strongly as K3/Claude;
- required canonical coverage is much thinner: no real different-pair concurrency test, limited old-SQLite/restart/historical-selection validation, limited pricing behavior tests, and no Round 2 Playwright feature suite;
- a half-populated corrupted persisted selection would fall through a legacy path, recorded as a robustness note rather than a canonical failure because this state is outside the normal frozen data model.

Codex ranks above K2.6 because its actual pricing semantics are sound and its final repository is compact and stable, even though its required coverage is incomplete.

### 6.4 Kimi Code + Kimi K2.6 — PARTIAL

K2.6 produced the cleanest observed validation outcome:

- 300 backend tests passed;
- 193 Vitest tests passed;
- typecheck/lint/build passed;
- 23 Playwright E2E tests passed.

It also implemented many requirements correctly: safe catalog, explicit selection, persistence, legacy compatibility, catalog failure states, historical metadata, lifecycle preservation, and broad full-stack tests.

However, two substantive canonical gaps remain.

#### Different-pair concurrency was not actually established

The test named as a concurrency/isolation check creates two Runs using the **same** `mock / mock-default` pair, and its E2E equivalent also completes the first Run before creating the second. The production registry built from normal settings exposes only one current real pair. Therefore the implementation does not establish the required behavior for concurrent Runs using different selections.

#### Pricing remained effectively global

The catalog stores per-model price fields, but the runtime provider only receives a `has_pricing` boolean. Actual cost calculation continues to read the global Settings price values. The tests verify pricing availability rather than proving that two different selected Models use two different prices or that a selected Model cannot inherit another Model's price.

This is the clearest example in the round that **“all tests green” does not necessarily mean “the requirement is correct.”** The test suite was broad, but some tests validated weaker behavior than the canonical requirement they were intended to prove.

### 6.5 Cursor + Grok 4.6 Medium — NOT IMPLEMENTED

Cursor produced a detailed implementation plan but exhausted its free quota before making any code changes.

Final delta relative to baseline:

- 0 files changed;
- 0 lines added;
- 0 lines deleted.

The uniform operator gates therefore serve as an effective baseline control rather than an evaluation of a Cursor implementation. Under the frozen rerun policy, quota exhaustion during a correctly prepared run is part of the observed end-to-end result rather than a reason for a selective rerun.

## 7. Cross-system findings

### 7.1 Green tests can validate the wrong thing

K2.6 is the most important case. It had the strongest visible CI/gate result, yet its “different selections” test used the same selection twice and its pricing tests only established pricing presence/absence. A coding benchmark needs independent requirement-level review, not just a count of passing tests.

### 7.2 Agent completion status and code quality are different signals

K3 was formally blocked but left the strongest canonical implementation. Claude was partial but left an extremely strong backend. Codex completed normally but covered less of the canonical matrix. Completion status should therefore be recorded separately from implementation correctness rather than used as a proxy for it.

### 7.3 Correctness, convergence, and efficiency form different product profiles

- **K3:** strongest correctness; heavy, slow, and resource-hungry; provider balance became an actual completion risk.
- **Claude:** deepest repository reasoning; heavyweight execution; strong architecture but weak final convergence/cleanup.
- **Codex:** most compact meaningful implementation; fastest observed completed implementation; strong convergence and reviewability, but less exhaustive canonical coverage.
- **K2.6:** broad implementation and validation; very capable at driving the repo to green, but weaker at ensuring tests exactly prove the hardest requirements.
- **Cursor:** excellent planning efficiency in Round 1, but Round 2 product quota/reliability prevented implementation entirely.

### 7.4 Product quota/cost behavior is part of end-to-end coding experience

Cursor's free-quota exhaustion and K3's provider-balance exhaustion are not static code defects, but they materially affect whether a user can finish a real coding task. They belong in the product-level benchmark conclusion.

At the same time, cost reporting must remain evidence-based. K3's Round 2 exact CNY cost was not captured, so the report records the observable 132k-token frontend subagent and balance termination without inventing a monetary estimate.

### 7.5 K3 vs K2.6 is the strongest partially controlled model comparison

Both use Kimi Code on the same baseline and task. K3 substantially improved on K2.6 in the exact areas that mattered most: Provider/Model interpretation, Run-scoped isolation, and per-model pricing. This pattern appeared first in Round 1 planning and then reappeared in Round 2 implementation, providing cross-round corroboration.

However, the provider path and reasoning configuration differ, so the result is still not a perfectly isolated model-only experiment.

## 8. Round 1 → Round 2 comparison

Round 1 planning ranking:

1. Claude Code + Opus 5
2. Cursor + Grok 4.6 Medium
3. Codex + GPT-5.6 Sol
4. Kimi Code + Kimi K3
5. Kimi Code + Kimi K2.6

Round 2 implementation ranking:

1. Kimi Code + Kimi K3
2. Claude Code + Opus 5
3. Codex + GPT-5.6 Sol
4. Kimi Code + Kimi K2.6
5. Cursor + Grok 4.6 Medium

The ranking reversal reinforces that planning quality, implementation correctness, validation discipline, convergence, cost, and product reliability are distinct dimensions. No single round should be interpreted as a universal model leaderboard.

## 9. Final system profiles

**Kimi Code + Kimi K3 — “correct but heavy.”**
Best canonical implementation in this round, especially on concurrency and pricing semantics. The major weakness is execution cost/latency and completion reliability under provider limits.

**Claude Code + Opus 5 — “deep but slow to converge.”**
Best-in-class repository and backend reasoning, but it expanded into a large implementation and stopped before final frontend cleanup, leaving a non-green repository.

**Codex + GPT-5.6 Sol — “compact, stable, and convergent.”**
The best scope/finish trade-off among completed runs. It made a small patch and finished cleanly, but did not pursue the full canonical edge-case/test matrix as deeply as K3/Claude.

**Kimi Code + Kimi K2.6 — “broad and test-driven, but can prove the wrong abstraction.”**
Very strong at implementing broadly and driving validation to green. The main weakness is requirement precision at the hardest semantic boundaries.

**Cursor + Grok 4.6 Medium — “strong planner, unmeasured implementer in this round.”**
Round 1 showed excellent plan quality and speed, but Round 2 cannot support an implementation-quality conclusion because quota exhaustion prevented any code change.

## 10. Limitations

- This is an end-to-end system benchmark, not a pure model or pure coding-harness benchmark.
- Products used different underlying models, provider paths, reasoning configurations, context-management strategies, system prompts, and tool implementations.
- Some duration, token, context, and cost measurements were unavailable and were intentionally not estimated.
- K3's exact Round 2 monetary cost is unavailable; high resource usage is inferred only from directly exposed token/tool/latency evidence and the eventual insufficient-balance termination.
- K2.6 and Claude were qualitatively long/heavy runs, but no invented wall-clock duration is reported without a reliable T0/T1.
- Uniform Playwright evaluation was partially blocked by a baseline/evaluator path issue, so only K2.6 achieved an operator-controlled Playwright result.
- More rounds with different task types are required before drawing durable general conclusions about any system.

## 11. Round conclusion

Round 2 shows that the most useful AI-coding evaluation cannot be reduced to “did it finish?” or “how many tests passed?”. The strongest result depended on four separate questions:

- Did the implementation satisfy the real requirement?
- Did the final repository remain healthy?
- Did the agent finish autonomously and cleanly?
- How much time, context, tokens, cost, and operational reliability did that result require?

On canonical correctness, **Kimi K3** is the Round 2 winner. On repository understanding, **Claude Opus 5** remains exceptionally strong but suffered from poor final convergence. On efficient completed delivery, **Codex GPT-5.6 Sol** stands out. **Kimi K2.6** demonstrated that broad green test coverage can still miss the core semantics of a requirement. **Cursor Grok 4.6 Medium** could not be meaningfully evaluated for implementation because quota exhaustion stopped the run before code changes.

The Round 2 result is therefore best understood as a set of distinct system profiles rather than a simple universal leaderboard.
