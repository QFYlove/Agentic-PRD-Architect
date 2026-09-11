# Benchmark Methodology

## Evaluation Goal

This benchmark evaluates AI coding systems on a real software project rather than isolated synthetic coding problems.

The primary target is end-to-end product experience:

- repository understanding
- requirement following
- planning
- tool use
- implementation
- testing
- debugging
- autonomy
- reviewability
- completion efficiency
- operational reliability

## Round Design

The benchmark uses different task phases rather than repeating one task shape.

### Round 1 — Planning

Repository understanding and architecture planning only. No code modification was allowed.

### Round 2 — Implementation

Full-stack implementation from one frozen canonical specification and one frozen implementation prompt.

### Round 3 — Debugging & Repair

Existing-code maintenance from a deliberately regressed seed. Systems were expected to reproduce failures, locate root causes, make minimal correct repairs, add regression coverage, and validate the final repository.

The three-round progression is:

`Planning → Implementation → Debugging & Repair`

## Experimental Controls

For each comparable run:

- All systems start from the same relevant Git baseline.
- Each system runs in an isolated repository/worktree.
- All systems receive the same task prompt within that round.
- Systems cannot inspect other systems' outputs.
- No system receives system-specific semantic hints unless recorded as a manual intervention.
- Raw outputs and final patches are preserved without editing.
- Missing measurements are not estimated.
- Post-run operator evaluation is not fed back to agents for selective repair.

### Round 3 history isolation

Round 3 required an additional control because the seed contained deliberately injected regressions.

The three agent repositories were created from the buggy seed tree using an exported snapshot and then re-initialized as independent one-commit Git repositories. This prevented an agent from using parent history or `git diff HEAD^` to discover exactly which lines had been changed when constructing the seed.

The frozen Round 3 seed metadata is:

- original baseline: `0edc069`
- buggy seed commit: `07445c45d3a28692524f6cd53676f004523b0424`
- buggy seed tree: `06938442d66bb9f04b904cdb2306e2dbb19a2cef`

## Attribution Limitation

Different products may use different underlying models, reasoning configurations, context-management strategies, system prompts, tools, permission systems, and provider paths.

Therefore:

- end-to-end outcomes may be directly compared as product experiences;
- differences must not automatically be attributed to the coding harness alone;
- differences must not automatically be attributed to the model alone;
- controlled comparisons should be used where possible.

For example:

Kimi Code + Kimi K2.6
vs.
Kimi Code + Kimi K3

holds the coding harness, repository baseline, and task prompt constant for Round 1 and Round 2 while changing the underlying model.

However, the provider path and reasoning configuration are not fully controlled: K2.6 was accessed through an internal OpenAI-compatible gateway, while K3 was accessed through Kimi Open Platform, and their reasoning configurations were not identical.

Therefore, this comparison provides stronger evidence about model-level effects than the cross-product comparisons, but it is not a perfectly isolated model-only experiment.

## Measurement Rules

### Duration

Wall-clock task duration is measured from prompt submission (`T0`) to the first explicit normal completion or blocker (`T1`) when those timestamps are reliably captured.

If a run later continues after a quota reset, waiting time is not silently folded into active execution time. Initial blocker time and continuation time should be recorded separately.

Missing duration is not estimated.

### Context Usage

Displayed active context usage, if exposed by the product.

Context usage is not treated as total token consumption.

### Token Usage

Only recorded when explicitly exposed by the system or provider.

### Cost

Only actual measured API/provider cost is recorded.

Missing monetary cost is not inferred from token estimates.

### Manual Intervention

Any user message after the original task prompt that provides additional semantic guidance counts as one intervention.

Permission approvals or mode changes that only unblock tool execution are operational events, not semantic interventions, but should still be documented when relevant.

### Code Metrics

For implementation or repair rounds:

- files changed
- lines added
- lines deleted

are measured relative to the relevant frozen round baseline.

### Testing

Implementation and repair rounds record, where available:

- first relevant test result
- autonomous repair rounds
- final agent-side test result
- operator-controlled post-run evaluator result

Agent-side validation and operator-side validation are recorded separately. Operator success does not retroactively convert a weak agent-side task closure into strong autonomous validation.

## Baseline Normalization

Pre-existing failures are not automatically attributed to an agent.

The relevant baseline/seed should be evaluated with the same command where practical. If the same failure exists before the agent change, it is recorded as baseline debt rather than a feature regression.

Round 3 provides a concrete example: `backend/tests/test_node_timings.py` already failed Ruff formatting/import-order checks in the buggy seed. Claude and Codex retained that same issue, so it is baseline-attributed. Kimi K2.6 fixed it, but receives no task-correctness credit for unrelated cleanup.

## Requirement-Level Review

Passing tests are not treated as sufficient evidence of requirement correctness.

When the benchmark contains a frozen canonical requirement, evaluator review must check whether tests and implementation actually establish that semantic behavior.

Round 2 demonstrated why this matters: broad green validation did not prove real different-pair concurrency or true selected-model pricing.

## Independent Acceptance Checks

A post-run acceptance probe may be used to clarify a frozen requirement that existing tests did not adequately exercise, but it must be labeled accurately.

For Round 3, the repeated-restart persistence probe was authored after the agent runs. It is therefore recorded as an **independent post-run acceptance check**, not as a pre-frozen hidden test.

The probe was never supplied back to an agent for repair.

## Evaluator Contamination

An evaluator-induced environment failure is discarded rather than attributed to an agent.

During the first Round 3 Kimi frontend evaluation, a temporary backup dependency directory named `node_modules.round3-backup` was placed inside the repository tree. Astro scanned that dependency tree, producing invalid diagnostics and excessive resource usage.

That attempt is not counted. After restoring the repository, the same frontend gates were run normally and passed.

## Benchmark Difficulty Disclosure

A benchmark report must preserve facts that make a task easier or harder than originally intended.

Round 3's buggy seed already produced three backend test failures. Two planted regressions therefore had strong existing localization signals. Round 3 is described as a regression-repair benchmark, not as a fully hidden fault-discovery benchmark.

## Frozen-Result Rule

Once a round is frozen:

- do not selectively rerun a system to improve its ranking;
- do not feed operator-discovered failures back to only one agent;
- do not rewrite the canonical specification or evaluation criteria after seeing results;
- extension runs must be labeled separately and must not retroactively alter the original frozen ranking.

## Production Integration Rule

Benchmark branches, worktrees, or deliberate buggy seeds are evidence artifacts, not production merge candidates by default.

After the benchmark:

- compare candidate diffs by module and behavior;
- selectively port or reimplement the strongest changes;
- preserve useful regression tests;
- do not wholesale merge the deliberately buggy Round 3 seed;
- run an independent product-level acceptance pass before merging into the formal product branch.
