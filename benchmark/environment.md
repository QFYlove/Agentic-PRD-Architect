# Benchmark Environment

Last updated: 2026-09-10

> This file records stable/reference execution-environment information. Per-run measurements such as duration, context usage, cost, completion status, and observed runtime deviations belong in `metrics.csv` and the round report.

## Baseline

Git tag: `ai-coding-benchmark-v1`
Commit: `0edc069`

## Systems

### Claude Code

- Reference/frozen Round 2 configuration version: 2.1.251.1
- Round 2 observed installed version: 2.1.258.1
- Model: Opus 5
- Interface: CLI
- Reasoning: not exposed / unknown

### Codex

- Version: 0.153.4
- Model: GPT-5.6 Sol
- Interface: Codex CLI
- Provider: internal OpenAI-compatible gateway
- Reasoning: not exposed / unknown

Round 2 operational note: permission mode was changed from Ask to “Approve for me” during execution. This was treated as an operational runtime deviation, not a semantic manual intervention.

### Kimi Code — K2.6

- Version: 0.41.0
- Model: Kimi K2.6
- Interface: CLI
- Provider: internal OpenAI-compatible gateway
- Reasoning: not exposed / unknown

### Kimi Code — K3

- Version: 0.41.0
- Model: Kimi K3
- Interface: CLI
- Provider: Kimi Open Platform
- API mode: OpenAI-compatible Chat Completions
- Model endpoint: `kimi-k3`
- Reasoning: always enabled; API default `max`

### Cursor

- Version: unknown
- Model: Grok 4.6 Medium
- Interface: Cursor Coding Agent
- Provider: Cursor
- Reasoning: Medium

### ZCode — Round 1 post-freeze extension

- Version: 3.11.2
- Model: GLM-5.3
- Interface: ZCode Desktop App
- Provider: not exposed / unknown
- Reasoning: UI setting `最高` (`highest`)
- Round 1 extension permission mode: `变更前确认` (`confirm-before-changes`)

## Round 2 Operator-Evaluator Environment Notes

The uniform Playwright evaluation exposed a shared baseline/configuration path issue on Cursor baseline, Codex, Claude, and K3:

`.venvScriptspython.exe: command not found`

Those Playwright results are recorded as evaluator `infra_error`, not implementation failures.

The Cursor worktree initially lacked local evaluation dependencies. Temporary symlinks to an existing evaluator `.venv` and `node_modules` were used only to execute the same read-only gate set against the unchanged baseline worktree. The symlinks were removed afterward and did not count toward Cursor's code delta.
