# 实验协议

**Status:** P0 修订稿（v0.2），P1 已实现对应的运行框架；待人工审核。

## 0. 审批闸门

以下操作在获得**另行的明确批准**前一律不执行。`config/pilot.yaml` 的 `approvals` 字段记录当前状态。P1 实现的 CLI（`python -m prd_benchmark.cli run --mode real`）只有在以下条件**全部**满足时才会构造真实客户端：`approvals.real_model_calls` 为 `approved`；命令行传入 `--confirm-spend`；设置了 `approvals.token_budget_limit`；设置了 `execution.condition_order_seed`；配置状态为 `frozen`；传入 `--provider-changelog-date`；用例集已冻结且哈希全部吻合。任一条件不满足即拒绝运行，且在拒绝前不写入任何文件。真实 Judge 在 P1 中没有实现，`judge --judge real` 一律拒绝。

| 操作 | 当前状态 |
|---|---|
| 真实模型调用（条件 A、B，含冒烟测试） | 未批准 |
| Judge API 调用 | 未批准 |
| 任何其他需要 API Key 的调用（包括不计费的 `GET /models`） | 未批准 |

未批准期间只允许：编写文档与用例、进程内模拟服务（`--mode fake`）与 Mock Judge 下的流程演练、单元测试。模拟服务驱动的是产品真实的 `OpenAICompatibleLLMProvider`（prompt 组装、流式解析、完整性校验都是真实代码），但不发起任何网络请求；它的输出与分数没有质量含义。

## 1. 运行前检查（每个批次）

1. 记录代码 commit 与 `git status --porcelain`；工作区不干净时记录差异文件清单（不记录内容），并在报告中注明。
2. 校验 `cases/manifest.yaml` 中所有用例的 SHA-256；任一不符则中止。
3. 确认用例状态全部为 `frozen`。
4. 确认 `DEEPSEEK_API_KEY` 环境变量**存在**；只检查存在性，不打印、不写入任何文件或日志。Benchmark 不读取 `.env`。
5. 记录：批次 ID、开始时间（含时区）、所在峰谷时段、DeepSeek 更新日志最新条目日期、价目表快照文件与日期。
6. 确认 `config/pilot.yaml` 的模型配置为 `deepseek-flash`，并把整份配置的 SHA-256 写入批次元数据。

## 2. 条件 A 执行规范

1. 从冻结用例读取三个输入字段，按产品规则判定输出语言（全部为 `zh`）。
2. 构造 `OpenAICompatibleLLMProvider`，参数与产品真实模式一致：`provider_name="deepseek"`、`base_url`、`model`、`request_timeout_seconds=90`、`max_output_tokens=16000`、`extra_body={"thinking": {"type": "disabled"}}`，并注入记录型 client。
3. 调用 `stream_prd(iteration=1, revision_plan=None, baseline_prd=None, ...)`，拼接文本后执行 `validate_generated_prd`。
4. 重试：与 B 的 Generator 相同，最多 2 次尝试，单次尝试上限 240 秒，仅对可重试错误重试，无退避。
5. 保存去掉结束标记后的文档，作为 `A`。

## 3. 条件 B 执行规范

1. 组装 `Settings(_env_file=None, enable_mock_llm=False, database_path=":memory:", ...)`，使用产品默认超时与默认门槛，不修改任何超时。
2. 用与条件 A 相同参数的 Provider（同样注入记录型 client）组装 `RunManager` + `AgentWorkflow`，不 import `backend.main`。
3. `CreateRunRequest`：三个输入字段原样传入，`quality_threshold=85`、`max_iterations=3`，`provider_id="deepseek"`、`model_id="deepseek-flash"`。
4. 调用 `wait_for_completion`，等待上限设为大于 600 秒的 run 超时（例如 660 秒），保证由产品自身的超时而不是 Benchmark 的等待来结束运行。
5. 不暂停、不恢复、不传 `user_override`、不取消。
6. 保存最终快照 JSON，从中导出 `B.best`、`B.last`、`B.v1`。

## 4. 运行顺序与时间窗口

- 用例按 ID 顺序串行执行，不并发，避免两个条件遭遇的限流不对称。
- 每个用例内 A、B 的先后顺序由固定种子的随机数决定，种子与实际顺序写入批次元数据。
- 同一用例的 A 与 B 必须在同一峰谷时段内完成；若跨时段，记录并在成本分析中分开计算。

## 5. 每次调用的记录字段（`calls.jsonl`）

记录型 client 包装 `AsyncOpenAI`，在 SDK 层截获每一次 HTTP 调用（包括重试、修复、失败与取消），每次调用写一行 JSON：

