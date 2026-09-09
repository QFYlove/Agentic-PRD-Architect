# Round 2 Experiment Protocol — Run-level Provider / Model Selection

Status: **Frozen candidate for Round 2**  
Round: `2`  
Phase: `implementation`  
Repository: `Agentic-PRD-Architect`  
Baseline tag: `ai-coding-benchmark-v1`  
Baseline commit: `0edc069`

Canonical spec SHA-256: `38dfcc7f745f8f0d9029164295cc88b029a1beee42adddbae97eab8ccfeffa9f`  
Exact implementation prompt SHA-256: `4606e0c392fae4bb901b5934db5bf0cd0bb55d9e11f857f3cac6c9ce935e2764`

## 1. Objective

Measure how well each AI coding system implements the same non-trivial full-stack feature on the same real repository when given the same requirements and baseline.

Round 2 evaluates end-to-end product behavior, including:

- repository understanding;
- requirement adherence;
- implementation quality;
- testing and debugging;
- autonomous repair;
- backward compatibility;
- security-sensitive requirement handling;
- concurrency correctness;
- reviewability;
- completion efficiency.

The experiment compares observed product configurations. Cross-product differences MUST NOT be described as pure harness-only or pure model-only effects.

## 2. Systems under test

| system_id | product | model | Round 1 harness/config information to preserve where possible |
|---|---|---|---|
| `claude-opus5` | Claude Code | Opus 5 | Claude Code `2.1.251.1`; reasoning not exposed/unknown |
| `codex-gpt56-sol` | Codex | GPT-5.6 Sol | Codex `0.153.4`; provider `internal-openai-compatible-gateway`; reasoning unknown |
| `cursor-grok46-medium` | Cursor | Grok 4.6 Medium | harness version unknown; reasoning `Medium` |
| `kimi-k26` | Kimi Code | Kimi K2.6 | Kimi Code `0.41.0`; internal OpenAI-compatible gateway; reasoning unknown |
| `kimi-k3` | Kimi Code | Kimi K3 | Kimi Code `0.41.0`; Kimi Open Platform; `max-default` |

Before each run, record the actually observed product version, model, provider path, and reasoning setting. If a product cannot be pinned to the Round 1 version/configuration, record the difference rather than estimating or silently normalizing it.

Do not change a system's model or reasoning setting after its Round 2 timer starts.

## 3. Experimental inputs to freeze

Round 2 has three frozen inputs:

1. Git baseline: `0edc069` (`ai-coding-benchmark-v1`).
2. Canonical feature spec: `benchmark/specs/round-02-canonical-spec.md` with the SHA-256 above.
3. Exact implementation prompt: `benchmark/prompts/round-02-implementation.md` with the SHA-256 above.

All systems MUST receive the exact same implementation prompt bytes/content. The canonical specification is embedded verbatim in that prompt.

If the canonical spec changes before the first Round 2 run:

- regenerate the exact prompt;
- recompute both hashes;
- update this protocol;
- freeze again.

After the first Round 2 run begins, the spec and prompt MUST NOT change. Any material requirement change requires either rerunning every Round 2 system from scratch or creating a new benchmark round/sub-round.

## 4. Prevent Round 1 leakage

Each Round 2 system MUST start in a fresh conversation/session.

Do NOT provide a Round 2 implementation system with:

- its own Round 1 planning answer;
- another system's Round 1 answer;
- Round 1 qualitative ranking;
- Round 1 comparison report;
- another system's Round 2 branch/worktree;
- another system's raw transcript or patch.

Round 1 influences Round 2 only through the frozen canonical spec.

Repository-level instructions that are part of the `0edc069` baseline, such as `AGENTS.md`, remain available equally to all systems.

## 5. Worktree isolation and baseline preparation

Use the existing independent worktrees/branches:

| system_id | worktree | branch |
|---|---|---|
| `claude-opus5` | `Agentic-PRD-Architect-claude` | `bench/provider-claude` |
| `codex-gpt56-sol` | `Agentic-PRD-Architect-codex` | `bench/provider-codex` |
| `cursor-grok46-medium` | `Agentic-PRD-Architect-cursor` | `bench/provider-cursor` |
| `kimi-k26` | `Agentic-PRD-Architect-kimi` | `bench/provider-kimi` |
| `kimi-k3` | `Agentic-PRD-Architect-kimi-k3` | `bench/provider-kimi-k3` |

