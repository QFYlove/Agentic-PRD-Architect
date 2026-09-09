# Round 2 Chat Start Prompt

我在做一个长期的 AI Coding benchmark，项目是 `Agentic-PRD-Architect`。

Round 1 已经完成并封版。现在开始 Round 2 implementation。

请把我上传的这些文件当作当前工作的事实来源和约束：

- `benchmark/HANDOFF.md`
- `benchmark/methodology.md`
- `benchmark/specs/round-02-canonical-spec.md`
- `benchmark/rounds/round-02-experiment-protocol.md`
- `benchmark/prompts/round-02-implementation.md`

工作方式要求：

1. 先阅读这些文件，再继续当前 Round 2；不要重新设计已经冻结的 benchmark 规则。
2. 不要为了“更严谨”自行增加新的实验变量、随机 run order、额外时间限制、大型 hidden evaluator、额外 benchmark 基础设施或新的 metrics 字段。你认为有必要增加任何规则时，先解释必要性并征求我的同意。
3. 保持方案简单、可操作。优先告诉我“下一步具体做什么”，不要一次让我搭很多额外东西。
4. `round-02-canonical-spec.md` 是五个 coding systems 的统一实现要求；不要让不同系统按自己的 Round 1 方案实现。
5. `round-02-experiment-protocol.md` 是我们的操作规则；不要擅自修改它。
6. 五个系统都从 `ai-coding-benchmark-v1` / `0edc069` 的干净独立 worktree 开始。
7. Round 2 的 coding-agent session 必须是 fresh session，不能给它们 Round 1 原始答案、排名或其他系统实现。
8. Benchmark operator 不需要在开跑前搭一套大型额外测试系统。Agent 按 canonical spec 自己实现并补测试；五个系统全部结束后，再用同一套项目回归门禁 + canonical acceptance checklist 做独立评估；只有关键要求无法判断时，才补一个小型 targeted check，并对五个实现完全一致地执行。
9. 缺失的 duration/token/context/cost 不要估算。
10. 如果我发终端输出，请先判断当前状态，再给我最少且明确的下一步命令。

当前目标：

先确认 Round 2 三个冻结文件和五个 worktree 状态正确，然后按 protocol 启动第一个 implementation run。不要继续扩展 benchmark 设计，除非发现明确矛盾或阻塞。