| 字段 | 说明 |
|---|---|
| `batch_id`、`case_id`、`condition` | `A` 或 `B` |
| `call_index` | 该运行内的调用序号 |
| `node` | `generator` / `tech_reviewer` / `ux_reviewer` / `biz_reviewer` / `optimizer` / `repair`；由请求中 `<user_input_json>` 的字段识别 |
| `role` | 评审与修复调用的角色（`tech` / `ux` / `biz`），其他为 `null` |
| `version` | B 内对应的 PRD 版本号；A 恒为 1；修复调用取最近一次被识别的版本 |
| `attempt` | 同一 `node` + `role` + `version` 下的第几次调用 |
| `configured_model` | 请求中发送的 `model`（应为 `deepseek-flash`） |
| `request_sha256` | 请求参数（不含 timeout）的哈希。报告用它核对每个用例 A 与 B.v1 的首次生成请求是否逐字节相同 |
| `stream` | 是否流式调用 |
| `response_model` | **必填**。服务端响应中的原始 `model` 字段（流式取第一个带该字段的 chunk）。服务端未返回时记 `null` 并设置 `response_model_missing: true`，**不得**回填配置值 |
| `response_models_seen` | 同一次调用中出现过的全部 `model` 值，用于发现流内不一致 |
| `started_at`、`ended_at`、`wall_seconds` | |
| `first_token_seconds` | 仅流式调用，从发出请求起计 |
| `http_status` | 成功为 200；异常时取状态码，没有则 `null` |
| `outcome` | `ok` / `error` / `timeout` / `cancelled` / `abandoned`（流在结束前被关闭） |
| `error_class` | 异常类名（不含消息正文，避免泄露服务端返回内容） |
| `finish_reason` | 原始值 |
| `input_tokens`、`output_tokens`、`total_tokens` | 原始 `usage` |
| `cache_hit_tokens`、`cache_miss_tokens`、`reasoning_tokens` | 原始 `usage` 中存在时记录，否则 `null` |
| `usage_raw_keys` | 原始 `usage` 的字段名列表，便于发现新字段 |

禁止记录：请求头、API Key、完整 system prompt（已在仓库中，以 commit 指代即可）。

记录的已知局限（P1 实现时确认）：
- 产品自身的节点超时与整次 run 超时是通过取消正在进行的调用实现的，所以这类调用在 `calls.jsonl` 中记为 `cancelled`，而不是 `timeout`；运行级错误码仍为 `RUN_TIMEOUT`。
- 流式调用的 usage 只在最后一个 chunk 返回。被取消或中断的流没有 Token 记录（记 `null`），但服务端可能已经计费，这部分只能通过账单对账发现。

`response_model` 判定：
- 同一批次所有调用的 `response_model` 应一致；出现多个不同值时，批次标记 `model_drift`，报告单独列出。
- 若 `response_model` 只是别名本身（例如 `deepseek-flash`），报告写明"服务端未暴露快照标识"，不声称已核实快照。
- `response_model_missing` 的调用比例写入报告。

## 6. 每次运行的产物

```
runs/<batch_id>/
  batch.json                  commit、未提交路径、配置哈希、模型配置、用例集版本、
                              条件顺序种子与实际顺序、服务商更新日志日期、Token 上限与用量、中止原因
  <case_id>/A/
    input.json                实际发送的输入字段（产品 CreateRunRequest 规范化后）、用例哈希、输出语言
    output.md                 A 的文档（通过校验时才存在）
    calls.jsonl               第 5 节
    meta.json                 状态、错误码、每次尝试的结果与耗时、文档哈希
  <case_id>/B/
    input.json、calls.jsonl、meta.json
    best.md、last.md、v1.md   三份文档始终分别保存（内容相同也各存一份）
    snapshot.json             最终快照
scores/<batch_id>/
  blind_map.json              doc_id ↔ 标签映射（评审完成前不提供给 Judge 和人工）
  judge/<doc_id>.pass<N>.json 每次 Judge 的原始输出、条目顺序、结构问题
  human/<doc_id>.yaml         人工复核记录（格式见 human.py 的 HumanReview）
  doc_scores[.rN].json        评分结果；每次重新计算生成新版本
reports/<batch_id>[.rN].md / .csv
```

所有产物以独占方式创建，已存在的文件一律拒绝覆盖；同一 batch_id 不能重复运行。重新计算分数（例如补充人工复核后）生成 `.r2`、`.r3` 等新版本，旧版本保留。是否提交进 Git 待人工决定（见 `config/pilot.yaml` 的 `open_decisions`）。

## 7. 失败、重跑与异常

**失败定义：**
- A：两次尝试都未通过校验，或遇到不可重试错误。
- B：最终状态为 `FAILED`（含整次 run 600 秒超时）。`MAX_ITERATIONS_REACHED` 是正常结束，不算失败。

**失败后的评分：**
- B 失败但已有已提交版本：仍对 `best_version` 评分，同时计入失败率。
- 没有任何可评文档的运行：质量分按两种口径报告——①意向性口径（ITT）记 0 分并计为含严重缺陷；②完成口径，只统计有文档的运行。两个口径必须同时出现。

