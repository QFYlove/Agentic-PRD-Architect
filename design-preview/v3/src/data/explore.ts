import type {
  BaselineItem,
  ExploreFinding,
  Group,
  Question,
  Turn,
} from "./types";

// Mock data only. The example idea comes from section 3.2 of the product
// definition. No figure below claims to be research data.

export const GROUPS: Group[] = [
  {
    key: "position",
    index: "01",
    title: "产品定位",
    en: "Positioning",
    priority: "P0",
  },
  { key: "goal", index: "02", title: "产品目标", en: "Goals", priority: "P0" },
  { key: "user", index: "03", title: "目标用户", en: "Users", priority: "P0" },
  {
    key: "problem",
    index: "04",
    title: "用户问题",
    en: "Problems",
    priority: "P0",
  },
  {
    key: "scenario",
    index: "05",
    title: "使用场景",
    en: "Scenarios",
    priority: "P1",
  },
  {
    key: "alternative",
    index: "06",
    title: "现有方案",
    en: "Alternatives",
    priority: "P1",
  },
  {
    key: "solution",
    index: "07",
    title: "解决方案",
    en: "Solution",
    priority: "P1",
  },
  {
    key: "feature",
    index: "08",
    title: "功能需求",
    en: "Features",
    priority: "P1",
  },
  {
    key: "constraint",
    index: "09",
    title: "业务约束",
    en: "Constraints",
    priority: "P1",
  },
  {
    key: "assumption",
    index: "10",
    title: "假设",
    en: "Assumptions",
    priority: "P2",
  },
  {
    key: "decision",
    index: "11",
    title: "已确认决策",
    en: "Decisions",
    priority: "P2",
  },
  {
    key: "open",
    index: "12",
    title: "待确认事项",
    en: "Open questions",
    priority: "P2",
  },
];

export const INITIAL_ITEMS: BaselineItem[] = [
  {
    id: "POS-01",
    group: "position",
    content: "以离线下载为入口的个人云存储产品，下载完成后可直接播放和管理。",
    status: "inferred",
    source: { kind: "ai", round: 1 },
    history: ["一款类似迅雷的云盘。"],
  },
  {
    id: "USR-01",
    group: "user",
    content: "大学生和刚工作的年轻人。",
    status: "confirmed",
    source: { kind: "user", round: 1 },
  },
  {
    id: "PRB-01",
    group: "problem",
    content: "非会员下载被严重限速。",
    status: "confirmed",
    source: { kind: "user", round: 1 },
  },
  {
    id: "PRB-02",
    group: "problem",
    content: "下载、转存、播放分散在两个工具里，需要来回切换。",
    status: "inferred",
    source: { kind: "ai", round: 1 },
  },
  {
    id: "SCN-01",
    group: "scenario",
    content: "下载美剧和课程资源，下载后在线观看。",
    status: "confirmed",
    source: { kind: "user", round: 1 },
  },
  {
    id: "ALT-01",
    group: "alternative",
    content: "迅雷下载 + 百度网盘存储的组合。",
    status: "confirmed",
    source: { kind: "user", round: 1 },
  },
  {
    id: "SOL-01",
    group: "solution",
    content: "服务端离线下载，完成后直接进入用户网盘并可在线播放。",
    status: "proposed",
    source: { kind: "ai", round: 2 },
  },
  {
    id: "FR-01",
    group: "feature",
    content: "磁力链接离线下载。",
    status: "confirmed",
    source: { kind: "user", round: 0 },
  },
  {
    id: "FR-02",
    group: "feature",
    content: "文件上传。",
    status: "confirmed",
    source: { kind: "user", round: 0 },
  },
  {
    id: "FR-03",
    group: "feature",
    content: "在线播放。",
    status: "confirmed",
    source: { kind: "user", round: 0 },
  },
  {
    id: "FR-04",
    group: "feature",
    content: "资源分享。",
    status: "confirmed",
    source: { kind: "user", round: 0 },
  },
  {
    id: "CON-01",
    group: "constraint",
    content: "团队 3 人。",
    status: "confirmed",
    source: { kind: "user", round: 2 },
  },
  {
    id: "CON-02",
    group: "constraint",
    content: "服务器预算有限（具体金额未提供）。",
    status: "confirmed",
    source: { kind: "user", round: 2 },
  },
  {
    id: "CON-03",
    group: "constraint",
    content: "希望 3 个月内上线。",
    status: "confirmed",
    source: { kind: "user", round: 2 },
  },
  {
    id: "ASM-01",
    group: "assumption",
    content: "热门资源可以通过文件去重（秒传）降低带宽和存储成本。",
    status: "assumption",
    source: { kind: "ai", round: 2 },
  },
  {
    id: "DEC-01",
    group: "decision",
    content: "MVP 的核心卖点是下载速度：免费用户也不限速。",
    status: "confirmed",
    source: { kind: "user", round: 2 },
  },
  {
    id: "OPEN-01",
    group: "open",
    content: "是否收费、如何收费尚未确定。",
    status: "open",
    source: { kind: "user", round: 1 },
  },
];

