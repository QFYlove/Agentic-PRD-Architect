# Agentic PRD Architect

[English](../README.md) | **简体中文**

Agentic PRD Architect 是给产品经理用的工作台。从一个模糊的想法开始，AI 一轮轮追问、整理需求，检查需求问题，整理成由你确认的 Product Brief，再逐章写 PRD，从四个角度独立审查，最后只按你采纳的意见修改。产出是一份带版本记录的 Markdown PRD。

每一步都由你触发。AI 任务执行一次就停下，AI 推断出的内容在你确认之前都不算数。

## 工作流程

每个项目只有两个空间：**需求**和**文档**。

1. **创建项目**：从想法开始、从已有需求开始（会议纪要、初步方案），或粘贴已有 PRD 直接审查。粘贴的 PRD 会按标题切成章节，直接进入第 7 步。
2. **需求探索**：Requirement Explorer 每轮读取你的回答，更新需求基线，再提出 1～3 个问题，并说明为什么要问。可以回答、跳过或选"暂时不确定"，后两种记为待确认事项。提问深度分"简要"（每轮 2 问）和"详细"（3 问）。
3. **需求基线**：12 个分组：产品定位、产品目标、目标用户、用户问题、使用场景、现有方案、解决方案、功能需求、业务约束、假设、产品决策、待确认事项。每条记录保留来源、状态、优先级和修改记录。AI 只能把条目标为推断、建议、假设或待确认，确认和否定只能由你操作。
4. **检查需求**：Product Analyst 检查信息缺口、逻辑冲突、场景遗漏、产品风险和产品机会，每条发现都要引用具体的需求条目。采纳的发现会在下一轮变成追问。
5. **Product Brief**：由代码根据需求基线整理，可以编辑，整体确认一次；确认后冻结为一个版本。"检查 Brief"会对这份快照运行 Product Analyst。
6. **大纲和正文**：Generator 按当前产品生成大纲，不套固定模板。你可以增删章节、改标题、调整顺序，确认后逐章流式生成；某一章失败可以单独重试。
7. **四维审查**：全部章节完成后，产品、体验、技术、商业四个 Reviewer 并行、独立审查。意见在正文中以荧光笔痕标出，可以采纳、修改后采纳、暂缓或拒绝。
8. **定向优化**：Optimizer 只针对已采纳的意见提出修改提案。你勾选要应用的修改，应用后生成新版本。你写过的章节，不经你勾选不会被改。
9. **编辑与复查**：保存章节时按规则判断影响范围，相关意见标为"需重新确认"，依赖它的章节标为待复查，只需复查这些章节。只改格式不会触发。
10. **版本、质量、导出**：版本只追加不覆盖，支持章节级对比；四项质量指标；导出 Markdown 时去掉内部标记和需求编号。

第 4～10 步可以按需反复进行，不必严格按顺序。

## 打分标准

Reviewer 不给总分。每个 Reviewer 给自己的 4 个维度各打 1～5 分并写理由，后端按 `分数 = Σ(维度分 ÷ 5 × 权重) × 100` 计算。缺一个维度就显示"未评分"，不替模型补分。四个分数分开显示，不做平均。

| Reviewer | 维度（权重） |
|---|---|
| 产品 | 问题定义与用户匹配 30% · 产品方案合理性 25% · 需求完整性与逻辑一致性 25% · MVP 范围与优先级 20% |
| 体验 | 用户需求与场景匹配 25% · 核心任务流程 30% · 交互清晰度 25% · 状态反馈及异常恢复 20% |
| 技术 | 技术可行性 30% · 架构、接口与数据完整性 25% · 可靠性及异常处理 25% · 安全性与实现约束 20% |
| 商业 | 用户价值 30% · 产品定位与差异化 25% · MVP 范围及优先级 20% · 商业模式与成本可持续性 25% |

意见分"必须修改 / 建议修改 / 可选"三级。没有证据的意见直接丢弃；引用在正文中找不到的会被标出，且不能定为必须修改；"需要补充数字"类意见最高只能是建议修改。

质量面板有四项独立指标：文档质量、需求成熟度、实施就绪度、未解决风险与阻塞，全部由规则计算；没有可衡量的数据时不显示数字。

