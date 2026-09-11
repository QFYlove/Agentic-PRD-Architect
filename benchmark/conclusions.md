# Cross-Round Conclusions

Conclusions are added here only when an observation is supported by multiple benchmark rounds or by a meaningfully controlled comparison.

## Current Status

The three-round core benchmark is complete.

- Round 1: repository understanding and planning only.
- Round 2: implementation and testing from one frozen canonical specification.
- Round 3: debugging and repair from one deliberately regressed seed.

Detailed round-specific findings remain in:

- `rounds/round-01-planning.md`
- `rounds/round-02-implementation.md`
- `rounds/round-03-debugging-repair.md`

ZCode + GLM-5.3 is tracked separately as a post-freeze extension. Its Round 1 extension is complete; its Round 2 extension remains incomplete and does not change the frozen original rankings.

## 1. Planning quality, implementation outcome, and repair quality are different signals

The rankings changed substantially across the three phases.

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

Round 3 debugging/repair ranking:

1. Claude Code + Opus 5
2. Codex + GPT-5.6 Sol
3. Kimi Code + Kimi K2.6

The ranking changes are evidence that repository understanding, architectural planning, implementation correctness, regression diagnosis, repair minimality, validation discipline, convergence, efficiency, and product reliability should be measured separately rather than collapsed into one proxy.

Claude produced the strongest Round 1 plan and the strongest overall Round 3 repair package, but its Round 2 run stopped before full-stack cleanup. K3 ranked only fourth in Round 1 planning but produced the strongest canonical implementation in Round 2. Codex was not the top system in any of the first two rounds, yet Round 3 showed a particularly strong combination of speed, minimality, and reviewability.

## 2. Kimi K3 vs K2.6 shows a repeated model-level difference under the same harness

Kimi Code + K2.6 and Kimi Code + K3 provide the strongest partially controlled comparison currently available because Round 1 and Round 2 held the following constant:

- Kimi Code 0.41.0;
- repository baseline;
- task prompt within each round;
- isolated worktrees;
- zero semantic manual interventions.

The provider path and reasoning configuration were not fully controlled, so this is not a perfectly isolated model-only experiment.

Despite that limitation, the same directional difference appeared in both rounds.

In Round 1, K3 interpreted the Provider/Model separation, Run-scoped isolation, and per-model pricing risks more precisely than K2.6. In Round 2, K3 then implemented the hardest of those requirements more faithfully: real different-pair concurrency isolation and actual selected-model pricing behavior. K2.6 produced broader green validation but its concurrency and pricing tests established weaker behavior than the canonical requirement.

Round 3 included K2.6 but not K3, so Round 3 adds no new controlled K3-vs-K2.6 evidence.

## 3. Deep reasoning and efficient convergence are separate product characteristics

Across the three rounds, the systems exhibit different trade-offs rather than one universal ordering on every dimension.

- **Claude** repeatedly demonstrates deep repository-specific reasoning. It won Round 1 and Round 3, but Round 2 exposed a convergence/cleanup cost: a large implementation remained unfinished and frontend regressions were left in the final worktree.
- **Codex** consistently favors compact, reviewable changes. In Round 2 it produced the smallest normally completed meaningful implementation; in Round 3 it produced the smallest correct repair and the fastest recorded completion at 361 sec. Its trade-off is thinner autonomous validation or edge-case coverage than the most exhaustive systems.
- **Kimi K3** produced the strongest Round 2 implementation correctness, but with high observable execution weight: a frontend subagent alone used 49m35s, 132k tokens, and 122 tool calls, and the overall run eventually stopped on insufficient provider balance.
- **Kimi K2.6** is strong at broad validation and reaching green gates, but Round 2 and Round 3 both show a tendency to optimize the visible validation surface even when semantic precision or scope discipline deserves separate scrutiny.
- **Cursor** demonstrated exceptional planning speed in Round 1, while Round 2 showed that product quota availability can dominate end-to-end task completion regardless of planning quality.

Accordingly, correctness, convergence, reviewability, efficiency, and product reliability should remain separate dimensions.

## 4. Green tests are necessary but not sufficient

Round 2 provided the clearest example: K2.6 achieved the strongest visible gate result, yet its “different selections” test used the same selection twice and its pricing tests validated availability rather than true selected-model pricing semantics.

Round 3 adds a smaller but related example. Kimi K2.6 made the full Ruff surface green by reformatting an unrelated pre-existing `test_node_timings.py` issue. The change was harmless, but it was outside the requested repair scope.

These results support two durable rules:

- passing tests do not prove that the tests encode the intended requirement;
- a coding agent should distinguish task regressions from baseline debt rather than treating every red check as mandatory task scope.

## 5. Repair correctness, repair ownership, and task closure are distinct

Round 3 is useful precisely because all three participating systems eventually achieved semantic acceptance.

Once correctness was equal, different engineering qualities became visible:

- Claude produced the strongest overall repair-and-verification package;
- Codex produced the cleanest minimal production diff;
- Kimi K2.6 produced the broadest fully green validation surface.

The event-cleanup repair illustrates ownership quality. Claude and Codex restored cleanup inside `_release_run_resources()`, while Kimi added event deletion separately at the known TTL and retention callers. Both behaviors passed the current acceptance criteria, but the centralized form is more robust to future callers.

The Codex result also shows that correct code and complete autonomous validation are separate signals. Operator evaluation later proved the patch correct, but the agent itself could not run the backend pytest suite in its local environment.

## 6. Benchmark difficulty must be described accurately

Round 3 should not be described as a fully hidden production-bug hunt.

The deliberately regressed seed already produced three backend test failures, including direct signals for the TTL and event-cleanup regressions. This reduced root-cause localization difficulty.

The repeated-restart persistence semantic was less directly covered and was checked after the runs with an independent acceptance probe. Because that probe was authored post-run, it is recorded as an independent acceptance check rather than a pre-frozen hidden test.

This distinction matters for benchmark credibility: methodology limitations should be preserved rather than retroactively hidden.

## 7. End-to-end results must not be attributed to the model alone

The benchmark compares observed system configurations, not isolated models or isolated harnesses. Products differ in model, provider path, reasoning behavior, context management, system prompts, tool implementations, permission flows, quotas, and other runtime characteristics.

The Kimi K2.6 vs K3 comparison is more controlled than the cross-product comparisons, but even it still differs in provider path and reasoning configuration.

Therefore the durable interpretation remains:

- compare end-to-end product outcomes directly;
- use controlled comparisons where possible;
- do not automatically attribute a cross-product difference to either the model or the coding harness alone;
- preserve quota, balance, environment, and permission failures as product-level evidence when they affect completion.

## 8. The core benchmark is now sufficient for the current objective

The three rounds cover three materially different coding-agent competencies:

1. **Planning** — repository understanding and architecture;
2. **Implementation** — non-trivial cross-stack feature delivery;
3. **Debugging & Repair** — fault reproduction, root-cause analysis, minimal repair, regression testing, and task closure.

Additional rounds would produce diminishing value for the current goal. The next higher-value phase is production integration: compare the strongest candidate changes by module, selectively port the best ideas and tests, and validate the resulting product independently of the benchmark.
