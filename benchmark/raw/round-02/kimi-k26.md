Continuing with the E2E test fixes. Let me first read the files I need to modify.                                                 
 
 ● The contract parser is permissive - it validates required fields but returns the whole object as the typed interface. Since       
   `CreateRunRequest` and `RunSnapshot` types already include the optional provider/model fields, the parser doesn't need changes.   
   … (15 more lines, ctrl+o to expand)
 
 ● Used Edit (contracts/v1/create_run_request.json) · +3 -1                                                                          
   +3 -1 contracts/v1/create_run_request.json                                                                                        
      3     "target_audience": "Podcast listeners and independent creators",                                                         
      4     "user_constraints": "Focus on a mobile-first MVP",                                                                       
      5     "quality_threshold": 85,                                                                                                 
      6 -   "max_iterations": 3                                                                                                      
      6 +   "max_iterations": 3,                                                                                                     
      7 +   "provider_id": "mock",                                                                                                   
      8 +   "model_id": "mock-default"                                                                                               
      9   }                                                                                                                          
 
 ● Now update the run_snapshot and terminal_snapshots.                                                                               
 
 ● Used Edit (contracts/v1/run_snapshot.json) · +5 -1                                                                                
   +5 -1 contracts/v1/run_snapshot.json                                                                                              
      1     "error": null,                                                                                                           
      2 -   "latest_event_sequence": 0                                                                                               
      2 +   "latest_event_sequence": 0,                                                                                              
      3 +   "provider_id": null,                                                                                                     
      4 +   "provider_display_name": null,                                                                                           
      5 +   "model_id": null,                                                                                                        
      6 +   "model_display_name": null                                                                                               
      7   }                                                                                                                          
 
 ● Now update terminal_snapshots.json. I'll add nullable fields to the existing ones, and add non-null fields to the COMPLETED one to
   represent a new Run with persisted selection.                                                                                     
 
 ● Used Edit (contracts/v1/terminal_snapshots.json) · +5 -1                                                                          
   +5 -1 contracts/v1/terminal_snapshots.json                                                                                        
     17       "created_at": "2026-07-26T10:00:00Z",                                                                                  
     18       "updated_at": "2026-07-26T10:05:00Z",                                                                                  
     19       "completed_at": "2026-07-26T10:05:00Z",                                                                                
     20 -     "latest_event_sequence": 20                                                                                            
     20 +     "latest_event_sequence": 20,                                                                                           
     21 +     "provider_id": "mock",                                                                                                 
     22 +     "provider_display_name": "Mock Provider",                                                                              
     23 +     "model_id": "mock-default",                                                                                            
     24 +     "model_display_name": "Mock PRD Model"                                                                                 
     25     },                                                                                                                       
 
 ● Now I need to add nullable provider/model fields to the remaining terminal snapshots to represent old Runs without selection      
   metadata.                                                                                                                         
 
 ● Used Edit (contracts/v1/terminal_snapshots.json) · +15 -3                                                                         
   +15 -3 contracts/v1/terminal_snapshots.json                                                                                       
     19       "created_at": "2026-07-26T10:00:00Z",                                                                                  
     20       "updated_at": "2026-07-26T10:10:00Z",                                                                                  
     21       "completed_at": "2026-07-26T10:10:00Z",                                                                                
     22 -     "latest_event_sequence": 30                                                                                            
     22 +     "latest_event_sequence": 30,                                                                                           
     23 +     "provider_id": null,                                                                                                   
     24 +     "provider_display_name": null,                                                                                         
     25 +     "model_id": null,                                                                                                      
     26 +     "model_display_name": null                                                                                             
     27     },                                                                                                                       
        … 12 more changes hidden (ctrl+o to expand)                                                                                  
 
 ● Now let me add a contract test for the new fields to `contracts.test.ts`.                                                         
 
 ● Used Edit (src/lib/contracts.test.ts) · +12 -2                                                                                    
   +12 -2 src/lib/contracts.test.ts                                                                                                  
      1     it("parses the backend-validated examples", () => {                                                                      
      2 -     expect(parseCreateRunRequest(createRunRequest).max_iterations).toBe(3);                                                
      3 -     expect(parseRunSnapshot(runSnapshot).status).toBe("QUEUED");                                                           
      2 +     const request = parseCreateRunRequest(createRunRequest);                                                               
      3 +     expect(request.max_iterations).toBe(3);                                                                                
      4 +     expect(request.provider_id).toBe("mock");                                                                              
      5 +     expect(request.model_id).toBe("mock-default");                                                                         
      6 +                                                                                                                            
      7 +     const snapshot = parseRunSnapshot(runSnapshot);                                                                        
      8 +     expect(snapshot.status).toBe("QUEUED");                                                                                
        … 5 more changes hidden (ctrl+o to expand)                                                                                   
 
 ● Let me also add a test for the terminal snapshot with non-null provider/model fields.                                             
 
 ● Used Edit (src/lib/contracts.test.ts) · +11                                                                                       
   +11 src/lib/contracts.test.ts                                                                                                     
      5                                                                                                                              
      6       expect(new Set(parsedStatuses)).toEqual(TERMINAL_RUN_STATUSES);                                                        
      7       expect(isTerminalRunStatus("GENERATING")).toBe(false);                                                                 
      8 +   });                                                                                                                      
      9 +                                                                                                                            
     10 +   it("parses persisted provider/model metadata on new runs", () => {                                                       
     11 +     const completed = terminalSnapshots.find(                                                                              
     12 +       (snapshot) => snapshot.status === "COMPLETED",                                                                       
     13 +     )!;                                                                                                                    
     14 +     const parsed = parseRunSnapshot(completed);                                                                            
        … 4 more changes hidden (ctrl+o to expand)                                                                                   
 
 ● Now let me run the vitest, typecheck, and lint to make sure everything passes after these changes.                                
 
 ● Ran a command                                                                                                                     
   $ npm run test:run 2>&1 | tail -20                                                                                                
    ✓ src/lib/helpers.test.ts (6 tests) 31ms                                                                                         
    ✓ src/lib/contracts.test.ts (7 tests) 5ms                                                                                        
    ✓ src/components/AgentDashboard.test.tsx (18 tests) 7029ms                                                                       
   … (16 more lines, ctrl+o to expand)
 
 ● Ran a command                                                                                                                     
   $ npm run typecheck 2>&1 | tail -10                                                                                               
   > cross-env ASTRO_TELEMETRY_DISABLED=1 astro check                                                                                
                                                                                                                                     
   19:46:02 [vite] Re-optimizing dependencies because vite config has changed                                                        
   … (6 more lines, ctrl+o to expand)
 
 ● Ran a command                                                                                                                     
   $ npm run lint 2>&1 | tail -10                                                                                                    
                                                                                                                                     
   > agentic-prd-architect@0.1.0 lint                                                                                                
   > eslint . --ext .astro,.ts,.tsx --max-warnings 0                                                                                 
 
 ● All frontend tests and checks pass. Now let me also run the backend tests one more time to make sure the contract JSON changes    
   don't break anything on the backend side.                                                                                         
 
 ● Ran a command                                                                                                                     
   $ ./.venv/bin/python -m pytest backend/tests -p no:cacheprovider -q 2>&1 | tail -10                                               
   ........................................................................ [ 24%]                                                   
   ........................................................................ [ 48%]                                                   
   ........................................................................ [ 72%]                                                   
   … (3 more lines, ctrl+o to expand)
 
 ● All tests are passing. Let me do one final check of the full E2E suite to make sure everything is still good after all the        
   changes.                                                                                                                          
 
 ● Ran a command                                                                                                                     
   $ npx playwright test --project=chromium 2>&1 | tail -30                                                                          
             |                                                ^                                                                      
         138 | }                                                                                                                     
         139 |                                                                                                                       
   … (27 more lines, ctrl+o to expand)
 
 ● The `recovery.spec.ts` test failed this time, but it passed in the previous full run. This is clearly a flaky test unrelated to my
   changes - it's a timing issue with SSE connection recovery. The spec explicitly says "Mock 和 Scenario Mock 保持确定性" and my    
   … (3 more lines, ctrl+o to expand)
 
 ● Ran a command                                                                                                                     
   $ npx playwright test e2e/recovery.spec.ts --project=chromium --repeat-each=3 2>&1 | tail -20                                     
   (node:47864) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.                                       
   (Use `node --trace-warnings ...` to show where the warning was created)                                                           
   (node:47864) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.                                       
   … (17 more lines, ctrl+o to expand)
 
 ● The recovery test is indeed flaky - it passed all 3 repetitions when run alone. The failure in the full suite was a timing issue  
   unrelated to my changes.                                                                                                          
   … (4 more lines, ctrl+o to expand)
 
 ● Used TodoList                                                                                                                     
 
 ● The user hasn't sent a new message - this is just a system reminder. I need to continue and produce the final report. Let me do   
   one final comprehensive check to make sure everything is in order, then write the final Chinese report.                           
   … (2 more lines, ctrl+o to expand)
 
 ● Ran a command                                                                                                                     
   $ ./.venv/bin/ruff format --check backend && ./.venv/bin/ruff check backend && ./.venv/bin/mypy backend && ./.venv/bin/python -m  
   pytest backend/tests -p no:cacheprovider -q 2>&1 | tail -5                                                                        
   44 files already formatted                                                                                                        
   All checks passed!                                                                                                                
   Success: no issues found in 21 source files                                                                                       
   … (5 more lines, ctrl+o to expand)
 
 ● Ran a command                                                                                                                     
   $ npm run typecheck && npm run lint && npm run test:run 2>&1 | tail -15                                                           
                                                                                                                                     
   > agentic-prd-architect@0.1.0 typecheck                                                                                           
   > cross-env ASTRO_TELEMETRY_DISABLED=1 astro check                                                                                
   … (27 more lines, ctrl+o to expand)
 
 ● Everything is passing. Let me also run the E2E suite one more time and get a clean result to include in the report.               
 
 ● Ran a command                                                                                                                     
   $ npx playwright test --project=chromium 2>&1 | grep -E '(passed|failed|✓|✗)' | tail -30                                          
     ✓  1 [chromium] › controls.spec.ts:15:1 › pause at review safe point and resume with user requirement (10.2s)                   
     ✓  2 [chromium] › controls.spec.ts:58:3 › cancel during generation rejects late results (1.6s)                                  
     ✓  3 [chromium] › controls.spec.ts:58:3 › cancel during review rejects late results (1.9s)                                      
   … (23 more lines, ctrl+o to expand)
 
 ● All 23 E2E tests passed this time. Now I have everything I need to write the final report in Chinese. Let me summarize:           
                                                                                                                                     
   … (66 more lines, ctrl+o to expand)
 
 ● 所有实现已完成，测试与静态检查全部通过。以下是最终报告。                                                                          
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   实现摘要                                                                                                                          
                                                                                                                                     
   本次 Round 2 在 Agentic-PRD-Architect 中完整实现了 Run 级 Provider / Model 选择 功能，主要改动如下：                              
                                                                                                                                     
   后端                                                                                                                              
                                                                                                                                     
   • 新增 backend/catalog.py：ProviderRegistry 负责从后端配置生成安全 catalog，支持解析、验证、实例化 run-scoped provider，并管理    
     per-model pricing。                                                                                                             
   • 扩展 Create Run API：CreateRunRequest 新增 provider_id + model_id 字段。显式选择时做严格校验（存在性、跨 Provider 匹配、可用性  
     ）；两字段均缺失时走 legacy 兼容路径，解析默认组合并持久化。                                                                    
   • Run 级绑定与隔离：RunManager 在 create_run() 时一次性解析并绑定 selection；工作流通过 manager.provider_for(run_id) 获取该 Run 的
     专属 provider，支持并发 Run 使用不同组合。                                                                                      
   • 新增 GET /api/providers：只读 catalog，绝不返回 credential、private Base URL 或真实 pricing。                                   
   • 持久化：Run snapshot 新增 provider_id、provider_display_name、model_id、model_display_name 四个 nullable 字段，无需 SQL DDL     
     migration，旧数据反序列化为 null。                                                                                              
   • 定价语义：各 provider 实现支持 has_pricing；缺少 pricing 时 cost 为 null，不 fallback。                                         
                                                                                                                                     
   前端                                                                                                                              
                                                                                                                                     
   • 新增 ProviderModelSelector 组件：加载 catalog，展示 Provider / Model 两级选择，Provider 切换时自动重置无效 Model。              
   • 集成到 ProductIdeaForm：未选择有效组合时禁用创建；同时提交 provider_id + model_id。                                             
   • AgentDashboard：首次加载时请求 catalog。                                                                                        
   • TelemetryPanel：展示 Run 持久化的 Provider / Model display names；旧 Run 缺失时安全渲染，不伪造信息。                           
   • Catalog 状态：完整处理 loading / empty / error / loaded 四种状态，error 时允许重试。                                            
                                                                                                                                     
   测试                                                                                                                              
                                                                                                                                     
   • 新增 backend/tests/test_provider_catalog.py（24 个测试）：覆盖 safe catalog、字段隔离、显式选择创建、legacy 兼容、旧 snapshot 加
     载、并发隔离、不可用 selection 失败、per-model pricing 等。                                                                     
   • 新增 Vitest：ProviderModelSelector.test.tsx（6 个）覆盖状态机与交互；TelemetryPanel.test.tsx（2 个）覆盖展示与缺失安全渲染。    
   • 新增 Playwright E2E：e2e/provider-selection.spec.ts（5 个）覆盖端到端选择、持久化观察、并发隔离、legacy 兼容、empty/failed      
     catalog 阻止创建。                                                                                                              
   • Contract fixtures：更新 contracts/v1/create_run_request.json、run_snapshot.json、terminal_snapshots.json，新增 contract 测试验证
     nullable / non-null 的 provider/model 元数据。                                                                                  
   • 修复 playwright.config.ts：将 Windows 路径改为 Unix 路径，使 E2E 可在 macOS 运行。                                              
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   实际运行过的测试/检查结果                                                                                                         
                                                                                                                                     
   ┌──────────────────┬────────────────────────────────────────────────────────────────┬────────────┐                                
   │ 检查项           │ 命令                                                           │ 结果       │                                
   ├──────────────────┼────────────────────────────────────────────────────────────────┼────────────┤                                
   │ 后端 pytest      │ ./.venv/bin/python -m pytest backend/tests -p no:cacheprovider │ 300 passed │                                
   ├──────────────────┼────────────────────────────────────────────────────────────────┼────────────┤                                
   │ 后端 ruff format │ ./.venv/bin/ruff format --check backend                        │ passed     │                                
   ├──────────────────┼────────────────────────────────────────────────────────────────┼────────────┤                                
   │ 后端 ruff lint   │ ./.venv/bin/ruff check backend                                 │ passed     │                                
   ├──────────────────┼────────────────────────────────────────────────────────────────┼────────────┤                                
   │ 后端 mypy        │ ./.venv/bin/mypy backend                                       │ passed     │                                
   ├──────────────────┼────────────────────────────────────────────────────────────────┼────────────┤                                
   │ 前端 Vitest      │ npm run test:run                                               │ 193 passed │                                
   ├──────────────────┼────────────────────────────────────────────────────────────────┼────────────┤                                
   │ 前端 typecheck   │ npm run typecheck                                              │ 0 errors   │                                
   ├──────────────────┼────────────────────────────────────────────────────────────────┼────────────┤                                
   │ 前端 lint        │ npm run lint                                                   │ 0 errors   │                                
   ├──────────────────┼────────────────────────────────────────────────────────────────┼────────────┤                                
   │ Playwright E2E   │ npx playwright test --project=chromium                         │ 23 passed  │                                
   └──────────────────┴────────────────────────────────────────────────────────────────┴────────────┘                                
                                                                                                                                     
   ────────────────────────────────────────────────────────────────────────────────                                                  
                                                                                                                                     
   仍未解决的限制                                                                                                                    
                                                                                                                                     
   • e2e/recovery.spec.ts 中的 SSE 恢复测试在完整套件顺序执行时偶发超时（与 Provider/Model 选择无关的既有 flaky timing）。单独运行该 
     文件时连续 3 次均通过。本次实现未引入回归。            