import type {
  CreateRunRequest,
  ErrorResponse,
  RunEvent,
  RunEventType,
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
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
