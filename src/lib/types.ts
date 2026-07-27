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
export type RevisionSource = ReviewRole | "user";
export type RevisionPriority = "high" | "medium" | "low";

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

export interface RoleReview {
  role: ReviewRole;
  score: number;
  summary: string;
  strengths: string[];
  feedback: string[];
}

export interface EvaluationResult {
  tech: RoleReview;
  ux: RoleReview;
  biz: RoleReview;
  overall_score: number;
  combined_feedback: string[];
}

export interface RevisionItem {
  source_role: RevisionSource;
  source_roles: RevisionSource[];
  issue: string;
  required_change: string;
  target_section: string;
  priority: RevisionPriority;
}

export interface RevisionPlan {
  iteration: number;
  objective: string;
  items: RevisionItem[];
  user_override?: string | null;
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
}

export interface PRDVersion {
  version: number;
  content: string;
  created_at: string;
  evaluation?: EvaluationResult | null;
  revision_plan?: RevisionPlan | null;
  token_usage: TokenUsage;
}

export interface RunSnapshot {
  run_id: string;
  user_idea: string;
  target_audience?: string | null;
  user_constraints?: string | null;
  current_iteration: number;
  max_iterations: number;
  quality_threshold: number;
  status: RunStatus;
  active_node?: string | null;
  versions: PRDVersion[];
  current_prd: string;
  latest_evaluation?: EvaluationResult | null;
  reviews: Partial<Record<ReviewRole, RoleReview>>;
  pending_revision_plan?: RevisionPlan | null;
  pending_user_override?: string | null;
  node_statuses: Record<string, NodeStatus>;
  total_tokens: TokenUsage;
  node_tokens: Record<string, TokenUsage>;
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
}

export interface RunSummary {
  run_id: string;
  user_idea: string;
  status: RunStatus;
  current_iteration: number;
  max_iterations: number;
  latest_score?: number | null;
  created_at: string;
  updated_at: string;
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
