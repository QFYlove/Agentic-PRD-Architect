# 设计原型 v4

Agentic PRD Architect 三个核心页面的可交互原型。设计说明见 [docs/v3-planning/design-proposal.md](../../docs/v3-planning/design-proposal.md)。

只使用前端 Mock 数据，不调用 API、数据库或模型。与正式应用 `src/` 和 `design-preview/v3/` 完全隔离：独立入口、独立样式、不导入其他目录的文件。刷新页面会重置演示状态。

## 运行

在仓库根目录执行（使用根目录已安装的 `vite` 和 `@vitejs/plugin-react`）：

```bash
npx vite --config design-preview/v4/vite.config.mjs
```

打开 http://127.0.0.1:4342/。

| 页面 | 地址 |
|---|---|
| 项目列表 | `#/` |
| 需求探索 | `#/p7/explore` |
| PRD 编辑器 | `#/p7/document` |

## 可以试的交互

- **项目列表**：在输入框里写一句话，"开始"才会变成可用；点"继续上次的工作"进入项目；搜索项目；展开"已交付"。
- **需求探索**：回答、跳过或"暂时不确定"本轮问题，然后发送；鼠标移到"记录了 N 项"上看右侧对应需求；在"待你决定"里确认、修改或否定推断，采纳或忽略 AI 发现；切到"全部需求"；关掉右侧面板。
- **PRD 编辑器**：点正文里带荧光笔痕的文字打开审查意见；采纳、修改后采纳、稍后、忽略；鼠标移到章节标题上点"编辑"，改完保存；点版本号查看历史版本或"与 v2 对比"；点"来源"看这一节依据的需求；导出 Markdown。
- 把窗口缩到 1024px、390px 查看窄屏布局。

## 截图

`screenshots/` 下：

- `home-*.png`、`explore-*.png`、`document-*.png`：三个页面在 1440 / 1280 / 1024 / 390 宽度下的首屏。
- `i01`–`i15`：主要交互过程。

重新生成（先启动开发服务器）：

```bash
node design-preview/v4/scripts/screenshots.mjs    # 12 张，并检查横向溢出和控制台错误
node design-preview/v4/scripts/interactions.mjs   # 交互演示 15 张
```

## 检查

```bash
cd design-preview/v4 && ../../node_modules/.bin/tsc -p tsconfig.json
npx eslint design-preview/v4 --ext .ts,.tsx,.mjs --max-warnings 0
npx prettier --check "design-preview/v4/**/*.{ts,tsx,css,mjs,html,json}"
```

## 结构

```
src/
  App.tsx                 顶栏、两个空间、hash 路由；项目状态在这里，切换空间不丢失
  components/
    Home.tsx              项目列表
    Explore.tsx           对话、AI 发现、本轮问题
    Requirements.tsx      需求面板：待你决定 / 全部需求
    Document.tsx          PRD 编辑器：目录、正文、编辑、审查意见、来源、版本
    ui.tsx                图标、状态标记、项目图形、进度条
  data/                   Mock 数据与类型
  lib/                    Markdown 子集解析（复制自 v3）、路由
  styles/                 tokens · base · app · home · explore · document
```
