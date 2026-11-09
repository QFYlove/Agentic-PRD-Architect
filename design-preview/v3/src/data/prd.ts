// Mock PRD for the editor prototype. Section bodies use a tiny Markdown
// subset (see lib/blocks.ts). Inline finding anchors: [[FD-01|quoted text]].

export type SectionOrigin = "ai" | "optimized" | "human";

export interface Section {
  id: string;
  num: string;
  title: string;
  level: 1 | 2;
  body: string;
  origin: SectionOrigin;
  requirements: string[];
  /** Sections that must be rechecked when this one changes. */
  impacts: string[];
  /** Line-level diff against the previous version, if the section changed. */
  diff?: DiffLine[];
}

export interface DiffLine {
  kind: "same" | "add" | "del";
  text: string;
  reason?: string;
}

export type Reviewer = "TECH" | "UX" | "BIZ";
export type Severity = "must_fix" | "should_fix" | "optional";
export type FindingStatus =
  | "open"
  | "accepted"
  | "modified"
  | "rejected"
  | "deferred"
  | "resolved"
  | "stale";

export const FINDING_STATUS_LABEL: Record<FindingStatus, string> = {
  open: "待处理",
  accepted: "已采纳",
  modified: "修改后采纳",
  rejected: "已拒绝",
  deferred: "暂缓",
  resolved: "已解决",
  stale: "需重新验证",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  must_fix: "必须修改",
  should_fix: "建议修改",
  optional: "可选",
};

export interface ReviewFinding {
  id: string;
  reviewer: Reviewer;
  severity: Severity;
  section: string;
  title: string;
  evidence: string;
  problem: string;
  recommendation: string;
  status: FindingStatus;
}

export interface Version {
  id: string;
  label: string;
  source: string;
  time: string;
  note: string;
}

export const VERSIONS: Version[] = [
  {
    id: "v3",
    label: "v3",
    source: "人工编辑",
    time: "14:20",
    note: "当前草稿",
  },
  {
    id: "v2",
    label: "v2",
    source: "AI 定向优化",
    time: "13:42",
    note: "采纳 FD-06、FD-07",
  },
  {
    id: "v1",
    label: "v1",
    source: "AI 生成",
    time: "13:10",
    note: "基于 Brief 确认版",
  },
];

