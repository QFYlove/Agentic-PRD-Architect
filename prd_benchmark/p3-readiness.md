# P3 实验准备清单

**Status:** 草案（v0.4，2026-10-27），待人工审核。本文件只列出准备事项、已实现的保护和需要决定的参数，不代表任何事项已获批准。所有审批项仍为 `not_approved`。PQB-P07 已完成技术冻结但尚未由人签署，其余 7 个 Pilot 用例仍为 draft。没有发起过任何真实模型或 Judge 调用；本文件中没有任何准确率、一致率或产品效果数据。

## 0. 结论先行（v0.3 调整后）

方案已调整为：**不要求接入 Anthropic 官方 API**。Judge 有两条路径，按顺序尝试：

1. **自动 CLI Judge（`judge.runner: claude_code_cli`）。** 先尝试现有网关。但当前网关环境下 `--bare` 无法认证（没有 `ANTHROPIC_API_KEY`），框架也不读取、不复用 IDE 的认证凭据，所以适配器会拒绝运行并提示改用手动流程。只有同时满足"显式提供 API Key + `allow_gateway: true` + 一份经人工核实、计费类型为 `gateway_per_token` 的价格快照"，网关路径才会放行；否则不放行，不绕过闸门。
2. **人工触发的 IDE Judge（`judge.runner: manual_ide`）。** PRD 生成完成后，由人在 IDE 中为每个任务新开一个隔离的 Claude Code 会话完成评审，再离线导入。操作步骤见 [manual-judge-runbook.md](manual-judge-runbook.md)，实现见 `judge_manual.py`。

**实验计划先只做 P07：** A/B 生成（需批准真实 DeepSeek 调用）→ 匿名评审包 → 每份文档两轮独立评审。第一次运行标记为技术冒烟测试（`--purpose smoke`），报告顶部会写明"不是质量结论"。

**预算：** DeepSeek 生成仍受原有预算闸门和停止条件约束；300k Token / US$5 足以覆盖 P07 生成的预留（见 4.3 节）。手动 IDE Judge 不经过框架的预算预留，费用未知，报告如实披露，不计入上限。原先"Judge 单次预留超出上限"的阻断只适用于自动 CLI Judge。

**v0.4 新增（P3 收尾）：**
- **P07 单独冻结**（`cases/freeze/PQB-P07.yaml`）：记录 P07 的输入字段、H、R、C、严重缺陷、`rule_relations`、`conflicts` 的范围，Rubric / Prompt / Schema / 配置版本，A/B 首次请求一致规则，以及用例文件、Rubric、Prompt、评分与生成代码的 SHA-256。冻结前检查已通过（见 6.3 节）。真实批次要求冻结清单由人签署 `confirmed_by`，目前未签署。
- **P91、P92 人工校准流程**已就绪（`calibration_set/runbook.md`），顺序由代码强制：登记角色 → A、B 提交并锁定 → 才能开始 Judge → 裁定 → 对照表。
- **人工 IDE Judge 离线演练**：P07 全流程以固定回复跑通（`tests/test_manual_judge_drill.py`），见 7a 节。

## 1. Judge：模型候选与运行方式

### 1.1 运行方式（已实现，未调用）

`judge_claude.py` 中的 `ClaudeCodeJudge` 为每份文档、每轮评审启动一个全新的 `claude -p` 进程。所用参数都已在本机安装版本（`claude --version` 为 `2.1.258.6`）的 `--help` 中逐个核对过：

