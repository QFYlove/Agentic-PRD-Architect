# Round 1 Extension — ZCode + GLM-5.3

Status: **completed — post-freeze extension**

Date: `2026-09-10`

Original frozen round: `Round 1 — Repository Understanding & Planning`

Original freeze tag: `ai-coding-benchmark-round1`

Baseline: `ai-coding-benchmark-v1` / `0edc069`

Prompt: `benchmark/prompts/round-01-planning.md`

Prompt SHA-256: `73db9b877cca5ac39bd338ea4672398470b68b042f0133904f4fd57e4e832149`

This run was added after the original five-system Round 1 result had already been frozen. It is therefore evaluated as an extension run. It may be compared with the original Round 1 results under the same task/baseline framing, but it does **not** rewrite the frozen Round 1 ranking.

## Configuration

- Product: ZCode Desktop App
- Version: `3.11.2`
- Model: `GLM-5.3`
- Provider: not exposed / unknown
- Reasoning setting: `最高` (`highest`)
- Permission mode: `变更前确认` (`confirm-before-changes`)
- Worktree: `Agentic-PRD-Architect-zcode`
- Branch: `bench/provider-zcode`
- Baseline commit: `0edc069`

The permission mode did not materially affect this planning-only run because no repository modifications were permitted or made.

## Measurements

| Metric | Result |
|---|---:|
| Duration | 188 sec (3m08s) |
| Semantic manual interventions | 0 |
| Files changed | 0 |
| Lines added | 0 |
| Lines deleted | 0 |
| Completion status | completed |
| Context / token usage | unavailable |
| Measured cost | unavailable |

After completion, `git status --short` returned no output, confirming the worktree remained clean.

## Evaluation

### Strengths

ZCode showed strong repository-specific understanding rather than producing a generic architecture proposal.

It correctly identified the process-level Provider singleton constructed in `create_app()`, the shared Provider held by `RunManager`, the existing global pricing configuration, the JSON-snapshot persistence strategy in SQLite, the current create-Run API shape, Telemetry coupling, frontend request path, and contract-test compatibility model.

Its proposed architecture covered the most important design risks that later became central to the Round 2 canonical specification:

- explicit Provider/Model identity;
- backend-controlled safe catalog metadata;
- strict invalid-selection failure with no silent fallback;
- Run-scoped Provider resolution;
- concurrent Run isolation;
- persisted Provider/Model identity and display metadata;
- old SQLite snapshot compatibility without SQL DDL migration;
- per-model pricing rather than applying one global price to every selected model;
- Mock / Scenario Mock preservation;
- frontend catalog loading/error handling;
- backend, contract, Vitest, Playwright and static/type/build coverage.

The risk section was also concrete. It called out the danger of missing one `workflow.py` Provider access and thereby accidentally executing a node with the default model, the migration of `is_mock` semantics from process-level to Run-level behavior, pricing regressions, contract compatibility, concurrency, and Scenario Mock construction.

### Limitations

The plan chose some API details differently from the canonical design that was frozen only later, including `GET /api/models` and a nested `model_selection` request object. These are not treated as Round 1 failures because the canonical Round 2 specification did not yet exist when the planning task was run.

The proposed configuration surface is also somewhat elaborate, including a custom per-provider model/pricing configuration format and broad documentation updates. That is implementable, but it introduces more configuration and migration surface than the most minimal design.

The frontend section briefly presented catalog failure as a choice between disabling submission and falling back to a default before recommending the stricter disabled state. The final recommendation is safe, but the intermediate ambiguity is weaker than stating the no-fallback UX invariant directly.

### Assessment

**Very strong planning with an unusually strong speed/depth trade-off.**

The run completed in 188 seconds, only 36 seconds slower than the fastest measured original Round 1 run (Cursor at 152 seconds), while surfacing more of the repository-specific pricing, Provider-access, persistence and regression-risk detail that distinguished the deepest plans.

## Reference position against the frozen Round 1 results

The original frozen ranking remains unchanged:

1. Claude Code + Opus 5
2. Cursor + Grok 4.6 Medium
3. Codex + GPT-5.6 Sol
4. Kimi Code + Kimi K3
5. Kimi Code + Kimi K2.6

For a **non-frozen extension comparison only**, ZCode + GLM-5.3 is best placed between Claude and Cursor:

1. Claude Code + Opus 5
2. **ZCode + GLM-5.3 — extension reference position**
3. Cursor + Grok 4.6 Medium
4. Codex + GPT-5.6 Sol
5. Kimi Code + Kimi K3
6. Kimi Code + Kimi K2.6

This reference placement is based on planning quality, not speed alone. It does not replace or amend the official five-system Round 1 ranking.

## Raw evidence

- Raw captured output: `benchmark/raw/round-01/zcode-glm53.md`
- Extension manifest: `benchmark/raw/round-01/zcode-extension-manifest.yaml`
- Raw SHA-256: `af05d19f44668903da9e4a735bc869e9ccac441ba11ccf2fc38be24001876c1d`