export const SECTIONS: Section[] = [
  {
    id: "s1",
    num: "1",
    title: "产品概述",
    level: 1,
    origin: "ai",
    requirements: ["POS-01", "USR-01"],
    impacts: ["s3"],
    body: [
      "一款以离线下载为入口的个人云盘。用户提交磁力链接后，由服务端完成下载，文件直接进入网盘，可以在线播放和私密分享。",
      "目标用户是大学生和刚工作的年轻人 [用户输入]。他们现在组合使用下载工具和网盘，非会员下载被严重限速 [用户输入]。",
      "> 核心卖点：免费用户不限制单任务下载速度。每日流量上限的额度 [待确认]。",
    ].join("\n"),
  },
  {
    id: "s2",
    num: "2",
    title: "用户问题与场景",
    level: 1,
    origin: "ai",
    requirements: ["PRB-01", "PRB-02", "SCN-01"],
    impacts: ["s3", "s4-1"],
    body: [
      "| 编号 | 用户问题 | 来源 |",
      "| PRB-01 | 非会员下载被严重限速 | 用户输入 |",
      "| PRB-02 | 下载、转存、播放分散在两个工具里 | AI 推断，已确认 |",
      "主要场景：晚上提交一部剧集或一套课程的磁力链接，第二天在手机上直接观看。",
    ].join("\n"),
  },
  {
    id: "s3",
    num: "3",
    title: "产品目标与 MVP 范围",
    level: 1,
    origin: "optimized",
    requirements: ["DEC-01", "CON-01", "CON-02", "CON-03"],
    impacts: ["s4-1", "s4-4", "s7"],
    body: [
      "| 优先级 | 功能 | 说明 |",
      "| P0 | 离线下载 | 核心价值，详细设计见 4.1 |",
      "| P0 | 在线播放 | 下载完成即可播放 |",
      "| P1 | 私密分享 | 只能分享自己网盘中的文件 |",
      "| P1 | 文件上传 | 网页端和移动端 |",
      "| 暂不纳入 | 公开资源广场 | 版权风险，见 F-01 |",
      "约束：团队 3 人，[[FD-03|服务器预算有限]]，计划 3 个月内上线 [用户输入]。",
    ].join("\n"),
  },
  {
    id: "s4",
    num: "4",
    title: "功能需求",
    level: 1,
    origin: "ai",
    requirements: [],
    impacts: [],
    body: "按优先级排列。P0 功能写到可以直接开发的程度，P1 只写核心流程。",
  },
  {
    id: "s4-1",
    num: "4.1",
    title: "离线下载",
    level: 2,
    origin: "human",
    requirements: ["FR-01", "DEC-01", "CON-02"],
    impacts: ["s5", "s6", "s7"],
    body: [
      "用户粘贴磁力链接，服务端解析文件列表，用户勾选后开始下载。",
      "1. 用户在首页粘贴磁力链接。",
      "2. 系统解析并展示文件列表和总大小。",
      "3. 用户勾选文件，确认后任务进入队列。",
      "4. [[FD-01|下载完成后文件进入「离线下载」目录，并发送通知。]]",
      "- 免费用户同时最多 3 个任务 [假设]。",
      "- 单任务不限速；当日流量用尽后新任务排队到次日。",
    ].join("\n"),
    diff: [
      {
        kind: "same",
        text: "用户粘贴磁力链接，服务端解析文件列表，用户勾选后开始下载。",
      },
      { kind: "same", text: "1. 用户在首页粘贴磁力链接。" },
      { kind: "same", text: "2. 系统解析并展示文件列表和总大小。" },
      { kind: "same", text: "3. 用户勾选文件，确认后任务进入队列。" },
      {
        kind: "same",
        text: "4. 下载完成后文件进入「离线下载」目录，并发送通知。",
      },
      {
        kind: "del",
        text: "- 免费用户不限速、不限流量。",
        reason: "人工修改：与预算约束冲突",
      },
      {
        kind: "add",
        text: "- 免费用户同时最多 3 个任务 [假设]。",
        reason: "人工修改",
      },
      {
        kind: "add",
        text: "- 单任务不限速；当日流量用尽后新任务排队到次日。",
        reason: "FD-03 修改后采纳",
      },
    ],
  },
  {
    id: "s4-2",
    num: "4.2",
    title: "文件上传",
    level: 2,
    origin: "ai",
    requirements: ["FR-02"],
    impacts: ["s7"],
    body: "支持网页端拖拽上传和移动端选择相册文件上传。单文件大小上限 [待确认]。",
  },
  {
    id: "s4-3",
    num: "4.3",
    title: "在线播放",
    level: 2,
    origin: "ai",
    requirements: ["FR-03", "PRB-02"],
    impacts: ["s7"],
    body: [
      "下载完成的视频可以直接播放，不需要先转存。",
      "- 支持倍速、记忆播放进度。",
      "- [[FD-04|常见视频格式在服务端转码后播放。]]",
    ].join("\n"),
  },
  {
    id: "s4-4",
    num: "4.4",
    title: "私密分享",
    level: 2,
    origin: "optimized",
    requirements: ["FR-04"],
    impacts: ["s5", "s7"],
    body: [
      "用户只能分享自己网盘中的文件，生成私密链接和提取码。",
      "- 链接默认 7 天过期 [用户输入]。",
      "- [[FD-02|访问者打开过期链接时，提示链接已失效。]]",
      "- 收到侵权投诉后，管理员可以下架分享链接。",
    ].join("\n"),
    diff: [
      {
        kind: "del",
        text: "用户可以把文件分享到公开资源广场。",
        reason: "采纳 FD-06：版权风险",
      },
      {
        kind: "add",
        text: "用户只能分享自己网盘中的文件，生成私密链接和提取码。",
        reason: "采纳 FD-06",
      },
      { kind: "same", text: "- 链接默认 7 天过期 [用户输入]。" },
      { kind: "same", text: "- 访问者打开过期链接时，提示链接已失效。" },
      {
        kind: "add",
        text: "- 收到侵权投诉后，管理员可以下架分享链接。",
        reason: "采纳 FD-07",
      },
    ],
  },
  {
    id: "s5",
    num: "5",
    title: "业务规则",
    level: 1,
    origin: "ai",
    requirements: ["DEC-01", "CON-02"],
    impacts: ["s4-1", "s4-4", "s6", "s7"],
    body: [
      "| 编号 | 规则 | 关联 |",
      "| BR-01 | 免费用户每日流量上限，额度待确认 | 4.1 |",
      "| BR-02 | 当日流量用尽后，新任务排队到次日 0 点 | 4.1 |",
      "| BR-03 | 分享链接默认 7 天过期，可手动提前失效 | 4.4 |",
      "| BR-04 | 被投诉的分享链接下架后不可恢复 | 4.4 |",
    ].join("\n"),
  },
  {
    id: "s6",
    num: "6",
    title: "异常处理",
    level: 1,
    origin: "ai",
    requirements: ["FR-01"],
    impacts: ["s7"],
    body: [
      "- 磁力链接无法解析：提示链接无效，不创建任务。",
      "- [[FD-05|下载长时间没有进度：任务标记为失败。]]",
      "- 网盘空间不足：任务暂停，提示清理空间。",
    ].join("\n"),
  },
  {
    id: "s7",
    num: "7",
    title: "验收标准",
    level: 1,
    origin: "ai",
    requirements: [],
    impacts: [],
    body: [
      "- AC-01 提交有效磁力链接后，可以看到文件列表和总大小。",
      "- AC-02 下载完成后，文件出现在「离线下载」目录，并收到通知。",
      "- AC-03 当日流量用尽后，新任务显示排队状态和预计开始时间。",
      "- AC-04 打开过期分享链接，看到失效提示，无法下载文件。",
    ].join("\n"),
  },
  {
    id: "s8",
    num: "8",
    title: "假设与待确认事项",
    level: 1,
    origin: "ai",
    requirements: ["ASM-01", "OPEN-01"],
    impacts: [],
    body: [
      "| 事项 | 类型 | 影响的决策 |",
      "| 热门资源可以去重降低成本 | 假设 | 带宽预算、流量上限 |",
      "| 每日流量上限的额度 | 待确认 | BR-01、商业模式 |",
      "| 是否收费 | 待确认 | 会员体系是否纳入 MVP |",
    ].join("\n"),
  },
];

