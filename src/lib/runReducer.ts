import type {
  NodeStatus,
  PRDVersion,
  RevisionPlan,
  ReviewRole,
  RoleReview,
  RunEvent,
  RunSnapshot,
  RunStatus,
  TokenUsage,
} from "./types";
import { localizedErrorMessage } from "./errorMessages";
import { isTerminalRunStatus } from "./types";

export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "open"
  | "recovering"
  | "closed";

export interface VersionDraft {
  version: number;
  attempt: number;
  content: string;
  complete: boolean;
}

export interface VersionScore {
  version: number;
  tech: number;
  ux: number;
  biz: number;
  overall: number;
}

export interface RunViewState {
  runId: string | null;
  snapshot: RunSnapshot | null;
  status: RunStatus | null;
  connection: ConnectionStatus;
  latestSequence: number;
  events: RunEvent[];
  drafts: Record<number, VersionDraft>;
  reviewsByVersion: Record<number, Partial<Record<ReviewRole, RoleReview>>>;
  scoresByVersion: Record<number, VersionScore>;
  selectedVersion: number | null;
  selectionPinned: boolean;
  pendingRevisionPlan: RevisionPlan | null;
  isCreating: boolean;
  pendingControl: "pause" | "resume" | "cancel" | null;
  error: string | null;
}

export const initialRunViewState: RunViewState = {
  runId: null,
  snapshot: null,
  status: null,
  connection: "idle",
  latestSequence: 0,
  events: [],
  drafts: {},
  reviewsByVersion: {},
  scoresByVersion: {},
  selectedVersion: null,
  selectionPinned: false,
  pendingRevisionPlan: null,
  isCreating: false,
  pendingControl: null,
  error: null,
};

export type RunAction =
  | { type: "CREATE_STARTED" }
  | { type: "RUN_SELECTED"; runId: string }
  | { type: "SNAPSHOT_LOADED"; snapshot: RunSnapshot }
  | { type: "EVENT_RECEIVED"; event: RunEvent }
  | { type: "CONNECTION_CHANGED"; connection: ConnectionStatus }
  | {
      type: "CONTROL_STARTED";
      control: "pause" | "resume" | "cancel";
    }
  | { type: "CONTROL_FINISHED" }
  | { type: "STATUS_UPDATED"; status: RunStatus }
  | { type: "VERSION_SELECTED"; version: number }
  | { type: "ERROR"; message: string }
  | { type: "CLEAR_ERROR" }
  | { type: "RESET" };

function numberPayload(
  payload: Record<string, unknown>,
  key: string,
  fallback: number,
): number {
  return typeof payload[key] === "number" ? payload[key] : fallback;
}

function stringPayload(
  payload: Record<string, unknown>,
  key: string,
): string | null {
  return typeof payload[key] === "string" ? payload[key] : null;
}

function statusPayload(payload: Record<string, unknown>): RunStatus | null {
  return typeof payload.current === "string"
    ? (payload.current as RunStatus)
    : null;
}

function versionsFromSnapshot(
  versions: PRDVersion[],
): Record<number, VersionDraft> {
  return Object.fromEntries(
    versions.map((version) => [
      version.version,
      {
        version: version.version,
        attempt: 1,
        content: version.content,
        complete: true,
      },
    ]),
  );
}

function reviewsFromSnapshot(
  snapshot: RunSnapshot,
): Record<number, Partial<Record<ReviewRole, RoleReview>>> {
  const entries: Array<[number, Partial<Record<ReviewRole, RoleReview>>]> = [];
  for (const version of snapshot.versions) {
    const evaluation = version.evaluation;
    if (evaluation) {
      entries.push([
        version.version,
        {
          tech: evaluation.tech,
          ux: evaluation.ux,
          biz: evaluation.biz,
        },
      ]);
    }
  }
  if (Object.keys(snapshot.reviews).length > 0) {
    entries.push([snapshot.current_iteration, snapshot.reviews]);
  }
  return Object.fromEntries(entries);
}

function scoresFromSnapshot(
  versions: PRDVersion[],
): Record<number, VersionScore> {
  return Object.fromEntries(
    versions
      .filter((version) => version.evaluation)
      .map((version) => {
        const evaluation = version.evaluation!;
        return [
          version.version,
          {
            version: version.version,
            tech: evaluation.tech.score,
            ux: evaluation.ux.score,
            biz: evaluation.biz.score,
            overall: evaluation.overall_score,
          },
        ];
      }),
  );
}

