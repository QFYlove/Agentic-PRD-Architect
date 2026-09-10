# Round 2 实现任务 Prompt

你当前位于 `Agentic-PRD-Architect` 仓库中，正在执行 AI Coding Benchmark 的 Round 2。

你的任务是实现下方完整给出的 canonical specification（规范基准）。

本次运行规则：

- 从已提供给你的仓库状态开始。该仓库已准备在 `ai-coding-benchmark-v1` / `0edc069`。
- 首先阅读并遵守仓库自身的 `AGENTS.md` 以及其他相关 baseline 文档，然后根据需要检查真实代码。
- 完整实现该功能，包括 canonical specification 要求的测试。
- 你可以修改源代码和测试，并运行相关开发/测试命令。
- 不得查看其他 benchmark 系统的输出、分支、worktree、transcript、报告或实现。
- 不得依赖或重建你自己在 Round 1 中提出的方案。以下 canonical specification 是本轮实现的唯一权威依据。
- 不得修改 benchmark prompts、specs、raw-output records、metrics 或其他 evaluation artifacts。
- 避免与本需求无关的重构和依赖变更。
- 不要创建 Git commit。
- 尽最大努力自主完成实现。不要因为 canonical specification 已经明确回答的设计选择而停下来询问；对于规范有意留白的实现细节，请做出符合当前仓库惯例的合理选择并继续。
- 在完成之前，运行你能够执行的、与本仓库相关的 test/static/type/build 检查，并在可能的情况下自主修复失败。
- 最终回答请使用中文，并报告：实现摘要、实际运行过的测试/检查及其结果、以及任何仍未解决的限制或 blocker。除非你实际运行过某项测试，否则不要声称它已通过。

现在开始实现。

---

# Round 2 Canonical Specification — Run 级 Provider / Model 选择

状态：**Round 2 已冻结（Frozen for Round 2）**  
Benchmark baseline：`ai-coding-benchmark-v1` / `0edc069`  
任务类型：实现 + 测试

## 1. 目的

在 Agentic-PRD-Architect 中实现 **Run 级 Provider / Model 选择（Run-level Provider / Model Selection）**。

用户创建新 Run 时，必须能够为该 Run 选择一个允许使用的 Provider 和一个允许使用的 Model。可选项由后端控制。解析后的选择在该 Run 整个生命周期内不可变，需要随 Run 持久化，并且能够在安全的 Run/Telemetry 元数据中查看，同时绝不能泄露后端凭据或内部连接信息。

本规范是 Round 2 的权威依据。Round 1 中各 Agent 提出的方案不是本轮实现指令。如果 Round 1 的方案之间存在分歧，所有 Round 2 系统都必须遵循本文档，而不是遵循自己此前的方案。

## 2. Baseline 与实现约束

实现必须：

- 从 Git tag `ai-coding-benchmark-v1`、commit `0edc069` 开始；
- 除非本规范明确要求改变，否则保留现有仓库惯例和契约；
- 避免无关重构；
- 除非 baseline 确实无法在不增加/升级依赖的情况下实现该功能，否则避免新增或升级依赖；
- 保留现有核心 Agent pipeline 和执行语义；
- 保留现有 REST 控制、SSE streaming、Pause、Resume、Cancel 行为；
- 保留 SQLite 作为 source of truth；
- 保留确定性的 Mock 和 Scenario Mock 行为；
- 所有凭据和私有 Provider 配置都必须仅保留在后端。

本任务中不得重新设计以下核心行为：

- Generator → 三个独立 Reviewer → Aggregator → Optimizer；
- Reviewer 并行执行；
- 确定性的 Aggregator 行为；
- quality-gate 行为；
- 与 Provider/Model 选择无关的既有 Run 生命周期语义。

除非该功能严格要求，否则以下现有契约约束必须保持稳定：

- 现有 `HealthResponse` 的字段形状和语义；
- 现有 `RunEventType` 集合——不要仅为了表示 Provider/Model 选择而新增事件类型。

## 3. 规范术语

### Provider

由后端配置的模型 Provider。它具有：

- 用于 API 和持久化的稳定 `provider_id`；
- 展示给用户的安全 `provider_display_name`；
- 仅后端可见的执行配置，例如凭据和 Base URL；
- 一个或多个允许使用的 Model。