Immediately before each run, verify:

- `git rev-parse HEAD` resolves to `0edc069`;
- the worktree contains no implementation changes from Round 1 or an earlier Round 2 attempt;
- `git status --porcelain` is empty;
- no other benchmark system's outputs are reachable through copied files in that worktree;
- the same baseline dependency lockfiles are present.

The canonical spec/prompt should be stored by the benchmark controller/main benchmark record and delivered as the exact prompt. Do not pre-copy new benchmark-control files into an experimental worktree if doing so would make its Git working tree differ from `0edc069` at T0.

If a worktree is not clean, restore/recreate it from `0edc069` before starting the timed run.

## 6. Environment preflight

Before the timed prompt is submitted, record:

- OS and architecture;
- relevant runtime versions;
- product/harness version;
- selected model;
- provider path if observable;
- reasoning setting if observable;
- relevant application/test environment mode;
- whether repository dependencies are already installed;
- any known baseline test failure.

Use the same application environment and test fixtures for all systems wherever the products allow it.

Do not expose API keys, bearer tokens, private Base URLs, or other secrets in benchmark raw logs.

If baseline tests are run as a preflight, run the same frozen preflight commands for every worktree. Preflight time is not included in the agent task duration.

A failure caused by the benchmark operator preparing the wrong baseline/environment invalidates that attempt and should be restarted from a fresh baseline. A product/model/provider failure occurring during the actual timed run is part of the observed end-to-end result and should be recorded rather than manually hidden.

## 7. Run order

To reduce operator/order bias, use the following deterministic shuffled order, generated once from seed `round-02-20260909`:

1. `kimi-k3`
2. `codex-gpt56-sol`
3. `kimi-k26`
4. `cursor-grok46-medium`
5. `claude-opus5`

Do not reorder systems based on early results.

## 8. Start condition and timing

Use a new session for the selected system and point it only at its designated clean worktree.

`T0` is the moment the exact Round 2 implementation prompt is submitted to the system.

Duration is wall-clock time from `T0` to `T1`, including:

- repository reading performed by the agent;
- editing;
- command execution;
- tests;
- debugging;
- tool latency;
- product-side waiting during the task.

Operator preflight before `T0` is excluded.

### Hard ceiling

Round 2 has a **60-minute wall-clock ceiling per system**.

If a system has not produced a final completion response by 60 minutes:

- stop the run at the ceiling;
- preserve the worktree exactly as-is;
- set `completion_status` to `partial` unless a clearer `blocked`/`failed` state applies;
- record `timeout_60m` in notes;
- do not give the agent extra time unless every system is rerun under a revised protocol.

## 9. Allowed agent behavior

During the timed run, the agent may:

- read repository files;
- search the repository;
- edit source code and tests;
- run existing development/test/static/type/build commands;
- create new source/test files required by the feature;
- repair its own failures autonomously.

The agent must follow the exact prompt and repository instructions.

It must not inspect other benchmark systems' outputs or branches/worktrees.

The prompt asks agents not to create commits. If a system creates one anyway, do not rewrite history during the timed run; record the protocol deviation and still measure the final diff against `0edc069`.

Dependency changes are discouraged by the canonical spec. If an agent changes dependency manifests/lockfiles, preserve and count those changes and review them as part of scope/reviewability rather than manually undoing them.

## 10. Manual intervention policy

A **manual intervention** is any user/operator message after the original prompt that provides additional semantic guidance, correction, requirements, file hints, debugging advice, or implementation direction.

Examples that count:

- telling the agent which file to edit;
- explaining an error or suggesting a fix;
- restating a requirement to redirect the implementation;
- answering a design question with new guidance;
- asking it to run a particular missing test after it otherwise would have stopped.

Record one intervention per guidance message.

### Operational actions that do not count as semantic interventions

The following do not increment `manual_interventions`, but should be noted separately in the raw run notes when material:

- clicking an unavoidable permission/approval control without adding guidance;
- acknowledging an OS permission dialog;
- a pure transport-level `continue` action that adds no task information after a product-imposed response boundary.

Wall-clock duration continues during such actions.