| 参数 / 设置 | 作用 |
|---|---|
| `-p --output-format json` | 非交互运行，输出单个 JSON 结果对象 |
| `--bare` | 不加载 hooks、skills、插件、MCP、自动记忆和 CLAUDE.md；只认 `ANTHROPIC_API_KEY` |
| `--restricted` | 去掉执行命令和代码的工具与 WebFetch，不读取用户和项目设置文件 |
| `--tools ""` | 关闭全部内置工具 |
| `--strict-mcp-config` + `--disallowedTools "mcp__*"` | 不连接任何 MCP 服务器，并拒绝所有 MCP 工具 |
| `--disable-slash-commands` | 关闭 skills |
| `--no-session-persistence` | 会话不落盘、不可恢复 |
| `--system-prompt` | 完全替换默认系统提示，内容为正式 Judge 系统指令 + Rubric 第 4 节 + Schema |
| `--json-schema` | `JudgeOutput` 的 JSON Schema；返回后仍走完整的严格解析和校验管道 |
| `--model`、`--effort` | 请求的模型和推理强度 |
| 工作目录 | 每次一个新的空临时目录，用完删除；`HOME` 指向其中的空目录 |
| 环境变量 | 只保留 `PATH`、语言设置、`ANTHROPIC_API_KEY`/`ANTHROPIC_BASE_URL`；另设 `CLAUDE_CODE_SIMPLE=1`、`CLAUDE_CODE_MAX_OUTPUT_TOKENS`、`CLAUDE_CODE_MAX_RETRIES=0`、关闭自动记忆和非必要网络流量 |
| 用户提示 | 通过 stdin 传入（题面、金标准、匿名文档），不出现在进程参数中 |

**不使用的参数：** `--max-turns` 在官方文档中存在，但本机 2.1.258.6 的 `--help` 里没有，因此不用。`--max-budget-usd` 只作为可选的软上限（见第 4.2 节）。

**隔离的边界（未能保证的部分）：**
- 系统指令、Schema 和金标准由我们显式传入；文档中的指令在系统指令里被明确声明为不可信数据。但模型是否真的不受文档中的注入影响，只能靠校准和人工复核发现，无法由参数保证。
- `--bare` 和 `--restricted` 的效果以官方文档为准，没有用真实运行验证。
- 管理员下发的 managed settings 在 `--restricted` 下仍然生效（官方文档原文），如果本机有这类策略，可能影响 Judge 的行为。
- 一次 CLI 运行内部可能发起不止一次 API 请求（例如结构化输出不匹配时的内部重试，文档没有说明）。框架按"最多 3 次请求"预留预算，并在 CLI 报告的成本超过预留时停止批次。

### 1.2 模型候选（未调用核实）

价格来自 Anthropic 官方价目表（2026-10-27 获取，已保存为草稿快照 `price_snapshots/`），只适用于 Anthropic 官方 API Key 计费。

| 候选 | 模型 ID | 输入 / 缓存写入 5m / 缓存读取 / 输出（US$ / 百万 Token） | 上下文 / 最大输出 |
|---|---|---|---|
| **推荐** Claude Opus 5.5 | `claude-opus-5-5` | 4 / 5 / 0.20 / 20 | 1M / 128K |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | 2 / 2.50 / 0.10 / 10 | 1M / 128K |
| Claude Haiku 5.5 | `claude-haiku-5-5` | 0.10 / 0.125 / 0.01 / 0.50（≤100K Token 的提示） | 1M |

**推荐 Opus 5.5 的依据：** 本 Judge 要做的是长上下文（系统指令约 2 万字节，P07 金标准与题面约 2.5 万字节，再加整份 PRD）、逐条带原文引用的判定，以及区分 `missing`/`partial`/`contradicted`/`internal` 这类需要细致阅读的分类。这类任务对模型能力敏感，Opus 是当前默认的高能力模型。它与 DeepSeek 生成器属于不同模型家族。

**需要注意的代价：** Opus 5.5 的思考不能关闭，思考按输出计费；价格是 Sonnet 5.5 的 2 倍。如果预算是主要约束，Sonnet 5.5 是次选；Haiku 5.5 便宜得多，但长文档逐条判定的可靠性风险最高，不建议作为唯一 Judge。具体选择需要你决定，`config/pilot.yaml` 中 `judge.model_id` 保持为空，只记录了 `candidate_model_id: claude-opus-5-5`。

**模型标识：** CLI 的 JSON 输出中 `modelUsage` 按模型名列出用量，适配器记录这些名称作为"实际返回的模型标识"。Anthropic 的模型 ID 不带日期后缀，所以只能确认模型名，不能确认快照版本；报告中会标为"快照无法核实"，不会据此声称没有模型漂移。

## 2. 价格快照与成本口径

