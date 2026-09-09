调研完成，以下是设计方案。

---

A. 当前架构理解（只列与本需求相关的部分）

A.1 Provider 只在应用工厂里构造一次

backend/main.py::create_app 是唯一的 Provider 构造点：

def create_app(*, settings=None, provider: LLMProvider | None = None) -> FastAPI:
    if provider is None:
        if app_settings.enable_mock_llm:
            provider = ScenarioMockLLMProvider(...) if app_settings.e2e_test_mode else MockLLMProvider(...)
        else:
            if app_settings.llm_provider == "deepseek":
                api_key, base_url, model = (deepseek_api_key, deepseek_base_url, deepseek_model)
            else:
                api_key, base_url, model = (glm_api_key, glm_base_url, glm_model)
            provider = OpenAICompatibleLLMProvider(provider_name=..., api_key=api_key.get_secret_value(), ...)
    manager = RunManager(settings=app_settings, provider=provider, ...)

关键事实：进程内只存在一个 LLMProvider 实例，app_settings.llm_provider 是进程级的 Literal["deepseek","glm"]。这正是本需求要改的地方，也是 memory-bank/architecture.md §7「Provider 特有差异只在应用工厂注入」这条约束的落点——改造后这条约束需要重述为「只在 Provider Catalog 注入」。

A.2 Provider 抽象已经足够干净

backend/providers/base.py 定义 LLMProvider(ABC)：is_mock: bool = False + 四个抽象方法（stream_prd / generate_review / generate_revision_plan / repair_structured），返回的 ProviderTextEvent / ProviderStructuredResult 都带 model: str。

backend/providers/compatible.py 的 OpenAICompatibleLLMProvider.__init__(*, provider_name, api_key, base_url, model, request_timeout_seconds, max_output_tokens, extra_body, client)——密钥、base URL、extra_body 全部是构造参数，没有任何 wire model 携带它们。这意味着「一个 (provider, model) 对应一个实例」在现有类上零改动即可成立，无需修改 compatible.py。

A.3 消费侧：全部通过 self.manager.provider

backend/run_manager.py 持有 self.provider，backend/workflow.py 共约 9 处引用：

┌─────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│        位置         │                                                  用途                                                   │
├─────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ workflow.py:129     │ run_started payload 的 "mock": self.manager.provider.is_mock                                            │
├─────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ workflow.py:306,    │ log_event(..., provider=type(self.manager.provider).__name__)                                           │
│ 591                 │                                                                                                         │
├─────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ workflow.py:367     │ _stream_generation → stream_prd                                                                         │
├─────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ workflow.py:513     │ _reviewer_node 内 call() → generate_review                                                              │
├─────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ workflow.py:600     │ _validated_structured → repair_structured                                                               │
├─────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ workflow.py:779     │ optimizer → generate_revision_plan                                                                      │
├─────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ run_manager.py      │ create_run 里 is_mock=、cost_available=；record_usage 里 estimate_cost(...,                             │
│                     │ is_mock=)；log_event(provider=...)                                                                      │
└─────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────┘

已逐一确认：这些调用点全部有 run_id（或 state.run_id）在作用域内。 所以「按 Run 取 Provider」是一次机械替换，不是重构——满足「不重构无关模块」。

A.4 快照是整体 JSON 持久化

backend/run_store.py 的表结构只有三列：

runs(run_id TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL, updated_at TEXT NOT NULL)

_persist 写 snapshot.model_dump_json()，_load_snapshots 用 RunSnapshot.model_validate_json() 读回，非终态 Run 恢复为 FAILED + RUN_INTERRUPTED。结论：给 RunSnapshot 加可选字段不需要任何 DDL 迁移。

A.5 现有的向后兼容与契约范式

- CreateRunRequest 继承 StrictModel（extra="forbid"）→ 新字段必须是 可选带默认，否则旧客户端不受影响、但新字段一旦必填就会打断旧 payload。
- contracts/v1/run_snapshot.json 里没有 output_language、best_version、node_timings 键，却能通过 test_contracts.py 校验——这就是本仓库认可的契约演进方式（optional + default）。
- backend/schemas.py::_coerce_feedback 与前端 src/lib/contracts.ts::normalizeFeedbackItem（未知 severity → should_fix）是「宽松读取旧数据」的既有先例。

A.6 成本与健康检查

- backend/telemetry.py::estimate_cost(usage, settings, *, is_mock)：mock → 0.0；not settings.has_model_pricing → None；否则用全局 model_input_price_per_million / model_output_price_per_million。
- HealthResponse(status, mock_mode, provider)，main.py 里 provider = "mock" if provider.is_mock else app_settings.llm_provider；backend/tests/test_api.py 用精确相等断言这个 JSON。

---

B. 影响范围

后端

