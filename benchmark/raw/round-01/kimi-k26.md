我已经完成了对仓库的深度代码审查。以下是完整的架构分析与实施方案。

────────────────────────────────────────────────────────────────────────────────

A. 当前架构理解

Provider 全局单例模式
• backend/config.py 通过环境变量配置单个全局 Provider（llm_provider: "deepseek" | "glm"），以及对应的 API Key、Base URL、
Model。
• backend/main.py() 在应用启动时根据 Settings 创建一个全局 LLMProvider 实例（MockLLMProvider 或
OpenAICompatibleLLMProvider），并注入 RunManager。
• backend/run_manager.py 在 init 中接收该单例 provider，所有 Run 共享同一实例。
• backend/workflow.py 的各节点通过 self.manager.provider 直接调用流式生成、评审和优化（约 5 处直接访问）。

Run 创建与持久化
• POST /api/runs 的 CreateRunRequest（backend/schemas.py:101）仅包含业务参数：user_idea、target_audience、user_constraints、
quality_threshold、max_iterations。无任何 Provider/Model 选择字段。
• PRDRunState（backend/schemas.py:319）仅通过 is_mock: bool 标记是否使用 Mock，不记录具体 Provider 或 Model。
• SQLiteRunStore（backend/run_store.py:169）将完整 RunSnapshot JSON 存入 runs 表，无需 schema migration。

前端
• src/components/ProductIdeaForm.tsx 创建表单仅包含业务输入和质量设置。
• src/lib/types.ts 与后端 Pydantic 模型手工对齐。
• TelemetryPanel（src/components/TelemetryPanel.tsx）仅展示 is_mock 标签，不展示 Provider/Model 名称。
• HealthResponse 返回应用级 mock_mode 和默认 provider 字符串。

测试与契约
• backend/tests/helpers.py 的 make_manager() 创建全局 MockLLMProvider 注入 Manager。
• contracts/v1/create_run_request.json 和 run_snapshot.json 等 fixture 是前后端的可执行契约边界。
• E2E 在 Mock 模式下跑全量验收。

────────────────────────────────────────────────────────────────────────────────

B. 影响范围

┌───────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────┐
│ 文件                                  │ 修改原因                                                                               │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ backend/config.py                     │ 新增可用模型列表解析逻辑（从现有环境变量推导，或新增显式配置）；保持现有密钥配置不动。 │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ backend/schemas.py                    │ CreateRunRequest 新增可选 model_key；PRDRunState/RunSnapshot 新增 provider_id +        │
│                                       │ model_id（或 model_key）；HealthResponse 可能新增 available_models 摘要。              │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ 新建 backend/provider_factory.py      │ 集中管理 Provider 注册表、安全元数据暴露、按选择创建 Provider 实例。避免 main.py 膨胀  │
│                                       │ 。                                                                                     │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ backend/main.py                       │ 不再创建全局单例 Provider；改为初始化 ProviderFactory 并注入 RunManager；新增 GET      │
│                                       │ /api/providers 路由。                                                                  │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ backend/run_manager.py                │ init 接收 ProviderFactory 替代单例 provider；create_run() 根据 request 创建        │
│                                       │ per-run Provider 并缓存；get_provider(run_id) 替代 .provider 属性；record_usage 从     │
│                                       │ per-run provider 读取 is_mock。                                                        │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ backend/workflow.py                   │ 所有 self.manager.provider 改为 self.manager.get_provider(run_id)，约 5 处。           │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ backend/providers/base.py             │ 可选：在 LLMProvider 基类增加 provider_id/model_id 只读属性，方便 Telemetry 记录。     │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ backend/tests/helpers.py              │ make_manager() / make_sqlite_manager() 改为接收 ProviderFactory。                      │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ backend/tests/test_api.py             │ 新增创建 Run 时带 model_key、不带 model_key（向后兼容）、非法 model_key 的用例。       │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ backend/tests/test_workflow.py        │ 验证 Workflow 节点能正确获取 per-run Provider。                                        │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ 新建/修改                             │ 注册表解析、安全元数据过滤、Mock 模式行为。                                            │
│ backend/tests/test_provider_factory.p │                                                                                        │
│ y                                     │                                                                                        │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ contracts/v1/create_run_request.json  │ 补充可选 model_key 示例。                                                              │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ contracts/v1/run_snapshot.json        │ 补充 provider_id + model_id 示例。                                                     │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ contracts/v1/terminal_snapshots.json  │ 补充旧 Run 无 provider 字段的兼容性示例。                                              │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ src/lib/types.ts                      │ CreateRunRequest、RunSnapshot 新增对应字段；新增 ModelOption 类型。                    │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ src/lib/api.ts                        │ 新增 listProviders() 方法和解析器。                                                    │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ src/lib/contracts.ts                  │ 新增 parseModelOption / parseModelListResponse 运行时校验。                            │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ src/components/ProductIdeaForm.tsx    │ 在表单中增加 Provider/Model 选择区域（或置于"质量设置"内）。                           │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ src/components/AgentDashboard.tsx     │ 在创建 Run 前或表单加载时获取可用模型列表并传入表单。                                  │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ src/components/TelemetryPanel.tsx     │ 展示当前 Run 的 Provider/Model 信息；旧 Run 显示"默认"或隐藏。                         │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ src/hooks/useAgentRun.ts              │ 新增获取模型列表的状态和方法；createRun 传入 model_key。                               │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ e2e/helpers.ts /                      │ Mock 模式下验证表单选择和 Telemetry 展示。                                             │
│ e2e/happy-path.spec.ts                │                                                                                        │
├───────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ memory-bank/progress.md               │ 记录新增能力。                                                                         │
└───────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────────────────────