export const FINDINGS: ExploreFinding[] = [
  {
    id: "F-01",
    kind: "risk",
    title: "资源分享存在版权合规风险",
    evidence: "R-01 用户原话「经常下美剧和课程资源」，FR-04「资源分享」。",
    impact:
      "公开分享第三方影视资源可能导致侵权责任和应用下架，影响分享功能的范围。",
    recommendation:
      "把分享限定为私密链接，增加侵权投诉和下架流程，作为 P0 业务规则。",
    related: ["FR-04", "SCN-01"],
    status: "open",
  },
  {
    id: "F-02",
    kind: "consistency",
    title: "「免费不限速」与「服务器预算有限」冲突",
    evidence: "DEC-01「免费用户也不限速」，CON-02「服务器预算有限」。",
    impact:
      "带宽成本随免费用户量线性增长，这一决策决定成本模型和是否需要收费。",
    recommendation:
      "明确「不限速」的含义：不限单任务速度，但设置每日流量或并发上限。",
    related: ["DEC-01", "CON-02", "OPEN-01"],
    status: "open",
  },
  {
    id: "F-03",
    kind: "scenario",
    title: "缺少下载失败和死链的处理",
    evidence: "FR-01 只描述了提交磁力链接，没有失败路径。",
    impact: "死链和低热度资源很常见，没有规则会导致任务长期卡住、占用配额。",
    recommendation: "补充超时判定、失败通知和配额返还规则。",
    related: ["FR-01"],
    status: "open",
  },
  {
    id: "F-04",
    kind: "opportunity",
    title: "下载完成即可播放，省去转存步骤",
    evidence: "PRB-02「下载、转存、播放分散在两个工具里」。",
    impact:
      "现有方式需要 3 步，合并后用户只需提交链接。代价是需要服务端转码能力。",
    recommendation:
      "作为 SOL-01 的一部分验证；需要验证的假设：用户会在下载后立即观看。",
    related: ["PRB-02", "SOL-01"],
    status: "open",
  },
];