function withNodeStatus(
  snapshot: RunSnapshot | null,
  node: string,
  status: NodeStatus,
): RunSnapshot | null {
  if (!snapshot) {
    return null;
  }
  return {
    ...snapshot,
    active_node:
      status === "RUNNING"
        ? node
        : snapshot.active_node === node
          ? null
          : (snapshot.active_node ?? null),
    node_statuses: { ...snapshot.node_statuses, [node]: status },
  };
}

function withTelemetry(
  snapshot: RunSnapshot | null,
  payload: Record<string, unknown>,
): RunSnapshot | null {
  if (!snapshot) {
    return null;
  }
  const tokens = payload.tokens as TokenUsage | undefined;
  return {
    ...snapshot,
    total_tokens: tokens ?? snapshot.total_tokens,
    estimated_cost_usd:
      typeof payload.cost === "number"
        ? payload.cost
        : payload.cost === null
          ? null
          : (snapshot.estimated_cost_usd ?? null),
    cost_available:
      typeof payload.cost_available === "boolean"
        ? payload.cost_available
        : snapshot.cost_available,
    is_mock:
      typeof payload.mock === "boolean" ? payload.mock : snapshot.is_mock,
    elapsed_seconds:
      typeof payload.elapsed === "number"
        ? payload.elapsed
        : snapshot.elapsed_seconds,
  };
}

function applyEvent(state: RunViewState, event: RunEvent): RunViewState {
  const payload = event.payload;
  const version = numberPayload(payload, "version", event.iteration);
  const next: RunViewState = {
    ...state,
    latestSequence: event.sequence,
    events: [...state.events, event],
    error: null,
  };

  switch (event.event) {
    case "status_changed":
    case "pause_requested": {
      const status = statusPayload(payload);
      return status ? { ...next, status } : next;
    }
    case "run_paused":
      return { ...next, status: "PAUSED" };
    case "run_resumed":
      return { ...next, status: "OPTIMIZING" };
    case "node_started": {
      const node = stringPayload(payload, "node");
      return node
        ? { ...next, snapshot: withNodeStatus(next.snapshot, node, "RUNNING") }
        : next;
    }
    case "prd_stream_reset": {
      const attempt = numberPayload(payload, "attempt", 1);
      const current = state.drafts[version];
      if (current && attempt <= current.attempt) {
        return next;
      }
      return {
        ...next,
        drafts: {
          ...state.drafts,
          [version]: { version, attempt, content: "", complete: false },
        },
      };
    }
    case "prd_delta": {
      const attempt = numberPayload(payload, "attempt", 1);
      const delta = stringPayload(payload, "delta") ?? "";
      const current = state.drafts[version];
      if (current && (current.complete || current.attempt !== attempt)) {
        return next;
      }
      if (!current && attempt !== 1) {
        return next;
      }
      return {
        ...next,
        drafts: {
          ...state.drafts,
          [version]: {
            version,
            attempt,
            content: `${current?.content ?? ""}${delta}`,
            complete: false,
          },
        },
        selectedVersion: state.selectionPinned
          ? state.selectedVersion
          : version,
      };
    }
    case "prd_generated": {
      const attempt = numberPayload(payload, "attempt", 1);
      const content = stringPayload(payload, "content") ?? "";
      return {
        ...next,
        drafts: {
          ...state.drafts,
          [version]: { version, attempt, content, complete: true },
        },
        selectedVersion: state.selectionPinned
          ? state.selectedVersion
          : version,
        snapshot: withNodeStatus(next.snapshot, "generator", "SUCCEEDED"),
      };
    }
    case "review_completed": {
      const review = payload as unknown as RoleReview;
      if (!["tech", "ux", "biz"].includes(review.role)) {
        return next;
      }
      return {
        ...next,
        reviewsByVersion: {
          ...state.reviewsByVersion,
          [event.iteration]: {
            ...state.reviewsByVersion[event.iteration],
            [review.role]: review,
          },
        },
        snapshot: withNodeStatus(
          next.snapshot,
          `${review.role}_reviewer`,
          "SUCCEEDED",
        ),
      };
    }
    case "scores_updated": {
      return {
        ...next,
        scoresByVersion: {
          ...state.scoresByVersion,
          [event.iteration]: {
            version: event.iteration,
            tech: numberPayload(payload, "tech", 0),
            ux: numberPayload(payload, "ux", 0),
            biz: numberPayload(payload, "biz", 0),
            overall: numberPayload(payload, "overall", 0),
          },
        },
        snapshot: withNodeStatus(next.snapshot, "aggregator", "SUCCEEDED"),
      };
    }
    case "revision_planned": {
      const plan = payload.revision_plan as RevisionPlan | undefined;
      return {
        ...next,
        pendingRevisionPlan: plan ?? null,
        snapshot: withNodeStatus(next.snapshot, "optimizer", "SUCCEEDED"),
      };
    }
    case "telemetry_updated":
      return { ...next, snapshot: withTelemetry(next.snapshot, payload) };
    case "run_completed":
      return { ...next, status: "COMPLETED", connection: "closed" };
    case "max_iterations_reached":
      return {
        ...next,
        status: "MAX_ITERATIONS_REACHED",
        connection: "closed",
      };
    case "run_cancelled":
      return { ...next, status: "CANCELLED", connection: "closed" };
    case "run_failed":
      return {
        ...next,
        status: "FAILED",
        connection: "closed",
        error: localizedErrorMessage(stringPayload(payload, "code")),
      };
    default:
      return next;
  }
}

