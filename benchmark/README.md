# Agentic PRD Architect — AI Coding Benchmark

This directory contains a real-project benchmark of multiple AI coding systems working on Agentic PRD Architect.

## Systems

Original frozen five-system set:

- Claude Code + Opus 5
- Codex + GPT-5.6 Sol
- Cursor + Grok 4.6 Medium
- Kimi Code + Kimi K2.6
- Kimi Code + Kimi K3

Post-freeze extension systems:

- ZCode + GLM-5.3

## Benchmark Baseline

Git tag: `ai-coding-benchmark-v1`
Commit: `0edc069`

## Structure

- `methodology.md` — evaluation methodology and attribution limits
- `environment.md` — tool/model execution environments
- `metrics.csv` — quantitative measurements
- `prompts/` — exact benchmark prompts
- `specs/` — canonical implementation specifications
- `raw/` — unedited agent outputs and run metadata
- `rounds/` — per-round analysis
- `conclusions.md` — conclusions supported across multiple rounds

## Current Rounds

### Round 1 — Repository Understanding & Planning

Status: **complete**

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

See `rounds/round-01-zcode-extension.md`.

### Round 2 — Implementation

Status: **complete / frozen**

Task: implement the same feature from one shared frozen canonical specification.

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

Round 2 should not be interpreted as a pure model leaderboard. It evaluates the observed coding-system configurations end to end, including model, harness/product, provider path, reasoning configuration, tool use, context management, quotas, and execution reliability.

## Current Takeaway

The first two rounds show that planning quality, implementation correctness, test-gate success, convergence, efficiency, and product reliability are distinct signals. Cross-round claims are kept in `conclusions.md`; round-specific findings remain in their individual round reports.
