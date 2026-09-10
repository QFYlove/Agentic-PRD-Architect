我先阅读核心文档，然后深入代码，最后输出分析与方案。

我已完成文档与核心代码的阅读（`backend/config.py`、`main.py`、`run_manager.py`、`run_store.py`、`schemas.py`、`providers/*`、`workflow.py`、`telemetry.py`，以及 `src/lib/api.ts`、`contracts.ts`、`types.ts`、`ProductIdeaForm.tsx`、`TelemetryPanel.tsx`、`useAgentRun.ts`、契约测试）。以下是分析与方案，未修改任何文件。

---

## A. 当前架构理解

与本需求直接相关的现有实现：

1. **Provider 是进程级单例**：`backend/main.py:create_app()`（85–134 行）在应用启动时根据 `Settings` 决定唯一的 `LLMProvider` 实例——`ENABLE_MOCK_LLM=true` 时是 `MockLLMProvider`（E2E 模式下是 `ScenarioMockLLMProvider`），否则按 `llm_provider`（`deepseek` | `glm`）构造一个 `OpenAICompatibleLLMProvider`，读入 `deepseek_*` / `glm_*` 的 key、base URL、model。没有任何工厂/注册表抽象，就是一个 if/else。

2. **RunManager 持有该单例**：`backend/run_manager.py:48-53` 将 provider 注入 `RunManager`，整个 run 生命周期通过 `self.manager.provider`（workflow.py 中多处）调用 `stream_prd / generate_review / generate_revision_plan`。也就是说**所有 run 共用同一个模型**，且 `is_mock`、`cost_available`（run_manager.py:158-159）都是进程级的。

3. **配置**：`backend/config.py` 的 `Settings` 用 `SecretStr` 保存 key（43、46 行，`repr=False`），`Literal["deepseek","glm"]` 限制 provider（32 行），定价是全局单一 `model_input/output_price_per_million`。启动校验（104-131 行）只校验**被选中的那一个** provider 的 key 存在。

4. **创建 Run**：`POST /api/runs`（main.py:279-292）→ `RunManager.create_run`（run_manager.py:124-177）→ 构造 `RunSnapshot` 并写入 store。`CreateRunRequest`（schemas.py:101-123）只有 idea/audience/constraints/quality_threshold/max_iterations，**没有任何模型字段**。

5. **持久化**：`SQLiteRunStore`（run_store.py:169+）把整个 `RunSnapshot` 序列化为 JSON 存进 `runs(run_id, snapshot_json, updated_at)` 表；启动时 `_load_snapshots` 反序列化恢复。没有 schema migration 机制——字段演进靠 Pydantic 默认值（test_contracts.py:29-45 正是这样测旧快照兼容的）。

6. **Telemetry**：`PRDRunState` 里有 `is_mock`、`total_tokens`、`node_tokens`、`estimated_cost_usd`、`cost_available`（schemas.py:364-375）；成本用全局定价在 `telemetry.estimate_cost` 计算。**没有 provider/model 字段**。前端 `TelemetryPanel.tsx` 展示 tokens/cost/mock 标签。

7. **前端**：`src/lib/types.ts:66` 的 `CreateRunRequest`、`api.ts:createRun`、`ProductIdeaForm.tsx`（只有 idea/audience/constraints/threshold/iterations 五个字段）、`useAgentRun.ts:307` 组装请求。`GET /api/health` 返回 `mock_mode` + `provider` 名。

8. **契约测试**：`backend/tests/test_contracts.py` 用 `tests/` 下的 JSON fixture 校验 Pydantic 模型和 OpenAPI schema 的向后兼容（新字段必须带默认值）。

---

## B. 影响范围

