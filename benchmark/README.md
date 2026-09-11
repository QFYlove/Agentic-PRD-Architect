# Agentic PRD Architect — AI Coding Benchmark

This directory contains a real-project benchmark of multiple AI coding systems working on Agentic PRD Architect.

## Systems

Original frozen five-system set:

- Claude Code + Opus 5
- Codex + GPT-5.6 Sol
- Cursor + Grok 4.6 Medium
- Kimi Code + Kimi K2.6
- Kimi Code + Kimi K3

Post-freeze extension system:

- ZCode + GLM-5.3

ZCode is tracked as an extension and does not retroactively change the frozen original Round 1 / Round 2 rankings.

## Benchmark Baseline

Git tag: `ai-coding-benchmark-v1`
Commit: `0edc069`

## Structure

- `methodology.md` — evaluation methodology and attribution limits
- `environment.md` — tool/model execution environments
- `metrics.csv` — quantitative measurements
- `prompts/` — exact benchmark prompts
- `specs/` — canonical implementation specifications
- `raw/` — unedited agent outputs, patches, evaluator logs, and run metadata
- `rounds/` — per-round analysis
- `conclusions.md` — conclusions supported across multiple rounds
- `HANDOFF.md` — operational state and continuation notes

## Current Rounds

### Round 1 — Repository Understanding & Planning

Status: **complete / frozen**

Task: design Run-level Provider / Model Selection without modifying the repository.

Planning-quality ranking:

1. Claude Code + Opus 5
2. Cursor + Grok 4.6 Medium
3. Codex + GPT-5.6 Sol
4. Kimi Code + Kimi K3
5. Kimi Code + Kimi K2.6

See `rounds/round-01-planning.md`.

#### Round 1 post-freeze extension — ZCode + GLM-5.3

Status: **complete**

ZCode Desktop App 3.11.2 + GLM-5.3 (`最高`) was run later against the same baseline and original Round 1 prompt. It completed in 188 sec with 0 semantic interventions and left the worktree clean.

This extension does not alter the frozen five-system Round 1 ranking. Its qualitative reference position is between Claude and Cursor.

See:

- `rounds/round-01-zcode-extension.md`
- `raw/round-01/zcode-glm53.md`

### Round 2 — Implementation

Status: **complete / frozen**

Task: implement Run-level Provider / Model Selection from one shared frozen canonical specification.

Implementation ranking under the frozen evaluation priority:

1. Kimi Code + Kimi K3
2. Claude Code + Opus 5
3. Codex + GPT-5.6 Sol
4. Kimi Code + Kimi K2.6
5. Cursor + Grok 4.6 Medium

See:

- `specs/round-02-canonical-spec.md`
- `prompts/round-02-implementation.md`
- `rounds/round-02-experiment-protocol.md`
- `rounds/round-02-implementation.md`

Round 2 showed that green tests are not sufficient evidence of requirement correctness, completion status is not a proxy for implementation quality, and product quota/provider reliability materially affects end-to-end task completion.

#### Round 2 post-freeze extension — ZCode + GLM-5.3

Status: **incomplete / blocked**

ZCode is being evaluated separately as a late extension against the same frozen Round 2 task. The run has already hit GLM-5.3 quota limits more than once and is not part of the frozen original Round 2 ranking.

Do not mix GLM-5.3-Flash or another model into the same extension run.

### Round 3 — Debugging & Repair

Status: **complete / frozen**

Task: diagnose and repair three deliberate regressions in Run lifecycle, SQLite recovery persistence, and TTL/retention resource cleanup.

Round 3 ranking:

1. Claude Code + Opus 5
2. Codex + GPT-5.6 Sol
3. Kimi Code + Kimi K2.6

All three systems achieved semantic acceptance and passed the independent repeated-restart acceptance probe. The differentiators were repair minimality, cleanup ownership, regression-test quality, validation closure, scope discipline, and efficiency.

Key results:

- Claude: 533 sec, 4 files, +142/-5, strongest overall debugging/verification package.
- Codex: 361 sec, 3 files, +27/-2, smallest and fastest recorded correct repair.
- Kimi K2.6: duration not recorded, 5 files, +111/-8, broad validation but minor scope creep and less centralized cleanup ownership.

Important limitation: the buggy seed already produced three backend test failures, so Round 3 is a regression-repair benchmark rather than a fully hidden fault-discovery benchmark.

See:

- `prompts/round-03-debugging-repair.md`
- `raw/round-03/manifest.yaml`
- `rounds/round-03-debugging-repair.md`

## Current Takeaway

The three-round core benchmark now covers a complete progression:

`Planning → Implementation → Debugging & Repair`

The results do not support a single universal winner across every dimension.

- Claude is strongest on deep repository reasoning and won Round 1 and Round 3, but Round 2 exposed convergence/cleanup risk.
- Codex is consistently compact and reviewable, with the best recorded Round 3 efficiency and strong convergence.
- Kimi K3 produced the strongest Round 2 implementation correctness, but with high execution weight and provider-balance risk.
- Kimi K2.6 is strong at broad validation and driving repositories to green, but Round 2 and Round 3 both show that green gates can coexist with weaker semantic precision or unnecessary scope.
- Cursor showed excellent Round 1 planning efficiency, but Round 2 quota exhaustion prevented implementation.

This benchmark evaluates observed end-to-end coding-system configurations, not isolated models or isolated harnesses. Cross-round claims are kept in `conclusions.md`; round-specific findings remain in their individual reports.
