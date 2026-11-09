import type { Group, Insight, Item, Message, Question } from "./types";

// Mock data. The example idea is the one used in section 3.2 of the product
// definition. Nothing below is presented as research data.

export const GROUPS: Group[] = [
  { key: "position", label: "产品定位", core: true },
  { key: "goal", label: "产品目标", core: true },
  { key: "user", label: "目标用户", core: true },
  { key: "problem", label: "用户问题", core: true },
  { key: "scenario", label: "使用场景", core: false },
  { key: "alternative", label: "现有方案", core: false },
  { key: "solution", label: "解决方案", core: false },
  { key: "feature", label: "功能需求", core: false },
  { key: "constraint", label: "业务约束", core: false },
  { key: "decision", label: "产品决策", core: false },
  { key: "assumption", label: "假设", core: false },
  { key: "open", label: "待确认事项", core: false },
];

export const ITEMS: Item[] = [
  {
    id: "POS-01",
    group: "position",
    text: "以离线下载为入口的个人云盘，下载完成后可以直接播放和管理。",
    status: "inferred",
    source: "ai",
    round: 1,
    reason: "根据你描述的四项功能和「类似迅雷」归纳。",
    previous: ["一款类似迅雷的云盘。"],
  },
  {
    id: "USR-01",
    group: "user",
    text: "大学生和刚工作的年轻人。",
    status: "confirmed",
    source: "you",
    round: 1,
  },
  {
    id: "PRB-01",
    group: "problem",
    text: "非会员下载被严重限速。",
    status: "confirmed",
    source: "you",
    round: 1,
  },
  {
    id: "PRB-02",
    group: "problem",
    text: "下载、转存、播放分散在两个工具里，需要来回切换。",
    status: "inferred",
    source: "ai",
    round: 1,
    reason: "你提到同时使用迅雷和百度网盘，我推断切换工具本身也是负担。",
  },
  {
    id: "SCN-01",
    group: "scenario",
    text: "下载美剧和课程资源，下载后在线观看。",
    status: "confirmed",
    source: "you",
    round: 1,
  },
  {
    id: "ALT-01",
    group: "alternative",
    text: "迅雷下载，再存到百度网盘。",
    status: "confirmed",
    source: "you",
    round: 1,
  },
  {
    id: "SOL-01",
    group: "solution",
    text: "服务端完成离线下载，文件直接进入用户网盘并可在线播放。",
    status: "proposed",
    source: "ai",
    round: 2,
    reason: "把下载和存储放在一处，可以同时回应限速和切换工具两个问题。",
  },
  {
    id: "FR-01",
    group: "feature",
    text: "磁力链接离线下载",
    status: "confirmed",
    source: "you",
    round: 0,
  },
  {
    id: "FR-02",
    group: "feature",
    text: "文件上传",
    status: "confirmed",
    source: "you",
    round: 0,
  },
  {
    id: "FR-03",
    group: "feature",
    text: "在线播放",
    status: "confirmed",
    source: "you",
    round: 0,
  },
  {
    id: "FR-04",
    group: "feature",
    text: "资源分享",
    status: "confirmed",
    source: "you",
    round: 0,
  },
  {
    id: "CON-01",
    group: "constraint",
    text: "团队 3 人。",
    status: "confirmed",
    source: "you",
    round: 2,
  },
  {
    id: "CON-02",
    group: "constraint",
    text: "服务器预算有限，具体金额未提供。",
    status: "confirmed",
    source: "you",
    round: 2,
  },
  {
    id: "CON-03",
    group: "constraint",
    text: "希望 3 个月内上线。",
    status: "confirmed",
    source: "you",
    round: 2,
  },
  {
    id: "DEC-01",
    group: "decision",
    text: "核心卖点是下载速度：免费用户也不限速。",
    status: "confirmed",
    source: "you",
    round: 2,
  },
  {
    id: "ASM-01",
    group: "assumption",
    text: "热门资源可以通过文件去重降低带宽和存储成本。",
    status: "assumption",
    source: "ai",
    round: 2,
    reason: "这是「免费不限速」在成本上可行的前提之一，尚未验证。",
  },
  {
    id: "OPEN-01",
    group: "open",
    text: "是否收费、如何收费。",
    status: "open",
    source: "you",
    round: 1,
  },
];