If an agent asks a question that the frozen spec already answers, avoid coaching it. If you choose to reply with semantic content anyway, count that reply as a manual intervention.

## 11. Stop condition

`T1` is the earliest of:

1. the agent produces its final task-completion response;
2. the agent explicitly states that it is blocked and cannot continue without user guidance;
3. the 60-minute hard ceiling is reached;
4. the product irrecoverably terminates the run.

At `T1`:

- stop all agent editing;
- preserve the final worktree;
- preserve the unedited transcript/raw output;
- do not feed evaluator failures back to the agent in Round 2.

Any post-`T1` human fixes are outside the Round 2 run and must not be included in that system's implementation result.

## 12. First test result

`first_test_result` measures the agent's first post-edit automated test execution against its implementation.

Use one of:

- `pass`
- `fail`
- `infra_error`
- `not_run`

Rules:

- An operator preflight test does not count.
- A test run performed by the agent before its first source/test edit is baseline exploration and does not count as the first implementation test.
- The first relevant post-edit pytest, contract-test, Vitest, or Playwright execution counts.
- A pure formatter command does not count.
- Record the exact command and a short unedited failure/pass summary in the raw notes/report even though `metrics.csv` stores only the normalized result.

Static/type/build checks should also be preserved in raw notes, but do not replace an actual test-suite result when an actual test was run.

## 13. Autonomous repair rounds

An **autonomous repair round** is one complete cycle in which:

1. an automated test/static/type/build validation reports a failure caused or exposed by the implementation;
2. the agent changes code/tests/config in response without receiving semantic user guidance;
3. the agent re-runs a relevant validation.

Count the cycle when the re-run occurs.

Multiple edits made between one failing validation and the next validation re-run count as one repair round.

If the user provides semantic debugging help between failure and repair, that cycle may still be documented, but it is no longer a purely autonomous repair and the guidance message increments `manual_interventions`.

## 14. Final test result

`final_test_result` describes the final known state of the relevant automated validations the agent actually ran before `T1`.

Use one of:

- `pass` — all relevant validations in the agent's final validation set passed;
- `fail` — at least one known relevant validation remained failing;
- `infra_error` — validation could not complete because of environment/tool failure;
- `not_run` — the agent completed/stopped without running a relevant automated test suite.

Do not infer a pass from a confident final message. Missing measurements are left missing/not-run rather than estimated.

## 15. Independent evaluator after T1

Agent self-tests are not sufficient for comparative correctness.

Before the first Round 2 agent run, freeze one operator-controlled evaluator derived from the canonical acceptance criteria. Apply the same evaluator to every final worktree after `T1`.

The evaluator should include, at minimum:

- baseline regression suites;
- backend catalog safety/contract checks;
- explicit valid/invalid Provider+Model creation checks;
- no-silent-fallback checks;
- old API compatibility;
- old SQLite snapshot compatibility with no DDL migration;
- persisted ID/display-name checks;
- concurrent Run isolation;
- per-model pricing and missing-price-null behavior;
- Mock/Scenario Mock determinism;
- frontend Loading/Empty/Error/selection behavior;
- Run/Telemetry metadata rendering;
- deterministic Playwright coverage without billable external model calls.

Do not tell an agent which evaluator case failed and then allow it to repair within the same Round 2 run.

Record evaluator commands and results in the Round 2 report. If the existing `metrics.csv` schema is kept unchanged, put the aggregate evaluator result in `notes`; if the schema is intentionally extended before the first run, use one consistent new evaluator-result field for all systems.

## 16. Code metrics

Measure code metrics after `T1`, relative to commit `0edc069`, before any human edits.

Required fields:

- `files_changed`
- `lines_added`
- `lines_deleted`

Include tracked and untracked implementation/test files. Do not count ignored runtime artifacts such as caches/build output that Git already ignores.

One reproducible measurement procedure is:

```bash
git add -N .
git diff --name-only 0edc069 -- .
git diff --numstat 0edc069 -- .
git reset
```

Interpretation:

- `files_changed` = unique paths from the name-only diff;
- `lines_added` / `lines_deleted` = sums from `--numstat`;
- binary files count as changed files but not textual line additions/deletions; note them separately.

