export type RunStatus =
  | "QUEUED"
  | "GENERATING"
  | "REVIEWING"
  | "AGGREGATING"
  | "OPTIMIZING"
  | "PAUSE_REQUESTED"
  | "PAUSED"
  | "CANCEL_REQUESTED"
  | "COMPLETED"
  | "MAX_ITERATIONS_REACHED"
  | "CANCELLED"
  | "FAILED";

export type NodeStatus =
  | "PENDING"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "SKIPPED";
export type ReviewRole = "tech" | "ux" | "biz";
export type RevisionSource = ReviewRole | "user" | "optimizer";
export type RevisionPriority = "high" | "medium" | "low";
export type ChangeType = "ADD" | "UPDATE" | "REMOVE" | "CONSOLIDATE" | "RETAIN";
export type GateStatus = "PASSED" | "NEEDS_REVISION" | "BLOCKED" | "UNSCORED";
export type GenerationMode = "standard" | "compact";
export type RecoveryMode =
  | "restart"
  | "regenerate_compact"
  | "continue_from_best";
export type RecoveryAction =
  | "retry"
  | "regenerate_compact"
  | "continue_from_best"
  | "check_configuration"
  | "edit_input"
  | "none";
export type FailureCategory =
  | "transient"
  | "permanent"
  | "output_limit"
  | "interrupted";
export type FindingStatus =
  | "resolved"
  | "partially_resolved"
  | "unresolved"
  | "declined"
  | "not_checked";

/**
 * How much a single reviewer finding is allowed to block a run.
 *
 * Only `must_fix` gates completion. The other two tiers are advice that outlives
 * a finished PRD, which is why a run can legitimately end with a dozen open
 * items and still be done.
 */
export type FeedbackSeverity = "must_fix" | "should_fix" | "optional";

/** Highest first — the order findings are grouped in for reading. */
export const FEEDBACK_SEVERITIES: readonly FeedbackSeverity[] = [
  "must_fix",
  "should_fix",
  "optional",
];

export interface FindingObservation {
  finding_id: string;
  role: ReviewRole;
  severity: FeedbackSeverity;
  problem: string;
  evidence?: string | null;
}

/**
 * One reviewer finding. The first three fields are the original contract; the
 * rest arrived with the V2 reviewer contract and are absent on legacy runs.
 */
export interface FeedbackItem {
  severity: FeedbackSeverity;
  issue: string;
  recommendation: string;
  finding_id?: string | null;
  title?: string | null;
  category?: string | null;
  section?: string | null;
  evidence?: string | null;
  user_impact?: string | null;
  source_role?: ReviewRole | null;
  source_roles?: ReviewRole[];
  merged_from?: string[];
  observations?: FindingObservation[];
  confidence?: number | null;
  severity_adjusted_from?: FeedbackSeverity | null;
}

export type RunEventType =
  | "run_started"
  | "status_changed"
  | "node_started"
  | "prd_delta"
  | "prd_stream_reset"
  | "prd_generated"
  | "review_completed"
  | "scores_updated"
  | "revision_planned"
  | "pause_requested"
  | "run_paused"
  | "run_resumed"
  | "telemetry_updated"
  | "run_completed"
  | "max_iterations_reached"
  | "run_cancelled"
  | "run_failed";

export interface CreateRunRequest {
  user_idea: string;
  target_audience?: string | null;
  user_constraints?: string | null;
  quality_threshold: number;
  max_iterations: number;
  provider_id?: string;
  model_id?: string;
  generation_mode?: GenerationMode;
}

export interface ProviderModel {
  model_id: string;
  model_display_name: string;
  capabilities?: string[] | null;
}
export interface Provider {
  provider_id: string;
  provider_display_name: string;
  models: ProviderModel[];
}
export interface ProviderCatalog {
  providers: Provider[];
}

export interface ResumeRunRequest {
  user_override?: string | null;
}

export interface CreateRunResponse {
  run_id: string;
  status: RunStatus;
  events_url: string;
  created_at: string;
}

export interface ControlResponse {
  run_id: string;
  status: RunStatus;
  message: string;
}

export interface DimensionScore {
  dimension: string;
  score: number;
  rationale: string;
  weight?: number | null;
}

export interface FindingResolution {
  finding_id: string;
  status: FindingStatus;
  note?: string | null;
  source_version?: number | null;
  title?: string | null;
  severity?: FeedbackSeverity | null;
}

export interface RoleReview {
  role: ReviewRole;
  score: number;
  summary: string;
  strengths: string[];
  feedback: FeedbackItem[];
  /** Empty or absent on reviews scored before the rubric existed. */
  dimension_scores?: DimensionScore[];
  rubric_version?: string | null;
  scoring_version?: string | null;
  filtered_findings?: number;
  resolutions?: FindingResolution[];
}

export interface EvaluationResult {
  tech: RoleReview;
  ux: RoleReview;
  biz: RoleReview;
  overall_score: number;
  combined_feedback: FeedbackItem[];
  findings_before_dedup?: number | null;
  gate_status?: GateStatus | null;
  rubric_version?: string | null;
  scoring_version?: string | null;
  finding_resolutions?: FindingResolution[];
}