| 文件 | 为什么改 |
|---|---|
| `backend/config.py` | 新增 per-provider 模型目录配置（允许的 provider/model 列表、每个模型的定价），扩展启动校验：所有“允许”的真实 provider 都必须有 key（否则不可列入目录） |
| `backend/providers/registry.py`（新） | Provider 注册表/工厂：维护 provider id → 实例（或实例工厂）的映射，供 run 级解析；输出安全元数据 |
| `backend/schemas.py` | 新增 `ModelSelection`（provider_id + model_id）、`ProviderInfo`/`ModelInfo`（安全元数据）、`ModelCatalogResponse`；`CreateRunRequest` 加可选 `model_selection`；`PRDRunState` 加持久化字段 |
| `backend/main.py` | `create_app` 改为构造 provider 注册表而非单例；新增 `GET /api/models`；health 逻辑调整 |
| `backend/run_manager.py` | `create_run` 解析并校验选择、写入 snapshot；`is_mock`/`cost_available` 改为按 run 计算；workflow 需要按 run 取 provider |
| `backend/workflow.py` | provider 访问从 `self.manager.provider` 改为按 run_id 从注册表取（`run_manager.py` 已有 `provider` 引用处） |
| `backend/run_store.py` | 基本不改（JSON blob 存储，Pydantic 默认值即 migration）；只需确认旧快照加载路径 |
| `backend/telemetry.py` | `estimate_cost` 接受 per-model 定价而非只用全局 `settings` |
| `src/lib/types.ts` / `contracts.ts` / `api.ts` | 新增 `ModelCatalog` 类型、`listModels()`、`CreateRunRequest.model_selection` |
| `src/components/ProductIdeaForm.tsx` | 新增 Provider/Model 联动选择器（loading/empty/error 态） |
| `src/components/TelemetryPanel.tsx`（或 Snapshot 头部） | 展示本 run 的 provider/model |
| `src/hooks/useAgentRun.ts` | 加载模型目录、把选择并入 create 请求 |
| `backend/tests/*`、`src/**/*.test.tsx`、`e2e/*`、`tests/` 契约 fixture | 见 G 节 |
| `.env.example`、`PRD.md`、`memory-bank/design-document.md`、`tech-stack.md`、`progress.md` | AGENTS.md 要求文档与 API/协议变更保持一致 |

不需要动：LangGraph 拓扑、质量门、Aggregator、事件/SSE 协议（不新增事件类型，选择随快照走）、状态机、EventStore。

---

## C. 数据模型与 API 设计

**安全元数据**（新增 Pydantic，全部 `StrictModel`）：

```python
class ModelInfo(StrictModel):
    model_id: str            # 如 "deepseek-v4-flash"
    display_name: str        # 如 "DeepSeek V4 Flash"
    # 可选安全能力信息，例如 supports_json_mode: bool（可后续扩展）

class ProviderInfo(StrictModel):
    provider_id: str         # "deepseek" | "glm" | "mock"
    display_name: str
    is_mock: bool
    models: list[ModelInfo]

class ModelCatalogResponse(StrictModel):
    providers: list[ProviderInfo]
    default: ModelSelection | None   # 由现有 llm_provider + *_model 推导，前端预选
```

明确不包含：api_key、base_url、timeout、价格（价格不属于“能力信息”，且会暗示内部配置；成本仍由后端计算后给出 `estimated_cost_usd`）。`ModelSelection = {provider_id: str, model_id: str}`。

**新 endpoint**：`GET /api/models` → `ModelCatalogResponse`。Mock 模式下返回单一 `mock` provider（`is_mock: true`），此时前端禁用选择器（或只显示 Mock）。

**创建 Run API**：`CreateRunRequest` 增加可选字段 `model_selection: ModelSelection | None`。
- 省略/null → 使用后端默认（保持现行为，旧客户端零改动）。
- 提供时 → 后端在注册表中精确查找；**provider 不存在、model 不存在、或该 provider 未配置 key（不可用）→ 422 `MODEL_NOT_AVAILABLE`**（新增 AppError 子类，沿用现有错误体格式 `{error:{code,message,request_id}}`），绝不静默回退到默认模型。
- Mock 模式下若请求了真实 provider：同样 `MODEL_NOT_AVAILABLE`（目录里没有它，天然成立）。

**RunSnapshot 持久化**：`PRDRunState` 新增：

```python
model_selection: ModelSelection | None = None
model_display: ModelDisplay | None = None   # 创建时的快照：provider/model display name + is_mock
```

关键点：**display 名称在创建时物化存进快照**，而不是读取时再从注册表反查——这样服务重启、配置变更甚至该模型下架后，旧 run 的 Telemetry 仍能正确显示“当时用的什么”。`is_mock` 语义从“进程是否 mock”改为“本 run 是否 mock”（对旧快照，Pydantic 默认值加载后仍由该字段承载，语义不变）。

**错误语义汇总**：
- `MODEL_NOT_AVAILABLE`（422）：选择的 provider/model 不在目录或无凭据。
- 现有 `ProviderUnavailableError` 等运行期错误不变。
- 目录 endpoint 本身不暴露任何失败细节（如“缺 DEEPSEEK_API_KEY”），只是不列出该 provider。

**向后兼容**：
- `POST /api/runs` 不带 `model_selection` → 默认模型，行为与现在完全一致。
- 旧 SQLite 快照 JSON 缺新字段 → Pydantic 默认 `None`，加载正常；在 `test_contracts.py` 按现有模式加旧 fixture 回归。
- `GET /api/runs` 的 `RunSummary` 可选加 `model_selection`（带默认 None），旧客户端忽略。