C. 数据模型与 API 设计

Provider / Model 元数据定义

  # backend/provider_factory.py（新建）                                                                                           
  class ModelOption(StrictModel):                                                                                                 
      model_key: str           # 唯一标识，如 "deepseek:deepseek-v4-flash"                                                        
      provider_id: str         # "deepseek" | "glm" | "mock"                                                                      
      provider_name: str       # 人类可读，如 "DeepSeek"                                                                          
      model_id: str            # 端点模型 ID                                                                                      
      model_name: str          # 人类可读，如 "DeepSeek V4 Flash"                                                                 
      capabilities: list[str] = Field(default_factory=list)                                                                       
      is_mock: bool = False                                                                                                       

后端通过 ProviderFactory.list_available() 返回 list[ModelOption]，绝不包含 api_key、base_url。

创建 Run API 变化

  # backend/schemas.py                                                                                                            
  class CreateRunRequest(StrictModel):                                                                                            
      user_idea: str = Field(...)                                                                                                 
      target_audience: str | None = None                                                                                          
      user_constraints: str | None = None                                                                                         
      quality_threshold: float = 85.0                                                                                             
      max_iterations: int = 3                                                                                                     
      model_key: str | None = Field(default=None, max_length=128)                                                                 

• model_key 为 可选。旧客户端不发送时，使用后端配置的默认模型（与当前行为一致）。
• 校验器验证 model_key 必须在当前可用列表中；否则 422。

RunSnapshot 保存选择

  # backend/schemas.py — PRDRunState 新增                                                                                         
  class PRDRunState(StrictModel):                                                                                                 
      # ... 现有字段 ...                                                                                                          
      provider_id: str | None = None                                                                                              
      model_id: str | None = None                                                                                                 

• 使用两个独立字段而非单个 model_key，避免前端解析 colon 分隔符，也便于 Telemetry 直接读取。
• 新增字段有默认值 None，Pydantic 反序列化旧 SQLite JSON 时自动填充，无需数据库 migration。

新增 Endpoint

  GET /api/providers                                                                                                              

响应：

  {                                                                                                                               
    "items": [                                                                                                                    
      {                                                                                                                           
        "model_key": "deepseek:deepseek-v4-flash",                                                                                
        "provider_id": "deepseek",                                                                                                
        "provider_name": "DeepSeek",                                                                                              
        "model_id": "deepseek-v4-flash",                                                                                          
        "model_name": "DeepSeek V4 Flash",                                                                                        
        "capabilities": ["streaming", "structured_output"],                                                                       
        "is_mock": false                                                                                                          
      },                                                                                                                          
      {                                                                                                                           
        "model_key": "mock:mock",                                                                                                 
        "provider_id": "mock",                                                                                                    
        "provider_name": "Mock LLM",                                                                                              
        "model_id": "mock",                                                                                                       
        "model_name": "确定性演示模型",                                                                                           
        "capabilities": ["streaming", "structured_output"],                                                                       
        "is_mock": true                                                                                                           
      }                                                                                                                           
    ]                                                                                                                             
  }                                                                                                                               

错误语义

