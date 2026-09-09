# Benchmark Environment

Last updated: 2026-09-09

> This file records static execution environment information.
> Per-run measurements such as duration, context usage and cost are stored in `metrics.csv`.

## Baseline

Git tag: `ai-coding-benchmark-v1`
Commit: `0edc069`

## Systems

### Claude Code

- Version: 2.1.251.1
- Model: Opus 5
- Interface: CLI

### Codex

- Version: 0.153.4
- Model: GPT-5.6 Sol
- Interface: Codex CLI
- Provider: internal OpenAI-compatible gateway

### Kimi Code — K2.6

- Version: 0.41.0
- Model: Kimi K2.6
- Interface: CLI
- Provider: internal OpenAI-compatible gateway

### Kimi Code — K3

- Version: 0.41.0
- Model: Kimi K3
- Interface: CLI
- Provider: Kimi Open Platform
- API mode: OpenAI-compatible Chat Completions
- Model endpoint: `kimi-k3`
- Reasoning: always enabled; API default `max`

### Cursor

- Model: Grok 4.6 Medium
- Interface: Cursor Coding Agent