## 架构

- **前端**：Astro 4 + React 18（`src/v3/`）。`/` 是 V3 工作台，`/runs` 是 V2 仪表盘，作为只读历史保留。
- **后端**：FastAPI。V3 在 `backend/v3/`，接口前缀 `/api/v3`；V2 的运行流程（`/api/runs`、LangGraph 循环）保持不变。
- **模型调用**：五类，分别是 Explorer、Analyst、Generator（大纲和单章）、四个 Reviewer、Optimizer。每次调用是一个 Job，事件持久化，支持 SSE 断线续传。重试规则与 V2 共用：临时故障重试一次，输出被截断不重试。
- **存储**：SQLite（`data/agentic-prd.sqlite3`）。V3 使用独立的 `v3_*` 表和编号迁移，第一次迁移前会把数据库文件备份到 `data/backups/`。
- **规则写在代码里，不靠 Prompt**：AI 输出的状态限制、用户原话逐字核对、意见证据校验、跨角色去重和与已有意见匹配、章节乐观锁、影响分析、评分和质量指标。

详细说明见 [product-definition.md](product-definition.md)、[v3-planning/](v3-planning/)、[product-audit/architecture-map.md](product-audit/architecture-map.md)。

## 安装

- Node.js 24.15.0 和 npm 11.12.1
- Python 3.13

```bash
npm ci
python3 -m venv .venv
./.venv/bin/python -m pip install -r backend/requirements-dev.txt
cp .env.example .env
npm run playwright:install
```

`.env` 已被 Git 忽略，请勿提交任何 API 密钥。

## Provider 配置

默认启用模拟模型，无需任何凭据。它的回复是固定规则生成的，只用于开发和测试；启用时顶栏会显示"模拟模型"。

```env
ENABLE_MOCK_LLM=true
LLM_PROVIDER=deepseek
LLM_MAX_OUTPUT_TOKENS=16000
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# LLM_PROVIDER=glm
# GLM_API_KEY=
# GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
# GLM_MODEL=glm-5.2
```

使用真实模型时，设置 `ENABLE_MOCK_LLM=false` 并填写所选 Provider 的密钥。启动时会校验配置，不会静默回退到模拟模型。需要费用估算时，再配置 `MODEL_INPUT_PRICE_PER_MILLION` 和 `MODEL_OUTPUT_PRICE_PER_MILLION`。

## 本地运行

```bash
./.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
npm run dev
```

访问 `http://127.0.0.1:4321`，健康检查地址为 `http://127.0.0.1:8000/api/health`。Uvicorn 必须单 Worker 运行，因为运行中的任务和 SSE 订阅都在进程内。

## 测试

```bash
npm run lint && npm run typecheck
npm run test:run
npm run test:e2e
./.venv/bin/ruff format --check backend && ./.venv/bin/ruff check backend
./.venv/bin/mypy backend
./.venv/bin/python -m pytest -p no:cacheprovider
```

自动化测试全部使用模拟模型。端到端测试使用独立的 4331/8011 端口和内存数据库。真实模型冒烟测试需要经批准的密钥和预算，手动执行。

## 当前限制

- Prompt 只在模拟模型下验证过。
- 单 Worker、本地 SQLite、无外部队列。后端重启时未完成的任务标为 `JOB_INTERRUPTED`，不会自动续跑。
- 每个项目同一时间只能运行一个 AI 任务。
- 删除项目是软删除，没有自动清理。
- V2 的旧运行不能转为 V3 项目。
- 只支持 Markdown 导出，不支持 PDF / DOCX 的导入或导出。
- 锁定的 Astro 4 / Mermaid 10 依赖存在已知上游告警，当前版本只适合本地使用。

## 常见问题

- 端口被占用：释放 4321/8000；端到端测试还需要 4331/8011。
- 前端无法访问 API：检查两个服务、`/api/health`、`PUBLIC_API_BASE_URL` 和 `FRONTEND_ORIGINS`。
- 提示"这个项目正在执行一个 AI 任务"：等当前任务完成，每个项目一次只能运行一个任务。
- 某个章节生成失败：其他章节已保存，在文档页单独重试这一章即可。