┌────────────────────────────────────────────────────┬───────────┬─────────────────────────┐
│ 场景                                               │ HTTP 状态 │ Error Code              │
├────────────────────────────────────────────────────┼───────────┼─────────────────────────┤
│ model_key 不在可用列表                             │ 422       │ INVALID_MODEL_SELECTION │
├────────────────────────────────────────────────────┼───────────┼─────────────────────────┤
│ model_key 对应 Provider 配置不完整（如缺 API Key） │ 503       │ PROVIDER_UNAVAILABLE    │
├────────────────────────────────────────────────────┼───────────┼─────────────────────────┤
│ 旧 Run 无 provider_id（读取时）                    │ —         │ 前端降级显示"默认"      │
└────────────────────────────────────────────────────┴───────────┴─────────────────────────┘

向后兼容方案

• API 层面：CreateRunRequest.model_key 可选，旧请求 omission 时使用 Settings 中的默认 Provider（与当前 llm_provider 逻辑对齐）。
• SQLite 层面：旧快照缺少 provider_id/model_id → Pydantic 默认 None。前端读取到 None 时，Telemetry 根据 is_mock 显示"Mock"或"默认
模型"。
• Health Check：保留现有 HealthResponse 结构，可额外增加 default_model_key 字段，但不破坏旧字段。
• 契约层面：contracts/v1/ fixture 新增字段示例，同时保留旧字段的 fixture 用于兼容性测试。

────────────────────────────────────────────────────────────────────────────────

D. Provider 层设计

当前 Provider Factory / Config 工作方式

当前 create_app() 在启动时读取 Settings.llm_provider、deepseek_api_key、deepseek_base_url、deepseek_model 等，直接 new
OpenAICompatibleLLMProvider(...) 或 new MockLLMProvider()，产生一个全局实例。

改造成 Run 级选择

新建 backend/provider_factory.py：

  class ProviderFactory:                                                                                                          
      def __init__(self, settings: Settings) -> None:                                                                             
          self.settings = settings                                                                                                
          self._cache: dict[str, LLMProvider] = {}                                                                                
                                                                                                                                  
      def list_available(self) -> list[ModelOption]:                                                                              
          """从 Settings 推导可用模型，过滤掉配置不完整的。"""                                                                    
          options: list[ModelOption] = []                                                                                         
          if self.settings.enable_mock_llm:                                                                                       
              options.append(ModelOption(..., is_mock=True))                                                                      
          if self.settings.deepseek_api_key and self.settings.deepseek_api_key.get_secret_value():                                
              options.append(ModelOption(provider_id="deepseek", model_id=self.settings.deepseek_model, ...))                     
          # 同理 GLM ...                                                                                                          
          return options                                                                                                          
                                                                                                                                  
      def create_provider(self, model_key: str | None) -> LLMProvider:                                                            
          if model_key is None:                                                                                                   
              model_key = self._default_model_key()                                                                               
          option = next((o for o in self.list_available() if o.model_key == model_key), None)                                     
          if option is None:                                                                                                      
              raise InvalidModelError(f"Model {model_key} is not available")                                                      
          if option.is_mock:                                                                                                      
              return MockLLMProvider(...)                                                                                         
          # 按 provider_id 创建 OpenAICompatibleLLMProvider                                                                       
          if option.provider_id == "deepseek":                                                                                    
              return OpenAICompatibleLLMProvider(                                                                                 
                  provider_name="deepseek",                                                                                       
                  api_key=self.settings.deepseek_api_key.get_secret_value(),                                                      
                  base_url=self.settings.deepseek_base_url,                                                                       
                  model=option.model_id,                                                                                          
                  ...                                                                                                             
              )                                                                                                                   
          # ...                                                                                                                   

避免暴露 Key / Base URL

• list_available() 只返回 ModelOption，不含任何凭证。
• api_key 仅在 create_provider() 内部从 Settings 读取，且 Settings 只在后端进程内存在。
• 日志中只记录 provider_id / model_id，不记录 key。

Mock 处理

• ProviderFactory.list_available() 在 enable_mock_llm=true 时包含 Mock 选项。
• Mock 选项的 is_mock=true，前端据此显示"模拟数据"标签。
• MockLLMProvider 自身无状态，可被多个 Run 共享；工厂缓存中可复用同一实例。

────────────────────────────────────────────────────────────────────────────────

E. Persistence

SQLite 是否需要 migration

不需要。 SQLiteRunStore 将完整 RunSnapshot 作为 JSON 保存。PRDRunState 新增字段带有 Pydantic 默认值（None），旧数据反序列化时自动
填充。

老 Run 怎么读取

