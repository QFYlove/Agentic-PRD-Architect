import type { StageKey } from "./types";

export interface Project {
  id: string;
  code: string;
  name: string;
  summary: string;
  stage: StageKey;
  entry: "idea" | "requirement" | "review";
  openFindings: number;
  openQuestions: number;
  version: string | null;
  updatedAt: string;
  updatedLabel: string;
  seed: number;
}

export const PROJECTS: Project[] = [
  {
    id: "p7",
    code: "P-0007",
    name: "云盘离线下载",
    summary: "以离线下载为入口的个人云盘，面向大学生和刚工作的年轻人。",
    stage: "explore",
    entry: "idea",
    openFindings: 4,
    openQuestions: 3,
    version: null,
    updatedAt: "2026-11-08 14:32",
    updatedLabel: "今天 14:32",
    seed: 7,
  },
  {
    id: "p6",
    code: "P-0006",
    name: "课程预约与签到",
    summary: "线下培训机构的课程预约、候补和到课签到。",
    stage: "review",
    entry: "requirement",
    openFindings: 6,
    openQuestions: 2,
    version: "v3",
    updatedAt: "2026-11-07 18:05",
    updatedLabel: "昨天 18:05",
    seed: 6,
  },
  {
    id: "p5",
    code: "P-0005",
    name: "会员积分体系改版",
    summary: "现有积分规则复杂、兑换率低，重新设计获取和消耗规则。",
    stage: "prd",
    entry: "requirement",
    openFindings: 2,
    openQuestions: 5,
    version: "v2",
    updatedAt: "2026-11-05 10:12",
    updatedLabel: "11-05 10:12",
    seed: 5,
  },
  {
    id: "p4",
    code: "P-0004",
    name: "工单系统 PRD 审查",
    summary: "审查一份已有的客服工单系统 PRD。",
    stage: "deliver",
    entry: "review",
    openFindings: 0,
    openQuestions: 0,
    version: "v4",
    updatedAt: "2026-10-28 16:40",
    updatedLabel: "10-28 16:40",
    seed: 4,
  },
  {
    id: "p3",
    code: "P-0003",
    name: "家庭记账小程序",
    summary: "多人共同记账，按成员和类别查看支出。",
    stage: "brief",
    entry: "idea",
    openFindings: 1,
    openQuestions: 4,
    version: null,
    updatedAt: "2026-10-21 09:03",
    updatedLabel: "10-21 09:03",
    seed: 3,
  },
];

export interface Activity {
  time: string;
  project: string;
  actor: "user" | "ai";
  text: string;
  ref: string;
}

export const ACTIVITY: Activity[] = [
  {
    time: "14:32",
    project: "P-0007",
    actor: "user",
    text: "回答了 2 个问题",
    ref: "R-02",
  },
  {
    time: "14:31",
    project: "P-0007",
    actor: "ai",
    text: "发现逻辑冲突",
    ref: "F-02",
  },
  {
    time: "14:29",
    project: "P-0007",
    actor: "user",
    text: "确认了目标用户",
    ref: "USR-01",
  },
  {
    time: "18:05",
    project: "P-0006",
    actor: "ai",
    text: "完成 Tech / UX / Biz 审查",
    ref: "v3",
  },
  {
    time: "17:48",
    project: "P-0006",
    actor: "user",
    text: "手动修改了退课规则",
    ref: "§5.2",
  },
  {
    time: "10:12",
    project: "P-0005",
    actor: "user",
    text: "保存版本",
    ref: "v2",
  },
];

export const ENTRY_MODES = [
  {
    code: "A",
    title: "从想法开始",
    detail: "用一两句话描述产品构想，AI 通过追问帮你理清问题。",
  },
  {
    code: "B",
    title: "从已有需求开始",
    detail: "粘贴业务需求、会议纪要或初步方案，AI 提取已知信息和缺口。",
  },
  {
    code: "C",
    title: "审查已有 PRD",
    detail: "上传或粘贴现有 PRD，直接进入多维度审查。",
  },
] as const;