- **来源：** 只用官方价目表。已保存三份**草稿**快照（`price_snapshots/`）：DeepSeek `deepseek-flash`、Claude Opus 5.5、Claude Sonnet 5.5。数字由自动网页摘要转录，`status: draft`，**必须由人逐项核对后改为 `verified`**，否则真实运行一律拒绝。
- **DeepSeek（草稿）：** 输入缓存命中 0.006 / 0.003、未命中 0.3 / 0.15、输出 1.2 / 0.6（US$ / 百万 Token，高峰 / 非高峰）。高峰为 UTC 周一至周五 01:00–04:00、06:00–10:00，中国法定节假日除外。节假日例外没有建模，按高峰计价，只会高估。
- **Claude（草稿）：** 见 1.2 节。缓存写入按 5 分钟和 1 小时两档中较高的一档计价，因为 CLI 不报告用的是哪一档。
- **两类数字，分开报告：**
  - "估算成本"：框架用快照对**服务端报告的 Token** 计价，DeepSeek 和 Judge 分别汇总。用量未知的调用按预留的最坏情况计入，并单独列出这部分金额。
  - CLI 的 `total_cost_usd`：Claude Code 自己的客户端估算，单独记录为 `cli_cost_estimate_usd`，不当作账单。
  - 只有与真实账单核对后的数字才称"可核实成本"。本轮没有账单。

## 3. 认证与计费方式（只检查了本机可安全读取的状态）

检查方式：只判断环境变量是否存在、网关主机是否为官方主机，没有读取或输出任何值，没有发起认证请求。

| 项目 | 本机现状 |
|---|---|
| CLI | `~/.baidu-cc/baidu-cc/bin/claude`，版本 2.1.258.6（同目录 `ducc` 为其别名） |
| `ANTHROPIC_API_KEY` | 未设置 |
| `ANTHROPIC_BASE_URL` | 已设置，**非 Anthropic 官方主机** |
| `ANTHROPIC_MODEL` | 已设置，不是 Claude 模型名（适配器不传递此变量，用 `--model` 显式指定） |
| Bedrock / Vertex / Foundry 开关 | 均未设置 |

**结论：**
- 当前会话很可能通过内部网关认证计费，计费方式不属于"Anthropic API 按 Token 计费""Claude 订阅额度"中任何一种已知情形，本框架无法得知价格，也无法限制实际费用。
- `--bare` 模式不读取订阅登录，所以订阅额度本来就不能用于这个 Judge。即使能用，订阅额度也不等于账单金额。
- 适配器只在"有 `ANTHROPIC_API_KEY` 且没有指向非官方网关"时放行（`judge_auth_blockers`）。其他情形一律拒绝，等待你决定。

## 4. 预算保护

### 4.1 已实现的机制（`guard.py`，覆盖真实调用路径）

DeepSeek 调用（`RecordingClient`）和 Judge 调用（`ClaudeCodeJudge`）都经过同一个 `CallGuard`：

1. **请求前预留：** 输入 Token 上界取请求内容的 UTF-8 字节数（字节级分词器下每个 Token 至少 1 字节，所以这是硬上界；对中文约高估 2–3 倍）。输出取请求的最大输出（DeepSeek 为 `max_tokens=16000`；Judge 为 `CLAUDE_CODE_MAX_OUTPUT_TOKENS=32000`），Judge 再乘以每次 CLI 运行最多的 API 请求数（默认 3）。按快照中最贵的输入单价和输出单价计算费用。
2. **双上限检查：** "已计入 + 未结算预留 + 本次预留"超过 Token 上限或费用上限任意一个，就拒绝本次调用，调用不会发出。
3. **结算：** 服务端报告了完整用量时，按实际用量和调用时段的价格结算，释放多余的预留。超时、取消、流中断、非零退出、用量缺失时，**最坏情况预留永久计入，不释放**。
4. **跨命令累计：** 每个命令把账本写入 `ledgers/<batch>/`，后续命令启动时读入，所以生成和 Judge 两个阶段共用同一个批次上限。
5. **停止条件（全部有测试）：**

| 条件 | 行为 |
|---|---|
| 同一批次同一通道返回的模型标识变化 | 停止 |
| 模型标识缺失，或只返回配置的别名 | 不停止，报告"快照无法核实" |
| 连续 2 次超时（产品内部以取消实现的超时也算） | 停止 |
| 冒烟测试中任意 1 次 Judge 输出无效 | 停止，不重试 |
| 正式 Pilot 中至少 4 次 Judge 调用后无效率超过 25% | 停止 |
| Token 或费用任一上限达到 | 停止后续调用 |
| 预留/结算异常、缺少价格快照却设了费用上限、CLI 报告的成本超过本次预留 | 停止 |