export const REVIEW_FINDINGS: ReviewFinding[] = [
  {
    id: "FD-03",
    reviewer: "BIZ",
    severity: "must_fix",
    section: "s3",
    title: "流量上限没有额度，无法判断预算是否够用",
    evidence: "「服务器预算有限」；BR-01「额度待确认」。",
    problem:
      "MVP 范围建立在免费不限速上，但成本上限未定义，范围是否可行无法评估。",
    recommendation:
      "在 3 中给出额度的确定方式（例如按预算倒推），并在 8 中保留为待确认。",
    status: "modified",
  },
  {
    id: "FD-01",
    reviewer: "TECH",
    severity: "should_fix",
    section: "s4-1",
    title: "下载完成的定义不清楚",
    evidence: "「下载完成后文件进入「离线下载」目录，并发送通知。」",
    problem: "部分文件完成、部分失败时的状态没有定义。",
    recommendation: "补充任务状态：排队、下载中、部分完成、完成、失败。",
    status: "open",
  },
  {
    id: "FD-05",
    reviewer: "TECH",
    severity: "should_fix",
    section: "s6",
    title: "「长时间没有进度」没有判定时长",
    evidence: "「下载长时间没有进度：任务标记为失败。」",
    problem: "没有阈值无法开发和测试，也没有说明失败后流量是否返还。",
    recommendation: "给出超时时长和流量返还规则，同步到 BR 和 AC。",
    status: "open",
  },
  {
    id: "FD-02",
    reviewer: "UX",
    severity: "should_fix",
    section: "s4-4",
    title: "过期链接页没有给访问者下一步",
    evidence: "「访问者打开过期链接时，提示链接已失效。」",
    problem: "访问者不知道是否可以联系分享者重新获取。",
    recommendation: "失效页展示分享者昵称和「请对方重新分享」的说明。",
    status: "open",
  },
  {
    id: "FD-04",
    reviewer: "TECH",
    severity: "optional",
    section: "s4-3",
    title: "转码格式范围未说明",
    evidence: "「常见视频格式在服务端转码后播放。」",
    problem: "「常见」无法验收；转码成本受格式范围影响。",
    recommendation: "列出 MVP 支持的格式，其他格式提示下载后本地播放。",
    status: "deferred",
  },
  {
    id: "FD-06",
    reviewer: "BIZ",
    severity: "must_fix",
    section: "s4-4",
    title: "公开资源广场的版权风险",
    evidence: "v1「用户可以把文件分享到公开资源广场。」",
    problem: "公开分享第三方影视资源存在侵权风险。",
    recommendation: "MVP 只保留私密分享。",
    status: "resolved",
  },
];

export interface TraceNode {
  id: string;
  kind: string;
  text: string;
}

export const TRACE: Record<string, TraceNode[]> = {
  "s4-1": [
    { id: "PRB-01", kind: "用户问题", text: "非会员下载被严重限速" },
    { id: "DEC-01", kind: "产品决策", text: "免费用户也不限速" },
    { id: "SCN-01", kind: "使用场景", text: "下载美剧和课程资源" },
    { id: "FR-01", kind: "功能需求", text: "磁力链接离线下载" },
    { id: "BR-02", kind: "业务规则", text: "流量用尽后排队到次日" },
    { id: "AC-03", kind: "验收标准", text: "排队状态和预计开始时间" },
  ],
  "s4-4": [
    { id: "SCN-01", kind: "使用场景", text: "下载美剧和课程资源" },
    { id: "FR-04", kind: "功能需求", text: "资源分享" },
    { id: "F-01", kind: "探索发现", text: "资源分享存在版权合规风险" },
    { id: "BR-03", kind: "业务规则", text: "分享链接默认 7 天过期" },
    { id: "AC-04", kind: "验收标准", text: "过期链接无法下载" },
  ],
  s3: [
    { id: "DEC-01", kind: "产品决策", text: "免费用户也不限速" },
    { id: "CON-02", kind: "业务约束", text: "服务器预算有限" },
    { id: "OPEN-01", kind: "待确认", text: "是否收费" },
  ],
};
