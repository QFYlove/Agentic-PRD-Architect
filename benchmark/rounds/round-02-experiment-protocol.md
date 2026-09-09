# Round 2 Experiment Protocol — Run-level Provider / Model Selection

Status: **Frozen for Round 2**
Round: `2`
Phase: `implementation`
Repository: `Agentic-PRD-Architect`
Baseline tag: `ai-coding-benchmark-v1`
Baseline commit: `0edc069`

Canonical spec SHA-256: `4c6c7bc167262b80c1957362fe818934b4ff9e5a54e0fe2892e46b7184fd8a68`
Exact implementation prompt SHA-256: `6964fefd330cd03e936a67623baf454c27ebf6a3dc314cbbcda470556b8891a0`

## 1. Objective

Measure how well each AI coding system implements the same non-trivial full-stack feature on the same real repository when given the same baseline, same canonical specification, and same implementation prompt.

Round 2 evaluates end-to-end product behavior rather than a pure harness-only or model-only effect.

## 2. Systems under test

| system_id | product | model | configuration to preserve where possible |
|---|---|---|---|
| `claude-opus5` | Claude Code | Opus 5 | Claude Code `2.1.251.1`; reasoning unknown |
| `codex-gpt56-sol` | Codex | GPT-5.6 Sol | Codex `0.153.4`; internal OpenAI-compatible gateway; reasoning unknown |
| `cursor-grok46-medium` | Cursor | Grok 4.6 Medium | Cursor Coding Agent; reasoning `Medium` |
| `kimi-k26` | Kimi Code | Kimi K2.6 | Kimi Code `0.41.0`; internal OpenAI-compatible gateway; reasoning unknown |
| `kimi-k3` | Kimi Code | Kimi K3 | Kimi Code `0.41.0`; Kimi Open Platform; reasoning configuration recorded as observed |

If the actual product/model/version/provider path differs when Round 2 is run, record the observed value instead of silently normalizing it.

## 3. Frozen inputs

Round 2 freezes three inputs before the first implementation run:

1. Git baseline: `0edc069` (`ai-coding-benchmark-v1`).
2. Canonical specification: `benchmark/specs/round-02-canonical-spec.md`.
3. Exact implementation prompt: `benchmark/prompts/round-02-implementation.md`.

All systems receive the same implementation prompt content. The canonical specification is embedded verbatim in that prompt.

After the first valid Round 2 run starts, do not materially change the spec or prompt. A material requirement change requires a new round/sub-round or rerunning every system.

## 4. Prevent Round 1 / cross-system leakage

Each Round 2 system starts in a fresh coding-agent session.

Do not provide it with:

- its own Round 1 answer;
- another system's Round 1 answer;
- the Round 1 ranking/report;
- another system's Round 2 branch, transcript, raw output, or patch.

Round 1 influences Round 2 only through the frozen canonical specification.

## 5. Worktree preparation

Use the existing isolated worktrees:

| system_id | worktree | branch |
|---|---|---|
| `claude-opus5` | `Agentic-PRD-Architect-claude` | `bench/provider-claude` |
| `codex-gpt56-sol` | `Agentic-PRD-Architect-codex` | `bench/provider-codex` |
| `cursor-grok46-medium` | `Agentic-PRD-Architect-cursor` | `bench/provider-cursor` |
| `kimi-k26` | `Agentic-PRD-Architect-kimi` | `bench/provider-kimi` |
| `kimi-k3` | `Agentic-PRD-Architect-kimi-k3` | `bench/provider-kimi-k3` |

Immediately before a run, verify only the essentials:

- `HEAD == 0edc069`;
- `git status --porcelain` is empty;
- the correct worktree/branch is open;
- the intended coding product/model is selected;
- required local wrappers/environment needed to launch that product are available.

Static machine/environment information belongs in `benchmark/environment.md`; it does not need to be re-collected in full before every run.

Do not copy Round 2 benchmark-control files into an experimental worktree before T0 if doing so would dirty the worktree. Deliver the exact implementation prompt through the coding product instead.

## 6. Run order

No seeded/randomized order is required for Round 2.

Run the five systems in any convenient fixed order. Record the actual start date/time for each run, and do not change the spec, prompt, scoring rules, or intervention policy based on earlier results.

## 7. Timing

`T0` = the moment the exact Round 2 implementation prompt is submitted to the coding system.

`T1` = the earliest of:

- the system produces its final task-completion response;
- the system explicitly stops because of a blocker;
- the product irrecoverably terminates;
- the 120-minute safety ceiling is reached.

Duration is wall-clock `T1 - T0`, including repository reading, editing, tests, debugging, tool latency, and product-side waiting.

The **120-minute ceiling is a safety cutoff, not a performance target**. It exists only to prevent runaway/stuck sessions. If reached, preserve the worktree as-is and record the run as `partial`, `blocked`, or `failed` as appropriate.

## 8. Allowed agent behavior

During the timed run, the coding system may:

- inspect repository files;
- edit source code and tests;
- create source/test files required by the feature;
- run existing development, test, static, type, and build commands;
- repair its own failures autonomously.

