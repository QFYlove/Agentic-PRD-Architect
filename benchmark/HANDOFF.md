# AI Coding Benchmark — Working Handoff

Last updated: 2026-09-09

## Project

Repository:

`Agentic-PRD-Architect`

Benchmark baseline:

- Tag: `ai-coding-benchmark-v1`
- Commit: `0edc069`

## Goal

Evaluate real AI coding systems on a real repository across multiple rounds.

Systems currently included:

- Claude Code + Opus 5
- Codex + GPT-5.6 Sol
- Cursor + Grok 4.6 Medium
- Kimi Code + Kimi K2.6
- Kimi Code + Kimi K3

The benchmark evaluates end-to-end system behavior rather than attempting to claim a pure harness comparison.

## Worktrees

Main:

`~/Documents/Agentic-PRD-Architect`

Experimental worktrees:

- `Agentic-PRD-Architect-claude`
- `Agentic-PRD-Architect-codex`
- `Agentic-PRD-Architect-cursor`
- `Agentic-PRD-Architect-kimi`
- `Agentic-PRD-Architect-kimi-k3`

Branches:

- `bench/provider-claude`
- `bench/provider-codex`
- `bench/provider-cursor`
- `bench/provider-kimi`
- `bench/provider-kimi-k3`

All experiments compare against:

`ai-coding-benchmark-v1`

## Benchmark Structure

`benchmark/README.md`
- benchmark overview

`benchmark/methodology.md`
- experimental methodology

`benchmark/environment.md`
- execution environment

`benchmark/metrics.csv`
- quantitative results

`benchmark/prompts/`
- exact prompts

`benchmark/raw/`
- unedited agent outputs

`benchmark/rounds/`
- per-round analysis

`benchmark/conclusions.md`
- cross-round conclusions

## Round 1

Task:

Run-level Provider / Model Selection — repository understanding and planning only.

No code modification was allowed.

Round 1 is complete.

Planning-quality ranking:

1. Claude Code + Opus 5
2. Cursor + Grok 4.6 Medium
3. Codex + GPT-5.6 Sol
4. Kimi Code + Kimi K3
5. Kimi Code + Kimi K2.6

Important limitation:

Different products used different models / providers / reasoning configurations, so the ranking represents observed end-to-end configurations rather than pure harness or pure model quality.

Kimi K2.6 vs K3 is more controlled because Kimi Code 0.41.0, repository baseline and prompt were held constant, but provider path and reasoning configuration still differed.

## Round 1 Measurements

Cursor + Grok 4.6 Medium:
- Duration: 152 sec
- Manual interventions: 0

Codex + GPT-5.6 Sol:
- Duration: 370 sec
- Manual interventions: 0

Claude Code + Opus 5:
- Duration: 753 sec
- Displayed context: 77.9k / 200k
- Manual interventions: 0

Kimi Code + K2.6:
- Displayed context: 126k / 256k
- Manual interventions: 0

Kimi Code + K3:
- API cost: CNY 6.50
- Duration/token/context unavailable
- Manual interventions: 0

Do not interpret displayed context occupancy as token consumption.

## Round 2

Next task:

Implementation of Run-level Provider / Model Selection.

Important:

Do NOT let each system implement its own Round 1 proposal.

First create one shared:

`benchmark/specs/round-02-canonical-spec.md`

All systems must receive the same specification and start from the same benchmark baseline.

Round 2 should measure at least:

- duration
- manual interventions
- files changed
- lines added/deleted
- first test result
- autonomous repair rounds
- final test result
- completion status
- context/token/cost when actually observable

## Canonical Feature Direction

The shared Round 2 specification should require:

- explicit `provider_id + model_id`
- backend-controlled safe catalog
- no frontend secrets/Base URLs
- strict invalid-selection failure
- no silent fallback
- Run-scoped Provider binding
- concurrent Run isolation
- Snapshot persistence of IDs + display names
- old API compatibility
- old SQLite compatibility
- no SQL DDL migration
- per-model pricing semantics
- missing price → null
- Mock / Scenario Mock determinism
- existing core Agent loop unchanged
- existing REST/SSE/pause/resume/cancel behavior unchanged
- catalog loading/empty/error disables new Run creation
- comprehensive backend/contract/Vitest/Playwright coverage

## Next Action

Create the Round 2 canonical specification before sending any implementation prompt to the coding agents.