停止状态一旦触发就锁定，之后所有调用在发出前被拒绝；已生成的运行记录、调用记录、Judge 原始回复和账本都保留。

### 4.2 可靠程度

| 保护 | 可靠程度 | 原因 |
|---|---|---|
| Token 上限 | 只要服务端如实报告用量就可靠；用量未知时按最坏情况计入，偏保守 | 预留在请求前完成 |
| 费用上限（DeepSeek） | **估算层面**可靠 | 依赖价格快照准确；不含账单层面的其他费用 |
| 费用上限（Judge） | **估算层面**可靠，但依赖两个未验证的假设 | ①一次 CLI 运行最多 3 次 API 请求；②`CLAUDE_CODE_MAX_OUTPUT_TOKENS` 能约束全部请求（官方原文是"大多数请求"）。框架用 CLI 报告的成本作为事后核对：超出预留就停批次，但那一次调用的超额已经发生 |
| `--max-budget-usd` | **不可靠，不作为保障** | 官方文档写明它基于客户端估算，"spend can pass the cap"。只可作为额外的软上限 |
| 实际账单 | **框架无法保证** | 账单只能由服务商侧控制：建议为 Benchmark 单独开 API Key，并在服务商控制台设置额度上限 |

### 4.3 P07 冒烟测试的调用预算（由代码结构推出，没有实测）

**DeepSeek（生成器）：**

| 情形 | A | B |
|---|---|---|
| 最少（v1 即通过门槛，无重试） | 1 | 4 |
| 跑满 3 轮、无重试 | 1 | 14（3 生成 + 9 评审 + 2 优化） |
| 理论上限（每次都重试一次，评审与优化各修复一次） | 2 | 39（6 生成 + 27 评审 + 6 优化） |

每次 DeepSeek 调用的预留（按草稿价目表最坏单价）：输入中不含 PRD 时约 2.2 万 Token、US$0.021；含一份 1 万字中文 PRD 时约 5.2 万 Token、US$0.030。理论上限 41 次调用的费用预留合计不超过约 US$2。

**Claude Judge：** P07 产生最多 4 份待评文档（A、B.best、B.last、B.v1，内容相同的合并），每份 2 轮，最多 **8 次** CLI 运行，每次不重试。

每次 Judge 运行的预留（P07，文档按 1 万中文字符计）：

| 模型 | 按 1 次 API 请求预留 | 按 3 次 API 请求预留 |
|---|---|---|
| Opus 5.5 | 11.1 万 Token / US$1.27 | 33.3 万 Token / US$3.81 |
| Sonnet 5.5 | 11.1 万 Token / US$0.64 | 33.3 万 Token / US$1.91 |

预留是上界，不是预计用量：实际结算按服务端报告的用量释放多余部分。但在结算之前，下一次调用必须能放进剩余额度。

### 4.4 需要你在三者中选择（我不擅自改）

1. **提高冒烟上限**，例如 Token 上限 100 万、费用上限 US$15（Opus，按 1 次请求预留）。
2. **改用 Sonnet 5.5 作为冒烟 Judge**，并按 1 次请求预留：8 次合计预留约 US$5.1，仍略超 US$5，需要同时把预留倍数设为 1 或略微提高费用上限。
3. **降低预留倍数**（`max_api_requests_per_call: 1`）：风险是 CLI 内部多发的请求不在预留之内，只能靠事后核对发现。

另外，`CLAUDE_CODE_MAX_OUTPUT_TOKENS` 设为 16000 能把每次预留降低约 30%，但长文档逐条判定的输出可能被截断，截断会被判为无效输出并停止冒烟测试。

**结论：** 300,000 Token 的上限对 DeepSeek 部分大致够用（取决于 PRD 长度和是否跑满 3 轮，未测量），对 Judge 部分不够。冒烟测试很可能在 B 跑完之前或第一次 Judge 调用前就因预算停止；停止本身会被记录，不会重跑。

## 5. 正式 Pilot：预算、停止与重试