export const TURNS: Turn[] = [
  {
    kind: "user",
    round: 0,
    text: "我想做一个类似迅雷的云盘，支持磁力链接下载、文件上传、在线播放和资源分享。",
    extracted: [
      { id: "FR-01", action: "created" },
      { id: "FR-02", action: "created" },
      { id: "FR-03", action: "created" },
      { id: "FR-04", action: "created" },
    ],
  },
  {
    kind: "ai",
    round: 1,
    summary:
      "我理解的初步构想是一款以离线下载为入口的个人云盘。四项功能已经明确，但还不清楚给谁用、解决什么问题。先确认这两点，它们会决定功能的优先级。",
    questions: [
      {
        id: "Q-01",
        priority: "P0",
        text: "主要给谁用？",
        purpose: "目标用户决定功能优先级和合规边界。",
        target: "user",
      },
      {
        id: "Q-02",
        priority: "P0",
        text: "用户现在用什么方式解决？最不满意的是什么？",
        purpose: "找到真正的痛点，避免做成功能堆叠的云盘。",
        target: "problem",
      },
      {
        id: "Q-03",
        priority: "P1",
        text: "是否计划收费？",
        purpose: "影响限速策略、存储配额和成本约束。",
        target: "open",
      },
    ],
    findings: [],
  },
  {
    kind: "user",
    round: 1,
    text: "主要是大学生和刚工作的年轻人，经常下美剧和课程资源。现在用迅雷加百度网盘，非会员限速很严重。收费还没想好。",
    extracted: [
      { id: "USR-01", action: "created" },
      { id: "PRB-01", action: "created" },
      { id: "PRB-02", action: "created" },
      { id: "SCN-01", action: "created" },
      { id: "ALT-01", action: "created" },
      { id: "POS-01", action: "updated" },
      { id: "OPEN-01", action: "created" },
    ],
  },
  {
    kind: "ai",
    round: 2,
    summary:
      "痛点很清楚：限速，以及在两个工具之间切换。我把「切换工具」记为推断，需要你确认。另外，分享第三方影视资源有合规风险，我在右侧做了标记。",
    questions: [
      {
        id: "Q-04",
        priority: "P0",
        text: "如果只能先做好一件事，用户最在意下载速度、存储空间，还是播放体验？",
        purpose: "确定 MVP 的核心价值，其他功能围绕它取舍。",
        target: "decision",
      },
      {
        id: "Q-05",
        priority: "P1",
        text: "有哪些已知限制？比如团队规模、预算、上线时间。",
        purpose: "约束决定方案的可行范围。",
        target: "constraint",
      },
    ],
    findings: ["F-01", "F-04"],
  },
  {
    kind: "user",
    round: 2,
    text: "下载速度最重要，核心卖点就是免费用户也不限速。团队 3 个人，服务器预算有限，希望 3 个月内上线。",
    extracted: [
      { id: "DEC-01", action: "created" },
      { id: "CON-01", action: "created" },
      { id: "CON-02", action: "created" },
      { id: "CON-03", action: "created" },
      { id: "SOL-01", action: "created" },
      { id: "ASM-01", action: "created" },
    ],
  },
];

/** The round currently waiting for the user's answers. */
export const CURRENT_ROUND = {
  round: 3,
  summary:
    "「免费不限速」和「预算有限」放在一起会直接决定成本模型，这是目前最需要你做的取舍。其余两个问题可以稍后回答。",
  findings: ["F-02", "F-03"],
  questions: [
    {
      id: "Q-06",
      priority: "P0",
      text: "预算有限的前提下，「不限速」具体指什么？不限单任务速度，还是不限每日流量？",
      purpose: "F-02 的冲突需要你决定取舍，这会改变成本模型。",
      target: "decision",
      finding: "F-02",
    },
    {
      id: "Q-07",
      priority: "P1",
      text: "分享功能是否只允许分享自己上传或下载的文件，并且只用私密链接？",
      purpose: "回应版权风险 F-01，决定分享规则。",
      target: "feature",
      finding: "F-01",
    },
    {
      id: "Q-08",
      priority: "P2",
      text: "是否需要支持手机、电脑、电视多端播放？",
      purpose: "可以暂缓，影响播放器的开发范围。",
      target: "feature",
    },
  ] satisfies Question[],
};

export const DRAFT_ANSWERS: Record<string, string> = {
  "Q-06": "不限制单个任务的速度，但免费用户每天有流量上限，具体额度再算。",
  "Q-07": "只能分享自己网盘里的文件，用私密链接，7 天过期。",
  "Q-08": "",
};

/** Canned follow-up shown after the user submits round 3. */
export const NEXT_ROUND = {
  summary:
    "已经把你的回答整理成两条待确认的决策。流量上限的额度会影响成本估算，我记为待确认事项。下一步建议补充失败场景。",
  questions: [
    {
      id: "Q-09",
      priority: "P1",
      text: "离线下载多久没有进度算失败？失败后是否返还当日流量？",
      purpose: "补全 F-03 的失败路径。",
      target: "feature",
      finding: "F-03",
    },
  ] satisfies Question[],
};