**允许重跑的唯一情形：** 基础设施错误——即运行因 `PROVIDER_TEMPORARY_ERROR`（429、5xx、连接或传输超时）在重试耗尽后失败。规则：
- 每个用例每个条件最多重跑 1 次；
- 对 A、B 对称适用：只要任一条件因此重跑，另一条件的原结果保留，不追加重跑；
- 原始失败运行的产物保留，报告列出所有重跑。

**不允许重跑：** 内容质量差、校验失败（截断、缺结束标记）、结构化输出无效、模型 ID 无效、鉴权或余额错误、整次 run 超时。前四类是被测系统的真实表现；后两类说明配置有问题，应中止整个批次而不是重跑单个用例。

**批次中止条件：** 出现 `PROVIDER_MODEL_INVALID`、`AUTHENTICATION_FAILED`、`INSUFFICIENT_BALANCE`、`FORBIDDEN`，或累计 Token 达到批准的预算上限。

## 8. 盲化与评审流程

1. **匿名化：** 每份待评文档分配随机 ID（固定种子，映射表单独保存，评审完成前不向 Judge 和人工评审者公开）。只传文档正文，不传文件名、时间、Token 或条件信息。同一运行中内容完全相同（SHA-256 相同）的文档（例如 `B.best` 与 `B.last`，或 v1 即为最佳版本时的 `B.best` 与 `B.v1`）只评一次，复用分数。
2. **程序化检查：** 完整性、长度等协变量、结构计数（只记录不计分）。
3. **LLM Judge（需另行批准）：** 每份文档独立评两次，第二次打乱 R、C 条目顺序；Judge 看到的是匿名文档 + 该用例的冻结输入 + 金标准 + Rubric。输出要求见 [rubric.md](rubric.md) 第 8 节。
4. **证据校验：** 程序检查 Judge 引用的每段原文是否逐字出现在文档中；找不到的引用作废，对应判定退回人工。
5. **人工复核：** 范围与比例见 [rubric.md](rubric.md) 第 9 节。人工评审者在复核期间同样不知道条件标签。
6. **揭盲与汇总：** 全部人工复核完成并锁定后，才合并映射表、计算对比结果。

残余泄露风险：B 的文本可能更长、结构更完整，评审者可能据此猜出条件。报告中记录评审者事后对每份文档条件的猜测与把握度，用来估计盲化效果。

**Judge 校准（在正式评分前）：** 先由人工对 2 份不参与正式统计的 Mock 或手写示例文档打分，再用 Judge 评同样两份，比对后只允许调整 Judge prompt 的措辞，不允许调整 Rubric 和金标准。Judge prompt 在正式评分前冻结并记录哈希。

## 9. 报告

`reports/<batch_id>.md` 至少包含：

1. 批次元数据：commit、配置哈希、用例哈希、时间窗口、模型配置、`response_model` 观测值与一致性、`model_drift` 标记。
2. 每份文档的总分、六个维度得分、加权覆盖率 r、严重缺陷列表；每个数字标注 `auto` 或 `human_reviewed`。
3. 三组对比（`B.best − A`、`B.best − B.v1`、`A − B.v1`）的逐用例配对差值与汇总；`B.last` 单独列出。
4. 按用例类型（8 类）列出结果。
5. 成本侧：每个条件的调用次数、输入/输出 Token、缓存命中 Token（如有）、端到端耗时、首 token 延迟、估算成本与对账成本，以及 B 相对 A 的倍数。
6. 可靠性：失败率（按错误码）、各节点重试与修复次数、质量门槛通过率（仅 B）、B 的最终状态分布。
7. B 内部评审分数与外部评分的相关性（仅描述，n 很小）。
8. 分数与文档长度的相关性，以及长度分层后的结果。
9. Judge 两次评分的一致率、Judge 与人工的一致率。
10. 局限性：至少重申归因边界、样本量、浮动别名、不可复现采样、残余盲化泄露。

`reports/<batch_id>.csv` 每个标签一行（内容相同、共用一个 doc_id 的标签各占一行），字段与报告第 2 项一致；缺失值留空，不写 `N/A`。

## 10. 第一阶段规模与预算

- 规模：8 个用例 × 2 个条件 × 1 次 = 16 次运行，最多 32 份文档（A、B.best、B.last、B.v1），内容相同的去重后评分，预计 24 份左右。
- 执行前先跑 1 个用例做冒烟测试，用于核对调用记录字段、`response_model`、Token 交叉核对和账单对账流程。冒烟测试结果不计入 Pilot 统计。冒烟测试同样需要批准。
- 预算：在请求批准时提供基于冒烟测试实测 Token 的估算，以及硬性的 Token 上限；未提供前不执行。

