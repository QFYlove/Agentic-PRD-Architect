import type {
  CreateRunRequest,
  ErrorResponse,
  FeedbackItem,
  FeedbackSeverity,
  RoleReview,
  RunEvent,
  RunEventType,
  RunListResponse,
  RunSnapshot,
  RunStatus,
} from "./types";

const RUN_STATUSES: ReadonlySet<string> = new Set([
  "QUEUED",
  "GENERATING",
  "REVIEWING",
  "AGGREGATING",
  "OPTIMIZING",
  "PAUSE_REQUESTED",
  "PAUSED",
  "CANCEL_REQUESTED",
  "COMPLETED",
  "MAX_ITERATIONS_REACHED",
  "CANCELLED",
  "FAILED",
]);

const RUN_EVENT_TYPES: ReadonlySet<string> = new Set([
  "run_started",
  "status_changed",
  "node_started",
  "prd_delta",
  "prd_stream_reset",
  "prd_generated",
  "review_completed",
  "scores_updated",
  "revision_planned",
  "pause_requested",
  "run_paused",
  "run_resumed",
  "telemetry_updated",
  "run_completed",
  "max_iterations_reached",
  "run_cancelled",
  "run_failed",
]);

const FEEDBACK_SEVERITIES: ReadonlySet<string> = new Set([
  "must_fix",
  "should_fix",
  "optional",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isFeedbackSeverity(value: unknown): value is FeedbackSeverity {
  return isString(value) && FEEDBACK_SEVERITIES.has(value);
}

/**
 * One reviewer finding, from whatever shape the wire actually carried.
 *
 * The backend coerces legacy `string` feedback on load, so structured items are
 * what a current server sends. This still accepts a bare string and an unknown
 * severity, mapping both to `should_fix`: a finding whose tier cannot be read
 * must never be promoted to a blocker, because that would show a red "必须修复"
 * on a run that never had one.
 */
function normalizeFeedbackItem(value: unknown): FeedbackItem | null {
  if (isString(value)) {
    const text = value.trim();
    return text === ""
      ? null
      : { severity: "should_fix", issue: text, recommendation: text };
  }
  if (!isRecord(value)) {
    return null;
  }
  const issue = isString(value.issue) ? value.issue.trim() : "";
  const recommendation = isString(value.recommendation)
    ? value.recommendation.trim()
    : "";
  if (issue === "" && recommendation === "") {
    return null;
  }
  return {
    severity: isFeedbackSeverity(value.severity)
      ? value.severity
      : "should_fix",
    issue: issue === "" ? recommendation : issue,
    recommendation: recommendation === "" ? issue : recommendation,
  };
}

export function normalizeFeedback(value: unknown): FeedbackItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map(normalizeFeedbackItem)
    .filter((item): item is FeedbackItem => item !== null);
}

/** A reviewer payload with its feedback list guaranteed structured. */
export function normalizeReview(review: RoleReview): RoleReview {
  return { ...review, feedback: normalizeFeedback(review.feedback) };
}

export function parseCreateRunRequest(value: unknown): CreateRunRequest {
  if (
    !isRecord(value) ||
    !isString(value.user_idea) ||
    value.user_idea.length < 10 ||
    !isFiniteNumber(value.quality_threshold) ||
    !isFiniteNumber(value.max_iterations)
  ) {
    throw new TypeError("Invalid CreateRunRequest contract");
  }
  return value as unknown as CreateRunRequest;
}

export function parseRunSnapshot(value: unknown): RunSnapshot {
  if (
    !isRecord(value) ||
    !isString(value.run_id) ||
    !isString(value.user_idea) ||
    !isString(value.status) ||
    !RUN_STATUSES.has(value.status) ||
    !Array.isArray(value.versions) ||
    !isFiniteNumber(value.latest_event_sequence) ||
    !isRecord(value.total_tokens)
  ) {
    throw new TypeError("Invalid RunSnapshot contract");
  }
  return value as unknown as RunSnapshot;
}

export function parseRunListResponse(value: unknown): RunListResponse {
  if (
    !isRecord(value) ||
    !Array.isArray(value.items) ||
    !isFiniteNumber(value.total)
  ) {
    throw new TypeError("Invalid RunListResponse");
  }
  for (const item of value.items) {
    if (
      !isRecord(item) ||
      !isString(item.run_id) ||
      !isString(item.user_idea) ||
      !isString(item.status) ||
      !RUN_STATUSES.has(item.status) ||
      !isFiniteNumber(item.current_iteration) ||
      !isFiniteNumber(item.max_iterations) ||
      !isString(item.created_at) ||
      !isString(item.updated_at)
    ) {
      throw new TypeError("Invalid RunSummary");
    }
  }
  return value as unknown as RunListResponse;
}

export function parseRunEvent(value: unknown): RunEvent {
  if (
    !isRecord(value) ||
    !isString(value.run_id) ||
    !isFiniteNumber(value.sequence) ||
    !isString(value.event) ||
    !RUN_EVENT_TYPES.has(value.event) ||
    !isString(value.timestamp) ||
    !isFiniteNumber(value.iteration) ||
    !isRecord(value.payload)
  ) {
    throw new TypeError("Invalid RunEvent contract");
  }
  return value as unknown as RunEvent;
}

export function parseErrorResponse(value: unknown): ErrorResponse {
  if (
    !isRecord(value) ||
    !isRecord(value.error) ||
    !isString(value.error.code) ||
    !isString(value.error.message) ||
    !isString(value.error.request_id)
  ) {
    throw new TypeError("Invalid ErrorResponse contract");
  }
  return value as unknown as ErrorResponse;
}

export function isRunStatus(value: string): value is RunStatus {
  return RUN_STATUSES.has(value);
}

export function isRunEventType(value: string): value is RunEventType {
  return RUN_EVENT_TYPES.has(value);
}