文件: backend/providers/catalog.py
改动: 新增
为什么必须改: 目录的唯一定义处：内部含密描述符 + 对外安全元数据 + 实例缓存 + resolve() 显式失败
────────────────────────────────────────
文件: backend/config.py
改动: 新增 llm_allowed_models（目录声明）与可选 per-model 价格；validate_provider_configuration 扩展为校验整个目录
为什么必须改: 需求 1「选项由后端配置定义并控制」；启动即校验，避免运行期才发现某条目缺 key
────────────────────────────────────────
文件: backend/schemas.py
改动: CreateRunRequest +2 可选字段；PRDRunState / RunSnapshot +4 可选字段；新增 ProviderInfo / ModelInfo / ProviderCatalogResponse
为什么必须改: 需求 4/5/6 与契约唯一真相源
────────────────────────────────────────
文件: backend/main.py
改动: create_app 改为构建 Catalog 并注入 RunManager；新增 GET /api/providers；contract_models 追加新模型
为什么必须改: Provider 不再是单例；前端需要拉取可选项
────────────────────────────────────────
文件: backend/run_manager.py
改动: create_run 里解析并落库选择；新增 provider_for(run_id)；is_mock / cost_available / record_usage 改为按 Run 判定
为什么必须改: 需求 5/6/9
────────────────────────────────────────
文件: backend/workflow.py
改动: 9 处 self.manager.provider → self.manager.provider_for(run_id)
为什么必须改: 让每个 Run 真的走自己的模型
────────────────────────────────────────
文件: backend/errors.py
改动: 新增 ProviderNotAllowedError(400) / ModelNotAllowedError(400)
为什么必须改: 需求 9 显式失败，且 user_message 固定、不泄露内部信息
────────────────────────────────────────
文件: backend/telemetry.py
改动: estimate_cost 接收「该 Run 的价格」而不是直接读全局 Settings
为什么必须改: 多模型共存后全局单价必然算错

契约

┌──────────────────────────────────────┬────────────────────────────────────────────────────────────────────┐
│                 文件                 │                                改动                                │
├──────────────────────────────────────┼────────────────────────────────────────────────────────────────────┤
│ contracts/v1/provider_catalog.json   │ 新增 fixture                                                       │
├──────────────────────────────────────┼────────────────────────────────────────────────────────────────────┤
│ contracts/v1/create_run_request.json │ 追加 provider_id / model_id 示例（保留一份不含该字段的旧形态断言） │
├──────────────────────────────────────┼────────────────────────────────────────────────────────────────────┤
│ contracts/v1/run_snapshot.json       │ 追加持久化选择字段                                                 │
└──────────────────────────────────────┴────────────────────────────────────────────────────────────────────┘

前端

┌────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────┐
│                文件                │                                         改动                                          │
├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ src/lib/types.ts                   │ CreateRunRequest、RunSnapshot 加字段；新增 ProviderInfo / ModelInfo / ProviderCatalog │
├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ src/lib/contracts.ts               │ 新增 parseProviderCatalog；parseCreateRunRequest 保持对缺字段宽容                     │
├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ src/lib/api.ts                     │ AgentApi 接口 + HttpAgentApi 新增 listProviders()                                     │
├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ src/lib/errorMessages.ts           │ 新增 PROVIDER_NOT_ALLOWED / MODEL_NOT_ALLOWED 中文文案                                │
├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ src/components/ProductIdeaForm.tsx │ Provider / Model 联动选择器 + loading/empty/error 状态                                │
├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ src/components/TelemetryPanel.tsx  │ 展示该 Run 实际使用的 Provider / Model 显示名                                         │
├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ src/hooks/useAgentRun.ts           │ 透传选择字段（createRun 已接受完整 request，改动很小）                                │
├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ src/test/fixtures.ts               │ makeSnapshot 携带新字段；新增 makeProviderCatalog                                     │
├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ e2e/helpers.ts                     │ startRun 支持可选 provider/model                                                      │
└────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────┘

文档（AGENTS.md 强制）

README.md、docs/README_ZH.md、.env.example、PRD.md、memory-bank/design-document.md（§7.7 / §9.1 / §15）、memory-bank/architecture.md（§7 注入点 + §8 文件职责表新增 catalog.py）、memory-bank/progress.md（每步记录）。

▎ 注：.env.example 在本会话中不可读（权限限制），其内容我是从 README.md 的 Provider 配置段与 design-document §15 逐字还原的。实施时需按实际文件内容对齐。

---

C. 数据模型与 API 设计

C.1 后端配置里的目录声明

在 Settings 中新增一个显式白名单（保持 pydantic-settings 可从环境读取，JSON 字符串形式）：