---

## D. Provider 层设计

**现状**：无工厂。`main.py` 一个 if/else 产出单例 provider，key/base_url/model 全部在构造时烧进实例；`OpenAICompatibleLLMProvider` 已经是“provider_name + model”参数化的，复用性好。

**改造**：新增 `backend/providers/registry.py`：

```python
class ProviderRegistry:
    def __init__(self, *, default_selection: ModelSelection, settings) -> None: ...
    def catalog(self) -> list[ProviderInfo]          # 只含安全元数据；无 key 的真实 provider 不出现
    def resolve(self, selection: ModelSelection | None) -> ResolvedProvider
        # None → default；未知/不可用 → raise ModelNotAvailableError（不 fallback）
    def mock_provider(self) -> LLMProvider
```

实现要点：
- 真实 provider 实例**懒构造并缓存**（每个 (provider, model) 一个 `OpenAICompatibleLLMProvider`，`AsyncOpenAI` 客户端随实例缓存，避免每 run 新建连接池）。key 始终留在实例内。
- 目录构建规则：`enable_mock_llm=true` → 目录含 `mock`（且仅 mock，与“从不静默回退”一致）；否则遍历 deepseek/glm，**有 key 的才列出**，每个 provider 的 models 来自配置（见下）。
- Mock：`resolve` 对 mock 选择返回共享的 `MockLLMProvider`；`ScenarioMockLLMProvider` 保持 E2E 专用。Mock 不接受 model 选择差异（或目录给 mock 一个固定 model id），保证确定性测试不受影响。
- 定价：配置从单一全局价改为 per-model（如 `DEEPSEEK_MODELS=deepseek-v4-flash:0.27:1.10,deepseek-reasoner:0.55:2.19`，格式 `model:in:out`；不填价格则该模型 `cost_available=false`）。`registry` 暴露 `pricing_for(selection)` 给 `estimate_cost`，替代 `settings.has_model_pricing`。
- RunManager 构造改为接收 `registry`，保留 `self.provider`（默认 provider）供日志兼容；`workflow.py` 中 `self.manager.provider` 改为 `self.manager.provider_for(run_id)`——从 snapshot 的 `model_selection` 解析。这一改动点集中在 workflow.py 约 5 处引用，不触碰节点逻辑。
- 泄漏防护：`catalog()` 返回的 Pydantic 模型字段白名单式定义（`extra="forbid"`），结构上不可能带出 key/base_url；`observability.py` 日志沿用现有脱敏实践，只在 `run_accepted` 里加 `provider_id`/`model_id`。

---

## E. Persistence

- **不需要 SQL migration**：`SQLiteRunStore` 存的是整份 snapshot JSON，新字段 `model_selection`/`model_display` 带默认值 `None`，老行反序列化即兼容，新行自动携带。表结构不变。
- **老 Run**：`_load_snapshots` → `RunSnapshot.model_validate_json`，缺字段得 None；Telemetry 对 None 显示“默认模型”或直接省略行。`test_contracts.py` 增加“旧 fixture 无 model 字段可加载”的用例（照抄 `test_best_version_defaults_to_absent_for_older_snapshots` 的模式）。
- **新 Run**：`create_run` 在构造 `RunSnapshot` 时写入 `model_selection` 和物化的 `model_display`，随现有 `run_store.create()` / `save_unlocked()` 全量持久化，刷新/重启后可读。
- InMemoryRunStore（`:memory:` 测试路径）零改动。

---

## F. Frontend

**创建 Run 界面（`ProductIdeaForm.tsx`）**：
- 表单加载时调用 `api.listModels()`（经 `useAgentRun` 或组件本地 state，推荐 hook 层提供 `modelCatalog` 状态避免多组件重复请求）。
- 两个下拉：Provider select 变更时把 Model select 重置为该 provider 第一个模型（联动）。默认预选 `catalog.default`。
- 状态：**Loading**（骨架/禁用下拉，允许先填 idea）；**Empty/仅 Mock**（隐藏选择器，显示“Mock 模式”标签，保持现状体验）；**Error**（请求目录失败：显示重试按钮，提交按钮禁用或回退为“使用默认模型”——推荐禁用提交并提示，避免用户在不知情下用错模型；目录为空则同错误态）。
- 提交时带 `model_selection`；后端 `MODEL_NOT_AVAILABLE`（422）映射到表单错误区（复用 `errorMessages.ts`），提示刷新目录。

