export type Space = "explore" | "document";

export type Route = { page: "home" } | { page: "project"; space: Space };

/** The five steps a project moves through. Shown as progress, not as tabs. */
export const STEPS = [
  "需求探索",
  "Product Brief",
  "PRD",
  "审查",
  "交付",
] as const;
export type Step = (typeof STEPS)[number];

// ---------- Requirement baseline ----------

export type GroupKey =
  | "position"
  | "goal"
  | "user"
  | "problem"
  | "scenario"
  | "alternative"
  | "solution"
  | "feature"
  | "constraint"
  | "assumption"
  | "decision"
  | "open";

export interface Group {
  key: GroupKey;
  label: string;
  /** Core (P0) information the AI asks about first. */
  core: boolean;
}

/** Mirrors section 3.4 of the product definition (Rejected items are hidden). */
export type ItemStatus =
  | "confirmed"
  | "inferred"
  | "proposed"
  | "assumption"
  | "open";

export const STATUS_TEXT: Record<ItemStatus, string> = {
  confirmed: "已确认",
  inferred: "AI 推断",
  proposed: "AI 建议",
  assumption: "假设",
  open: "待确认",
};

export interface Item {
  id: string;
  group: GroupKey;
  text: string;
  status: ItemStatus;
  source: "you" | "ai";
  round: number;
  /** Why the AI inferred or proposed it. Shown when the user is asked to decide. */
  reason?: string;
  previous?: string[];
}

export type InsightKind =
  | "gap"
  | "conflict"
  | "scenario"
  | "risk"
  | "opportunity";

export const INSIGHT_TEXT: Record<InsightKind, string> = {
  gap: "信息缺口",
  conflict: "逻辑冲突",
  scenario: "场景遗漏",
  risk: "产品风险",
  opportunity: "产品机会",
};

export type InsightState = "open" | "accepted" | "later" | "dismissed";

export interface Insight {
  id: string;
  kind: InsightKind;
  title: string;
  basis: string;
  suggestion: string;
  related: string[];
  state: InsightState;
}

export interface Change {
  item: string;
  kind: "added" | "updated";
}

export interface YouMessage {
  id: string;
  from: "you";
  round: number;
  text: string;
  changes: Change[];
  skipped?: string[];
}

export interface AiMessage {
  id: string;
  from: "ai";
  round: number;
  text: string;
  insights?: string[];
}

export type Message = YouMessage | AiMessage;

export interface Question {
  id: string;
  text: string;
  why: string;
  group: GroupKey;
  insight?: string;
  draft?: string;
}

export type AnswerState =
  | { kind: "answer"; text: string }
  | { kind: "skip" }
  | { kind: "unsure" };

// ---------- Document ----------

export type Reviewer = "tech" | "ux" | "biz";

export const REVIEWER_TEXT: Record<Reviewer, string> = {
  tech: "技术",
  ux: "体验",
  biz: "商业",
};

export type Severity = "high" | "medium" | "low";

export const SEVERITY_TEXT: Record<Severity, string> = {
  high: "必须修改",
  medium: "建议修改",
  low: "可选",
};

export type NoteState =
  | "open"
  | "accepted"
  | "modified"
  | "later"
  | "dismissed"
  | "resolved"
  | "recheck";

export const NOTE_STATE_TEXT: Record<NoteState, string> = {
  open: "待处理",
  accepted: "已采纳",
  modified: "修改后采纳",
  later: "稍后处理",
  dismissed: "已忽略",
  resolved: "已解决",
  recheck: "需重新确认",
};

export interface ReviewNote {
  id: string;
  reviewer: Reviewer;
  severity: Severity;
  section: string;
  title: string;
  quote: string;
  problem: string;
  suggestion: string;
  state: NoteState;
  userNote?: string;
}

export interface Section {
  id: string;
  num: string;
  title: string;
  level: 1 | 2;
  body: string;
  by: "ai" | "you";
  /** Baseline items this section is derived from. */
  sources: string[];
  /** Sections to recheck when this one changes. */
  impacts: string[];
}

export interface DiffLine {
  kind: "same" | "add" | "del";
  text: string;
  why?: string;
}

export interface Version {
  id: string;
  label: string;
  by: string;
  time: string;
  note: string;
}