• SQLiteRunStore._load_snapshots() 使用 RunSnapshot.model_validate_json()。
• 旧 JSON 缺少 provider_id/model_id → 自动设为 None。
• 前端 TelemetryPanel 读取到 None 时：
• 若 is_mock=true → 显示"Mock"
• 否则 → 显示"默认模型"或不显示具体模型名。

新 Run 怎么保存 Provider / Model

• RunManager.create_run() 在创建 RunSnapshot 时：
python                                                                                                                       
       provider = self.provider_factory.create_provider(request.model_key)                                                           
       self._run_providers[run_id] = provider                                                                                        
       snapshot = RunSnapshot(                                                                                                       
           ...,                                                                                                                      
           provider_id=provider.provider_id,  # 需在基类新增属性                                                                     
           model_id=provider.model_id,                                                                                               
           is_mock=provider.is_mock,                                                                                                 
       )                                                                                                                             
     
• RunManager.commit() 的持久化逻辑不变，因为 RunSnapshot 已包含新字段。

────────────────────────────────────────────────────────────────────────────────

F. Frontend

创建 Run 界面修改

ProductIdeaForm.tsx 在"质量设置" <details> 内或主表单底部新增模型选择：

  // 新增状态                                                                                                                     
  const [selectedModelKey, setSelectedModelKey] = useState<string | null>(null);                                                  
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);                                                            
                                                                                                                                  
  // 在 handleSubmit 中                                                                                                           
  await onSubmit({                                                                                                                
    ...,                                                                                                                          
    model_key: selectedModelKey,                                                                                                  
  });                                                                                                                             

• 如果 modelOptions.length === 0 → 显示加载中或错误。
• 如果 modelOptions.length === 1 → 可自动选中并禁用选择（减少用户操作）。
• 如果 modelOptions.length > 1 → 显示下拉选择框。

Provider 与 Model 选择联动

当前后端每个 Provider 只配置一个 Model，第一阶段可以只做一级选择（直接选 model_key）。若未来一个 Provider 下有多个 Model，再扩展为
两级联动（先选 Provider，再选 Model）。

Loading / Empty / Error 状态

• Loading：调用 GET /api/providers 时显示骨架屏或 disabled select。
• Empty：如果后端返回空列表（理论上不应发生，至少应有 Mock），显示"暂无可用的模型服务"。
• Error：API 失败时显示错误提示，但不应阻塞用户提交（可回退到默认模型，或禁用提交按钮）。

Telemetry / Run 信息展示

TelemetryPanel.tsx 在"模拟数据"标签旁新增：

  {snapshot.provider_id && (                                                                                                      
    <span className="tag ml-2" data-testid="telemetry-provider">                                                                  
      {snapshot.provider_id}                                                                                                      
      {snapshot.model_id ? ` / ${snapshot.model_id}` : ""}                                                                        
    </span>                                                                                                                       
  )}                                                                                                                              

旧 Run（provider_id === null）保持现有显示不变。

────────────────────────────────────────────────────────────────────────────────

G. Testing

Backend pytest（新增/修改）

┌────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 测试文件                   │ 关键 Case                                                                                         │
├────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 新建                       │ 1. list_available 在 Mock 开启时包含 mock；2. 在 DeepSeek key 存在时包含 DeepSeek；3. 返回结果不  │
│ test_provider_factory.py   │ 含 key/url；4. create_provider 缓存行为；5. 非法 model_key 抛出 InvalidModelError。               │
├────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 修改 test_api.py           │ 1. test_create_run_with_model_key：指定合法 model_key 创建，快照包含对应 provider_id/model_id；2. │
│                            │ test_create_run_without_model_key：向后兼容，使用默认模型；3. test_create_run_invalid_model_key： │
│                            │ 返回 422；4. test_list_providers：返回安全元数据列表，无 key。                                    │
├────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 修改 test_workflow.py      │ 1. 验证 Workflow 节点通过 get_provider(run_id) 获取到正确 Provider；2. Mock Run 的 is_mock 正确传 │
│                            │ 递；3. 真实 Provider Run（若测试使用替身）Telemetry 正确。                                        │
├────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 修改 test_run_manager.py   │ 1. create_run 时 provider_id/model_id 写入快照；2. 旧快照（无新字段）读取不抛异常。               │
├────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 修改 test_contracts.py     │ 1. Pydantic Fixture 包含新字段通过；2. OpenAPI schema 包含 ModelOption。                          │
└────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────┘

Contract tests

