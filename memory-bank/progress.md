# Agentic PRD Architect 实施进度

> 最近更新：2026-08-21
>
> 当前状态：本地 Showcase 功能完整，全量自动化门禁通过；真实 Provider 冒烟仍为
> 需要凭据的手动发布检查

## 已具备的能力

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Agentic Loop | 完成 | Generator → Tech/UX/Biz 并行 Reviewer → 确定性 Aggregator → Optimizer → Generator |
| 确定性总分 | 完成 | 总分只由后端等权计算，模型自报的总分一律不采用 |
| 质量门 | 完成 | `overall_score >= quality_threshold` 且 `must_fix_count == 0` 两个条件同时成立才 `COMPLETED` |
| 迭代预算终态 | 完成 | 预算用尽以 `MAX_ITERATIONS_REACHED` 收尾，属正常终态，终态面板同时给出未达成目标与最佳版本 |
| 反馈 severity | 完成 | `must_fix` / `should_fix` / `optional`；计数按需从存储反馈推导，不作为总数持久化 |
| Revision Plan | 完成 | Optimizer 输出结构化修订计划，下一轮 Generator 逐条处理 |
| 多版本与最佳版本 | 完成 | 每版独立保存正文、评审、修订计划与 Token；`best_version` / `best_score` 跟踪最高分而非最新版 |
| 版本对比 | 完成 | 「阅读对比」与「源码」两种视图 |
| GFM 渲染 | 完成 | `remark-gfm` 表格，`skipHtml` 禁用原始 HTML |
| Mermaid | 完成 | `flowchart`（含 `graph` 别名）/ `sequenceDiagram` / `stateDiagram-v2` / `mindmap` / `erDiagram` 白名单，首次用到才加载，`securityLevel: "strict"` + `htmlLabels: false`，解析失败降级为源码 |
| 生成完整性保护 | 完成 | `finish_reason` 与 completion sentinel 两个独立信号；输出上限 / 提前结束 / 服务中断映射到三个错误码与三段文案 |
| 失败保留 | 完成 | 后续版本生成失败时保留已提交的版本与其评审、修订计划，提示指名失败版本 |
| 显式输出上限 | 完成 | `LLM_MAX_OUTPUT_TOKENS` 作为 `max_tokens` 发送，默认 16000 |
| Per-node timing | 完成 | 节点、版本、attempt、墙钟秒数与 Token，含失败尝试 |
| SSE 可靠性 | 完成 | 按 `Last-Event-ID` 补发，不重复不丢事件；落后过多的客户端由原子快照重校准 |
| SQLite 持久化 | 完成 | 对话、快照与可回放事件写入 `data/agentic-prd.sqlite3`，重启后历史可浏览 |
| Markdown 下载 | 完成 | 任意版本导出原始 UTF-8 Markdown，sentinel 已剥离 |
| 任务控制 | 完成 | Pause / Resume（含补充优化要求）/ Cancel，取消为用户意图优先终态 |
| 真实 Provider | 完成 | DeepSeek 与 GLM 共用 OpenAI 兼容适配器；配置在启动时校验，不静默回退 Mock |
| Mock 模式 | 完成 | 确定性场景，无需外部凭据；Podcast v1=71.0、v2=88.0，v1 每位 Reviewer 各带一条 `must_fix` |

## 最新门禁结果

- 后端：pytest 276 项通过，无 skip（使用 `-p no:cacheprovider`）。
- 前端：Vitest 15 个文件、184 项测试通过。
- 浏览器：Playwright Chromium 18 项 E2E 通过。
- 静态检查：`astro check` 0 error / 0 warning / 0 hint，ESLint、Prettier、Ruff
  format/check、mypy strict 全部通过。
- 构建：Astro Node SSR 生产构建成功。
- 真实 Provider 冒烟：未执行：缺少授权或凭据。DeepSeek 与 GLM 的 SDK 替身契约、
  错误映射和结构化输出测试均已通过。

## 已知限制

- 后端必须以单 Uvicorn Worker 运行：Task 句柄、Run 锁、Pause/Resume/Cancel 信号和
  SSE 订阅 Condition 都在进程内，不支持水平扩展。
- 持久化只有本地 SQLite，不引入外部数据库、Redis 或队列。活动工作流不做
  checkpoint：启动时发现的非终态 Run 标记为 `RUN_INTERRUPTED`，不自动续跑。
- 终态任务不能继续优化，需要继续请新建任务。
- 不支持手工编辑 PRD 正文；用户通过创意描述、质量设置和暂停时的补充要求施加影响。
- 导出只支持 Markdown，没有 PDF / DOCX。
- 真实 Provider 的分数、篇幅、耗时和费用是所配置模型服务的属性，不是本应用的属性；
  只有 Mock 模式具有确定性。
- 锁定的 Astro 4 / Vite 5 / Mermaid 10 依赖树存在已公开上游告警。当前版本只适合本地
  Showcase，公网部署前必须先把这些 Major 升级作为显式变更完成并重跑全部门禁；不执行
  `npm audit fix --force`，因为它会改变 Major 版本且仍不能消除全部告警。
- `.env` 默认启用 Mock 并选择 DeepSeek，GLM 配置整段注释。关闭 Mock 前必须填写所选
  Provider 的有效 API Key。

## 下一步

获得明确授权、有效 API Key 和网络后，按 README 关闭 Mock，分别选择 DeepSeek 或 GLM
执行一次手动真实模型发布冒烟；记录模型、Token、估算费用、安全日志和最终状态。未获得
这些条件时无需重复默认自动化。