### Model

某个 Provider 下可选择的模型。它具有：

- 用于 API 和持久化的稳定 `model_id`；
- 展示给用户的安全 `model_display_name`；
- 可选的安全 capability 元数据；
- 可选的、仅后端可见的 model-specific pricing 元数据。

`model_id` 只需要在所属 Provider 内唯一。一次选择的规范身份是 `provider_id + model_id` 这一对值。

### Run selection

创建新 Run 时解析并确定的、不可变的 Provider/Model 组合。

## 4. 后端控制的安全 catalog

后端必须暴露一个只读 catalog，包含当前可选择的 Providers 和 Models。

使用仓库现有 API prefix/routing 约定，并新增相对路径为以下地址的 catalog endpoint：

`GET /providers`

响应在结构上必须等价于：

```json
{
  "providers": [
    {
      "provider_id": "provider-a",
      "provider_display_name": "Provider A",
      "models": [
        {
          "model_id": "model-a1",
          "model_display_name": "Model A1",
          "capabilities": null
        }
      ]
    }
  ]
}
```

要求：

- catalog 必须由后端控制的 configuration/registry 数据生成，而不是由前端常量生成。
- 只有对新 Run 而言有效且当前可选择的条目才可以出现在 catalog 中。
- 前端绝不能增加或覆盖 Provider、Model、credential、Base URL、header 或其他私有执行设置。
- 响应绝不能包含 API keys、tokens、secrets、私有 Base URLs、auth headers、原始环境变量值、任意后端配置透传内容或真实 model pricing 数值。
- `capabilities` 可以为 `null`，也可以只包含安全的公开元数据。
- Model pricing 配置仍然仅保留在后端。前端可以展示某个 Run 计算出的 Telemetry cost，但不能通过该 catalog 获得按 token/按 million 配置的 model price table。
- 合法但为空的 catalog 返回空的 `providers` 数组。
- catalog 配置/加载失败必须作为错误暴露，不能被转换成伪造的/default catalog。

只要保持上述外部可观察行为，实现可以自行选择内部 config schema、registry class、factory 和 dependency-injection 模式。

## 5. Create Run API 语义

扩展现有 Create Run request，不得重命名或替换现有 Create Run endpoint。

request 新增两个字段：

- `provider_id`
- `model_id`

### 5.1 显式选择

新的前端流程中，这两个字段必须一起发送。

当两个字段同时存在时，后端必须验证：

1. `provider_id` 存在于当前后端 catalog 中；
2. `model_id` 存在于该指定 Provider 下；
3. 该组合当前可选择/可用。

任何检查失败时：

- Run 创建必须失败，并使用仓库现有 error-envelope 约定返回清晰的 4xx 错误；
- 不得创建或部分持久化任何 Run；
- 不得替换 Provider 或 Model；
- 任何 retry 都不得静默改变该选择。

只包含 `provider_id` 或 `model_id` 其中一个字段的 request 必须校验失败。

### 5.2 旧版 Create Run 兼容性

如果 request 两个字段都不包含，则视为 legacy request，并且必须继续被接受。

仅对于该 legacy 路径：

- 保留 baseline 现有的默认 Provider/Model 解析行为；
- 在执行前，将该默认值解析为具体的 Provider/Model 组合；
- 对每个新创建的 Run 持久化解析后的组合；
- 如果 legacy default 无法解析为一个有效、可用的组合，则必须明确失败，不得以未知模型或静默替换后的模型启动 Run。

legacy 兼容路径不代表显式提供组合时允许 fallback。

### 5.3 Response 兼容性

现有 response 字段及其含义必须保持兼容。可以以向后兼容的方式新增安全的 Provider/Model 元数据。

## 6. Run 级绑定与并发隔离

Provider/Model 执行配置必须绑定到 Run，而不是绑定到可变的全局“current Provider/current Model”状态。

对于一个新创建的 Run：

- 在创建/启动时只解析一次 `provider_id + model_id`；
- 将解析得到的后端执行配置绑定到该 Run；
- 在该 Run 剩余生命周期内保持选择不可变；
- 属于该 Run 的每一次 Generator/Reviewer/Optimizer 模型调用都必须使用该 Run 绑定的选择。