class AllowedModel(StrictModel):
    provider_id: Literal["deepseek", "glm"]
    model_id: str                     # 真实调用用的模型名
    display_name: str                 # 前端展示名
    max_output_tokens: int | None = None
    input_price_per_million: Decimal | None = None
    output_price_per_million: Decimal | None = None

llm_allowed_models: list[AllowedModel] = []   # 空 → 回退为「当前 llm_provider 的单条目」

llm_allowed_models 为空时，目录由现有 llm_provider + {provider}_model 合成一条——这样已有 .env 不改也能跑，且行为与今天完全一致。

validate_provider_configuration 扩展：非 Mock 模式下遍历目录，逐条要求对应 {provider}_api_key 存在、model_id 非空、provider_id 去重后至少一条。启动即失败，符合 README 的「启动时校验，绝不静默回退 Mock」。

C.2 对外安全元数据（唯一允许上线的形状）

class ModelInfo(StrictModel):
    model_id: str
    display_name: str
    max_output_tokens: int | None = None
    cost_available: bool            # 该模型有价格吗（不含价格数值）

class ProviderInfo(StrictModel):
    provider_id: str
    display_name: str               # "DeepSeek" / "智谱 GLM" / "Mock"
    is_mock: bool
    models: list[ModelInfo]

class ProviderCatalogResponse(StrictModel):
    providers: list[ProviderInfo]
    default_provider_id: str
    default_model_id: str

这里没有 api_key、没有 base_url、没有 extra_body、没有价格数值。 含密信息只存在于 catalog.py 内部的 _ProviderCredentials（非 Pydantic wire model，或 model_config = {"extra": "forbid"} 且从不出现在任何 response_model 里）。是否暴露价格数值是个判断题：我建议不暴露，只给 cost_available 布尔量，理由是采购单价属于内部商业信息，而前端唯一需要的是「能不能显示费用」。

C.3 新增端点

GET /api/providers  →  200 ProviderCatalogResponse

只读、无参数、无副作用。必须加入 main.py 的 contract_models 元组（OpenAPI 显式注册规则）。

不需要其他新端点：GET /api/runs/{id} 返回的 RunSnapshot 已经承载「这个 Run 用了什么」。

C.4 Create Run 变化

class CreateRunRequest(StrictModel):
    ...
    provider_id: str | None = None
    model_id: str | None = None

语义：

- 两者都为 None → 使用目录默认（= 今天的行为）。
- 两者都给 → 严格校验。
- 只给一个 → 400 REQUEST_VALIDATION_FAILED（model_validator 校验成对出现）。理由：只给 provider_id 就得替它挑模型，那本质上是一次隐式替换，与需求 9 的精神冲突；宁可让调用方说清楚。

因为是 optional-with-default，extra="forbid" 不会伤到旧客户端。

C.5 RunSnapshot 持久化的选择

provider_id: str = "unknown"          # 旧数据默认
model_id: str = "unknown"
provider_display_name: str = "未知 Provider"
model_display_name: str = "未知模型"

为什么连显示名也存： 目录是配置驱动的，运维随时可以把某个模型从白名单里删掉。如果只存 id，那么一个月前跑完的 Run 在页面上就只剩一串裸 id，甚至查不到名字。存下当时的显示名让历史 Run 自洽——这也是需求 5「服务重启后仍然可见」的完整含义。

用 "unknown" 而不是 None：前端渲染路径不需要处理 null 分支，且旧 Run 显示「未知模型」比显示空白更诚实。

C.6 错误语义（需求 9 的核心）

┌──────────────────────────────────────┬──────────┬───────────────────────────┬─────────────────────────────────┐
│                 场景                 │   HTTP   │           code            │             处理点              │
├──────────────────────────────────────┼──────────┼───────────────────────────┼─────────────────────────────────┤
│ provider_id 不在目录                 │ 400      │ PROVIDER_NOT_ALLOWED      │ create_run 中 catalog.resolve() │
├──────────────────────────────────────┼──────────┼───────────────────────────┼─────────────────────────────────┤
│ provider_id 存在但 model_id 不在其下 │ 400      │ MODEL_NOT_ALLOWED         │ 同上                            │
├──────────────────────────────────────┼──────────┼───────────────────────────┼─────────────────────────────────┤
│ 只提供了其中一个字段                 │ 400      │ REQUEST_VALIDATION_FAILED │ Pydantic validator              │
├──────────────────────────────────────┼──────────┼───────────────────────────┼─────────────────────────────────┤
│ 该条目缺密钥（理论上启动已拦）       │ 503      │ PROVIDER_UNAVAILABLE      │ catalog.resolve()               │
├──────────────────────────────────────┼──────────┼───────────────────────────┼─────────────────────────────────┤
│ 运行期模型被上游拒绝                 │ 现状不变 │ PROVIDER_MODEL_INVALID 等 │ compatible.py 已有映射          │
└──────────────────────────────────────┴──────────┴───────────────────────────┴─────────────────────────────────┘