export function runReducer(
  state: RunViewState,
  action: RunAction,
): RunViewState {
  switch (action.type) {
    case "CREATE_STARTED":
      return { ...initialRunViewState, isCreating: true };
    case "RUN_SELECTED":
      return {
        ...initialRunViewState,
        runId: action.runId,
        connection: "connecting",
      };
    case "SNAPSHOT_LOADED": {
      const snapshot = action.snapshot;
      const drafts = versionsFromSnapshot(snapshot.versions);
      if (
        snapshot.current_prd &&
        drafts[snapshot.current_iteration] === undefined
      ) {
        drafts[snapshot.current_iteration] = {
          version: snapshot.current_iteration,
          attempt: 1,
          content: snapshot.current_prd,
          complete: false,
        };
      }
      const availableVersions = Object.keys(drafts).map(Number);
      const selectedVersion =
        state.selectionPinned &&
        state.selectedVersion !== null &&
        availableVersions.includes(state.selectedVersion)
          ? state.selectedVersion
          : (availableVersions.at(-1) ?? null);
      return {
        ...state,
        runId: snapshot.run_id,
        snapshot,
        status: snapshot.status,
        latestSequence: snapshot.latest_event_sequence,
        drafts,
        reviewsByVersion: reviewsFromSnapshot(snapshot),
        scoresByVersion: scoresFromSnapshot(snapshot.versions),
        selectedVersion,
        selectionPinned:
          state.selectionPinned && selectedVersion === state.selectedVersion,
        pendingRevisionPlan: snapshot.pending_revision_plan ?? null,
        isCreating: false,
        pendingControl: null,
        error: snapshot.error
          ? localizedErrorMessage(snapshot.error.code)
          : null,
      };
    }
    case "EVENT_RECEIVED":
      if (
        action.event.run_id !== state.runId ||
        action.event.sequence <= state.latestSequence ||
        (state.status !== null && isTerminalRunStatus(state.status))
      ) {
        return state;
      }
      return applyEvent(state, action.event);
    case "CONNECTION_CHANGED":
      return { ...state, connection: action.connection };
    case "CONTROL_STARTED":
      return { ...state, pendingControl: action.control, error: null };
    case "CONTROL_FINISHED":
      return { ...state, pendingControl: null };
    case "STATUS_UPDATED":
      return { ...state, status: action.status, pendingControl: null };
    case "VERSION_SELECTED":
      return {
        ...state,
        selectedVersion: action.version,
        selectionPinned: true,
      };
    case "ERROR":
      return {
        ...state,
        isCreating: false,
        pendingControl: null,
        error: action.message,
      };
    case "CLEAR_ERROR":
      return { ...state, error: null };
    case "RESET":
      return initialRunViewState;
  }
}