实现必须支持两个或更多并发 Run 使用不同 Provider/Model 组合，且彼此之间不能发生 cross-talk。

修改、创建、暂停、恢复或取消一个 Run，都不得改变另一个 Run 的 Provider/Model 选择。

允许共享只读 catalog/registry。不允许共享可变的 selected Provider/Model 状态。

## 7. 持久化与旧 SQLite 兼容性

Round 2 不允许 SQL DDL migration。

通过现有 SQLite 持久化路径存储的 Run serialized snapshot/payload 必须新增等价于以下内容的 nullable 字段：

- `provider_id`
- `provider_display_name`
- `model_id`
- `model_display_name`

要求：

- Round 2 实现后创建的每个新 Run 都必须持久化上述四个已解析值。
- display name 必须是 Run 创建时的名称快照，而不是在展示旧 Run 时从当前 catalog 动态重新解析。
- service restart 或 page refresh 后，已存储的 selection metadata 不得丢失。
- Round 2 之前创建的既有 SQLite database 和既有 Run row 必须无需 schema migration 即可继续读取。
- 当旧 snapshot 缺少这些字段时，将其反序列化为 `null`/missing-compatible 值；不得伪造历史值。
- 读取不包含 selection metadata 的旧 Run 时，既有 API/UI 不得崩溃。

如果一个 Round 2 之前创建、且没有持久化 selection 的旧 Run 必须继续进行额外模型执行，则保留 baseline 的 legacy Provider 解析行为。此兼容行为不得用于新 Run 或显式选择。

## 8. Rehydration 与历史 selection 不再可用时的行为

当一个持久化的新格式 Run 包含 Provider/Model selection 时，任何需要重建 Provider access 的执行路径都必须使用已持久化的 IDs。

如果持久化的显式 selection 已经不再存在于后端配置中：

- 该模型执行操作必须明确失败；
- 不得切换到其他 Provider/Model；
- 必须保留历史 IDs/display names 供查看。

系统必须区分“历史元数据仍然可读”和“该历史 Provider/Model 当前仍可执行”这两个概念。

## 9. Telemetry、Run 信息与契约保持

安全的 Run/Telemetry 信息必须让用户可以查看该 Run 选择的模型。

对于新 Run，至少暴露：

- `provider_id`
- `provider_display_name`
- `model_id`
- `model_display_name`

这些值必须来自 Run snapshot，而不是来自可变的当前 catalog lookup。

对于旧 Run，这些字段可以为 `null`，也可以在 UI 中表示为不伪造信息的 legacy/unknown 状态。

Telemetry、Run APIs、SSE payloads、返回给前端的 logs 和 error payloads 绝不能暴露：

- API keys；
- bearer tokens；
- auth headers；
- 私有/内部 Base URLs；
- secret environment variables；
- 原始 backend Provider config objects。

如果现有 Run-level Telemetry 已经提供稳定位置来暴露所选 Provider/Model，本任务不要求把 Provider/Model metadata 添加到每一个单独的 SSE event 中。

契约保持规则：

- 保持现有 `HealthResponse` 的字段形状和语义不变。
- 不要仅为了表示 Provider/Model selection 而新增 `RunEventType`。
- 优先通过持久化的 Run/Telemetry metadata 暴露所选择的 Provider/Model。

## 10. Per-model pricing 语义

任何受本功能影响的 pricing/cost 逻辑都必须以 Model 为作用域。

要求：

- pricing 属于某个具体 Model，而不是仅属于 Provider 或一个全局 default；
- pricing 配置仅保留在后端；
- 如果计算 cost estimate，必须使用该 Run 所选 Model 的 pricing；
- 绝不能将另一个 Model 的 pricing 作为 fallback；
- 如果所选 Model 的 pricing 未配置/未知，则得到的 cost/price 值必须是 `null`/unknown，而不是 `0`，也不能猜测；
- 显式配置为 0 的价格必须与缺少 pricing 明确区分；
- 除非 baseline 本身已经要求执行时必须存在 pricing，否则缺少 pricing 不得阻止 Run 执行。