- **预算：** 冒烟测试后，按实测的单用例生成用量和单份文档 Judge 用量分别估算，起点为"实测 × 8 × 1.5"。还必须单独考虑：B 的多轮生成和评审；Judge 双轮；输入与输出分开；重试和失败调用（按最坏情况计入）；缓存命中（会降低实际费用，不降低预留）；峰谷价格（预留按高峰价）；中断后用量未知的请求；人工复核的人力。这个公式只是估算起点，不是成本保证。
- **停止条件：** 同第 4.1 节，`judge.stop_mode` 改为 `pilot`。
- **重试：** 生成器只有基础设施错误允许每用例每条件重跑 1 次；Judge 不自动重试，无效输出记录为作废。
- 正式 Pilot 需要单独审批。

## 6. 人工校准与复核

### 6.1 校准集（已准备，未评分）

`calibration_set/` 中有两个不属于 P01–P08 的用例和两份完整 PRD（PQB-P91 会议室预订、PQB-P92 差旅报销），按设计包含：明确需求、含糊需求、一组冲突与两个取舍方案、明确硬约束违规、内部矛盾、语义等价的改写、遗漏、部分覆盖、把待澄清项写成已确认。设计意图写在 `calibration_set/README.md`，**不是金标准答案**。虚构引用、泛泛的 `behavior_impact` 等 Judge 侧错误无法靠文档制造，已由 `calibration/` 中的离线固定响应覆盖。

### 6.2 校准流程

操作步骤、角色和命令见 [calibration_set/runbook.md](calibration_set/runbook.md)。

1. 两名评审者用 `calibration export-review` 导出的匿名包（见第 7 节）独立评分，提交即锁定。两人都提交之前，框架拒绝为该文档准备或导入 Judge 会话。
2. 由第三人对分歧逐项裁定，写入裁定文件。
3. 之后才运行 Judge（需批准；按第 4.4 节的选择设置预算）。
4. 逐条比较人工与 Judge。只允许修改 Prompt 措辞，每次修改升 `judge-prompt` 版本号并记录原因；不修改 Rubric 和金标准。
5. 校准通过后冻结 Prompt 版本和 Schema 版本（`judge-output-v0.4`），写入批次元数据。Pilot 期间任何修改都必须升版本并另起批次。

本轮没有运行 Judge，没有任何真实一致率或准确率。

### 6.3 P07 冻结前检查（`freeze.py`，机械检查，不替代人工审核用例）

| 检查 | 结果 |
|---|---|
| 每条 H 都有原文引用，且能在冻结输入中逐字找到 | 通过（H1–H8） |
| `derived`、`design_choice` 关系没有引用 H，也没有被改写成 H | 通过（derived L2/L5/L8，design_choice L6、L9–L14） |
| 待澄清项保留，没有被改写成 H | 通过（C1–C11，核心 C1、C3） |
| Rubric 中各维度分值和判定计分与 `scoring.py` 一致，合计 100 | 通过 |

冻结后修改用例文件、`rubric.md`、`prompts/system-prompt.md`、`scoring.py`、`judge.py`、`judge_prompt.py`、`evidence.py`、`run_single.py`、`run_workflow.py`，或配置中 `model`、`conditions`、`output_language`、`scoring`、Judge 轮数，都会让冻结失效，真实批次被拒绝，必须升版本并重新冻结。审批、预算、价格和执行顺序字段不在冻结范围内，批准时可以填写。

注意：如果校准后修改了 Judge Prompt（6.2 节第 4 步），P07 冻结会按设计失效，需要在 Prompt 冻结后重新冻结 P07。

## 7. 匿名人工评审（已实现）

`review.py`：

- `export_review_package` 为每份去重后的文档分配随机评审 ID（与 Judge 侧的 `doc_id` 无关，字符集不含元音，不会拼出 best、last 之类的词），随机化展示顺序，每份导出题面、PRD 和空白评分表。
- 评审包不含条件标签、运行路径、Judge 输出、模型标识、分数或已有裁定；`package_leaks` 检查文件名和非 PRD 文件内容。映射表单独保存在 `private/mapping.json`。
- 评审包 README 明确提示：文本风格可能暴露来源，匿名评审不能保证完全盲化；评分表末尾有一栏记录评审者的猜测和把握度。
- `submit_review` 一经提交即锁定；`disagreements` 列出两人不一致的条目；`adjudicate` 要求每个分歧都有裁定，裁定写入后不可覆盖。

