# Cross-Round Conclusions

Conclusions are added here only when an observation is supported by multiple benchmark rounds or by a meaningfully controlled comparison.

## Current Status

Round 1 and Round 2 are complete.

- Round 1: repository understanding and planning only.
- Round 2: implementation and testing from one frozen canonical specification.

Detailed round-specific findings remain in:

- `rounds/round-01-planning.md`
- `rounds/round-02-implementation.md`

## 1. Planning quality and implementation outcome are not the same signal

The ranking changed substantially between the two rounds.

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

The reversal is evidence that repository understanding/planning, implementation correctness, final convergence, validation discipline, efficiency, and operational reliability should be measured separately rather than collapsed into one proxy.

Claude produced the strongest Round 1 plan and again demonstrated unusually deep repository-specific understanding in Round 2, but its Round 2 run stopped before full-stack cleanup. K3 ranked only fourth in Round 1 planning but produced the strongest canonical implementation in Round 2. Cursor ranked second in planning and was the fastest measured planner, but quota exhaustion prevented any Round 2 implementation.

## 2. Kimi K3 vs K2.6 shows a repeated model-level difference under the same harness

Kimi Code + K2.6 and Kimi Code + K3 provide the strongest partially controlled comparison currently available because both rounds held the following constant:

- Kimi Code 0.41.0;
- repository baseline;
- task prompt within each round;
- isolated worktrees;
- zero semantic manual interventions.

The provider path and reasoning configuration were not fully controlled, so this is not a perfectly isolated model-only experiment.

Despite that limitation, the same directional difference appeared in both rounds.

In Round 1, K3 interpreted the Provider/Model separation, Run-scoped isolation, and per-model pricing risks more precisely than K2.6. In Round 2, K3 then implemented the hardest of those requirements more faithfully: real different-pair concurrency isolation and actual selected-model pricing behavior. K2.6 produced broader green validation but its concurrency and pricing tests established weaker behavior than the canonical requirement.

This repeated pattern is stronger evidence than either round alone that the K3 configuration followed the intended architecture more precisely than the K2.6 configuration in this benchmark.

## 3. Deep reasoning and efficient convergence are separate product characteristics

Across the first two rounds, the systems exhibit different trade-offs rather than one universal ordering on every dimension.

- Claude repeatedly demonstrates deep repository-specific reasoning, but Round 2 exposed a convergence/cleanup cost: a large implementation remained unfinished and frontend regressions were left in the final worktree.
- Codex showed strong architecture/security reasoning in Round 1 and the most compact, normally completed meaningful implementation in Round 2. Its trade-off was thinner coverage of the full canonical edge-case matrix.
- K3 produced the strongest Round 2 implementation correctness, but with high observable execution weight: a frontend subagent alone used 49m35s, 132k tokens, and 122 tool calls, and the overall run eventually stopped on insufficient provider balance.
- Cursor demonstrated exceptional planning speed in Round 1, while Round 2 showed that product quota availability can dominate end-to-end task completion regardless of planning quality.

Accordingly, future rounds should continue keeping correctness, convergence, reviewability, efficiency, and product reliability as separate dimensions.

## 4. End-to-end results must not be attributed to the model alone

The benchmark compares observed system configurations, not isolated models or isolated harnesses. Products differ in model, provider path, reasoning behavior, context management, system prompts, tool implementations, permission flows, quotas, and other runtime characteristics.

The Kimi K2.6 vs K3 comparison is more controlled than the cross-product comparisons, but even it still differs in provider path and reasoning configuration.

Therefore the durable interpretation remains:

- compare end-to-end product outcomes directly;
- use controlled comparisons where possible;
- do not automatically attribute a cross-product difference to either the model or the coding harness alone;
- require more rounds and different task types before making broad general claims.