export interface RevisionItem {
  source_role: RevisionSource;
  source_roles: RevisionSource[];
  issue: string;
  required_change: string;
  target_section: string;
  priority: RevisionPriority;
  item_id?: string | null;
  change_type?: ChangeType | null;
  source_finding_ids?: string[];
  target_sections?: string[];
  affected_sections?: string[];
  reason?: string | null;
  expected_result?: string | null;
  must_preserve?: string[];
}

export interface DeclinedFinding {
  finding_id: string;
  reason: string;
}

export interface RevisionPlan {
  iteration: number;
  objective: string;
  items: RevisionItem[];
  user_override?: string | null;
  declined_findings?: DeclinedFinding[];
  plan_version?: string | null;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface RunError {
  code: string;
  message: string;
  retryable: boolean;
  stage?: string | null;
  node?: string | null;
  version?: number | null;
  attempt?: number | null;
  recovery_action?: RecoveryAction | null;
  category?: FailureCategory | null;
  trace_id?: string | null;
  occurred_at?: string | null;
}

/** A generation that streamed text but never became a version. */
export interface IncompleteDraft {
  version: number;
  attempt: number;
  characters: number;
  error_code: string;
}

export interface QualityIssue {
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  section?: string | null;
  line?: number | null;
  excerpt?: string | null;
}

export interface PRDQualityReport {
  characters: number;
  sections: number;
  tables: number;
  list_items: number;
  paragraphs: number;
  long_paragraphs: number;
  longest_paragraph: number;
  unlabeled_figures?: number;
  structure_complete: boolean;
  missing_sections: string[];
  issues: QualityIssue[];
  budget_characters?: number | null;
}

/**
 * One node call's wall-clock cost, as the backend recorded it.
 *
 * A run that takes eight minutes says nothing about which of its six model calls
 * owned the time. One entry per completed call answers that. `succeeded: false`
 * is a call that burned time and then produced an unusable document — those are
 * exactly the ones a slow run needs to show.
 */
export interface NodeTiming {
  node: string;
  version: number;
  attempt: number;
  seconds: number;
  succeeded: boolean;
  input_tokens: number;
  output_tokens: number;
}

export interface PRDVersion {
  version: number;
  content: string;
  created_at: string;
  evaluation?: EvaluationResult | null;
  revision_plan?: RevisionPlan | null;
  token_usage: TokenUsage;
  quality?: PRDQualityReport | null;
  generation_mode?: GenerationMode | null;
}

export interface RunSnapshot {
  run_id: string;
  user_idea: string;
  target_audience?: string | null;
  user_constraints?: string | null;
  output_language?: string;
  current_iteration: number;
  max_iterations: number;
  quality_threshold: number;
  status: RunStatus;
  active_node?: string | null;
  versions: PRDVersion[];
  current_prd: string;
  /** Which generation attempt produced `current_prd`; see runReducer. */
  current_prd_attempt?: number;
  latest_evaluation?: EvaluationResult | null;
  /** Highest-scoring version so far — not necessarily the latest one. */
  best_version?: number | null;
  best_score?: number | null;
  reviews: Partial<Record<ReviewRole, RoleReview>>;
  pending_revision_plan?: RevisionPlan | null;
  pending_user_override?: string | null;
  node_statuses: Record<string, NodeStatus>;
  total_tokens: TokenUsage;
  node_tokens: Record<string, TokenUsage>;
  /**
   * Per-call durations, in the order the calls returned. Optional: a snapshot
   * written before timings existed has no such key and must still render.
   */
  node_timings?: NodeTiming[];
  estimated_cost_usd?: number | null;
  cost_available: boolean;
  is_mock: boolean;
  elapsed_seconds: number;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error?: RunError | null;
  latest_event_sequence: number;
  provider_id?: string | null;
  provider_display_name?: string | null;
  model_id?: string | null;
  model_display_name?: string | null;
  trace_id?: string | null;
  generation_mode?: GenerationMode;
  incomplete_draft?: IncompleteDraft | null;
  source_run_id?: string | null;
  source_version?: number | null;
  recovery_mode?: RecoveryMode | null;
}

export interface RunSummary {
  run_id: string;
  user_idea: string;
  status: RunStatus;
  current_iteration: number;
  max_iterations: number;
  latest_score?: number | null;
  best_version?: number | null;
  best_score?: number | null;
  created_at: string;
  updated_at: string;
  source_run_id?: string | null;
}

export interface RunListResponse {
  items: RunSummary[];
  total: number;
}

export interface RunEvent<
  TPayload extends Record<string, unknown> = Record<string, unknown>,
> {
  run_id: string;
  sequence: number;
  event: RunEventType;
  timestamp: string;
  iteration: number;
  payload: TPayload;
}

export interface RunHistoryResponse {
  items: RunEvent[];
}

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    request_id: string;
  };
}

export const TERMINAL_RUN_STATUSES = new Set<RunStatus>([
  "COMPLETED",
  "MAX_ITERATIONS_REACHED",
  "CANCELLED",
  "FAILED",
]);

export function isTerminalRunStatus(status: RunStatus): boolean {
  return TERMINAL_RUN_STATUSES.has(status);
}
