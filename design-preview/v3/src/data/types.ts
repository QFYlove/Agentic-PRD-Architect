export type PageKey = "workspace" | "explore" | "editor";

export type StageKey =
  | "explore"
  | "solution"
  | "brief"
  | "prd"
  | "review"
  | "deliver";

export interface Stage {
  key: StageKey;
  index: string;
  label: string;
  en: string;
}

export const STAGES: Stage[] = [
  { key: "explore", index: "01", label: "需求探索", en: "Explore" },
  { key: "solution", index: "02", label: "产品方案", en: "Solution" },
  { key: "brief", index: "03", label: "Product Brief", en: "Brief" },
  { key: "prd", index: "04", label: "PRD", en: "Document" },
  { key: "review", index: "05", label: "审查", en: "Review" },
  { key: "deliver", index: "06", label: "交付", en: "Deliver" },
];

/** Status of a baseline item. Mirrors section 3.4 of the product definition. */
export type ItemStatus =
  | "confirmed"
  | "inferred"
  | "assumption"
  | "proposed"
  | "open"
  | "rejected";

export const STATUS_LABEL: Record<ItemStatus, string> = {
  confirmed: "已确认",
  inferred: "AI 推断",
  assumption: "假设",
  proposed: "AI 建议",
  open: "待确认",
  rejected: "已拒绝",
};

export type Priority = "P0" | "P1" | "P2";

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
  index: string;
  title: string;
  en: string;
  priority: Priority;
}

export interface ItemSource {
  kind: "user" | "ai";
  round: number;
}

export interface BaselineItem {
  id: string;
  group: GroupKey;
  content: string;
  status: ItemStatus;
  source: ItemSource;
  /** Earlier wordings, newest last. */
  history?: string[];
}

export type FindingKind =
  | "completeness"
  | "consistency"
  | "scenario"
  | "risk"
  | "opportunity";

export const FINDING_KIND: Record<
  FindingKind,
  { code: string; label: string }
> = {
  completeness: { code: "A", label: "需求完整性" },
  consistency: { code: "B", label: "逻辑一致性" },
  scenario: { code: "C", label: "场景遗漏" },
  risk: { code: "D", label: "产品风险" },
  opportunity: { code: "E", label: "产品机会" },
};

export type ExploreFindingStatus =
  | "open"
  | "accepted"
  | "deferred"
  | "rejected"
  | "resolved";

export interface ExploreFinding {
  id: string;
  kind: FindingKind;
  title: string;
  evidence: string;
  impact: string;
  recommendation: string;
  related: string[];
  status: ExploreFindingStatus;
}

export interface Question {
  id: string;
  priority: Priority;
  text: string;
  purpose: string;
  target: GroupKey;
  finding?: string;
}

export type ExtractionAction = "created" | "updated";

export interface Extraction {
  id: string;
  action: ExtractionAction;
}

export interface UserTurn {
  kind: "user";
  round: number;
  text: string;
  extracted: Extraction[];
  skipped?: string[];
}

export interface AiTurn {
  kind: "ai";
  round: number;
  summary: string;
  questions: Question[];
  findings: string[];
}

export type Turn = UserTurn | AiTurn;

export type QuestionState = "pending" | "answered" | "skipped" | "unknown";