**Telemetry / Run 信息**：`TelemetryPanel.tsx` 新增一行“模型：`{provider display} / {model display}`”（`snapshot.model_display`），Mock 标签沿用 `is_mock`。老快照无值时该行隐藏。`ConversationSidebar` 的 summary 如后端加了字段可顺带展示（可选）。

**契约**：`types.ts` 新增 `ModelCatalog`/`ProviderInfo`/`ModelInfo`/`ModelSelection`；`contracts.ts` 加对应 parser（沿用现有 TypeError 模式）；`api.ts` 加 `listModels()`。

---

## G. Testing

**Backend pytest（新增/修改）**
- `tests/test_config.py`：模型目录配置解析（列表格式、非法价格报错）、“无 key 的 provider 不进目录”校验。
- `tests/test_api.py`：
  - `GET /api/models` 返回结构、**响应中不含 api_key/base_url 字符串**（安全断言）；
  - `POST /api/runs` 带 `model_selection` 成功创建，snapshot 回读含选择；
  - 带未知 provider / 未知 model / mock 模式下选真实 provider → 422 `MODEL_NOT_AVAILABLE`，且 run 未创建、无事件残留；
  - 不带 `model_selection`（旧客户端）行为不变。
- `tests/test_run_manager.py`：`provider_for(run_id)` 按 snapshot 解析；不同 run 可同时用不同 provider；`cost_available`/成本按 per-model 定价。
- `tests/test_run_store.py`：旧 JSON 快照（无 model 字段）加载兼容；新快照持久化 round-trip。
- `tests/test_contracts.py` + `tests/fixtures`（`run_snapshot.json` 等）：新字段默认值兼容、`ModelCatalogResponse` 进 OpenAPI contract models。
- `tests/test_mock_provider.py` / mock 相关：Mock 模式目录与默认路径不回归（现有全部测试继续通过即覆盖）。
- 安全：`tests/test_observability_security.py` 加“目录与 snapshot 序列化中无 SecretStr 值泄漏”断言。

**Contract tests**：OpenAPI contract_models 列表（main.py:403-417）加入 `ModelCatalogResponse`、`ModelSelection`；fixture JSON 更新。

**Vitest**
- `src/lib/contracts.test.ts` / `api.test.ts`：`parseModelCatalog`、`listModels()`（含 malformed 响应抛错）。
- `components.test.tsx` / 新 `ModelSelector.test.tsx`：联动逻辑、loading/empty(mock)/error 态、提交 payload 含 `model_selection`。
- `useAgentRun.test.tsx`：createRun 携带选择；`MODEL_NOT_AVAILABLE` 错误呈现。
- `TelemetryPanel` 测试：显示模型行、旧 snapshot 无字段不渲染。

**Playwright E2E**（Mock 后端，端口 4331/8011）：
- happy-path：创建 run 时选择器显示“Mock”且流程照常完成（回归现有 spec 的隐式覆盖）；
- 新 spec 或扩展现有：`/api/models` 失败/为空时的错误态（可用 route mock）。

**Static/type checks**：`ruff format/check + mypy`（新 registry 模块类型完整）、`astro check`、ESLint、`npm run build`、`test:e2e`。

---

## H. 风险

1. **`workflow.py` 对 `manager.provider` 的引用改为 per-run**——最大回归面：漏改一处会导致某节点悄悄用默认模型（违反“不静默回退”）。需 grep 全量覆盖并加“run 的所有节点调用同一 provider”断言。
2. **`is_mock` 语义迁移**：从进程级变 run 级后，`cost_available`、Mock 确定性路径、前端 Mock 标签都依赖它；任何地方仍读 `settings.enable_mock_llm` 判断成本可能算错。建议统一改为读 snapshot。
3. **契约破坏**：`CreateRunRequest` 是 `extra="forbid"`，加字段对旧后端 + 新前端不兼容，反之安全；契约 fixture/OpenAPI 快照若不同步会挂 CI。新字段必须全部带默认值。
4. **配置复杂化**：per-provider 模型列表 + 定价格式是新配置面，校验不足会让启动失败信息难以排查（要保持现有“启动即校验、无静默回退”的风格）。
5. **成本计算回归**：现有全局定价字段仍需被旧路径/默认模型使用，两套定价并存期间 `estimate_cost` 分支容易算错（尤其 `cost_available=false` 判定）。
6. **并发**：多个 run 共享缓存的 `AsyncOpenAI` 客户端一般安全，但需确认 `max_retries=0`、timeout 语义不因共享改变（低风险）。
7. **Mock/E2E 确定性**：`ScenarioMockLLMProvider` 的构造路径（e2e_test_mode 分支）不能因注册表重构被绕过。

