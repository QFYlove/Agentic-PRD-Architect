// Types for the /api/v3 project workspace. Mirrors backend/v3/models.py.

export type EntryMode = "idea" | "requirement" | "review";
export type Depth = "brief" | "detailed";
export type ItemStatus =
  | "confirmed"
  | "inferred"
  | "assumption"
  | "proposed"
  | "open"
  | "rejected";
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
export type Reviewer = "analyst" | "product" | "ux" | "tech" | "biz";
export type Severity = "must_fix" | "should_fix" | "optional";
export type FindingStatus =
  | "open"
  | "accepted"
  | "modified"
  | "rejected"
  | "deferred"
  | "resolved"
  | "stale";
export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";
export type Stage = "explore" | "brief" | "prd" | "review" | "deliver";

export interface Group {
  key: GroupKey;
  label: string;
  prefix: string;
  core: boolean;
}

export interface Meta {
  groups: Group[];
  mock: boolean;
  provider: string;
  model: string;
}

export interface JobError {
  code: string;
  message: string;
  retryable: boolean;
  recovery_action: string | null;
  trace_id: string | null;
}

export interface Job {
  id: string;
  project_id: string;
  kind: string;
  status: JobStatus;
  result: Record<string, unknown>;
  error: JobError | null;
  usage: { input_tokens: number; output_tokens: number; total_tokens: number };
  cost: number | null;
  latest_sequence: number;
  events_url: string;
  created_at: string;
}

export interface JobEvent {
  job_id: string;
  sequence: number;
  event: string;
  payload: Record<string, unknown>;
}

export interface ProjectSummary {
  id: string;
  code: string;
  name: string;
  entry_mode: EntryMode;
  depth: Depth;
  round: number;
  doc_title: string;
  outline_confirmed_at: string | null;
  updated_at: string;
  created_at: string;
  stage: Stage;
  counts: {
    questions: number;
    decide: number;
    items: number;
    sections: number;
    written: number;
    open_findings: number;
    blocking: number;
  };
  brief_version: number | null;
  active_job: Job | null;
}

export interface Change {
  item: string;
  kind: "added" | "updated";
}

export interface Message {
  id: string;
  round: number;
  role: "user" | "ai";
  kind: string;
  content: string;
  answers: {
    question: string;
    text: string;
    kind: string;
    answer: string;
  }[];
  changes: Change[];
  finding_codes: string[];
  created_at: string;
}

export interface Question {
  id: string;
  code: string;
  round: number;
  priority: "P0" | "P1" | "P2";
  text: string;
  purpose: string;
  target_group: GroupKey;
  finding_code: string | null;
  state: "pending" | "answered" | "skipped" | "unknown";
  answer: string | null;
}

export interface Conversation {
  round: number;
  messages: Message[];
  questions: Question[];
}

export interface Item {
  id: string;
  code: string;
  group: GroupKey;
  content: string;
  status: ItemStatus;
  source_kind: "user" | "ai";
  source_round: number;
  source_quote: string | null;
  priority: "P0" | "P1" | "P2";
  reason: string | null;
  links: string[];
  updated_at: string;
}

export interface Revision {
  id: string;
  before_content: string | null;
  after_content: string;
  before_status: ItemStatus | null;
  after_status: ItemStatus;
  actor: string;
  reason: string | null;
  created_at: string;
}

export interface Opportunity {
  user_problem: string;
  current_solution: string;
  shortfall: string;
  value: string;
  cost: string;
  assumptions: string[];
}

export interface Finding {
  id: string;
  code: string;
  scope: "baseline" | "prd";
  reviewer: Reviewer;
  reviewers: Reviewer[];
  kind: string;
  severity: Severity;
  title: string;
  category: string;
  section: string | null;
  evidence: string;
  evidence_verified: boolean;
  problem: string;
  cause: string | null;
  impact: string;
  recommendation: string;
  confidence: number | null;
  opportunity: Opportunity | null;
  related_items: string[];
  related_sections: string[];
  brief_version: number | null;
  status: FindingStatus;
  verification: string;
  user_note: string | null;
  updated_at: string;
}

export interface FindingEvent {
  id: string;
  from_status: string | null;
  to_status: string;
  actor: string;
  note: string | null;
  created_at: string;
}

export interface BriefSection {
  key: string;
  title: string;
  text: string;
  item_codes: string[];
  edited: boolean;
}

export interface Brief {
  id: string;
  version: number;
  sections: BriefSection[];
  unconfirmed_count: number;
  confirmed_at: string | null;
  created_at: string;
}

export interface Section {
  id: string;
  code: string;
  position: number;
  level: number;
  num: string;
  title: string;
  goal: string;
  contents: string[];
  item_codes: string[];
  depends: string[];
  open_points: string[];
  body: string;
  origin: "ai" | "optimized" | "human";
  status: "planned" | "generating" | "done" | "failed";
  needs_recheck: boolean;
  error: string | null;
  row_version: number;
}

export interface SectionList {
  title: string;
  outline_confirmed: boolean;
  items: Section[];
}

export interface Impact {
  change: string;
  sections: string[];
  stale: string[];
}

export interface VersionSummary {
  id: string;
  number: number;
  label: string;
  source: string;
  actor: string;
  note: string;
  finding_codes: string[];
  section_codes: string[];
  created_at: string;
}

export interface VersionDetail extends VersionSummary {
  sections: {
    code: string;
    num: string;
    level: number;
    title: string;
    body: string;
  }[];
}

export interface DiffSection {
  code: string;
  num: string;
  title: string;
  kind: "added" | "changed" | "removed";
  lines: { kind: "same" | "add" | "del"; text: string }[];
}

export interface ReviewResult {
  id: string;
  reviewer: Reviewer;
  summary: string;
  strengths: string[];
  risks: string[];
  blocking: boolean;
  dimension_scores: { dimension: string; score: number; rationale: string }[];
  score: number | null;
  finding_codes: string[];
  filtered_findings: number;
  scope: string[];
  created_at: string;
}

export interface ProposalChange {
  id: string;
  change_type: "ADD" | "UPDATE" | "REMOVE" | "CONSOLIDATE" | "RETAIN";
  section_code: string;
  new_title: string | null;
  reason: string;
  before: string;
  after: string;
  finding_codes: string[];
  affected_sections: string[];
  must_preserve: string[];
  human_section: boolean;
  warnings: string[];
  state: "pending" | "applied" | "skipped";
}

export interface Proposal {
  id: string;
  code: string;
  status: "pending" | "applied" | "partial" | "discarded";
  objective: string;
  declined: { finding_code: string; reason: string }[];
  changes: ProposalChange[];
  created_at: string;
}

export interface QualityView {
  value: number | null;
  reason?: string;
  formula?: string;
  details: string[];
}

export interface Quality {
  document_quality: QualityView;
  requirement_maturity: QualityView & { missing_core?: string[] };
  implementation_readiness: QualityView;
  risks: {
    blocking: number;
    open_findings: number;
    stale_findings: number;
    deferred_findings: number;
    open_items: number;
    assumptions: number;
    unverified_evidence: number;
  };
}

export interface Sources {
  items: { code: string; group: string; status: ItemStatus; content: string }[];
  depends: string[];
  findings: string[];
}
