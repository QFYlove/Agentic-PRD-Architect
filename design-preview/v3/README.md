# V3 视觉原型

Agentic PRD Architect V3.0 三个核心页面的可交互视觉原型。只使用 Mock 数据，不调用 API、数据库或模型。与正式应用 `src/` 完全隔离：独立入口、独立样式、不导入 `src/` 下的任何文件。

## 运行

在仓库根目录执行（使用根目录已安装的 `vite` 与 `@vitejs/plugin-react`，不需要额外安装依赖）：

```bash
npx vite --config design-preview/v3/vite.config.mjs
```

打开 http://127.0.0.1:4341/。

| 页面 | 地址 |
|---|---|
| 01 项目工作台 | `#/workspace` |
| 02 需求探索 | `#/explore` |
| 03 PRD 编辑器 | `#/editor` |

页面顶部黑色条用于在三个页面之间切换。刷新页面会重置所有演示状态。

## 可以试的交互

- **工作台**：切换输入方式；筛选项目；点击项目行展开；"继续需求探索"进入页面 02。
- **需求探索**：把鼠标移到对话中的 `+ USR-01` 等引用上，查看右侧基线的高亮和连接线；在本轮问题中回答、选择"暂时不知道"或"跳过"后提交本轮；在基线中确认、拒绝、编辑条目；展开"AI 发现"并采纳或暂缓；把窗口缩到 1024px 以下查看对话 / 基线切换。
- **PRD 编辑器**：点击目录跳转；点击正文中带下划线的文字定位到对应问题；在右侧采纳 / 修改后采纳 / 暂缓 / 拒绝；编辑并保存一个章节，观察人工标记、"需重新验证"和影响提示；切换 v1 / v2 查看只读历史；"对比 v2"查看差异；"导出 .md"下载；"需求追溯"查看追溯链；"收起"右栏。

## 截图

`screenshots/` 下有 1440 / 1280 / 1024 / 390 四个宽度的三个页面，以及若干交互状态。重新生成（需先启动上面的开发服务器）：

```bash
node design-preview/v3/scripts/screenshots.mjs     # 12 张：3 页面 × 4 宽度，并检查横向溢出和控制台错误
node design-preview/v3/scripts/interactions.mjs    # 交互冒烟 + 12 张状态截图
```

## 检查

```bash
cd design-preview/v3 && ../../node_modules/.bin/tsc -p tsconfig.json
npx eslint design-preview --ext .ts,.tsx,.mjs --max-warnings 0
npx prettier --check "design-preview/v3/**/*.{ts,tsx,css,mjs,html,json}"
```

## 结构

```
index.html · vite.config.mjs · tsconfig.json
src/
  App.tsx              顶栏、阶段导航、hash 路由
  components/          Workspace · Exploration · Baseline · Editor · Marks（状态符号、封面、Logo）
  data/                Mock 数据与类型（示例需求来自产品定义 3.2 的云盘例子）
  lib/blocks.ts        PRD 章节用的小型 Markdown 解析与导出
  styles/              tokens · base · shell · workspace · explore · editor
```

设计规范见 [docs/v3-planning/design-system.md](../../docs/v3-planning/design-system.md)，交互说明见 [interaction-specification.md](../../docs/v3-planning/interaction-specification.md)。
