# PRD Quality Benchmark

**Status:** P3 收尾完成，待人工审核。rubric-v0.4、用例 v0.3、Judge Prompt v0.1。PQB-P07 已做技术冻结（`cases/freeze/PQB-P07.yaml`，尚待人工签署 `confirmed_by`），其余用例仍为 draft。尚未发起任何真实模型或 Judge 调用，尚无真实结果；Judge Prompt 没有经过真实模型或人工校准。

本 Benchmark 独立于 `benchmark/`（AI Coding Benchmark）。两者不共享数据、配置、结果或排名，本目录的任何内容都不改变 `benchmark/` 下已冻结的记录。

## 研究问题

在相同需求输入和可比模型条件下，相比单 Agent 一次性生成 PRD，Agentic PRD Architect 现有的多 Agent 工作流能否提升需求覆盖率、正确性、业务流程完整性、异常处理能力和可执行性？这些收益对应多少额外 Token、耗时和成本？

## 第一阶段条件

| 条件 | 含义 |
|---|---|
| A | 单 Agent 一次性生成：与工作流 v1 相同的 Generator prompt、参数和完整性校验，只调用一次生成（含同样的重试策略） |
| B | 完整工作流：Generator → Tech/UX/Biz 并行评审 → Aggregator → Optimizer 循环，门槛 85 分、最多 3 轮 |

B 的主要结果是 `best_version`，同时分别记录和报告最后一个版本与 v1。`B.best − A` 衡量的是完整产品策略的效果，不代表多 Agent 架构的独立因果贡献。详见 [methodology.md](methodology.md)。

## 文件

| 文件 | 内容 |
|---|---|
| [methodology.md](methodology.md) | 研究设计、变量控制、度量口径、已知度量缺口、解释边界 |
| [experiment-protocol.md](experiment-protocol.md) | 审批闸门、运行步骤、调用记录字段、产物布局、失败与重跑规则、盲评流程 |
| [rubric.md](rubric.md) | 评分规则（`rubric-v0.4`）、严重缺陷门槛、程序/Judge/人工职责划分 |
| [config/pilot.yaml](config/pilot.yaml) | Pilot 配置（模型 `deepseek-flash`，浮动别名；所有审批开关关闭） |
| [cases/](cases/) | 8 个 Pilot 用例及金标准（v0.3）；P07 单独冻结，冻结清单在 `cases/freeze/`，其余 draft |
| [prompts/system-prompt.md](prompts/system-prompt.md) | 正式 Judge 系统指令（`judge-prompt-v0.1`），由 `judge_prompt.py` 与 Rubric 第 4 节、输出 Schema、用例金标准组装 |
| [calibration/](calibration/) | 离线校准样例：固定 Judge 响应 + 人工计算的预期结果，用于检验解析、引用校验、评分、去重和人工裁定流程 |
| [p3-readiness.md](p3-readiness.md) | P3 实验准备清单（v0.4）：Claude Code Judge 运行方式与隔离边界、认证检查结果、价格快照、预算预留与停止条件、调用预算、校准与匿名评审、批准清单 |
| [manual-judge-runbook.md](manual-judge-runbook.md) | 人工触发的 IDE Judge 操作手册：导出匿名任务、隔离会话、元数据填写、导入 |
| [price_snapshots/](price_snapshots/) | 官方价目表草稿快照（未经人工核对，真实运行前必须改为 verified） |
| [calibration_set/](calibration_set/) | Judge 校准用的两个独立用例和两份完整 PRD（不属于 Pilot，尚未人工评分）；[runbook.md](calibration_set/runbook.md) 为人工校准操作说明 |
| `*.py`、[tests/](tests/) | 运行框架与测试 |

## 运行（仅模拟模式）

在仓库根目录、使用产品的虚拟环境执行。`--output-root` 指向临时目录可以避免在本目录留下演练产物。

```bash
./.venv/bin/python -m prd_benchmark.cli validate
./.venv/bin/python -m prd_benchmark.cli run    --batch-id dryrun-001 --mode fake --output-root /tmp/pqb
./.venv/bin/python -m prd_benchmark.cli judge  --batch-id dryrun-001 --judge mock --output-root /tmp/pqb
./.venv/bin/python -m prd_benchmark.cli report --batch-id dryrun-001 --output-root /tmp/pqb
```

`--mode fake` 使用进程内的模拟服务，驱动产品真实的 Provider 与工作流代码，不访问网络；`--judge mock` 的判定由哈希生成。二者产出的分数没有质量含义，报告顶部会标注。`--mode real` 与 `--judge real` 在当前配置下一律拒绝（见 [experiment-protocol.md](experiment-protocol.md) 第 0 节）。

检查与测试（不在产品默认的 pytest / ruff / mypy 范围内，需要显式指定路径）：

```bash
./.venv/bin/ruff format --check prd_benchmark && ./.venv/bin/ruff check prd_benchmark
./.venv/bin/mypy prd_benchmark
./.venv/bin/python -m pytest -p no:cacheprovider prd_benchmark/tests
```

## 结果的地位

自动评分（程序化检查和 LLM Judge）是待复核的证据，不是客观真值。报告中的每个分数都标明来源：`auto`、`partially_reviewed` 或 `human_reviewed`。第一阶段每个用例只运行一次，结论只能是描述性的，不做显著性宣称。