• 更新 contracts/v1/create_run_request.json：增加带 model_key 的示例。
• 更新 contracts/v1/run_snapshot.json：增加 provider_id + model_id。
• 新增 contracts/v1/model_options.json：GET /api/providers 响应示例。
• 保留旧格式 fixture 用于向后兼容测试。

Vitest（新增/修改）

┌──────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────┐
│ 测试文件                                 │ 关键 Case                                                                           │
├──────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 修改 src/lib/api.test.ts                 │ listProviders 成功、失败、非法响应处理。                                            │
├──────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 修改 src/lib/contracts.test.ts           │ parseModelOption 校验通过/失败。                                                    │
├──────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 修改 src/components/components.test.tsx  │ ProductIdeaForm 在有多个模型选项时显示选择框、选择一个后提交包含 model_key、只有一  │
│                                          │ 个选项时自动选中。                                                                  │
├──────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
│ 修改 src/components/panels.test.tsx 或   │ TelemetryPanel 在有 provider_id 时展示、无时不展示。                                │
│ 新建                                     │                                                                                     │
└──────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────┘

Playwright E2E

┌────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 场景               │ 验证点                                                                                           │
├────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ happy-path.spec.ts │ 创建 Run 时表单包含模型选择（Mock 模式下至少有一项）；完成后 Telemetry 面板显示 Provider/Model。 │
├────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ layout.spec.ts     │ 模型选择框在不同屏幕尺寸下正常渲染。                                                             │
├────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ failures.spec.ts   │ 若 E2E 有故障注入能力，可测试非法 model_key 时前端收到明确错误。                                 │
└────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────┘

Static / type checks

• npm run typecheck（TypeScript strict）
• ./.venv/bin/mypy backend（Python strict）
• ./.venv/bin/ruff check backend
• npm run lint

────────────────────────────────────────────────────────────────────────────────

H. 风险

Workflow 中 Provider 访问模式变更
workflow.py 中 5 处 self.manager.provider 需要改为 self.manager.get_provider(run_id)。如果遗漏一处，会导致该节点使用错误
Provider（甚至可能是未初始化的全局 Provider）。这是本需求最容易破坏现有系统的地方。

RunManager 并发与 Provider 生命周期
RunManager 原本持有一个无状态单例。改为 per-run Provider 字典后，需要在 cleanup_expired / _release_run_resources 中及时清理，避
免内存泄漏。asyncio.Lock 顺序不能变。

Mock 模式的确定性测试
现有 pytest 和 E2E 大量依赖 Mock 的确定性输出。如果 ProviderFactory 在测试中的默认行为改变（例如默认不再选 Mock），会导致大量测
试失败。make_manager() 必须显式注入 ProviderFactory 并确保默认选中 Mock。

旧 SQLite 数据兼容性
虽然 Pydantic 默认值可以处理缺失字段，但如果错误地使用了 extra="forbid" 的基类来反序列化包含未知旧字段的数据，或在某个中间层手
动 json.loads 后 strict 校验，可能引发兼容性问题。需要确保 RunSnapshot.model_validate_json() 路径覆盖旧数据。

契约断裂
CreateRunRequest 新增可选字段不会破坏旧请求，但 StrictModel 意味着如果前端发送了后端不认识的字段会 422。因此新增字段必须在前后
端同步。contracts/v1/ 的 fixture 必须更新，否则契约测试会失败。

Health Check 语义混淆
原来 HealthResponse.provider 表示应用默认 Provider。引入 per-run 选择后，Health Check 不应被误解为"所有 Run 都用这个 Provider"
。应在文档和响应中明确这是"默认/当前可用"状态。

────────────────────────────────────────────────────────────────────────────────

I. 实施计划

推荐以小步、可验证的方式拆分，每步完成后可独立跑通门禁：

Step 1: Provider Factory 与注册表（后端 only）

• 新建 backend/provider_factory.py，包含 ModelOption、ProviderFactory。
• ProviderFactory 从 Settings 推导可用列表，暴露 list_available() 和 create_provider()。
• 编写 test_provider_factory.py 覆盖可用列表、安全过滤、Mock 行为、错误 case。
• 验证：pytest backend/tests/test_provider_factory.py -v 通过。

Step 2: 暴露 GET /api/providers

• backend/schemas.py 新增 ModelOption、ProviderListResponse。
• backend/main.py 新增 GET /api/providers 路由，调用 ProviderFactory.list_available()。
• 编写 API 测试验证响应中无 key/url。
• 验证：pytest backend/tests/test_api.py::test_list_providers -v 通过；mypy / ruff 通过。

