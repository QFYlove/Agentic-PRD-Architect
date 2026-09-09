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

## Experimental Controls

For each comparable run:

- All systems start from the same Git baseline.
- Each system uses an independent Git worktree.
- All systems receive the same task prompt.
- Systems cannot inspect other systems' outputs.
- No system receives system-specific hints unless recorded as a manual intervention.
- Raw outputs are preserved without editing.
- Missing measurements are not estimated.

## Attribution Limitation

Different products may use different underlying models, reasoning configurations, context-management strategies, system prompts and tools.

Therefore:

End-to-end outcomes may be directly compared as product experiences.

Differences must not automatically be attributed to the coding harness alone.

Where possible, controlled experiments are used to isolate individual variables.

FFor example:

Kimi Code + Kimi K2.6
vs.
Kimi Code + Kimi K3

holds the coding harness, repository baseline and task prompt constant while changing the underlying model.

However, the provider path and reasoning configuration are not fully controlled:
K2.6 was accessed through an internal OpenAI-compatible gateway, while K3 was accessed through Kimi Open Platform, and their reasoning configurations were not identical.

Therefore, this comparison provides stronger evidence about model-level effects than the cross-product comparisons, but it is not a perfectly isolated model-only experiment.

## Measurement Rules

### Duration

Wall-clock task duration.

### Context Usage

Displayed active context usage, if exposed by the product.

Context usage is not treated as total token consumption.

### Token Usage

Only recorded when explicitly exposed by the system or provider.

### Cost

Only actual measured API cost is recorded.

### Manual Intervention

Any user message after the original task prompt that provides additional guidance counts as one intervention.

### Code Metrics

For implementation rounds:

- files changed
- lines added
- lines deleted

are measured relative to the benchmark baseline.

### Testing

Implementation rounds record:

- first test result
- autonomous repair rounds
- final test result
