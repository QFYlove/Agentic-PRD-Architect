我已经完整阅读了规定文档和与本需求相关的全部关键代码（backend/config.py、main.py、schemas.py、run_manager.py、run_store.py、      
   workflow.py、providers/、errors.py、telemetry.py、contracts/v1/、前端                                                             
   api.ts/types.ts/contracts.ts/ProductIdeaForm.tsx/TelemetryPanel.tsx/errorMessages.ts/runReducer.ts 及测试 helpers）。以下是分析与 
   设计，未修改任何文件。                                                                                                            
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   A. 当前架构理解（与本需求相关）                                                                                                   
                                                                                                                                     
   Provider 配置与创建（进程级单例）                                                                                                 
                                                                                                                                     
   • backend/config.py:11-131 — Settings 用 pydantic-settings 从环境读取：enable_mock_llm、llm_provider: Literal["deepseek","glm"]、 
     deepseek_api_key/base_url/model、glm_*（SecretStr，repr=False）、全局 llm_max_output_tokens、全局价格                           
     model_input/output_price_per_million。启动时 validate_provider_configuration 校验：Mock 关闭时所选 Provider 必须有 Key 且模型非 
     空——不静默回退 Mock。                                                                                                           
   • backend/main.py:85-134 — create_app() 在启动时创建唯一一个 Provider 实例：Mock / ScenarioMock（仅 APP_ENV=test +                
     E2E_TEST_MODE）/ OpenAICompatibleLLMProvider。此后全进程共享。                                                                  
   • backend/providers/base.py:36-81 — LLMProvider ABC：stream_prd / generate_review / generate_revision_plan / repair_structured，类
     属性 is_mock。                                                                                                                  
   • backend/providers/compatible.py:48-73 — DeepSeek/GLM 共用适配器，构造时注入 provider_name/api_key/base_url/model。              
   • backend/providers/mock.py:152-153 — MockLLMProvider.is_mock = True，内部模型名写死为 mock-prd-v1 等。                           
   • backend/providers/scenario.py:38 — E2E 故障注入 Provider，继承 Mock。                                                           
                                                                                                                                     
   Provider 的消费方式                                                                                                               
                                                                                                                                     
   • backend/run_manager.py:53 — RunManager.provider 保存单例；create_run()（run_manager.py:124-177）用它设置快照的 is_mock 和       
     cost_available。                                                                                                                
   • backend/workflow.py — 所有节点通过 self.manager.provider.* 调用模型（stream_prd L367、generate_review L513、                    
     generate_revision_plan L779、repair_structured L600）；run_started 事件 payload 的 config.mock 来自该单例（L129）。             
   • backend/telemetry.py:19-36 — estimate_cost 用 Settings 里的全局价格；Mock 返回 0.0；无价格返回 None（架构规则：缺价格必须是     
     null）。                                                                                                                        
                                                                                                                                     
   Run 创建与持久化                                                                                                                  
                                                                                                                                     
   • backend/schemas.py:101-122 — CreateRunRequest（StrictModel，extra="forbid"）：只有                                              
     idea/audience/constraints/threshold/iterations，没有 provider/model 字段。                                                      
   • backend/schemas.py:319-391 — PRDRunState / RunSnapshot 同样没有 provider/model 字段；有 is_mock、cost_available。               
   • backend/run_store.py:169-304 — SQLite 只存 snapshot_json 完整 JSON blob（runs 表三列），加载用 RunSnapshot.model_validate_json。
     这意味着新增带默认值的可选字段即可向后兼容，无需 SQL migration（已有先例：current_prd_attempt、best_version 的兼容测试见        
     backend/tests/test_contracts.py:29-45）。                                                                                       
                                                                                                                                     
   API 与契约                                                                                                                        
                                                                                                                                     
   • backend/main.py:279-292 — POST /api/runs → 202。GET /api/health 返回 provider（当前默认 provider 名）。main.py:403-437 显式注册 
     契约模型到 OpenAPI；backend/tests/test_contracts.py 用 contracts/v1/*.json fixture 双向校验。                                   
   • 前端 src/lib/api.ts:36-45 — AgentApi 接口；src/lib/types.ts:66-72 — CreateRunRequest；src/lib/contracts.ts:133-147 —            
     parseRunSnapshot 只做最小字段检查，新增可选字段不会破坏前端解析。                                                               
   • src/components/ProductIdeaForm.tsx — 创建表单，目前只有质量设置，无模型选择；onSubmit 一路传到 useAgentRun.createRun →          
     api.createRun。                                                                                                                 
   • src/components/TelemetryPanel.tsx — 显示迭代/时长/Token/费用和 Mock 标签，无 provider/model 展示。                              
   • src/lib/errorMessages.ts — 错误码→文案映射表，新错误码需要在这里登记。                                                          
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   B. 影响范围（预计修改的文件）                                                                                                     
                                                                                                                                     
   后端                                                                                                                              
                                                                                                                                     
   ┌───────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────┐
   │ 文件                              │ 原因                                                                                       │
   ├───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
   │ backend/config.py                 │ 新增每个 Provider 的模型列表配置（如 deepseek_models，默认回退到 deepseek_model），供目录  │
   │                                   │ （catalog）派生                                                                            │
   ├───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
   │ backend/providers/registry.py（新 │ Provider/Model 目录 + 按 id 解析 Provider 实例的工厂；安全元数据的唯一来源                 │
   │ 增）                              │                                                                                            │
   ├───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
   │ backend/providers/__init__.py     │ 导出 registry 类型                                                                         │
   ├───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
   │ backend/errors.py                 │ 新增 ProviderNotAvailableError / ModelNotAvailableError（400，安全文案）                   │
   ├───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
   │ backend/schemas.py                │ CreateRunRequest 增加可选 provider/model；PRDRunState 增加 llm_provider/llm_model（可选、  │
   │                                   │ 默认 None）；新增 ModelInfo/ProviderInfo/ProviderCatalogResponse；RunSummary 可选加同两字  │
   │                                   │ 段                                                                                         │
   ├───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
   │ backend/run_manager.py            │ 注入 registry；create_run 解析并校验选择（失败即 400，不创建 Run）；按 run 保存 Provider   │
   │                                   │ 实例；provider_for(run_id)；is_mock/cost_available 按所选 Provider 计算；资源释放          │
   ├───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
   │ backend/workflow.py               │ 所有 self.manager.provider.* 调用点改为 manager.provider_for(run_id)；run_started payload  │
   │                                   │ 带上所选 provider/model                                                                    │
   ├───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
   │ backend/main.py                   │ 装配 registry；新增 GET /api/providers；OpenAPI 契约模型登记                               │
   ├───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
   │ backend/telemetry.py              │ 费用计算按 Run 所选模型判定（非默认模型且无价格 → None，不得按默认价格估算）               │
   ├───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
   │ backend/tests/helpers.py          │ make_manager 构造 registry（包装单 provider），保持现有测试签名                            │
   └───────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────┘
                                                                                                                                     
   契约与后端测试                                                                                                                    
                                                                                                                                     
   ┌───────────────────────────────────────────────────────────────────────────────────────┬────────────────────────────────────────┐
   │ 文件                                                                                  │ 原因                                   │
   ├───────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────┤
   │ contracts/v1/providers_response.json（新增）                                          │ 目录响应样本                           │
   ├───────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────┤
   │ contracts/v1/run_snapshot.json / terminal_snapshots.json                              │ 补上 llm_provider/llm_model 示例       │
   ├───────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────┤
   │ contracts/v1/create_run_request.json                                                  │ 可保持不变（新字段可选），建议另加带选 │
   │                                                                                       │ 择的样本                               │
   ├───────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────┤
   │ backend/tests/test_contracts.py、test_config.py、test_api.py、test_run_manager.py、   │ 见 G 节                                │
   │ test_workflow.py、新增 test_provider_registry.py                                      │                                        │
   └───────────────────────────────────────────────────────────────────────────────────────┴────────────────────────────────────────┘
                                                                                                                                     
   前端                                                                                                                              
                                                                                                                                     
   ┌────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────┐
   │ 文件                               │ 原因                                                                                      │
   ├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
   │ src/lib/types.ts                   │ ModelInfo/ProviderInfo/ProviderCatalogResponse；CreateRunRequest.provider?/model?；RunSna │
   │                                    │ pshot.llm_provider?/llm_model?                                                            │
   ├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
   │ src/lib/api.ts                     │ listProviders() 方法与解析器                                                              │
   ├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
   │ src/lib/contracts.ts               │ parseProvidersResponse                                                                    │
   ├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
   │ src/components/ProductIdeaForm.tsx │ Provider/Model 级联选择与 Loading/Error 状态；提交时带上选择                              │
   ├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
   │ src/components/AgentDashboard.tsx  │ 挂载时拉取目录并传给表单                                                                  │
   ├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
   │ src/components/TelemetryPanel.tsx  │ 展示本次 Run 的 Provider/Model                                                            │
   ├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
   │ src/lib/errorMessages.ts           │ 新错误码文案                                                                              │
   ├────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
   │ src/test/fixtures.ts + 相关测试文  │ 快照工厂补字段；新增选择器/目录/遥测测试                                                  │
   │ 件                                 │                                                                                           │
   └────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────┘
                                                                                                                                     
   E2E 与文档                                                                                                                        
                                                                                                                                     
   • e2e/helpers.ts（选择模型辅助）、e2e/happy-path.spec.ts（默认选择不破坏）或新增 e2e/provider-selection.spec.ts。                 
   • .env.example、README.md、docs/README_ZH.md、memory-bank/design-document.md、memory-bank/architecture.md（文件职责表 + 决策）、完
     成后 memory-bank/progress.md。                                                                                                  
                                                                                                                                     
   不需要改：state_machine.py、event_store.py、run_store.py（JSON blob 天然兼容）、prompts.py、prd_document.py、language.py、SSE 协议
   与 17 种事件集合。                                                                                                                
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   C. 数据模型与 API 设计                                                                                                            
                                                                                                                                     
   Provider / Model 元数据（后端唯一来源）                                                                                           
                                                                                                                                     
   ```python                                                                                                                         
     class ModelInfo(StrictModel):                                                                                                   
         id: str                      # "deepseek-v4-flash"                                                                          
         display_name: str            # 默认同 id                                                                                    
         capabilities: dict[str, bool]  # {"streaming": true, "structured_output": true}                                             
                                                                                                                                     
     class ProviderInfo(StrictModel):                                                                                                
         id: str                      # "deepseek" | "glm" | "mock"                                                                  
         display_name: str            # "DeepSeek" / "GLM" / "Mock"                                                                  
         is_mock: bool                                                                                                               
         models: list[ModelInfo]                                                                                                     
                                                                                                                                     
     class ProviderCatalogResponse(StrictModel):                                                                                     
         default_provider: str                                                                                                       
         default_model: str                                                                                                          
         providers: list[ProviderInfo]                                                                                               
   ```                                                                                                                               
                                                                                                                                     
   绝不包含：api_key、base_url、超时、价格（价格也不必要暴露）。这些只留在 Settings/registry 内部。                                  
                                                                                                                                     
   创建 Run API                                                                                                                      
                                                                                                                                     
   CreateRunRequest 增加两个可选字段：                                                                                               
                                                                                                                                     
   ```python                                                                                                                         
     provider: str | None = Field(default=None, max_length=64)                                                                       
     model: str | None = Field(default=None, max_length=128)                                                                         
   ```                                                                                                                               
                                                                                                                                     
   • 都缺省 → 使用服务端默认选择（= 当前行为：Mock 开启时 Mock；否则 LLM_PROVIDER + 配置的模型）。这是向后兼容关键。                 
   • 只给 model 不给 provider → 400（语义不完整，避免猜）。                                                                          
   • 指定了但不在目录中 → 400 显式失败，不创建 Run、不换模型。                                                                       
                                                                                                                                     
   响应 202 不变。                                                                                                                   
                                                                                                                                     
   RunSnapshot                                                                                                                       
                                                                                                                                     
   PRDRunState 增加：                                                                                                                
                                                                                                                                     
   ```python                                                                                                                         
     llm_provider: str | None = None                                                                                                 
     llm_model: str | None = None                                                                                                    
   ```                                                                                                                               
                                                                                                                                     
   • 新 Run：创建时写入解析结果（如 "deepseek" / "deepseek-v4-flash"；Mock 写 "mock" / "mock-prd-v1"）。                             
   • 旧 Run（字段缺失）：反序列化为 None，前端显示「服务端默认模型」。StrictModel extra="forbid" 只影响「旧代码读新数据」，不影响本方
     向。                                                                                                                            
                                                                                                                                     
   新 endpoint                                                                                                                       
                                                                                                                                     
   GET /api/providers → ProviderCatalogResponse，200。无鉴权（与现有 API 一致）、CORS 沿用。注册进 contract_models 以进 OpenAPI。GET 
   /api/health 保持不变（仍报告服务端默认 provider）。                                                                               
                                                                                                                                     
   错误语义                                                                                                                          
                                                                                                                                     
   ┌───────────────────────────┬───────────────────────────────────────┬────────────────────────────────────────┬───────────────────┐
   │ 场景                      │ HTTP                                  │ code                                   │ 说明              │
   ├───────────────────────────┼───────────────────────────────────────┼────────────────────────────────────────┼───────────────────┤
   │ 指定 provider 不在目录    │ 400                                   │ PROVIDER_NOT_AVAILABLE                 │ 明确失败，不      │
   │                           │                                       │                                        │ fallback          │
   ├───────────────────────────┼───────────────────────────────────────┼────────────────────────────────────────┼───────────────────┤
   │ provider 有效但 model 不  │ 400                                   │ MODEL_NOT_AVAILABLE                    │ 同上              │
   │ 在其列表                  │                                       │                                        │                   │
   ├───────────────────────────┼───────────────────────────────────────┼────────────────────────────────────────┼───────────────────┤
   │ 只给 model 未给 provider  │ 400                                   │ MODEL_NOT_AVAILABLE（或                │ 语义不完整        │
   │                           │                                       │ PROVIDER_NOT_AVAILABLE）               │                   │
   ├───────────────────────────┼───────────────────────────────────────┼────────────────────────────────────────┼───────────────────┤
   │ 目录内 provider 运行期认  │ 走现有 PROVIDER_AUTHENTICATION_FAILED │ —                                      │ 复用              │
   │ 证失败                    │  路径                                 │                                        │                   │
   └───────────────────────────┴───────────────────────────────────────┴────────────────────────────────────────┴───────────────────┘
                                                                                                                                     
   前端 errorMessages.ts 增加两条文案，如「所选模型不可用，请刷新后重新选择。」                                                      
                                                                                                                                     
   向后兼容方案                                                                                                                      
                                                                                                                                     
   1. 旧客户端（不带 provider/model）→ 服务端默认选择，行为与今天完全一致。                                                          
   2. 旧 SQLite 行 → Pydantic 默认值 None 兜底，无需 migration；加一条「删除字段后仍可反序列化」的契约测试（仿                       
      test_streaming_attempt_defaults_to_one_for_older_snapshots）。                                                                 
   3. 新前端对旧后端：前端先探测 GET /api/providers，404/失败则隐藏选择器、按旧格式提交（extra="forbid" 会拒绝未知字段，所以必须探测 
      后再决定是否发送）。                                                                                                           
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   D. Provider 层设计                                                                                                                
                                                                                                                                     
   现状                                                                                                                              
                                                                                                                                     
   create_app 启动时构造一个 Provider 单例，RunManager/AgentWorkflow 全部经 manager.provider 使用；Mock/Scenario/真实 Provider 的选择
   由 enable_mock_llm + e2e_test_mode + llm_provider 决定。                                                                          
                                                                                                                                     
   改造：ProviderRegistry（新文件 backend/providers/registry.py）                                                                    
                                                                                                                                     
   职责：从 Settings 派生目录和工厂，是唯一知道 key/base_url 的地方。                                                                
                                                                                                                                     
   ```python                                                                                                                         
     class ProviderRegistry:                                                                                                         
         def __init__(self, settings: Settings, *, scenario: ScenarioMockLLMProvider | None = None): ...                             
         def catalog(self) -> ProviderCatalogResponse: ...          # 安全元数据，无密钥                                             
         def resolve(self, provider_id: str | None, model_id: str | None) -> ResolvedProvider: ...                                   
             # ResolvedProvider = (instance, provider_id, model_id, is_mock, pricing 可用性)                                         
   ```                                                                                                                               
                                                                                                                                     
   目录构造规则：                                                                                                                    
                                                                                                                                     
   • enable_mock_llm=true → 目录含 mock 条目（E2E 模式下其背后就是 Scenario Provider，故障注入路径不变）。                           
   • deepseek_api_key 已配置 → 含 deepseek 条目，模型列表来自 deepseek_models（新增逗号分隔配置，缺省 = [deepseek_model]，保持单模型 
     现状）。GLM 同理。                                                                                                              
   • 未配 Key 的 Provider 不进目录 → 选择它必然 400，从机制上杜绝「选了但没 Key 时悄悄换模型」。                                     
   • 默认选择：enable_mock_llm 时 mock，否则 llm_provider + 对应 *_model——与今天的默认行为逐一对应。                                 
   • Mock 关闭时的启动校验（所选 provider 必须有 Key）保留不变。                                                                     
                                                                                                                                     
   实例缓存：真实 Provider 按 (provider_id, model_id) 缓存 OpenAICompatibleLLMProvider（AsyncOpenAI client 可复用）；Mock 全局单例。 
                                                                                                                                     
   RunManager / Workflow 改动                                                                                                        
                                                                                                                                     
   • RunManager.__init__ 接收 registry（保留 provider 作为默认 Provider 属性以最小化测试 churn，或 helpers 统一包一层 registry——推荐 
     后者，语义唯一）。                                                                                                              
   • create_run：在 _create_lock 内先 registry.resolve(request.provider, request.model)，失败抛 AppError(400)，在创建快照之前；成功则
     self._run_providers[run_id] = instance，快照写入 llm_provider/llm_model/is_mock/cost_available。                                
   • 新增 provider_for(run_id)，未知 run 回退默认（实际上只会被已创建 run 调用）。                                                   
   • _release_run_resources 清理 _run_providers。                                                                                    
   • workflow.py 的 5 处 self.manager.provider 调用点 + run_started payload 的 mock 字段改为按 run 解析；run_started 的 config 增加  
     provider/model 便于 Trace 展示。                                                                                                
   • 日志（observability.py 白名单风格）记录 provider/model id——不是敏感信息；key/base_url 依旧不进日志。                            
                                                                                                                                     
   密钥不外泄                                                                                                                        
                                                                                                                                     
   目录响应由 registry 从「显示名 + id + 静态能力表」构造，不经过 Settings 的 SecretStr 字段；ProviderInfo/ModelInfo 用              
   extra="forbid" 锁住形状，再加一条安全测试：序列化目录和快照中不出现 api_key、base_url、key 值本身（仿                             
   test_observability_security.py 的思路）。                                                                                         
                                                                                                                                     
   Mock 的处理                                                                                                                       
                                                                                                                                     
   • Mock 是目录中的普通条目（is_mock: true，模型 mock-prd-v1）。                                                                    
   • 默认开发 .env（Mock 开、无 Key）下目录 = 仅 [mock]，前端选择器只有一项——现有全部 Mock 确定性测试、Playwright 场景零变化。       
   • Mock 关闭且未指定时，任何「请求 mock」的创建调用 400 失败，而不是悄悄用真实模型（反向 silent fallback 同样禁止）。              
                                                                                                                                     
   费用语义                                                                                                                          
                                                                                                                                     
   estimate_cost 目前用全局价格。改造为：仅当 Run 所选 (provider, model) 等于价格配置所对应的默认模型时用配置价格；Mock 恒 0.0；其余 
   情况 cost_available=False、estimated_cost_usd=None（遵守「缺价格必须是 null，不能按零费用展示」的不可变决策）。                   
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   E. Persistence                                                                                                                    
                                                                                                                                     
   • 不需要 SQL migration。runs 表存的是整个 snapshot_json blob（run_store.py:246-261），新字段在 Pydantic 层以可选默认值加入即可。  
   • 老 Run 读取：RunSnapshot.model_validate_json 对缺失的 llm_provider/llm_model 填 None；RUN_INTERRUPTED 恢复路径                  
     （_load_snapshots）不受影响。前端把 None 显示为「服务端默认（历史运行）」。                                                     
   • 新 Run 保存：create_run 时把解析出的 provider/model id 写进快照，随每次 commit() 持久化——重启、刷新后仍可读出，满足要求 5。     
   • 需要补一条契约级回归测试：从 fixture 删掉这两个字段后仍能反序列化（仿现有 current_prd_attempt/best_version 兼容测试）。         
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   F. Frontend                                                                                                                       
                                                                                                                                     
   创建 Run 界面（ProductIdeaForm.tsx + AgentDashboard.tsx）                                                                         
                                                                                                                                     
   • AgentDashboard 挂载时调用 api.listProviders()，把目录传给表单（表单保持受控、可测试）。                                         
   • 表单在「质量设置」上方新增「模型」区块：Provider 下拉 + Model 下拉。                                                            
   • 联动：Model 下拉只列当前 Provider 的 models；切换 Provider 时 Model 重置为该 Provider 的第一个（或目录给出的 default）。初始选中
     = default_provider/default_model。                                                                                              
   • 提交体增加 provider/model（仅当目录加载成功时；否则按旧格式提交）。                                                             
   • 目录只有一个 Provider 一个模型时仍展示（只读或禁用态），让「本次 Run 用什么模型」始终可见。                                     
                                                                                                                                     
   Loading / Empty / Error                                                                                                           
                                                                                                                                     
   • Loading：选择器骨架/禁用，提交不受影响前不可选。                                                                                
   • Error（目录拉取失败或 404 旧后端）：隐藏选择器，显示温和提示「模型选择不可用，将使用服务端默认模型」，提交不带 provider/model—— 
     这不是 silent fallback（用户未指定任何选择；指定后失败才必须显式报错）。                                                        
   • Empty：目录至少含一个可用 Provider（mock 或已配置的），空目录视为 Error 处理。                                                  
   • 提交后后端返回 400 PROVIDER_NOT_AVAILABLE 等 → 走现有 ApiClientError + errorMessages.ts 文案路径，在表单错误区显示。            
                                                                                                                                     
   Telemetry / Run 信息                                                                                                              
                                                                                                                                     
   • TelemetryPanel 在指标区加一行「模型」：{llm_provider} / {llm_model}（如 deepseek / deepseek-v4-flash），None 时显示「服务端默认 
     （历史运行）」；Mock 标签逻辑不变。                                                                                             
   • RunSummary 若加上同两字段，ConversationSidebar 可在历史条目里小字显示（可选增强，成本低）。                                     
   • Trace：run_started payload 的 config.provider/model 可由 trace.ts 白名单映射成一行文案。                                        
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   G. Testing                                                                                                                        
                                                                                                                                     
   Backend pytest                                                                                                                    
                                                                                                                                     
   新增 backend/tests/test_provider_registry.py：                                                                                    
   • 目录只含已配置 Provider：Mock 开 + 无 Key → 仅 mock；配置 DeepSeek Key 后出现 deepseek 条目。                                   
   • 目录序列化结果中不出现 key、base_url（安全回归）。                                                                              
   • resolve(None, None) 返回默认（mock 模式 → mock；非 mock → 配置的 provider/model）。                                             
   • resolve("deepseek", ...) 在未配置时抛 ProviderNotAvailableError；错误 model 抛 ModelNotAvailableError。                         
   • 解析缓存：同 (provider, model) 返回同一实例。                                                                                   
                                                                                                                                     
   test_config.py：                                                                                                                  
   • deepseek_models 逗号解析、缺省回退 deepseek_model、空项过滤。                                                                   
                                                                                                                                     
   test_api.py：                                                                                                                     
   • GET /api/providers 200 + 形状 + 无敏感字段。                                                                                    
   • 带有效 provider/model 创建 Run → 202，快照含 llm_provider/llm_model。                                                           
   • 带未知 provider / 未知 model / 只给 model → 400 对应错误码，且未创建 Run（GET /api/runs 数量不变）。                            
   • 旧格式请求（无新字段）→ 202，行为与现状一致。                                                                                   
                                                                                                                                     
   test_run_manager.py / test_workflow.py：                                                                                          
   • 不同 Run 解析到不同 Provider 实例；workflow 调用的是 per-run provider（可用两个不同 Mock 子类断言被调用的是哪个）。             
   • is_mock、cost_available 按所选 provider 写入快照。                                                                              
   • 非默认模型 Run 的费用为 None 且 cost_available=False（不是 0、不是按默认价格算）。                                              
                                                                                                                                     
   test_contracts.py：                                                                                                               
   • 新 fixture providers_response.json 通过 Pydantic 校验。                                                                         
   • 快照 fixture 删除 llm_provider/llm_model 仍可反序列化（老数据兼容）。                                                           
   • OpenAPI 组件包含 ProviderCatalogResponse。                                                                                      
                                                                                                                                     
   test_observability_security.py：目录/快照/日志中无 key、base_url。                                                                
                                                                                                                                     
   Contract tests（前后端共享 fixture）                                                                                              
                                                                                                                                     
   • contracts/v1/providers_response.json 新增；run_snapshot.json、terminal_snapshots.json 补 llm_provider/llm_model。               
   • 前端 src/lib/contracts.test.ts 同步消费新 fixture。                                                                             
                                                                                                                                     
   Vitest                                                                                                                            
                                                                                                                                     
   • src/lib/api.test.ts：listProviders 成功/网络错误/非法响应。                                                                     
   • src/lib/contracts.test.ts：parseProvidersResponse 接受合法、拒绝缺字段样本。                                                    
   • src/components/components.test.tsx：表单渲染选择器、Provider→Model 级联重置、提交体包含选择、目录加载失败时降级提交（不含       
     provider/model）。                                                                                                              
   • src/components/AgentDashboard.test.tsx：挂载拉目录、失败时表单仍可用。                                                          
   • TelemetryPanel 相关测试：显示 provider/model，历史快照（字段缺失）显示默认文案。                                                
                                                                                                                                     
   Playwright E2E                                                                                                                    
                                                                                                                                     
   • 现有 18 项必须全绿（Mock 默认路径不变）。                                                                                       
   • 新增（或并入 happy-path）：                                                                                                     
       • 创建页可见模型选择器且默认选中 Mock；创建后 Telemetry 显示 mock / mock-prd-v1。                                             
       • API 层（page.request）POST 非法 provider → 400 + 错误码，UI 不进入运行态。                                                  
   • 不需要真实 Key 的用例；真实 provider 选择仍属手动冒烟。                                                                         
                                                                                                                                     
   Static / type checks                                                                                                              
                                                                                                                                     
   • ruff format --check、ruff check、mypy backend（strict：registry 全类型标注）。                                                  
   • npm run lint、npm run typecheck（astro check）、npm run format:check、npm run build。                                           
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   H. 风险                                                                                                                           
                                                                                                                                     
   1. Provider 单例假设散布在 workflow：workflow.py 有 5 处 self.manager.provider 调用点 + run_started payload + 重试日志。漏改任何一
      处，会出现「评审用了 A 模型、生成用了 B 模型」的静默混用——这正是本需求最危险的地方。改完后必须有「per-run provider 被实际调用」
      的测试。                                                                                                                       
   2. 费用语义：对非默认模型按全局价格估算是错误数据，比没有数据更糟（架构规则明确禁止）。必须落入 None 分支。                       
   3. 默认行为漂移：默认选择若不是「Mock 开→mock、否则 env provider」，现有 276 项 pytest、184 项 Vitest、18 项 E2E 会大面积变红。   
   4. E2E 故障注入：ScenarioMockLLMProvider 必须仍是测试模式下所有 Run 的解析结果，否则 failures.spec.ts 的注入失效。                
   5. extra="forbid" 版本偏斜：新前端直接向旧后端发 provider 字段会被 422。必须经 GET /api/providers 探测后再决定是否发送。          
   6. 契约同步面：Pydantic ↔ contracts/v1/*.json ↔ TS 类型 ↔ 前端运行时解析四处同步，漏一处契约测试就抓不住漂移。                    
   7. 密钥泄漏面：目录 endpoint 是新的对外出口，必须有序列化级安全测试，防止未来有人把 Settings 字段直接塞进响应。                   
   8. 并发：4 个并发 Run 各用不同 Provider 时，cancel/pause 信号与 provider 实例的对应关系不能串（现有 per-run 结构可覆盖，但要避免把
      provider 缓存键写成 run 无关的全局单例而又按 model 区分错）。                                                                  
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   I. 实施计划（小步、可验证）                                                                                                       
                                                                                                                                     
   1. Schemas + errors：CreateRunRequest、PRDRunState、ProviderCatalogResponse 等模型与两个新错误码。跑 pytest tests/test_schemas.py 
      + test_contracts.py（旧 fixture 应仍通过，证明向后兼容）。                                                                     
   2. Config + Registry：deepseek_models/glm_models 与 ProviderRegistry，含目录安全单测。此时不改任何调用方。                        
   3. RunManager/Workflow 按 Run 解析：注入 registry、create_run 校验与持久化、provider_for、workflow 调用点切换。跑全部现有 pytest——
      默认路径行为应零变化。                                                                                                         
   4. API + 契约：GET /api/providers、OpenAPI 登记、contracts/v1 fixture 更新、test_api.py/test_contracts.py 新用例。                
   5. 前端契约层：types.ts/api.ts/contracts.ts + 对应 Vitest。                                                                       
   6. 前端 UI：表单选择器（含级联与三态）、Dashboard 拉取、Telemetry 展示、错误文案。Vitest 组件测试。                               
   7. E2E：新增 provider 选择用例，回归全部既有 spec。                                                                               
   8. 文档：.env.example、README.md、docs/README_ZH.md、design-document.md（API/模型小节）、architecture.md（文件职责表 + 目录/默认选
      择决策）、progress.md。                                                                                                        
   9. 全量门禁：pytest、test:run、test:e2e、Ruff/mypy/ESLint/Prettier/astro check、npm run build。                                   
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   FINAL PLAN                                                                                                                        
                                                                                                                                     
   1. backend/schemas.py：CreateRunRequest 加可选 provider/model；PRDRunState（及 RunSummary）加可选 llm_provider/llm_model（默认    
      None，老数据免 migration）；新增 ModelInfo/ProviderInfo/ProviderCatalogResponse。                                              
   2. backend/errors.py：新增 PROVIDER_NOT_AVAILABLE / MODEL_NOT_AVAILABLE（HTTP 400，安全文案）。                                   
   3. backend/config.py：新增 deepseek_models / glm_models 逗号分隔模型列表，缺省回退现有单模型配置；启动校验保持不变。              
   4. 新建 backend/providers/registry.py：ProviderRegistry 从 Settings 派生安全目录（只含已配置 Provider；mock 开关语义不变；默认选择
      = 当前行为），按 id 解析/缓存 Provider 实例；key/base_url 永不进入目录。                                                       
   5. backend/run_manager.py：注入 registry；create_run 先解析后建快照（非法选择 400 且不创建 Run）；按 run 保存实例、写             
      llm_provider/llm_model/is_mock/cost_available；新增 provider_for(run_id) 并在资源释放时清理。                                  
   6. backend/workflow.py：全部 manager.provider 调用点改为 manager.provider_for(run_id)；run_started 的 config 增加 provider/model。
   7. backend/telemetry.py：非默认模型 Run 的费用为 None（cost_available=False），绝不按错误价格估算。                               
   8. backend/main.py：装配 registry（E2E 模式下 mock 条目仍指向 Scenario Provider），新增 GET /api/providers，新模型注册进 OpenAPI  
      契约集。                                                                                                                       
   9. 契约 fixture：新增 contracts/v1/providers_response.json，快照 fixture 补 llm_provider/llm_model，加「老快照缺字段仍可反序列化」
      测试。                                                                                                                         
   10. 前端契约层：types.ts、api.ts（listProviders）、contracts.ts 解析器。                                                          
   11. 前端 UI：AgentDashboard 挂载拉目录（失败则降级为默认提交）；ProductIdeaForm 增加 Provider/Model 级联选择与 Loading/Error 态   
       ；TelemetryPanel 展示本 Run 模型；errorMessages.ts 补新错误码。                                                               
   12. 测试：新增 test_provider_registry.py；扩展                                                                                    
       test_config.py/test_api.py/test_run_manager.py/test_workflow.py/test_contracts.py/test_observability_security.py；前端        
       api.test.ts/contracts.test.ts/组件测试；Playwright 新增模型选择用例并回归既有 18 项。                                         
   13. 文档同步：.env.example、README.md、docs/README_ZH.md、memory-bank/design-document.md、memory-bank/architecture.md、           
       memory-bank/progress.md。                                                                                                     
   14. 收尾全量门禁：pytest、Vitest、Playwright、Ruff、mypy、ESLint、Prettier、astro check、SSR build。                              
                                                                                                                                     
   设计到此为止，未开始编码。如需我按此计划进入实现阶段，请指示。     