校验必须发生在 create_run 同步返回 202 之前，不能等到 workflow 跑起来才失败——否则用户会看到一个 QUEUED 然后 FAILED 的 Run，而不是一次干净的表单报错。

user_message 固定为「所选 Provider / 模型不在允许列表中，请重新选择。」，不回显任何内部条目细节。

C.7 向后兼容清单

1. 旧 create payload（无新字段）→ 走默认，行为不变。
2. 旧 SQLite 行（无新字段）→ model_validate_json 用默认值填充，"unknown" / 「未知模型」。
3. 旧前端 → 不调 /api/providers、不发新字段，正常工作。
4. 空 llm_allowed_models → 目录由现有单 Provider 配置合成，.env 无需改动。
5. HealthResponse 不改字段（见 H.1）。

---

D. Provider 层设计

D.1 backend/providers/catalog.py（新增）

@dataclass(frozen=True)
class _ModelEntry:                     # 后端内部，含密，绝不进 wire
    provider_id: str
    model_id: str
    display_name: str
    api_key: SecretStr | None
    base_url: str
    max_output_tokens: int | None
    extra_body: dict[str, object]
    input_price_per_million: Decimal | None
    output_price_per_million: Decimal | None

class ProviderCatalog:
    def __init__(self, settings, *, mock_provider: LLMProvider | None = None): ...

    def public_catalog(self) -> ProviderCatalogResponse: ...      # 只投影安全字段
    def default_selection(self) -> tuple[str, str]: ...
    def resolve(self, provider_id: str | None, model_id: str | None) -> ResolvedProvider: ...
    # ResolvedProvider = (provider: LLMProvider, provider_id, model_id,
    #                     provider_display_name, model_display_name,
    #                     input_price, output_price)

- resolve() 内部 dict[(provider_id, model_id)] -> LLMProvider，懒构造 + 缓存。缓存是必要的：OpenAICompatibleLLMProvider 持有 HTTP client，一个 Run 里有 6 次调用，每次新建实例会浪费连接池。
- resolve() 找不到条目就 raise ProviderNotAllowedError / ModelNotAllowedError。没有任何 or default 分支——这是需求 9 在代码上的唯一保障点，也是 review 时应该重点看的一行。
- public_catalog() 是唯一从 _ModelEntry 到 ProviderInfo 的转换函数。密钥不泄露的证明因此收敛到一个函数上，而不是散落在路由里。

D.2 create_app 的改造