The `git add -N` step is an operator measurement action performed only after `T1`; it is not part of the timed agent run.

If an agent improperly modifies benchmark-control files visible inside its worktree, those changes count and should additionally be noted as protocol/spec noncompliance.

## 17. Other metrics

Continue the existing methodology rules:

### Duration
Wall-clock `T1 - T0` in seconds.

### Context usage
Record displayed active context usage only if explicitly exposed. Do not interpret context occupancy as total token consumption.

### Tokens
Record input/output token usage only if explicitly exposed by the product/provider.

### Cost
Record only actual measured API cost. Do not estimate missing cost.

### Manual interventions
Count only semantic guidance messages as defined above.

### Completion status
Use:

- `completed` — agent delivered an implementation and declared the task complete;
- `partial` — meaningful implementation exists but the task was left incomplete, including timeout;
- `blocked` — agent could not proceed because of a blocking product/environment condition;
- `failed` — no usable implementation was produced.

`completion_status` records task completion, not independent evaluator correctness. Evaluator results must be reported separately.

## 18. Raw evidence preservation

For every system preserve, without editing:

- exact initial prompt;
- full agent transcript/output where exportable;
- start/end timestamps;
- product/model/reasoning/version metadata;
- permission/continuation actions if material;
- exact test commands and results visible in the transcript;
- final Git diff/patch;
- final `git status`;
- evaluator output;
- observable context/token/cost information.

Never fill an unavailable metric from guesswork.

## 19. Evaluation order

Do not rank implementations primarily by speed.

Evaluate in this order:

1. **Canonical correctness and critical safety/compatibility gates**.
2. **Independent evaluator results and regression status**.
3. **Autonomy** — manual interventions and autonomous repair behavior.
4. **Scope/reviewability** — unnecessary refactors, dependency churn, patch coherence.
5. **Efficiency** — wall-clock duration, code delta, and measured cost/tokens where available.

A faster implementation that violates a critical canonical requirement must not outrank a slower implementation solely because of duration.

### Critical failure examples

Treat the following as major correctness failures even if many ordinary tests pass:

- credential/private Base URL exposed to the frontend;
- explicit invalid selection silently falls back;
- concurrent Runs can overwrite each other's selection;
- new Run selection is not persisted;
- old SQLite data becomes unreadable or a forbidden SQL DDL migration is introduced;
- core Agent loop/lifecycle behavior is broken;
- Mock/Scenario Mock becomes nondeterministic;
- frontend can create a new Run while catalog is unavailable/empty/error without a valid pair.

## 20. Re-run policy

Do not selectively rerun a system because its implementation was poor.

A run may be invalidated and restarted only for a benchmark-operator/setup error that made the starting conditions non-comparable, such as the wrong commit or contaminated worktree.

If a product/model/provider itself fails during the correctly prepared timed run, preserve that outcome as part of the product experience unless the same external outage invalidates the entire comparison window.

If the spec, prompt, evaluator requirements, time ceiling, or material environment policy changes after any valid Round 2 run, rerun all systems or create a new separately labeled round/sub-round.

## 21. Round 2 execution checklist

Before each run:

- [ ] Fresh session with no Round 1 conversation context.
- [ ] Correct designated worktree/branch.
- [ ] `HEAD == 0edc069`.
- [ ] Clean Git status.
- [ ] Exact prompt hash matches the frozen value.
- [ ] Product/model/provider/reasoning/version recorded.
- [ ] No other Agent outputs available.
- [ ] Environment/preflight comparable.

During run:

- [ ] Record `T0`.
- [ ] Do not provide semantic hints unless intentionally accepting a manual intervention.
- [ ] Record unavoidable operational permission/continue actions separately.
- [ ] Capture first post-edit test result.
- [ ] Count autonomous repair rounds.
- [ ] Enforce 60-minute ceiling.

After run:

- [ ] Record `T1` and duration.
- [ ] Freeze worktree; no human fixes.
- [ ] Preserve raw output/transcript.
- [ ] Record final agent test state.
- [ ] Measure Git file/line delta from `0edc069`.
- [ ] Run the same frozen independent evaluator.
- [ ] Record completion status.
- [ ] Record context/tokens/cost only when actually observable.
- [ ] Update Round 2 metrics/report without estimating missing values.