Step 3: 数据模型扩展（向后兼容）

• backend/schemas.py：CreateRunRequest 加 model_key: str | None；PRDRunState/RunSnapshot 加 provider_id + model_id。
• 更新 contracts/v1/ fixture（保留旧格式 fixture 用于兼容测试）。
• 编写测试验证旧快照 JSON 反序列化不抛异常。
• 验证：pytest backend/tests/test_schemas.py backend/tests/test_contracts.py -v 通过。

Step 4: RunManager 支持 per-run Provider

• RunManager.init 接收 provider_factory: ProviderFactory 替代 provider: LLMProvider。
• 新增 get_provider(run_id: UUID) -> LLMProvider；内部用 dict[UUID, LLMProvider] 缓存。
• create_run() 根据 request.model_key 创建 Provider 并写入快照；处理 model_key 无效时明确失败。
• cleanup_expired / _release_run_resources 清理 per-run Provider 引用。
• 更新 backend/tests/helpers.py 的工厂函数。
• 验证：pytest backend/tests/test_run_manager.py backend/tests/test_api.py -v 通过。

Step 5: Workflow 适配 per-run Provider

• backend/workflow.py：所有 self.manager.provider 改为 self.manager.get_provider(run_id)。
• run_started 事件的 config payload 中追加 provider_id 和 model_id。
• 更新 test_workflow.py 验证 Workflow 能正确获取 Provider。
• 验证：pytest backend/tests/test_workflow.py -v 通过。

Step 6: 前端类型与 API Client

• src/lib/types.ts：新增 ModelOption、ProviderListResponse；扩展 CreateRunRequest、RunSnapshot。
• src/lib/api.ts：新增 listProviders()。
• src/lib/contracts.ts：新增解析器。
• 编写 Vitest 测试。
• 验证：npm run test 通过。

Step 7: 前端 UI 修改

• ProductIdeaForm.tsx：在表单中增加模型选择（从 props 接收 options）。
• AgentDashboard.tsx / useAgentRun.ts：加载时获取模型列表，传入表单；createRun 携带 model_key。
• TelemetryPanel.tsx：展示 provider_id / model_id。
• 编写组件测试。
• 验证：npm run test + npm run typecheck 通过。

Step 8: E2E 与契约验收

• 更新 e2e/helpers.ts 和 happy-path spec，验证创建流程和 Telemetry 展示。
• 全量跑 E2E：npm run test。
• 全量后端测试：pytest -p no。
• 验证：Playwright 18 项全部通过。

Step 9: 文档与进度更新

• 更新 memory-bank/progress.md 记录新增能力。
• 如有必要，更新 README.md 中 Provider 配置章节（说明 Run 级选择）。
• 验证：人工 review。

────────────────────────────────────────────────────────────────────────────────

FINAL PLAN

新建 backend/provider_factory.py：实现 ProviderFactory，从 Settings 安全推导可用模型列表（list_available），按 model_key 创建对
应 LLMProvider 实例（create_provider），结果绝不暴露 key/url。

扩展 backend/schemas.py：CreateRunRequest 新增可选 model_key；PRDRunState/RunSnapshot 新增 provider_id + model_id（默认 None，
保证旧 JSON 兼容）。

新增 GET /api/providers：返回 list[ModelOption] 安全元数据，供前端渲染选择框。

改造 RunManager：init 接收 ProviderFactory；create_run() 按请求创建 per-run Provider 并缓存到 dict[UUID,
LLMProvider]；get_provider(run_id) 取代原来的 .provider 属性。

改造 Workflow：所有节点将 self.manager.provider 改为 self.manager.get_provider(run_id)，确保每个 Run 使用自己的模型。

更新测试工厂与 helpers：make_manager() 改为注入 ProviderFactory；补充 test_provider_factory.py 和 API/Workflow 的 per-run 测试
。

前端类型扩展：src/lib/types.ts 新增 ModelOption 等；src/lib/api.ts 新增 listProviders()。

前端 UI 修改：ProductIdeaForm 增加模型选择；useAgentRun 加载可用列表；TelemetryPanel 展示当前 Run 的 Provider/Model。

更新契约 fixture：contracts/v1/ 补充含新字段的示例，保留旧格式用于兼容性验证。

全量门禁验证：pytest → npm run test → npm run typecheck → npm run build → npm run test → ruff / mypy，全部通过后更新
memory-bank/progress.md。