## 7a. 人工 IDE Judge 离线演练（固定回复，未调用模型）

| 检查点 | 结果 |
|---|---|
| export → session → import → 解析 → 引用核验 → 评分 → 去重 → 人工裁定 → 报告 | 通过 |
| 任务包无泄露；任务 ID、输入哈希唯一；两轮在不同临时目录（仓库外） | 通过 |
| 无效 JSON、带围栏的不完整 JSON：原样保存、记为无效、冒烟测试立即停止 | 通过 |
| 不存在的引用：该判定记为未核实，不得分也不扣分 | 通过 |
| 缺少操作者、隔离确认不全、0 Token、费用无来源：拒绝导入，不写任何文件 | 通过 |
| 重复导入：拒绝 | 通过 |
| 两轮相同的硬约束主张合并为一个候选；待定时没有最终总分、合格状态为待定 | 通过 |
| 人工确认 / 否决后最终总分与合格状态更新，否决后分数高于确认后 | 通过 |
| 原始回复与解析记录分开保存 | 通过 |
| 未知字段保持 `unknown`，报告写"成本：未知"，不显示为 0；人工 Judge 不进入预算账本 | 通过 |
| 未批准时导入、真实 DeepSeek（仅 P07）、自动 Claude Judge 均被拒绝 | 通过 |

## 8. 数据保存

- `prd_benchmark/.gitignore` 忽略 `runs/`、`scores/`、`review/`、`ledgers/` 和 `reports/`（`reports/published/` 除外，留给人工确认后脱敏的汇总报告）。原始 PRD、Judge 原始回复、调用日志、人工评分原件、条件映射表和用量元数据都在被忽略的目录中。根目录 `.gitignore` 没有改动。
- 用例、方法论、Prompt、评分代码、价格快照和校准集正常版本控制。
- Judge 原始回复写入 `scores/<batch>/judge_raw/`，解析后的记录写入 `scores/<batch>/judge/`，两者分开；所有文件只写一次，已存在的不会被覆盖或重评。
- 原始回复中的凭据按模式和已知值替换为 `[REDACTED]`；API Key 只存在于子进程环境中，不写入任何文件。

## 9. 最小批准清单

"已就绪"指工程准备已完成、可以审核；"已批准"只能由你填写。当前所有事项均**未批准**。生成调用与 Judge 调用分开审批。

| # | 事项 | 已就绪 | 已批准 | 由谁决定 |
|---|---|---|---|---|
| 1 | 人工核对 DeepSeek 价格快照，改为 `verified` | 草稿已保存 | 否 | 你或指定人 |
| 2 | `config/pilot.yaml`：`token_budget_limit`（建议 300000）、`usd_budget_limit`（建议 5.0）、`condition_order_seed`；配置 `status: frozen` | 字段已存在 | 否 | 你决定，我可代改 |
| 3 | 审核 P07 并在 `cases/freeze/PQB-P07.yaml` 签署 `confirmed_by` | 技术冻结完成 | 否 | 审核用例的人 |
| 4 | **生成审批**：P07 真实 DeepSeek 调用（`real_model_calls: approved`，命令行 `--confirm-spend --purpose smoke --cases PQB-P07 --provider-changelog-date <日期>`） | 闸门已就绪 | 否 | 你 |
| 5 | **Judge 审批**：`judge.runner: manual_ide`、`judge_calls: approved` | 手动流程与演练已完成 | 否 | 你 |
| 6 | Judge 模型（推荐 `claude-opus-5-5`，以 IDE 可选为准），写入 `judge.model_id` | 候选已记录 | 否 | 你 |
| 7 | 指定四个角色：Judge 操作者、评审者 A、B、裁定人（互不兼任） | 占位 ID 与强制检查已就绪 | 否 | 你 |
| 8 | P91、P92 人工校准：A、B 评分 → Judge（需第 5 项）→ 裁定 → 对照 → 冻结 Prompt | 流程与命令已就绪 | 否 | 你 |
| 9 | 原始输出是否另行备份（默认只存本地、不进 Git） | 默认已生效 | 否 | 你 |

建议顺序：7 → 8（人工评分部分不需要任何审批）→ 5、6 → 8 的 Judge 部分 → 冻结 Prompt 并按需重新冻结 P07 → 1、2、3 → 4 → P07 冒烟测试。
