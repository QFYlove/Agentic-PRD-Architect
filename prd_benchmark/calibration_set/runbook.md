# P91、P92 人工校准操作说明

**Status:** 草案，待人工审核。本说明只准备流程，**没有任何人工评分或 Judge 评审已经发生**，也没有任何准确率、一致率数据。Judge 步骤需要 `approvals.judge_calls: approved` 和 `judge.runner: manual_ide`，未获批准前只能完成第 1–3 步。

## 1. 角色（四人，互不兼任）

| 角色 | 占位 ID | 职责 | 不得接触 |
|---|---|---|---|
| Judge 操作者 | `judge-operator-tbd` | 按 [manual-judge-runbook.md](../manual-judge-runbook.md) 为每个任务新开隔离会话、导入回复 | 人工评分表（提交前后都不看） |
| 人工评审者 A | `reviewer-a-tbd` | 独立评分并提交 | B 的评分、Judge 输出、本目录 `README.md` 的设计意图 |
| 人工评审者 B | `reviewer-b-tbd` | 独立评分并提交 | A 的评分、Judge 输出、本目录 `README.md` 的设计意图 |
| 裁定人 | `adjudicator-tbd` | 对 A、B 的每个分歧给出最终结论 | 裁定前不看 Judge 输出 |

占位 ID 由你替换为真实人员的 ID（小写字母、数字、`-`、`_`）。框架要求四个 ID 互不相同；`roles.yaml` 写入后不可修改。

## 2. 顺序（框架强制）

1. **准备**（离线）：`stage` 把两份固定文档放进 `cal-*` 批次；`export-review` 导出匿名评审包；`judge-manual export` 导出 Judge 任务包；`roles` 登记角色。
2. **A、B 独立评分并锁定**：`submit` 写入后不可修改。
3. 两人对**每份文档**都提交之前，`judge-manual session` 和 `import` 一律拒绝。
4. **Judge**（需批准）：Judge 操作者按手册完成每份文档 × 2 轮，`session.yaml` 的 `operator` 必须是登记的 Judge 操作者。
5. **裁定**：`disagreements` 列出分歧（判定、矛盾类别、违反的 H、维度锚点、严重缺陷），裁定人用 `adjudicate` 写入，必须覆盖每个分歧，写入后不可修改。
6. **对照**：`compare` 生成 `review/<batch>/calibration-comparison.md`。裁定未完成时拒绝生成。
7. **调整 Prompt**（如需要）：只改 `prompts/system-prompt.md` 措辞，升 `judge-prompt` 版本号并记录原因；不改 Rubric、金标准和人工结果。改后用**新的** `cal-*` 批次重跑第 4–6 步（人工结果可以复用，Judge 结果不复用）。
8. **冻结 Prompt**：校准结论由你确认后，冻结 Prompt 和 Schema 版本。冻结会让 P07 的冻结清单失效（`prompts/system-prompt.md` 被纳入哈希），需要重新冻结 P07。

## 3. 命令（全部离线）

```bash
P=./.venv/bin/python
$P -m prd_benchmark.cli calibration stage --batch-id cal-01
$P -m prd_benchmark.cli calibration export-review --batch-id cal-01
$P -m prd_benchmark.cli judge-manual export --batch-id cal-01
$P -m prd_benchmark.cli calibration roles --batch-id cal-01 \
  --judge-operator judge-operator-tbd --reviewer-a reviewer-a-tbd \
  --reviewer-b reviewer-b-tbd --adjudicator adjudicator-tbd
$P -m prd_benchmark.cli calibration submit --batch-id cal-01 \
  --reviewer reviewer-a-tbd --review-id r-xxxxxxxx --sheet <填好的 scoresheet.yaml>
$P -m prd_benchmark.cli calibration disagreements --batch-id cal-01 --review-id r-xxxxxxxx
$P -m prd_benchmark.cli calibration adjudicate --batch-id cal-01 --review-id r-xxxxxxxx \
  --adjudicator adjudicator-tbd --decisions <decisions.yaml>
$P -m prd_benchmark.cli calibration compare --batch-id cal-01
```

`decisions.yaml` 的键与 `disagreements` 输出的键相同，例如 `items.R1: partial`、`items.R2.contradiction_kind: internal`、`critical_defects: [G1]`。

## 4. 评分表填写

每个 R、C 条目：`verdict`（covered / partial / missing / contradicted）、`quotes`（逐字引用文档）、`rationale`。判为 `contradicted` 时再填 `contradiction_kind`（general / internal）；认为违反了某条明确硬约束时，在 `hard_constraint` 填 H 编号。五个维度填 0–4 锚点。`critical_defects` 列出认定的严重缺陷（`rule_id` + 引用）。规则见 `rubric.md`。

## 5. 对照表的内容和限制

对照表逐份文档列出五部分：①R、C 覆盖判定；②矛盾判定（类别、是否归因于 H）；③严重缺陷与硬约束主张；④证据引用逐字核验；⑤冲突取舍等合理替代方案是否被误判为违规（P92 的 R4、R5）。Judge 两轮分别列出，不取平均。

计数只描述这两份文档上的逐项对照，**不是 Judge 的准确率或一致率**，不能外推到 P07 或其他 Pilot 文档。两份文档、每份两轮，样本量不足以做统计结论。

## 6. 与 Pilot 隔离

- 校准批次 ID 必须以 `cal-` 开头；`run` 拒绝 `cal-*` 批次 ID 和 P91、P92 用例，P91、P92 也不在 Pilot 用例清单中。
- 自动 Judge（`judge --judge claude`）拒绝 `cal-*` 批次；校准只走人工 IDE Judge。
- `cal-*` 批次的 `report`、`judge-manual` 和 `calibration` 命令只加载 `calibration_set/cases/`。
