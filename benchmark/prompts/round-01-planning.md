你现在位于 Agentic-PRD-Architect 仓库中。

这是一次 AI Coding benchmark 的第一阶段。

本阶段只做：
- 仓库理解
- 架构分析
- 实施方案设计

不要修改任何文件。
不要创建 commit。
不要安装或升级依赖。
不要执行会改变仓库状态的命令。

可以读取文件、搜索代码，并执行只读命令来理解项目。

首先阅读并遵守：
- AGENTS.md
- PRD.md
- README.md
- memory-bank/architecture.md
- memory-bank/design-document.md
- memory-bank/tech-stack.md
- memory-bank/progress.md

然后根据需要继续检查真实代码，不要只根据文档猜测。

---

## 需求

为 Agentic PRD Architect 设计：

“Run 级 Provider / Model Selection”

当前应用的模型 Provider / Model 主要通过后端环境配置决定。

目标是允许用户在创建一个新 Run 时，从后端允许的 Provider / Model 列表中选择本次 Run 使用的模型。

例如：

Provider:
DeepSeek

Model:
deepseek-xxx

另一个 Run 可以选择其他允许的 Provider / Model。

---

## 核心要求

1. Provider 和 Model 的可选项必须由后端配置和控制。

2. API Key、Token、内部 Base URL 等敏感信息绝不能发送到前端。

3. 前端只能获得安全的 Provider / Model 元数据，例如：
   - provider id
   - provider display name
   - model id
   - model display name
   - 可安全公开的能力信息

4. 创建 Run 时可以指定 Provider / Model。

5. 本次选择必须作为 Run 的一部分持久化，刷新页面或服务重启后仍能知道该 Run 使用的模型。

6. Telemetry / Run 信息中应能够看到本次 Run 使用的 Provider / Model，但不能泄漏任何凭据。

7. 现有 Mock 模式必须继续正常工作。

8. 必须考虑旧 API / 旧 SQLite 数据的向后兼容。

9. 不允许 silent fallback：
   如果指定 Provider / Model 不存在或不可用，应明确失败，而不是自动换模型。

10. 不得破坏现有核心架构约束，包括：
   - Generator → 三个独立 Reviewer → Aggregator → Optimizer
   - Reviewer 独立并行
   - Aggregator 确定性计算
   - 质量门逻辑
   - REST 控制 + SSE 实时事件
   - Pause / Resume / Cancel
   - SQLite 事实来源
   - Mock 确定性测试
   - 密钥只存在后端

11. 不要为了实现该需求重构无关模块。

12. 必须遵守仓库已有的契约、测试和文档维护规则。

---

## 请输出

### A. 当前架构理解
只描述与这个需求相关的现有实现，并指出对应真实文件/模块。

### B. 影响范围
列出预计需要修改的文件，并解释每个文件为什么需要修改。

### C. 数据模型与 API 设计
说明：
- Provider / Model 元数据怎么定义
- 创建 Run API 怎么变化
- RunSnapshot 怎么保存选择
- 是否需要新增 endpoint
- 错误语义
- 向后兼容方案

### D. Provider 层设计
说明：
- 当前 Provider factory / config 如何工作
- 如何改造成 Run 级选择
- 如何避免把 Key 或 Base URL 暴露给前端
- Mock 应如何处理

### E. Persistence
说明：
- SQLite 是否需要 migration
- 老 Run 怎么读取
- 新 Run 怎么保存 Provider / Model

### F. Frontend
说明：
- 创建 Run 界面怎么改
- Provider 与 Model 选择如何联动
- Loading / Empty / Error 状态
- Telemetry / Run 信息如何展示

### G. Testing
明确列出需要新增或修改的：
- Backend pytest
- Contract tests
- Vitest
- Playwright E2E
- Static/type checks

必须包含关键测试 case。

### H. 风险
指出这个需求最容易破坏现有系统的地方。

### I. 实施计划
给出推荐的开发顺序，以小步、可验证的方式拆分。

---

最后单独给出：

## FINAL PLAN

用简洁的编号步骤总结你最终推荐的实现方案。

不要开始编码。
