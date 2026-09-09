## A. 当前架构理解

  当前实现中，Provider/Model 是进程级配置，不是 Run 级配置：

  - backend/config.py 通过 Settings 读取：
      - ENABLE_MOCK_LLM
      - LLM_PROVIDER
      - DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL、DEEPSEEK_MODEL
      - GLM_API_KEY、GLM_BASE_URL、GLM_MODEL

  - backend/main.py 的 create_app() 根据全局配置创建一个 MockLLMProvider、ScenarioMockLLMProvider 或 OpenAICompatibleLLMProvider，然后
    把单个 Provider 注入 RunManager。

  - backend/providers/base.py 定义统一的 LLMProvider 接口，Generator、Reviewer、Optimizer 都使用同一个 Provider 实例。
  - backend/providers/compatible.py 是 DeepSeek/GLM 共用的 OpenAI-compatible adapter，真实调用时把 model=self.model 发送给上游。
  - backend/providers/mock.py 提供确定性 Mock 行为；scenario.py 为 E2E 场景控制提供扩展 Mock。
  - backend/run_manager.py 的 RunManager 当前持有一个全局 self.provider。创建 Run 时将 self.provider.is_mock 写入快照，并在 workflow
    中复用该 Provider。

  - backend/workflow.py 构建 Generator → 三个独立 Reviewer 并行 → Aggregator → Optimizer 的核心流程。Provider 是通过 workflow/manager
    依赖传入的。

  - backend/schemas.py 中：
      - CreateRunRequest 只有产品输入、质量阈值和迭代次数。
      - PRDRunState/RunSnapshot 保存运行状态、版本、评审、Token、成本、Mock 状态等，但没有 Provider/Model 字段。
      - HealthResponse 仅返回当前全局 Provider 名称和 Mock 状态。

  - backend/run_store.py 使用内存字典加 SQLite runs(snapshot_json) 保存快照。快照整体 JSON 化，没有独立 Provider/Model 表。
  - backend/main.py 暴露：
      - POST /api/runs
      - GET /api/runs/{run_id}
      - GET /api/runs
      - Pause/Resume/Cancel
      - SSE /api/runs/{run_id}/events
      - /api/health

  - 前端：
      - src/components/ProductIdeaForm.tsx 收集产品想法、目标用户、约束、质量阈值和最大迭代次数。
      - src/components/AgentDashboard.tsx 组合创建表单、Run 控制和结果展示。
      - src/hooks/useAgentRun.ts 负责创建 Run、Snapshot-first 恢复和 SSE 生命周期。
      - src/lib/api.ts 定义 REST client。
      - src/lib/types.ts 和 src/lib/contracts.ts 维护前后端契约。
      - src/components/TelemetryPanel.tsx 展示后端提供的 Telemetry，但目前没有 Provider/Model 信息。

  - 当前向后兼容模式已经存在：
      - SQLite 读取旧 Snapshot JSON 时，Pydantic 默认字段可以兼容新增可选字段。
      - RoleReview.feedback 对历史 list[str] 数据有显式转换逻辑。
      - 前端契约也对部分旧数据做归一化。

  ## B. 影响范围

  预计需要修改：

  - backend/config.py
      - 将单一 llm_provider/单一模型配置扩展为后端控制的允许 Provider/Model catalog。
      - 保留旧环境变量作为兼容输入。
      - 增加 catalog 校验、默认选择和可用性状态定义。

  - backend/schemas.py
      - 新增安全的 Provider/Model 元数据模型。
      - CreateRunRequest 增加 Provider/Model 选择字段。
      - PRDRunState/RunSnapshot 增加已选择的 Provider/Model 标识及安全展示信息。
      - 新增 Provider catalog API response 模型。
      - 新增稳定错误码相关模型无需改变现有错误 envelope。

  - backend/providers/base.py
      - 让 Provider 实例明确携带 provider_id、provider_display_name、model_id、model_display_name、is_mock 和安全能力元数据。
      - 接口方法本身不应接收或暴露凭据。

  - backend/providers/compatible.py
      - 保留当前 adapter，但构造参数改由 catalog entry 解析。
      - Provider/Model metadata 与内部 api_key/base_url 分离。
      - 继续将凭据仅用于后端 SDK client。

  - backend/providers/mock.py
      - 支持按 catalog entry 创建 Mock provider。
      - 维持当前确定性场景与现有分数、延迟、重试语义。

  - backend/providers/scenario.py
      - 确保 E2E 场景可绑定到被选择的 Mock entry，并继续支持超时/暂停等测试控制。

  - backend/main.py
      - 增加安全 catalog endpoint。
      - 创建 Run 时解析并校验请求中的 Provider/Model。
      - 为每个 Run 建立对应 Provider/workflow context。
      - /health 只返回安全的默认/运行模式信息，不返回 catalog 中的 secret。

  - backend/run_manager.py
      - 从“全局单 Provider”改为“Run 绑定 Provider”。
      - 创建时保存选择，并把 provider context 传给 workflow。
      - Telemetry、日志、事件 payload 使用 provider/model id，不使用凭据。

  - backend/workflow.py
      - 接收当前 Run 的 Provider，保证一个 Run 的所有 Generator/Reviewer/Optimizer 调用使用同一选择。
      - 不改变并行 Reviewer、Aggregator 确定性计算和质量门逻辑。

  - backend/run_store.py
      - 主要是兼容验证与快照读写检查。
      - 若采用 Snapshot JSON 内嵌字段，通常不需要 schema migration；仍应增加旧 JSON 默认值测试。

  - backend/observability.py、backend/telemetry.py
      - 结构化日志和 Telemetry 增加安全的 provider_id/model_id。
      - 明确禁止记录 API key、token、base URL。

  - src/lib/types.ts
      - 新增 Provider/Model metadata、catalog response、Run selection、Snapshot 字段。

  - src/lib/contracts.ts
      - 解析 catalog response、创建请求和旧 Snapshot。
      - 对旧 Snapshot 缺失 Provider/Model 字段进行兼容归一化。

  - src/lib/api.ts
      - 增加 listProviderCatalog() 或等价方法。

  - src/components/ProductIdeaForm.tsx
      - 加载并展示允许的 Provider/Model。
      - 增加联动选择和加载、空列表、错误状态。

  - src/components/AgentDashboard.tsx
      - 在创建表单加载 catalog，并把选择传给表单。
      - 在 Run 详情上下文中展示当前 Run 的 Provider/Model。

  - src/components/TelemetryPanel.tsx
      - 展示本次 Run 的安全 Provider/Model 信息。

  - src/components/ConversationSidebar.tsx 或 Run 摘要相关组件
      - 如需要，在历史 Run 列表中显示模型选择。

  - src/components/*.test.tsx、src/hooks/*.test.tsx、src/lib/*.test.ts
      - 更新创建请求、Snapshot 和 catalog 相关测试。

  - backend/tests/test_config.py
      - catalog 配置、默认值、secret 隔离和非法配置测试。

  - backend/tests/test_schemas.py
      - 新字段校验、旧 JSON 兼容、非法 Provider/Model 测试。

  - backend/tests/test_api.py、test_contracts.py
      - catalog endpoint、创建 Run 选择、明确错误语义和响应契约测试。

  - backend/tests/test_run_manager.py、test_workflow.py
      - Run-specific provider 绑定与全流程使用同一 provider 测试。

  - backend/tests/test_run_store.py
      - 旧 SQLite snapshot 读取、新字段持久化、重启恢复测试。

  - backend/tests/test_telemetry.py、test_observability_security.py
      - Provider/Model 可见、凭据不可见测试。

  - e2e/
      - Playwright 选择 Provider/Model、创建 Run、刷新恢复和错误场景。

  - contracts/v1/
      - 若该目录作为正式 JSON contract source，应新增或更新 CreateRun、catalog、Snapshot fixture。

  不建议修改无关的 LangGraph 状态机、评分聚合、质量门或 SSE 事件机制。

  ## C. 数据模型与 API 设计

  ### Provider/Model 元数据

  建议后端内部定义两层模型：

  class ProviderModelOption(BaseModel):
      provider_id: str
      provider_display_name: str
      model_id: str
      model_display_name: str
      capabilities: dict[str, bool] = {}
      available: bool = True

  内部配置 entry 另外保存：

  class ProviderModelConfig:
      provider_id: str
      model_id: str
      api_key: SecretStr | None
      base_url: str
      ...

  前端只接收 ProviderModelOption，绝不序列化或返回 api_key、base_url、内部 headers、SDK client 配置或 pricing secret。

  capabilities 只允许安全信息，例如 structured output、streaming、reasoning disabled；不要把供应商内部路由或配额信息公开。

  ### 新增 endpoint

  建议：

  GET /api/providers

  返回后端当前允许且可展示的 Provider/Model 元数据：

  {
    "items": [
      {
        "provider_id": "deepseek",
        "provider_display_name": "DeepSeek",
        "model_id": "deepseek-v4-flash",
        "model_display_name": "DeepSeek V4 Flash",
        "capabilities": {
          "streaming": true,
          "structured_output": true
        },
        "available": true
      }
    ]
  }

  “允许”与“可用”应区分：

  - 不在 catalog 中：请求无效。
  - 在 catalog 中但缺少 key、配置错误或暂时禁用：明确标记 available=false，创建时失败。
  - Mock catalog entry 在 Mock 模式下应始终可用，除非测试显式禁用。

  ### 创建 Run API

  POST /api/runs 请求增加：

  {
    "provider_id": "deepseek",
    "model_id": "deepseek-v4-flash"
  }

  建议字段名使用 provider_id 和 model_id，避免把 display name 当作稳定标识。

  字段可以先设为可选以兼容旧客户端：

  - 两者都缺失：使用后端配置的 default selection。
  - 只缺一个：返回 INVALID_PROVIDER_SELECTION。
  - 指定了不存在的组合：返回 PROVIDER_MODEL_NOT_ALLOWED。
  - 指定 entry 存在但不可用：返回 PROVIDER_MODEL_UNAVAILABLE。
  - 不允许自动换模型或自动切 Mock。

  新客户端应始终发送明确选择；旧客户端仍可依赖默认选择。

  ### RunSnapshot

  在 PRDRunState 中保存至少：

  provider_id: str
  provider_name: str
  model_id: str
  model_name: str
  provider_capabilities: dict[str, bool]
  is_mock: bool

  更稳妥的是只持久化安全元数据和稳定 id：

  - provider_id
  - model_id
  - provider_display_name
  - model_display_name
  - 可选 capabilities 快照
  - is_mock

  不要把 base_url、API key、secret pricing 或 SDK 配置写入 Snapshot。

  保存 display name 是为了历史 Run 在 catalog 后续改名后仍能准确显示当时的选择；id 用于机器识别。

  ### Telemetry / Run 信息

  在 Snapshot、run_started、telemetry_updated 和最终 Run 信息中加入：

  {
    "provider_id": "deepseek",
    "model_id": "deepseek-v4-flash"
  }

  必要时加入安全 display name。禁止加入：

  - API key
  - Authorization header
  - token
  - Base URL
  - 原始 provider exception
  - 内部请求体

  ### 错误语义

  建议稳定错误码：

  - PROVIDER_SELECTION_REQUIRED
  - INVALID_PROVIDER_SELECTION
  - PROVIDER_MODEL_NOT_ALLOWED
  - PROVIDER_MODEL_UNAVAILABLE
  - PROVIDER_CONFIGURATION_INVALID

  HTTP 状态建议：

  - 400：请求字段组合非法。
  - 404 或 400：Provider/Model 不存在。为了避免资源枚举，也可以统一使用 400。
  - 409：catalog entry 存在但当前不可用/配置不满足。
  - 422：Pydantic 基础字段验证失败。

  错误消息只说明安全原因，不暴露 key 是否存在的细节、完整 Base URL 或上游错误堆栈。

  ## D. Provider 层设计

  当前 factory 在 main.py:create_app() 内以 if/else 读取全局 Settings，构造单个 provider。推荐引入后端内部的 registry/factory：

  ProviderCatalog
    ├─ safe metadata for GET /api/providers
    └─ internal runtime config for provider construction

  ProviderFactory.build(provider_id, model_id)
    ├─ validate exact allowed pair
    ├─ validate availability and credentials
    ├─ build OpenAICompatibleLLMProvider or MockLLMProvider
    └─ raise explicit error on failure

  Run 创建流程应为：

  1. 读取请求中的 provider_id/model_id。
  2. 在 catalog 中精确查找允许的组合。
  3. 检查该 entry 是否可用。
  4. 创建绑定该选择的 Provider。
  5. 将 Provider 传给该 Run 的 workflow。
  6. 将安全元数据保存进 Snapshot。

  不要让 workflow 再次从环境变量选择模型，也不要让 provider 在找不到模型时回退到默认模型。

  ### 并发与生命周期

  当前 RunManager 假设一个全局 Provider。改造时不应简单替换 self.provider，否则并发创建不同模型的 Run 会互相覆盖。推荐：

  - RunManager 持有 ProviderFactory/catalog，而不是单个运行 Provider。
  - 每个 Run 在创建时建立 provider context，并存入 run_providers: dict[UUID, LLMProvider]，或由 workflow runner 根据 Snapshot 懒加载。
  - AgentWorkflow.run(run_id) 通过 manager/provider resolver 获取该 Run 的 provider。
  - Run 清理时释放该 Run 的 provider context。
  - 若 SDK client 可安全复用，可按 (provider_id, model_id) 缓存；缓存不得影响选择隔离。

  ### Mock

  Mock 应作为 catalog 中的显式安全 entry，例如：

  provider_id = "mock"
  model_id = "mock-deterministic-v1"

  Mock 模式下：

  - catalog 至少返回该 Mock entry。
  - 也可以返回配置声明的真实 entry，但不可用项必须标记不可用，不能创建。
  - 现有 Podcast v1/v2 分数、延迟、结构化输出修复和 E2E scenario 行为保持不变。
  - 不得因为用户选择真实 provider 而静默降级 Mock。

  ## E. Persistence

  ### 是否需要 SQLite migration

  当前 SQLite 只有：

  runs(run_id, snapshot_json, updated_at)

  如果 Provider/Model 作为 Snapshot JSON 字段保存，原则上不需要 SQLite schema migration，也不需要新增表。优点是：

  - 修改范围小。
  - 保持现有 SQLite 事实来源和原子 Snapshot 语义。
  - 旧数据库可继续读取。

  仍建议增加一个显式 snapshot normalization 版本，或在 Pydantic 字段上提供默认值，以便老数据读取：

  provider_id = "legacy-default"
  model_id = "legacy-default"
  provider_display_name = "Legacy default"
  model_display_name = "Legacy default"

  更好的兼容行为是：旧 Run 缺字段时显示：

  - provider_id="legacy"
  - model_id="legacy"
  - display name 为 “历史默认配置”

  而不是根据当前环境配置回填，因为那会错误地把历史 Run 显示成当前模型。

  ### 新 Run 保存

  创建 Run 时在第一次 run_store.create(snapshot) 之前写入：

  - Provider/Model id
  - display names
  - safe capabilities
  - is_mock

  后续所有快照更新都会通过现有 JSON 持久化自动保留这些字段。

  ### 老 Run 读取

  SQLite 启动加载时：

  1. RunSnapshot.model_validate_json(snapshot_json)。
  2. 缺少新增字段时由默认值/兼容 validator 补齐。
  3. 不改变原有 RUN_INTERRUPTED 处理逻辑。
  4. 旧 Run 的历史 Provider 信息不应伪造为当前默认值。

  ## F. Frontend

  ### 创建界面

  在 src/components/ProductIdeaForm.tsx 增加两个选择控件：

  - Provider 下拉选择。
  - Model 下拉选择。

  推荐流程：

  1. AgentDashboard 首次进入时调用 GET /api/providers。
  2. Provider 选择改变时，Model 选择自动切换到该 Provider 下第一个可用模型。
  3. 提交时发送 provider_id 和 model_id。
  4. 如果后端 catalog 发生变化，后端仍做最终校验。

  应避免在前端硬编码 DeepSeek/GLM 列表；前端只渲染 API 返回的数据。

  ### 状态

  必须覆盖：

  - Loading：显示禁用的选择控件或 skeleton。
  - Empty：没有可用 Provider/Model，禁止创建并显示可操作错误。
  - Error：catalog 获取失败，保留产品输入但禁用提交，允许重试。
  - Provider 有值但无可用 Model：显示空状态并禁用提交。
  - 创建提交期间：锁定选择，避免请求字段与界面状态不一致。
  - 旧后端不支持 /api/providers：应显示明确兼容错误，而不是回退到前端硬编码。

  ### Run 信息展示

  在 Run header、Telemetry 或 Trace 中展示：

  Provider: DeepSeek
  Model: deepseek-v4-flash

  历史 Run 从 Snapshot 中读取，不重新根据当前 catalog 推断。若是旧 Run，显示“历史默认配置”或“未记录”。

  Telemetry 只显示安全元数据，不显示任何凭据或 Base URL。

  ## G. Testing

  ### Backend pytest

  新增或修改：

  - backend/tests/test_config.py
      - catalog 配置可解析。
      - 默认选择合法。
      - provider/model entry 缺 key 时不可用。
      - SecretStr 不出现在 repr、日志或安全 catalog response。
      - 旧单一 LLM_PROVIDER 配置仍能生成兼容 catalog。

  - backend/tests/test_schemas.py
      - 合法 Provider/Model selection。
      - 只传 Provider 或只传 Model 被拒绝。
      - Snapshot 新字段校验。
      - 缺少新增字段的旧 Snapshot JSON 可读取。
      - capabilities 只接受安全结构。

  - backend/tests/test_api.py
      - GET /api/providers 只返回安全元数据。
      - 返回内容不包含 key、token、base URL。
      - 创建 Run 时选择 DeepSeek/model。
      - 创建 Run 时选择 Mock/model。
      - 不存在组合返回 PROVIDER_MODEL_NOT_ALLOWED。
      - entry 不可用返回 PROVIDER_MODEL_UNAVAILABLE。
      - 旧请求不带选择时按明确默认策略创建。
      - 不发生 silent fallback。

  - backend/tests/test_run_manager.py
      - 两个并发 Run 选择不同模型，各自绑定正确 Provider。
      - 同一 Run 所有节点调用使用同一 Provider/Model。
      - Run 清理后 provider context 释放。
      - 创建失败时不产生半成品 Snapshot 或任务。

  - backend/tests/test_workflow.py
      - Generator、三个 Reviewer、Optimizer 都使用 Run-specific provider。
      - Aggregator 仍完全确定性。
      - Pause/Resume/Cancel 行为不变。

  - backend/tests/test_run_store.py
      - 新字段写入 SQLite 并在新实例重启后读回。
      - 历史旧 JSON 无 Provider/Model 字段仍能加载。
      - 活动 Run 重启标记 RUN_INTERRUPTED 时仍保留模型信息。

  - backend/tests/test_telemetry.py
      - Telemetry 包含 provider/model id。
      - cost/mock 状态逻辑不变。

  - backend/tests/test_observability_security.py
      - 日志、事件、错误响应不含 API key、token、base URL。
      - 上游异常仍映射为稳定错误。

  ### Contract tests

  更新 contracts/v1 fixture：

  - Provider catalog response。
  - CreateRunRequest with selection。
  - RunSnapshot with selection。
  - Legacy CreateRunRequest without selection。
  - Legacy Snapshot without selection。

  验证前后端 parser 对新旧版本的行为一致。

  ### Vitest

  新增或修改：

  - src/lib/api.test.ts
      - catalog 请求 URL、成功解析、网络错误和非法响应。
      - 创建请求包含 provider/model。

  - src/lib/contracts.test.ts
      - catalog、Snapshot 新字段解析。
      - 旧 Snapshot 缺字段归一化。
      - 非法 selection 被拒绝。

  - src/components/components.test.tsx
      - Provider 列表加载后显示。
      - Provider 改变联动 Model。
      - 无可用模型禁用提交。
      - catalog 错误显示重试状态。
      - 提交 payload 包含正确的 id。

  - src/components/AgentDashboard.test.tsx
      - 初始 catalog 加载。
      - catalog 加载失败不影响已输入的产品想法。
      - Snapshot 恢复后显示该 Run 保存的 Provider/Model。

  - src/hooks/useAgentRun.test.tsx
      - 创建 Run 的 request 传递 selection。
      - 刷新恢复保留 selection。
      - SSE 事件不会覆盖 Snapshot 中的固定 selection。

  ### Playwright E2E

  新增场景：

  - Mock 模式下加载 Provider/Model，选择后创建完整 Run。
  - Provider 改变后 Model 列表联动。
  - 模拟 catalog 为空，创建按钮不可用并有清晰提示。
  - 模拟 catalog endpoint 失败，显示错误和重试。
  - 创建后刷新页面，Run 详情仍显示原 Provider/Model。
  - 服务重启/历史列表加载后，旧 Run 显示兼容占位信息。
  - 请求不存在的 Provider/Model，UI 显示明确失败，且不创建替代 Run。
  - 两个 Run 选择不同模型时各自展示正确信息。

  ### Static/type checks

  继续运行：

  ./.venv/bin/ruff format --check backend
  ./.venv/bin/ruff check backend
  ./.venv/bin/mypy backend
  npm run lint
  npm run typecheck
  npm run test:run
  npm run build
  npm run test:e2e

  ## H. 风险

  1. 全局 Provider 状态误用
      - 最大风险是继续使用 RunManager.provider，导致并发 Run 之间互相覆盖模型选择。
      - 必须让 Provider 绑定到 Run，而不是绑定到进程。

  2. silent fallback
      - catalog 查找失败、key 缺失或上游模型不可用时不能回退默认模型或 Mock。
      - 错误必须在创建阶段或明确的 workflow 阶段暴露。

  3. 敏感信息泄漏
      - 不能把 Settings、内部 provider config、SDK client 或异常对象直接序列化。
      - 日志、SSE、Snapshot、OpenAPI schema 和错误消息都需要检查。

  4. Snapshot 历史语义
      - 不应使用当前环境配置覆盖老 Run 的模型显示。
      - 新字段的默认值必须表达“历史未记录”，而不是伪造历史事实。

  5. Provider 与 workflow 生命周期
      - 每个 Run 需要稳定绑定同一 Provider；暂停、恢复、重启后的行为要清楚。
      - 当前服务重启不会自动续跑活动 Run，因此重启后只需保证历史 Snapshot 仍可读。

  6. Mock/E2E 回归
      - Mock entry 的 id 变化会影响确定性测试、Scenario 控制和 Playwright fixture。
      - 应保留一个稳定的 Mock provider/model id。

  7. 缓存与并发
      - Provider client 可以缓存，但 catalog 解析和可用性校验必须按 Run 创建时执行。
      - 不能让共享 client 的可变 model 字段被不同 Run 改写。

  8. 前后端契约漂移
      - 新 endpoint、新请求字段和 Snapshot 字段需要同步 Pydantic、TypeScript 和 contract fixtures。
      - 旧客户端/旧 SQLite 必须有明确测试覆盖。

  9. Telemetry 成本语义
      - 不同模型的 pricing 可能不同。
      - 成本配置应随内部 catalog entry 解析，前端仍只展示后端计算结果，不能自行推算。

  10. API 可用性与实际可用性混淆
      - “允许选择”不等于“当前有凭据或服务可用”。
      - catalog 要明确区分 allowed/available，但不能暴露过多内部诊断细节。

  ## I. 实施计划

  1. 先定义 Provider catalog 的内部配置模型、安全公开模型和稳定错误码。
  2. 在 config.py 中兼容现有单 Provider 环境变量，同时生成 catalog/default selection。
  3. 在 schemas.py 中加入 CreateRun、Snapshot、catalog response 字段，并实现旧 JSON 默认兼容。
  4. 实现 Provider registry/factory，将内部 secret config 与公开 metadata 分离。
  5. 保持 Mock provider 行为不变，增加稳定 Mock provider/model id。
  6. 将 RunManager 从全局 Provider 改为按 Run 创建和绑定 Provider context。
  7. 修改 workflow，使所有节点使用绑定的 Run provider。
  8. 增加 GET /api/providers，修改 POST /api/runs 的选择校验和错误返回。
  9. 将 provider/model 安全信息加入 Snapshot、Telemetry、事件和日志。
  10. 更新 TypeScript types/contracts/API client。
  11. 更新创建表单、联动选择、加载/空/错误状态和 Run/Telemetry 展示。
  12. 先补 Backend schema/factory/API 单测，再补 manager/workflow/persistence/security 测试。
  13. 补 Vitest contract、Hook、组件测试。
  14. 补 Playwright E2E，包括刷新恢复、空 catalog、非法选择和双 Run 隔离。
  15. 执行 Ruff、mypy、前端 lint/typecheck/Vitest、Astro build 和 Playwright；最后同步维护 PRD.md、memory-bank/architecture.md、
     design-document.md、tech-stack.md、progress.md。

  ## FINAL PLAN

  1. 定义后端控制的 Provider/Model catalog，公开模型与内部 secret 配置完全分离。
  2. 扩展 CreateRunRequest 和 RunSnapshot，保存安全的 Provider/Model 选择。
  3. 引入 ProviderFactory，使每个 Run 在创建时绑定唯一 Provider/Model。
  4. 修改 RunManager/workflow，确保并发 Run 互不影响且所有节点复用本 Run 选择。
  5. 新增 GET /api/providers，创建 Run 时严格校验，不允许 silent fallback。
  6. 将选择写入 SQLite Snapshot，并兼容旧请求和旧 Snapshot。
  7. 更新 Telemetry、事件、日志和前端 Run 信息，仅展示安全元数据。
  8. 更新前端 Provider/Model 联动选择及 Loading/Empty/Error 状态。
  9. 完成 Backend、contract、Vitest、Playwright 和静态检查覆盖。
  10. 同步更新架构/设计/技术栈/进度文档后再开始正式实现。

─ Worked for 6m 10s