def create_app(*, settings=None, provider: LLMProvider | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    if provider is not None:                      # 测试注入路径，保持不变
        catalog = ProviderCatalog.single(provider)
    elif app_settings.enable_mock_llm:
        mock = ScenarioMockLLMProvider(...) if app_settings.e2e_test_mode else MockLLMProvider(...)
        catalog = ProviderCatalog.single(mock)
    else:
        catalog = ProviderCatalog(app_settings)
    manager = RunManager(settings=app_settings, catalog=catalog, ...)

ProviderCatalog.single(provider) 保留现有的「注入一个 provider」测试入口，目录里只有它一条，默认就是它。这让 backend/tests/helpers.py::make_manager(provider=...) 及其覆盖的绝大多数现有 pytest 一行不改。

D.3 RunManager 的按 Run 解析

class RunManager:
    def __init__(self, *, settings, catalog: ProviderCatalog, run_store, event_store): ...

    async def create_run(self, request) -> CreateRunResponse:
        resolved = self.catalog.resolve(request.provider_id, request.model_id)   # 可能抛 400/503
        state = PRDRunState(..., provider_id=resolved.provider_id,
                            model_id=resolved.model_id,
                            provider_display_name=resolved.provider_display_name,
                            model_display_name=resolved.model_display_name,
                            is_mock=resolved.provider.is_mock,
                            cost_available=resolved.provider.is_mock or resolved.has_pricing)
        self._providers[run_id] = resolved

    def provider_for(self, run_id: str) -> LLMProvider:
        return self._resolved_for(run_id).provider

_resolved_for(run_id) 的查找顺序：内存 map → 若缺失（进程重启后恢复的 Run）则用快照里的 provider_id / model_id 重新 resolve()。注意重启恢复路径上非终态 Run 本来就会被标成 FAILED，所以这条回退主要服务于「模型已被移出白名单」的诊断清晰度，而不是继续执行。

workflow.py 的 9 处替换为 self.manager.provider_for(run_id)；日志字段建议从 type(provider).__name__ 升级为同时带 provider_id / model_id——这属于 observability 的自然延伸，且 log_event 是允许列表机制，加两个非敏感字段是安全的。

D.4 密钥不上线的三道防线

1. 类型层：含密的 _ModelEntry 是 dataclass，不是 Pydantic wire model，任何 response_model 都无法接受它。
2. 投影层：public_catalog() 是唯一出口，逐字段显式构造 ModelInfo，不用 model_dump() 整体转换——避免将来加字段时被自动带出去。
3. 测试层：一条专门的 pytest 断言 GET /api/providers 的响应 JSON 文本里不出现任何配置的 key、base URL 子串（见 G.1）。

D.5 Mock 的处理

ENABLE_MOCK_LLM=true → 目录只有一条 mock 条目（provider_id="mock", model_id="mock-prd-v1", is_mock=true, cost_available=true）。

- 确定性完全不变：MockLLMProvider 的 SCORES 表与反馈表不受影响。
- E2E_TEST_MODE 下换成 ScenarioMockLLMProvider，ScenarioController 挂载方式不变，E2E_SCENARIOS 四个场景不变。
- 18 个现有 E2E 因此在「不选任何 provider」时行为与今天一致。

Mock 模式下前端选择器会只显示一个选项——这是正确的，比隐藏控件更能说明系统状态。

---

E. Persistence

不需要 SQLite 迁移。 依据是 run_store.py 的表结构只有 snapshot_json TEXT，没有任何按字段的列。

- 写新 Run：RunSnapshot 多四个字段，model_dump_json() 自动带上，_persist 无改动。
- 读旧 Run：RunSnapshot.model_validate_json() 对缺失的 optional-with-default 字段填默认值 → provider_id="unknown"、model_display_name="未知模型"。这与 current_prd_attempt / best_version / output_language 的既有先例完全一致，test_contracts.py 里已有 del payload[...] 然后断言默认值的写法可以直接照抄。
- RunSummary：我建议不加 provider 字段。列表页每行已经有 idea / status / 分数，加模型名会让行变挤，而用户想知道用了什么模型时会点进去。这是可争议的取舍，但少改一个契约就少一处兼容风险。
- 不改 updated_at 语义、不改 WAL 设置、不改非终态→FAILED 的恢复逻辑。

唯一需要注意的：如果本地已有旧数据库文件，新代码读它时会得到「未知模型」的历史 Run——这是预期行为，应该在 progress.md 里写明，避免以后有人当成 bug。

---

F. Frontend

F.1 数据获取

AgentApi 新增 listProviders(): Promise<ProviderCatalog>，HttpAgentApi 走已有的 request<T> 漏斗（因此自动获得 ApiClientError + NETWORK_ERROR 语义）。

在 AgentDashboard 挂载时拉一次（Provider 目录是配置驱动的静态数据，不需要轮询），结果作为 props 传给 ProductIdeaForm。放在 Dashboard 而不是 Form 内部，是因为将来 Telemetry 也可能想查目录，且 Form 保持「受控展示 + 本地 useState」的现有风格。

F.2 ProductIdeaForm 的选择器

放在现有 <details>「质量设置」块之上、主输入框之下——模型选择比阈值更影响结果，不该藏在折叠区里。

两个 <select> 联动：

- Provider 变更 → Model 重置为该 Provider 的第一个模型（这是 UI 层的默认值填充，不是后端的 silent fallback，两者不冲突）。
- 初始值 = default_provider_id / default_model_id。
- 提交时始终成对发送 provider_id + model_id（符合 C.4 的成对要求）。

四态处理：

┌────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────┐
│          状态          │                                            表现                                             │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
│ loading                │ 两个 select 禁用，占位「正在加载可用模型…」，提交按钮禁用                                   │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
│ 成功且只有一条         │ 正常显示（Mock 模式），不隐藏                                                               │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
│ empty（providers: []） │ 显示「后端未配置可用模型」，提交按钮禁用                                                    │
├────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
│ error                  │ 显示 localizedErrorMessage(code) + 「重试」按钮；不允许绕过直接提交，因为那会退化成隐式默认 │
└────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────┘

新增文案进 src/lib/errorMessages.ts：PROVIDER_NOT_ALLOWED / MODEL_NOT_ALLOWED → 「所选模型不在后端允许列表中，请重新选择。」

F.3 Telemetry / Run 信息展示

TelemetryPanel 顶部新增一行，与已有的 data-testid="telemetry-mock" 同区：

模型  DeepSeek · deepseek-v4-flash        data-testid="telemetry-provider"

数据来自 snapshot.provider_display_name / model_display_name（不是重新查目录），所以刷新和重启后都稳定。旧 Run 显示「未知 Provider · 未知模型」。

Run header（AgentDashboard）不加——那里已经有 status / run_id / 目标分数，再加会过载。

---

G. Testing

G.1 后端 pytest

新增 backend/tests/test_provider_catalog.py：
1. 目录从 llm_allowed_models 正确构建；多 Provider 多 Model 都在。
2. llm_allowed_models 为空 → 合成单条目，等于旧 llm_provider 行为。
3. resolve() 命中同一 (provider, model) 两次 → 返回同一实例（缓存生效）。
4. resolve() 未知 provider → ProviderNotAllowedError；已知 provider + 未知 model → ModelNotAllowedError。
5. resolve() 永不回退：传一个不存在的 model，断言抛异常而不是返回 default 实例。
6. public_catalog() 的 model_dump_json() 中不含任何 api_key / base_url 子串（用可识别的哨兵值如 sk-SENTINEL-KEY、https://internal.sentinel.invalid 配置后断言 not in）。
7. enable_mock_llm=true → 目录只有 mock 条目，is_mock 为真。
8. 非 Mock 且某条目缺 key → Settings 构造期即 ValueError（启动校验）。

backend/tests/test_api.py 新增：
9. GET /api/providers 200，形状符合 ProviderCatalogResponse，Mock 模式下只有一条。
10. POST /api/runs 带合法 provider_id/model_id → 202，随后 GET /api/runs/{id} 快照里字段正确。
11. 带非法 provider_id → 400 PROVIDER_NOT_ALLOWED，且没有 Run 被创建（GET /api/runs 数量不变）。
12. 只给 model_id → 400 REQUEST_VALIDATION_FAILED。
13. 不带任何新字段（旧 payload）→ 202，快照里是默认选择。
14. GET /api/health 断言保持原样通过（确认没动 HealthResponse）。

backend/tests/test_run_manager.py / test_workflow.py 新增：
15. provider_for(run_id) 返回该 Run 解析出的实例；两个用不同模型创建的 Run 各自拿到不同实例。
16. 完整 Mock 两轮 Loop 在指定 provider/model 下跑通，终态与分数与现有断言一致（确定性未被破坏）。
17. cost_available 按 per-model 价格判定：有 per-model 价 → true；无 per-model 且无全局价 → false 且 estimated_cost_usd is None（守住「缺价必须为 null」这条不可变决策）。

backend/tests/test_run_store.py 新增：
18. 写入含新字段的快照 → 重新加载后字段一致。
19. 手工插入一条不含新字段的 snapshot_json → 加载成功，得到 "unknown" 默认值。

G.2 Contract 测试（双端）

20. 新增 contracts/v1/provider_catalog.json，由 backend/tests/test_contracts.py（Pydantic）与 src/test/contracts.test.ts（parseProviderCatalog）双向校验。
21. create_run_request.json 更新后仍通过；另加一个删除 provider_id/model_id 后断言默认值的用例（照抄 current_prd_attempt 的写法）。
22. run_snapshot.json 更新后仍通过；同样加删除字段的默认值断言。
23. 现有 assert {event.event for event in events} == set(RunEventType) 必须继续通过——本设计不新增事件类型，这是刻意的（见 H.3）。

G.3 Vitest

24. parseProviderCatalog 接受合法目录、拒绝缺 providers / default_provider_id 的输入。
25. HttpAgentApi.listProviders() 用 fake fetch 打通；失败时抛 ApiClientError 且 code 正确。
26. ProductIdeaForm：loading / empty / error / 正常四态渲染；Provider 切换后 Model 列表随之变化且选中值被重置。
27. ProductIdeaForm 提交 payload 包含成对的 provider_id + model_id。
28. TelemetryPanel 渲染 provider/model 显示名；旧快照（makeSnapshot() 默认）渲染「未知」而不崩。
29. runReducer 现有 184 个测试全绿——本设计不改 reducer 逻辑，这是回归哨兵。

G.4 Playwright E2E

30. 新增一条：打开表单 → 断言 Provider/Model 选择器存在且有默认值 → 选择（Mock 下唯一选项）→ 启动 → 完成后在「运行记录」tab 断言 data-testid="telemetry-provider" 显示 Mock 模型名。
31. 新增一条：刷新持久化——Run 完成后 reload 页面，重新进入该 Run，Provider/Model 显示不变（验证需求 5）。
32. 现有 18 条 E2E 全部保持通过；e2e/helpers.ts::startRun 的新参数为可选，不改调用方。

G.5 静态检查

33. ruff format --check + ruff check、mypy --strict（新增的 catalog.py 必须完全类型化，resolve() 返回类型明确）。
34. astro check 0 error / 0 warning / 0 hint、eslint、prettier --check、Astro SSR build。

---

H. 风险（最容易打坏现有系统的地方）

H.1 HealthResponse 的精确相等断言。 backend/tests/test_api.py 里 assert health.json() == {"status": "ok", "mock_mode": True, "provider": "mock"}。一旦顺手给 health 加个 providers 字段，这条测试立刻红，而且这是双端契约。结论：本设计明确不动 HealthResponse，目录信息只从 /api/providers 出。这是最容易被「顺手优化」破坏的一处。

H.2 成本计算静默算错。 这是最隐蔽的风险：estimate_cost 今天读全局单价，如果只做 provider 选择而不动 telemetry，那么用 GLM 跑的 Run 会拿 DeepSeek 的单价算出一个看起来正常但是错的数字。错的费用比没有费用更糟，且 architecture.md §2 明确要求「缺少价格时必须为 null，绝不显示 0」。必须把价格随 ResolvedProvider 传下去。

H.3 事件类型集合被锁定。 test_contracts_cover_every_terminal_status_and_event_type 断言 17 个事件类型的完整集合。加一个 provider_selected 事件会同时要求改 RunEventType、contracts/v1/run_events.json、前端 EVENT_TYPES、runReducer 和它的 184 个测试。没有必要：选择在 Run 创建时就确定，快照字段足够表达。抵制加事件的冲动。

H.4 extra="forbid" 的双向性。 CreateRunRequest 拒绝未知字段，所以如果前端先上线、后端还没加字段，所有创建请求会 422。实施顺序必须后端先行（见 I）。

H.5 Provider 实例泄漏。 RunManager._providers[run_id] 如果只增不删，长时间运行会累积。现有 RunManager 已有 Run 容量上限（RUN_CAPACITY_REACHED），可以复用同一清理点；至少要在 Run 进入终态时移除映射。

H.6 Mock 确定性。 MockLLMProvider 的 SCORES（Podcast v1=71.0 / v2=88.0）被 pytest 和 E2E 双重依赖。目录改造若不小心让 Mock 走了不同分支（比如误把 mock 当成需要价格的条目），会打断一批断言。ProviderCatalog.single() 这条专用路径就是为了避免这个。

H.7 单 Worker 前提未变。 ProviderCatalog 的实例缓存是进程内状态，与现有「单 Uvicorn worker + 进程内协调」的架构约束一致。不要因此顺手引入跨进程共享——那会打破 architecture.md 的既有决策。

H.8 文档漂移。 AGENTS.md 要求 API / 依赖 / 工作流语义变化时更新设计与技术栈文档。本需求同时改 API（新端点 + 请求字段）和注入点（§7），漏一处就违反仓库规则。

---

I. 实施计划（小步、每步可独立验证）

Step 0 · 契约先行（不改行为）
schemas.py 加 ProviderInfo / ModelInfo / ProviderCatalogResponse；CreateRunRequest 与 RunSnapshot 加 optional 字段；新增/更新三个 contracts/v1 fixture；src/lib/types.ts + contracts.ts 跟上。
✅ 验证：pytest 契约测试 + Vitest 契约测试全绿，且旧 payload 删字段用例通过；现有 276 pytest 不变。

Step 1 · catalog.py 纯单元件
实现 ProviderCatalog（含 single()）、Settings.llm_allowed_models、启动校验、errors.py 两个新错误。尚未接入任何路由。
✅ 验证：G.1 的 1–8，特别是「不回退」和「哨兵密钥不出现在 public_catalog」两条。

Step 2 · GET /api/providers
接入 create_app（provider 参数路径走 single()），注册 contract_models。
✅ 验证：G.1 的 9、14；health 断言必须原样通过。

Step 3 · Create Run 接收并持久化选择
create_run 调 resolve()、写入四个字段、按 Run 设定 is_mock / cost_available。此时 workflow 仍用默认 provider——这一步只验证「选择被记录」。
✅ 验证：G.1 的 10–13、18–19。

Step 4 · workflow 真正按 Run 取 Provider
RunManager.provider_for() + workflow.py 9 处替换 + 终态时清理映射 + 日志加 provider_id/model_id。
✅ 验证：G.1 的 15–16；全量 pytest；Mock 两轮 Loop 分数不变。

Step 5 · per-model 定价
estimate_cost 改为接收该 Run 的价格；record_usage 传入。
✅ 验证：G.1 的 17（含「无价 → null」）。

Step 6 · 前端数据层
api.ts 的 listProviders、errorMessages.ts 新文案、fixtures.ts 的 makeProviderCatalog 与 makeSnapshot 新字段。
✅ 验证：G.3 的 24–25、29。

Step 7 · 前端 UI
ProductIdeaForm 联动选择器四态 + TelemetryPanel 展示 + AgentDashboard 取数透传。
✅ 验证：G.3 的 26–28；astro check / eslint / prettier / SSR build。

Step 8 · E2E
e2e/helpers.ts 可选参数 + 两条新 spec。
✅ 验证：20 条 E2E 全绿（原 18 + 新 2）。

Step 9 · 文档与门禁
更新 .env.example、README.md、docs/README_ZH.md、PRD.md、design-document.md（§7.7 / §9.1 / §15）、architecture.md（§7 注入点改述为 Catalog、§8 新增 catalog.py 职责行）、progress.md（记录每步验证结果 + 旧 Run 显示「未知模型」的预期行为）。
✅ 验证：跑一遍完整门禁（pytest / Vitest / Playwright / ruff / mypy strict / eslint / prettier / astro check / SSR build）。

---

FINAL PLAN

1. 契约先行：在 backend/schemas.py 新增 ModelInfo / ProviderInfo / ProviderCatalogResponse（只含 provider_id、display_name、model_id、display_name、max_output_tokens、cost_available，无 key / base URL / 价格数值）；给 CreateRunRequest 加可选 provider_id + model_id（必须成对，否则 400），给 PRDRunState / RunSnapshot 加 provider_id / model_id / provider_display_name / model_display_name（optional + 默认 "unknown" / 「未知模型」）；同步 contracts/v1/{provider_catalog,create_run_request,run_snapshot}.json 与前端 types.ts / contracts.ts，并保留「删除新字段仍能解析」的用例。
2. 新增 backend/providers/catalog.py：内部含密 _ModelEntry（dataclass，非 wire model）+ 唯一投影函数 public_catalog() + 按 (provider_id, model_id) 缓存的 resolve()。resolve() 对未知/不可用条目抛 ProviderNotAllowedError(400) / ModelNotAllowedError(400) / ProviderUnavailableError(503)，代码中不存在任何默认回退分支。
3. 配置驱动目录：Settings 新增 llm_allowed_models（含 per-model display name、max_output_tokens、可选单价）；为空时由现有 llm_provider 合成单条目以保证旧 .env 零改动；validate_provider_configuration 扩展为启动时逐条校验密钥与模型名。
4. create_app 构建目录而非单实例：Mock / E2E Scenario / 显式注入 provider 三条路径统一走 ProviderCatalog.single()，保证 make_manager(provider=...) 覆盖的现有测试与 Mock 确定性完全不变；新增只读 GET /api/providers 并登记进 OpenAPI contract_models；HealthResponse 保持不动。
5. RunManager 按 Run 解析：create_run 在返回 202 之前调用 resolve()（校验失败即表单级 400，不产生僵尸 Run），把四个字段写入快照，并按该 Run 设定 is_mock / cost_available；新增 provider_for(run_id)，Run 进入终态时清理映射。
6. workflow.py 机械替换：9 处 self.manager.provider → self.manager.provider_for(run_id)（已确认全部调用点都有 run_id 在作用域内），日志补 provider_id / model_id；不新增任何 RunEventType，避免牵动 17 事件契约与 runReducer 的 184 个测试。
7. per-model 定价：estimate_cost 改为接收该 Run 解析出的单价，缺价时 cost_available=false 且 estimated_cost_usd=null，防止多模型共存后用错单价算出一个看似正常的错数字。
8. 持久化零迁移：run_store.py 表结构（snapshot_json TEXT）不变，新字段随 model_dump_json() 落库，旧行经 model_validate_json() 得到默认值 → 历史 Run 显示「未知模型」，与 current_prd_attempt / output_language 的既有兼容先例一致。
9. 前端：api.ts 新增 listProviders()，AgentDashboard 挂载时取一次目录并下传；ProductIdeaForm 新增 Provider→Model 联动选择器（loading / 单选项 / empty / error 四态，error 与 empty 时禁止提交），提交时成对发送；TelemetryPanel 用快照里的显示名展示「模型 DeepSeek · deepseek-v4-flash」，旧 Run 显示「未知」；errorMessages.ts 补两条中文文案。
10. 测试与门禁：按 G 节落地 34 项检查，重点是「不回退」断言、哨兵密钥不出现在 /api/providers 响应文本中、旧 payload / 旧 SQLite 行兼容、缺价为 null、health 断言原样通过、20 条 E2E（含刷新后仍显示同一模型）全绿。
11. 文档同步（AGENTS.md 强制）：.env.example、README.md、docs/README_ZH.md、PRD.md、design-document.md §7.7/§9.1/§15、architecture.md §7（注入点由「应用工厂」改述为「Provider Catalog」）与 §8（新增 catalog.py 职责行）、progress.md（逐步记录验证结果）。
12. 范围纪律：不引入跨进程共享状态、不改 Reviewer 并行与确定性聚合、不改质量门逻辑、不改 SSE 协议与 Pause/Resume/Cancel、不重构与本需求无关的模块。

第一阶段仅设计，未修改任何文件、未创建 commit、未变更依赖。

✻ Baked for 12m 33s · done 3:04 PM