It must not inspect other benchmark systems' outputs/worktrees or modify benchmark-control artifacts.

The prompt asks systems not to create commits. If one creates a commit anyway, record the deviation and still evaluate the final diff against `0edc069`; do not rewrite history during the timed run.

## 9. Manual intervention policy

A manual intervention is a user/operator message after the initial prompt that adds semantic guidance, correction, debugging advice, file hints, or implementation direction.

Examples that count include telling the system which file to edit, explaining how to fix an error, or restating a requirement to redirect its design.

Purely operational actions do not count as semantic interventions, for example approving an unavoidable permission prompt or sending a content-free continuation after a product-imposed boundary.

If the system asks a question already answered by the frozen specification, do not coach it. A neutral instruction such as “follow the canonical specification and make a reasonable repository-consistent choice for unspecified implementation details” adds no new design information and may be recorded as an operational continuation rather than a semantic intervention.

## 10. First test result

`first_test_result` records the first relevant automated test-suite execution after the system has made an implementation edit.

Allowed values:

- `pass`
- `fail`
- `infra_error`
- `not_run`

A formatter-only command does not count. A baseline test run before the first implementation edit does not count.

Record the actual command and short result in the Round 2 raw/run notes; `metrics.csv` stores only the normalized value.

## 11. Autonomous repair rounds

One autonomous repair round is:

1. a relevant automated validation fails;
2. the coding system changes the implementation without semantic user help;
3. it reruns a relevant validation.

Count one round when that validation is rerun. Several edits between one failure and the next validation rerun still count as one repair round.

## 12. Final test result

`final_test_result` describes the final validation state the system actually established before T1.

Allowed values:

- `pass`
- `fail`
- `infra_error`
- `not_run`

Do not infer a pass from the final prose response. Only record what was actually run.

## 13. Post-run operator evaluation

Do **not** build a large separate hidden-test framework before Round 2.

After every coding-system run has finished, evaluate all five final worktrees with the same operator-controlled process:

1. Run the repository's relevant full regression/static/type/build gates against each final worktree.
2. Review each implementation against the frozen canonical acceptance criteria.
3. If a critical canonical requirement cannot be established from those two steps, define a small targeted check derived only from the canonical spec, write it once before running it on any implementation, then apply that exact same check to all five worktrees.

The purpose is independent verification, not giving an agent another repair opportunity.

Do not feed post-T1 evaluator failures back to the coding system within Round 2.

No standalone evaluator framework or large hidden-test suite is required unless later evidence shows it is necessary.

## 14. Code metrics

After T1 and before human fixes, measure the final change relative to `0edc069`:

- `files_changed`
- `lines_added`
- `lines_deleted`

A reproducible procedure that includes untracked implementation files is:

```bash
git add -N .
git diff --name-only 0edc069 -- .
git diff --numstat 0edc069 -- .
git reset
```

The operator performs this only after T1; it is not part of the timed agent run.

## 15. Other metrics

Follow the existing benchmark methodology:

- **duration:** measured wall-clock seconds;
- **context:** only displayed active context usage when explicitly exposed;
- **tokens:** only explicitly exposed input/output token usage;
- **cost:** only actual measured cost;
- **manual interventions:** semantic guidance messages only;
- **completion status:** `completed`, `partial`, `blocked`, or `failed`.

Never estimate missing measurements.

## 16. Evidence to preserve

For each run preserve enough evidence to audit the result:

- exact initial prompt;
- full final transcript/output where exportable;
- T0/T1 or measured duration;
- observed product/model/version/provider/reasoning metadata;
- test/check commands and visible results;
- final `git status`;
- final Git diff/patch or reproducible diff reference;
- observable context/token/cost data.

## 17. Evaluation priority

Evaluate Round 2 in this order:

1. canonical correctness and critical safety/compatibility requirements;
2. post-run regression/evaluation result;
3. autonomy and manual intervention count;
4. scope discipline and reviewability;
5. efficiency: duration, code delta, and measured cost/tokens where available.

Speed alone must not outrank correctness.

Critical failures include credential/Base-URL leakage, explicit-selection fallback, concurrent Run cross-talk, missing selection persistence, breaking old SQLite compatibility, forbidden DDL migration, core Agent-loop/lifecycle regression, Mock nondeterminism, or allowing new UI Run creation without a valid catalog selection.

## 18. Re-run policy

Do not selectively rerun a system because its implementation quality was poor.

Restart a run only when the benchmark operator prepared the wrong baseline/environment or otherwise invalidated comparability before/during the attempt.

A product/model/provider failure during a correctly prepared timed run is part of the observed end-to-end result and should be recorded.

## 19. Minimal execution checklist

Before T0: verify clean `0edc069` worktree, correct branch, correct coding product/model, and exact frozen prompt.

During the run: do not provide semantic hints; note first test result and autonomous repair behavior; stop only at normal completion/blocker/product failure or the 120-minute safety ceiling.

After T1: freeze the worktree, preserve the output, measure the Git delta, record final validation state and observable usage/cost, then later apply the same post-run evaluation process to all five systems.
