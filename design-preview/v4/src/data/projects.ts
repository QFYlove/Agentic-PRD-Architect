import type { Step } from "./types";

export interface Project {
  id: string;
  name: string;
  summary: string;
  step: Step;
  /** What the user should do next, in their words. */
  next: string;
  pending: number;
  updated: string;
  last: string;
  seed: number;
  done?: boolean;
}

export const PROJECTS: Project[] = [
  {
    id: "p7",
    name: "云盘离线下载",
    summary: "以离线下载为入口的个人云盘，面向大学生和刚工作的年轻人。",
    step: "需求探索",
    next: "3 个问题等你回答，8 项内容等你决定",
    pending: 8,
    updated: "今天 14:32",
    last: "你确认了目标用户；AI 发现了一处逻辑冲突",
    seed: 7,
  },
  {
    id: "p6",
    name: "课程预约与签到",
    summary: "线下培训机构的课程预约、候补和到课签到。",
    step: "审查",
    next: "6 条审查意见待处理",
    pending: 6,
    updated: "昨天 18:05",
    last: "完成技术、体验、商业三方审查",
    seed: 4,
  },
  {
    id: "p5",
    name: "会员积分体系改版",
    summary: "重新设计积分的获取和消耗规则，提高兑换率。",
    step: "PRD",
    next: "第 5 章业务规则还在编写",
    pending: 2,
    updated: "11月5日",
    last: "你保存了 v2",
    seed: 9,
  },
  {
    id: "p3",
    name: "家庭记账小程序",
    summary: "多人共同记账，按成员和类别查看支出。",
    step: "Product Brief",
    next: "Brief 草稿等你确认",
    pending: 4,
    updated: "10月21日",
    last: "AI 生成了 Brief 草稿",
    seed: 2,
  },
  {
    id: "p4",
    name: "工单系统 PRD 审查",
    summary: "审查一份已有的客服工单系统 PRD。",
    step: "交付",
    next: "已导出 v4",
    pending: 0,
    updated: "10月28日",
    last: "你导出了 Markdown",
    seed: 5,
    done: true,
  },
];

export const ENTRY_MODES = [
  { key: "idea", label: "从想法开始", hint: "用一两句话描述你的产品想法……" },
  {
    key: "brief",
    label: "从已有需求开始",
    hint: "粘贴业务需求、会议纪要或初步方案……",
  },
  { key: "review", label: "审查已有 PRD", hint: "粘贴已有 PRD 的正文……" },
] as const;

export type EntryMode = (typeof ENTRY_MODES)[number]["key"];