export const INSIGHTS: Insight[] = [
  {
    id: "F-02",
    kind: "conflict",
    title: "「免费不限速」和「预算有限」很难同时成立",
    basis:
      "你确认了免费用户不限速，同时服务器预算有限。带宽成本会随免费用户数量增长。",
    suggestion:
      "明确「不限速」的范围，比如不限单个任务速度，但设置每日流量上限。",
    related: ["DEC-01", "CON-02", "OPEN-01"],
    state: "open",
  },
  {
    id: "F-01",
    kind: "risk",
    title: "公开分享影视资源有版权风险",
    basis: "使用场景是下载美剧和课程资源，功能里包含资源分享。",
    suggestion: "分享只限私密链接，并提供侵权投诉和下架流程。",
    related: ["FR-04", "SCN-01"],
    state: "open",
  },
  {
    id: "F-03",
    kind: "scenario",
    title: "还没有考虑下载失败的情况",
    basis: "离线下载只描述了提交链接，没有失败、超时和死链的处理。",
    suggestion: "补充超时判定、失败通知，以及失败后是否返还流量。",
    related: ["FR-01"],
    state: "open",
  },
  {
    id: "F-04",
    kind: "opportunity",
    title: "下载完成即可播放，省掉转存一步",
    basis: "用户现在需要下载、转存、再打开播放器三步。",
    suggestion:
      "作为方案的核心体验来验证。代价是需要服务端转码；需要验证用户是否会在下载后马上观看。",
    related: ["PRB-02", "SOL-01"],
    state: "open",
  },
];

export const MESSAGES: Message[] = [
  {
    id: "m0",
    from: "you",
    round: 0,
    text: "我想做一个类似迅雷的云盘，支持磁力链接下载、文件上传、在线播放和资源分享。",
    changes: [
      { item: "FR-01", kind: "added" },
      { item: "FR-02", kind: "added" },
      { item: "FR-03", kind: "added" },
      { item: "FR-04", kind: "added" },
    ],
  },
  {
    id: "m1",
    from: "ai",
    round: 1,
    text: "四项功能已经很清楚了。在讨论怎么做之前，我想先弄清楚两件事：这个产品给谁用，以及他们现在最不满意的是什么。这两点会决定哪个功能最值得先做好。",
  },
  {
    id: "m2",
    from: "you",
    round: 1,
    text: "主要是大学生和刚工作的年轻人，经常下美剧和课程资源。现在用迅雷加百度网盘，非会员限速很严重。收费还没想好。",
    changes: [
      { item: "USR-01", kind: "added" },
      { item: "PRB-01", kind: "added" },
      { item: "PRB-02", kind: "added" },
      { item: "SCN-01", kind: "added" },
      { item: "ALT-01", kind: "added" },
      { item: "POS-01", kind: "updated" },
      { item: "OPEN-01", kind: "added" },
    ],
  },
  {
    id: "m3",
    from: "ai",
    round: 2,
    text: "痛点很明确：限速，以及在两个工具之间来回切换。后一点是我推断的，需要你确认。另外，分享第三方影视资源有版权风险，我先记下来，稍后一起处理。",
    insights: ["F-01"],
  },
  {
    id: "m4",
    from: "you",
    round: 2,
    text: "下载速度最重要，核心卖点就是免费用户也不限速。团队 3 个人，服务器预算有限，希望 3 个月内上线。",
    changes: [
      { item: "DEC-01", kind: "added" },
      { item: "CON-01", kind: "added" },
      { item: "CON-02", kind: "added" },
      { item: "CON-03", kind: "added" },
      { item: "SOL-01", kind: "added" },
      { item: "ASM-01", kind: "added" },
    ],
  },
  {
    id: "m5",
    from: "ai",
    round: 3,
    text: "「免费不限速」和「预算有限」放在一起，会直接决定成本模型，这是目前最需要你做的取舍。另外两个问题可以简单回答，也可以先跳过。",
    insights: ["F-02", "F-03"],
  },
];

export const QUESTIONS: Question[] = [
  {
    id: "Q-06",
    text: "在预算有限的前提下，「不限速」具体指什么？",
    why: "这决定带宽成本怎么算，以及免费和付费用户的区别。",
    group: "decision",
    insight: "F-02",
    draft: "不限制单个任务的速度，但免费用户每天有流量上限，具体额度再算。",
  },
  {
    id: "Q-07",
    text: "分享是否只允许分享自己网盘里的文件，并且只用私密链接？",
    why: "回应版权风险，决定分享功能的边界。",
    group: "feature",
    insight: "F-01",
    draft: "只能分享自己网盘里的文件，用私密链接，7 天过期。",
  },
  {
    id: "Q-08",
    text: "需要同时支持手机、电脑和电视播放吗？",
    why: "影响播放器的开发范围，可以以后再定。",
    group: "feature",
  },
];

/** Canned AI reply after round 3 is submitted. */
export const NEXT = {
  text: "已经把你的回答整理成两条决策，等你确认。每日流量的额度会影响成本估算，我记为待确认事项。核心信息还差「产品目标」，下一轮我会问这个。",
  questions: [
    {
      id: "Q-09",
      text: "上线 3 个月后，你希望看到什么结果，才算这个产品做对了？",
      why: "产品目标还没有明确，它会决定 MVP 的取舍和以后怎么衡量。",
      group: "goal",
    },
  ] satisfies Question[],
};
