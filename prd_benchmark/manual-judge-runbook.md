# 人工 IDE Judge 操作手册

**Status:** 草案，待人工审核。未获批准（`approvals.judge_calls: approved` 且 `judge.runner: manual_ide`）前不要开始任何评审。手动 Judge 不会绕过生成阶段的审批：没有经批准的 A/B 运行产物，就没有可评的文档。

适用场景：自动 CLI Judge 因认证不满足而被拒绝时（例如当前网关环境），由人在 IDE 中的 Claude Code 里逐个执行评审任务，再把回复导入框架。

## 0. 原则

- **一个任务 = 一份文档的一轮评审 = 一个新会话。** 同一份文档的两轮评审（不同的任务 ID）必须在两个不同的新会话中完成，不得在同一会话里先后评两轮。
- **不得用正在开发 Benchmark 的会话评分**，也不得在打开本仓库的窗口或会话里评分。
- **只提供任务目录里的三个文件。** 不提供项目代码、CLAUDE.md、记忆、运行目录、报告、映射表或其他任务。
- **不修复、不重试。** 回复不合格就原样导入，由框架记为无效；冒烟测试中出现一次无效输出就停止。
- **框架不读取 IDE 或网关的认证信息**，也不知道这些会话的费用；费用记为 unknown，除非工具界面明确显示。

## 1. 导出任务包（离线，不调用模型）

在仓库根目录：

```bash
./.venv/bin/python -m prd_benchmark.cli judge-manual export --batch-id <batch>
```

- 每份去重后的文档 × 2 轮，各得到一个随机任务 ID（`t-xxxxxxxx`），与条件、`doc_id`、运行路径都无关。
- 任务内容：`judge-input.md`（正式 Judge 系统指令、Rubric 第 4 节、输出 Schema、该用例的题面与金标准，含 `rule_relations` 和 `conflicts`、匿名 PRD）、`schema.json`、`session.yaml`（元数据模板，全部为 `unknown`）。
- 导出后自动检查泄露（条件标签、运行路径、生成模型名、`doc_id`）；发现泄露则报错，不要使用该包。
- 映射表在 `judge_manual/<batch>/private/mapping.json`，**不得**给任何评审会话。
- 评审顺序见 `package/order.json`（已随机化）。

## 2. 准备隔离目录

对每个任务：

```bash
./.venv/bin/python -m prd_benchmark.cli judge-manual session --batch-id <batch> --task t-xxxxxxxx
```

命令打印一个新建的系统临时目录（仓库之外），里面只有该任务的三个文件。

## 3. 在 IDE 中执行评审

1. 在 IDE 中**新开一个窗口**，以上一步打印的临时目录作为工作区打开（不要在本仓库的窗口中操作）。
2. 在该窗口中**新开一个 Claude Code 会话**。不要继续或恢复任何已有会话。
3. 选择本次批次统一使用的模型（整个批次保持同一个模型；中途更换会被判为模型漂移并停止）。如果 IDE 允许，关闭或拒绝一切工具调用之外的文件读取、网页访问和 MCP；如果做不到，在会话中出现任何读取 `judge-input.md` 以外文件的工具调用时，记录到 `session.yaml` 的 `tool_calls_observed`。
4. 发送以下固定指令（不要改写，不要追加说明）：

   > 请阅读当前目录下的 judge-input.md，严格按其中 `<system_instructions>` 的要求完成评审。只把一个符合 schema.json 的 JSON 对象写入当前目录的 response.json，不要输出任何其他内容，不要读取其他文件。

5. 如果模型没有写文件而是在对话里输出了 JSON，把它**原样**复制到 `response.json`，不做任何修改、补全或格式修正。
6. 不要对评审结果提出意见、追问或要求修改；收到回复后结束会话。

## 4. 填写 session.yaml

只填你**看得到**的事实，看不到的保留 `unknown`。不要填 0，也不要估算。

| 字段 | 填写方式 |
|---|---|
| `operator` | 你的评审者 ID（必填） |
| `model_identifier`、`model_identifier_source` | IDE 中显示的模型名，以及在哪里看到的（例如"模型选择器""会话标题"）；看不到就保留 `unknown` |
| `ide`、`ide_version`、`claude_code_version` | 从 IDE 的"关于"页面或扩展页面读取 |
| `session_started_at`、`response_received_at` | ISO 8601 时间，含时区 |
| `input_tokens`、`output_tokens`、`cache_read_tokens`、`cache_write_tokens` | 只有工具界面明确显示时才填；输入、输出必须大于 0 |
| `cost_usd`、`cost_basis` | 只有工具明确显示费用时才填，同时写明来源（`displayed_by_tool`、`gateway_report`、`subscription_quota`）；否则保留 `unknown` |
| `tool_calls_observed` | 会话中是否出现读取其他文件、访问网络等工具调用 |
| `isolation` | 逐项确认六个条件，全部属实才能改为 `true`；任何一项不属实，这个任务不要导入，重新准备目录、新开会话 |

## 5. 导入

```bash
./.venv/bin/python -m prd_benchmark.cli judge-manual import --batch-id <batch> \
  --task t-xxxxxxxx --response <临时目录>/response.json --session <临时目录>/session.yaml
```

- 导入前检查：审批状态、任务 ID、`judge-input.md` 的哈希与导出时一致、元数据格式（`unknown` 之外不允许空值或 0 Token）、隔离确认、该任务未导入过、批次未处于停止状态。任何一项不满足都拒绝，且不写入任何文件。
- 原始回复与元数据写入 `scores/<batch>/judge_raw/`，解析后的记录写入 `scores/<batch>/judge/`，之后的严格解析、Schema 校验、引用核验、`behavior_impact` 校验、评分、候选去重和人工裁定与自动 Judge 完全相同。
- 无效输出同样会被写入（标为无效），并按停止规则处理：冒烟测试第一次无效就停止；正式 Pilot 中至少 4 次后无效率超过 25% 停止；模型标识变化停止。停止后拒绝所有后续导入。
- 导入完成后删除临时目录。

查看进度：

```bash
./.venv/bin/python -m prd_benchmark.cli judge-manual status --batch-id <batch>
```

## 6. 之后

- 运行 `report` 生成报告。报告会标明"人工触发的 IDE Judge"、成本未知、每个字段为 unknown 的次数；冒烟批次标明"技术冒烟测试，不是质量结论"。
- 严重缺陷候选的人工裁定、匿名人工复核（`review.py`）照常进行。负责人工复核的人不应同时担任 Judge 操作者，以免看到 Judge 输出后影响独立评分。

## 7. 已知限制

- 隔离依赖操作者遵守本手册；框架只能检查哈希、元数据和操作者的确认，不能证明会话真的是全新的、没有读取其他文件。
- IDE 中的 Claude Code 有自己的系统提示和工具，这些无法关闭或审计；Judge 指令是作为用户提供的文件传入的，不是系统提示，其约束力低于自动 CLI 方式中的 `--system-prompt`。
- 模型标识是操作者看到的显示名，不能核实具体快照。
- 费用和 Token 用量通常未知，不进入预算上限；报告如实披露。
- 两轮评审都由人手动触发，耗时长，且操作差异本身会引入噪声。

## 8. 校准批次（`cal-*`）

用于 P91、P92 时，流程相同，另有两条限制（见 [calibration_set/runbook.md](calibration_set/runbook.md)）：两名人工评审者都锁定提交之前，`session` 和 `import` 拒绝执行；`session.yaml` 的 `operator` 必须是 `roles.yaml` 中登记的 Judge 操作者。