如果 baseline 已经存在 pricing unit/currency schema，不要重新发明新的 schema。尽可能保留现有 pricing unit 和公开 Telemetry contract，同时将 lookup 语义调整为 per-model。

## 11. 前端行为

新的 Create Run UI 必须从后端 catalog 获取全部 Provider/Model 选项。

要求行为：

1. 在 Create Run 流程需要 catalog 时加载它。
2. 使用安全 display name 展示 Provider selector。
3. Model selector 只能展示属于当前已选 Provider 的 Models。
4. 在选择完整、有效的 Provider/Model 组合之前，不得启用新 Run 创建。
5. 新 UI 流程必须同时提交 `provider_id` 和 `model_id`。
6. Provider 改变时，如果当前 Model 对新 Provider 无效，必须清空/重置该 Model selection。
7. 如果 backend 拒绝一个 invalid/stale selection，不得在客户端静默替换它。
8. 展示清晰的失败状态，并允许用户重新选择。

### Catalog 状态

- **Loading：** selector/Create action 暂时不可用。
- **Empty：** 说明当前没有可用 Provider/Model，并禁用 Create。
- **Error：** 说明 catalog 加载失败并禁用 Create；允许 retry。
- **Loaded：** 仅在已选择有效组合后启用 Create。

前端不得包含 Provider credentials、私有 Base URLs 或一份并行的 hard-coded authoritative catalog。

### 既有 Run 展示

Run details/Telemetry UI 必须展示新 Run 持久化的 Provider 和 Model display names。

没有 metadata 的旧 Run 必须安全渲染，且不得伪造 selection。

## 12. Mock 与 Scenario Mock 要求

现有 Mock 和 Scenario Mock 行为必须继续保持确定性。

Provider/Model selection 功能不得：

- 在确定性的 mock tests 中引入 network access；
- 让 mock 输出依赖不确定的 catalog ordering；
- 改变逻辑 Agent pipeline；
- 让 Scenario Mock 行为依赖真实外部 Provider。

测试 fixture 可以提供确定性的 backend catalog。如果 catalog 中表示 Mock/Scenario Mock selection，其 IDs/display names 也必须是确定性的。

除非为了以向后兼容方式增加 Provider/Model metadata，现有 mock golden/contract 行为应保持不变。

## 13. 禁止静默 fallback — 规范规则

以下情况必须明确失败，并且绝不能静默 fallback：

- 未知 `provider_id`；
- 未知 `model_id`；
- Model 确实存在，但属于另一个 Provider；
- 不可用/被禁用的组合；
- 已持久化的显式 selection 当前已经无法解析执行；
- catalog 配置/加载失败。

唯一允许的兼容性解析，是第 5.2 节和第 7 节中针对真正早于新显式 selection 字段的 requests/Runs 所定义的 legacy 行为。

## 14. 必需测试覆盖

Round 2 如果缺少测试则视为未完成。这些是对 coding systems 的实现要求；benchmark operator 在开始 Round 2 前不需要额外构建大型 hidden-test suite。

### 14.1 Backend pytest

至少覆盖：

- safe catalog 成功响应；
- catalog 永远不会序列化 credentials/private Base URLs 或真实 model pricing 配置；
- 有效显式 selection 可以创建 Run；
- selection 持久化 IDs + display names；
- unknown Provider 失败且不创建 Run；
- unknown Model 失败且不创建 Run；
- Provider/Model cross-pair mismatch 失败；
- 两个 selection 字段只提供其中一个时校验失败；
- 两个字段都不提供的 legacy Create Run request 仍保持兼容；
- 缺少新字段的旧 Run snapshot/database row 仍可加载；
- 不需要 SQL DDL migration；
- 持久化的新 Run 在 repository/service reopen 后仍保留 metadata；
- 使用不同 selections 的并发 Runs 保持隔离；
- 已持久化的显式 selection 不可用时失败，而不是 fallback；
- 正确选择 per-model pricing；
- 所选 Model 缺少 pricing 时得到 `null`/unknown，而不是 `0`/fallback；
- Mock/Scenario Mock determinism 保持不变；
- 已选择 Provider/Model 的 Runs 仍保持既有 Pause/Resume/Cancel 行为；
- 既有 `HealthResponse` contract 保持不变。