---

## I. 实施计划（小步可验证）

1. **配置与元数据**：`config.py` 加模型目录配置 + 校验；`schemas.py` 加 `ModelSelection`/`ModelInfo`/`ProviderInfo`/`ModelCatalogResponse`；`PRDRunState` 加默认值字段。跑 `test_config` / `test_schemas` / 契约（先加旧 fixture 兼容用例，红→绿）。
2. **Registry**：新建 `providers/registry.py`（懒构造、目录、resolve、pricing）；单测覆盖“不存在的选择抛错”。
3. **接线后端**：`main.py` 用 registry（保留单 provider 兼容注入路径供测试）、`GET /api/models`、`run_manager.create_run` 校验+写入 snapshot、`workflow` 改 `provider_for(run_id)`、`telemetry.estimate_cost` 接 per-model 定价。`test_api`/`test_run_manager` 新用例 + 全量 pytest。
4. **前端类型与 API 层**：`types.ts`/`contracts.ts`/`api.ts` + Vitest。
5. **UI**：`ProductIdeaForm` 选择器（三态）+ `useAgentRun` + `TelemetryPanel` 模型行 + Vitest。
6. **E2E 与静态门**：Playwright 回归 + `ruff/mypy/lint/typecheck/build`。
7. **文档**：`.env.example`、`PRD.md` §5/§8、`memory-bank/design-document.md`、`tech-stack.md`、`progress.md` 同步。

每步均可独立提交并通过现有测试门。

---

## FINAL PLAN

1. `backend/config.py`：新增允许的 per-provider 模型目录配置（模型列表 + per-model 定价，格式 `model:in_price:out_price`，价格可选）；扩展校验——非 mock 模式下列入目录的真实 provider 必须有 key，保留现有全局定价作为默认模型回退配置。
2. `backend/schemas.py`：新增 `ModelSelection`、`ModelInfo`、`ProviderInfo`、`ModelCatalogResponse`（全部安全元数据，`extra="forbid"`）；`CreateRunRequest` 加可选 `model_selection`；`PRDRunState` 加 `model_selection: ModelSelection | None = None` 和 `model_display`（创建时物化的 display 快照 + `is_mock`）。
3. 新建 `backend/providers/registry.py`：`ProviderRegistry` 提供 `catalog()`（无 key 的 provider 不出现）、`resolve(selection)`（None→默认；未知/不可用→`ModelNotAvailableError`，绝不 fallback）、`pricing_for(selection)`；真实 provider 按 (provider, model) 懒构造缓存，key 只存实例内；mock 模式目录仅含 `mock`。
4. `backend/errors.py` + `main.py`：新增 422 `MODEL_NOT_AVAILABLE`；`create_app` 改用 registry（保留 `provider=` 注入用于测试）；新增 `GET /api/models`；OpenAPI contract models 纳入新模型。
5. `backend/run_manager.py` + `workflow.py`：`create_run` 解析并校验选择、写入 snapshot（`is_mock`/`cost_available` 变 per-run）；新增 `provider_for(run_id)` 替换 workflow 中所有 `manager.provider` 引用；`telemetry.estimate_cost` 改用 per-model 定价。
6. 持久化零 migration：靠 Pydantic 默认值加载旧 SQLite 快照；`backend/tests/fixtures` 契约 fixture 增加“无 model 字段的旧快照可加载”用例。
7. 前端：`types.ts`/`contracts.ts`/`api.ts` 加 `ModelCatalog` 类型、parser、`listModels()`；`ProductIdeaForm` 加 Provider→Model 联动下拉（Loading / 仅-Mock 隐藏 / Error 禁用提交 + 重试），默认预选目录 default；`TelemetryPanel` 展示 `model_display`（无值则隐藏）。
8. 测试：按 G 节补齐 pytest（含目录响应无密钥断言、不可用选择 422 且无残留 run）、契约、Vitest（联动/三态/payload）、Playwright 回归；全量跑 `pytest`、`ruff+mypy`、`lint+typecheck+test:run`、`test:e2e`、`build`。
9. 文档同步：`.env.example`、`PRD.md`、`memory-bank/{design-document,tech-stack,progress}.md`，Conventional Commits 分步提交。

关键设计决策回顾：选择在创建时物化进 snapshot（含 display 名）以抵御配置漂移；目录为白名单式安全元数据，结构上无法携带 key/base_url；`resolve` 失败即 422，无任何静默回退；Mock 模式目录单一 mock 条目，确定性路径不变。