### 14.2 Contract tests

至少覆盖：

- `GET /providers` 的 safe response shape；
- 向后兼容的 Create Run request/response schema；
- 显式 `provider_id + model_id` request fields；
- 旧 Run 中 nullable 的 Provider/Model metadata；
- 新 Run 中 non-null 的 persisted metadata；
- 既有 SSE/REST contracts 不发生回归；
- 不需要仅为了该功能新增 `RunEventType`。

### 14.3 Vitest

至少覆盖：

- catalog loading state；
- empty state；
- error state 与 retry 行为；
- Provider selection 会过滤 Models；
- Provider 改变时使不兼容的 Model selection 失效；
- 没有完整有效组合时 Create disabled；
- Create request 同时发送两个 IDs；
- backend selection error 被展示出来，且 client-side 不进行 fallback；
- 新 Run metadata 能够在 Run/Telemetry UI 中展示；
- null/missing metadata 的旧 Run 能安全渲染。

### 14.4 Playwright E2E

至少覆盖：

- 加载 catalog → 选择 Provider → 选择 Model → 创建 Run → 在 Run/Telemetry UI 中观察到同一份持久化 selection；
- 创建两个使用不同 selections 的 Runs，并验证每个 Run 都保持自己的 metadata/behavior；
- empty 或 failed catalog 会阻止创建新 Run；
- legacy/existing Run navigation 仍正常工作。

Playwright tests 应使用确定性的本地/mock fixtures，并且绝不能要求 billable external model calls。

### 14.5 Static/type/build 检查

运行仓库惯例要求的所有相关 backend/frontend static、type 和 build 检查。

## 15. 验收标准

只有在以下条件全部成立时，实现才算功能完整：

- [ ] 新 UI 创建的 Run 始终显式提交 `provider_id + model_id` 组合。
- [ ] Backend catalog 是权威且安全的。
- [ ] 前端 catalog 不会收到 credential/private Base URL 或真实 model pricing 配置。
- [ ] 无效或不可用的显式 selections 会失败，不 fallback，也不会产生部分 Run。
- [ ] selection 按 Run 绑定，并在并发 Runs 之间隔离。
- [ ] 新 Run snapshots 持久化 IDs + display names。
- [ ] 旧 APIs 保持兼容。
- [ ] 旧 SQLite 数据无需 SQL DDL migration 即可读取。
- [ ] catalog 配置变化后，持久化的历史 selections 不会被静默改变。
- [ ] Per-model pricing 语义正确；缺少 price 时为 `null`/unknown。
- [ ] Mock 和 Scenario Mock 保持确定性。
- [ ] 核心 Agent loop 和 lifecycle 行为保持不变。
- [ ] 既有 `HealthResponse` 和 `RunEventType` contracts 保持稳定。
- [ ] Catalog 的 loading/empty/error 状态会阻止新 UI 创建 Run。
- [ ] Backend pytest、contract、Vitest、Playwright 以及 static/type/build 覆盖被新增或更新，并且相关 suites 通过。

## 16. 明确非目标

Round 2 不要求：

- 从前端编辑 Provider credentials；
- 用户提供任意 Base URLs 或 API keys；
- 在 catalog 中暴露 backend model price tables；
- 修改一个已经创建的 Run 的 Provider/Model；
- 新增 database column 或 SQL DDL migration；
- 重新设计 Agent pipeline；
- 重新设计 REST/SSE transport；
- 重新设计 Pause/Resume/Cancel；
- 仅为了 Provider/Model selection 新增 `RunEventType`；
- 与 Run-scoped binding 无关的大范围 Provider abstraction refactor；
- 除表示 backend-controlled configured catalog 所需之外，额外增加新的 external Providers；
- 在 E2E tests 中进行真实付费 Provider 调用。

## 17. 实现自由度

本 benchmark 评估系统能否理解 baseline 仓库，并干净地实现该行为。因此，除上述不变量外，不规定具体内部实现选择。

Agent 可以选择符合仓库惯例的 module boundaries、types、factories、dependency injection 和 helper abstractions。不得为了适配自己偏好的架构而削弱或重新解释外部可观察要求。
