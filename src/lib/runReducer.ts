import type {
  EvaluationResult,
  FeedbackItem,
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
import { normalizeFeedback, normalizeReview } from "./contracts";
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

/** Open findings for one version, split by how much each one blocks. */
export interface SeverityCounts {
  mustFix: number;
  shouldFix: number;
  optional: number;
}

export interface VersionScore {
  version: number;
  tech: number;
  ux: number;
  biz: number;
  overall: number;
  /**
   * Findings still open on this version. Carried next to the score because
   * "reached the target" and "one blocking gap remains" are two independent
   * facts and the reader needs both at once.
   */
  severity: SeverityCounts;
}

export const EMPTY_SEVERITY_COUNTS: SeverityCounts = {
  mustFix: 0,
  shouldFix: 0,
  optional: 0,
};

export function countSeverities(items: FeedbackItem[]): SeverityCounts {
  return {
    mustFix: items.filter((item) => item.severity === "must_fix").length,
    shouldFix: items.filter((item) => item.severity === "should_fix").length,
    optional: items.filter((item) => item.severity === "optional").length,
  };
}

/**
 * Severity counts for an evaluation, preferring the aggregator's own combined
 * list and falling back to the three reviews it was built from -- a snapshot
 * written before `combined_feedback` was populated still has the reviews.
 */
function severitiesFromEvaluation(
  evaluation: EvaluationResult,
): SeverityCounts {
  const combined =
    evaluation.combined_feedback.length > 0
      ? evaluation.combined_feedback
      : [
          ...evaluation.tech.feedback,
          ...evaluation.ux.feedback,
          ...evaluation.biz.feedback,
        ];
  // Normalized first: a snapshot stored before severity existed holds bare
  // strings, and counting those as blockers would un-complete a finished run.
  return countSeverities(normalizeFeedback(combined));
}

/**
 * A revision plan placed on the two versions it connects.
 *
 * The backend writes the plan onto the version it produced
 * (`PRDVersion.revision_plan`) and stamps it with the reviewed iteration it
 * came from (`RevisionPlan.iteration`), so both ends are always recoverable --
 * including for historical versions after a reconnect.
 */
export interface VersionRevisionPlan {
  /** The reviewed version whose findings produced this plan. */
  sourceVersion: number;
  /** The version this plan was used to generate. */
  targetVersion: number;
  plan: RevisionPlan;
}

/**
 * How a run ended, in the terms the product promises.
 *
 * `quality_threshold` is an early-stop goal and `max_iterations` is an attempt
 * budget, so a run can end normally without ever reaching the target. When that
 * happens the reader has to be told two separate things: that the target was not
 * met, and which version actually scored best -- which is frequently not the
 * last one.
 *
 * The quality gate is a conjunction, so `thresholdMet` and `qualityGatePassed`
 * are separate fields rather than one flag: a run can hit 91 against a target of
 * 85 and still be held by a single blocking finding, and that state must not be
 * presented as either a failure or a finished document.
 */
export interface RunOutcome {
  thresholdMet: boolean;
  /** `thresholdMet && mustFixCount === 0`, as the server decided it. */
  qualityGatePassed: boolean;
  qualityThreshold: number;
  completedIterations: number;
  maxIterations: number;
  bestVersion: number | null;
  bestScore: number | null;
  /** Findings still open on the last scored version. */
  severity: SeverityCounts;
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
  /**
   * Plans keyed by the reviewed version that produced them, so selecting v1
   * shows the plan that turned v1 into v2 and never v2's own plan.
   */
  revisionPlansBySourceVersion: Record<number, VersionRevisionPlan>;
  /** Highest-scoring version so far. Tracks the best, not the latest. */
  bestVersion: number | null;
  bestScore: number | null;
  /** Set once the run reaches a scored ending. */
  outcome: RunOutcome | null;
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
  revisionPlansBySourceVersion: {},
  bestVersion: null,
  bestScore: null,
  outcome: null,
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

function optionalNumberPayload(
  payload: Record<string, unknown>,
  key: string,
): number | null {
  return typeof payload[key] === "number" ? payload[key] : null;
}

function statusPayload(payload: Record<string, unknown>): RunStatus | null {
  return typeof payload.current === "string"
    ? (payload.current as RunStatus)
    : null;
}

const SEVERITY_PAYLOAD_KEYS = [
  "must_fix_count",
  "should_fix_count",
  "optional_count",
] as const;

/**
 * Severity counts for a version, taken from the reviews the client already has.
 *
 * The three `review_completed` events carry the same findings the Reviewer panel
 * and the trace list, so counting them is what keeps those three views from
 * disagreeing about one set of feedback. Returns `null` when no review has
 * arrived, which is not the same fact as "no findings".
 */
function severitiesFromReviews(
  reviews: Partial<Record<ReviewRole, RoleReview>> | undefined,
): SeverityCounts | null {
  if (reviews === undefined) {
    return null;
  }
  // Already normalized on the way in, so these are structured findings.
  const items = (["tech", "ux", "biz"] as const).flatMap(
    (role) => reviews[role]?.feedback ?? [],
  );
  return items.length > 0 ? countSeverities(items) : null;
}

/**
 * Open findings by tier as a terminal or scoring event reports them.
 *
 * A backend that predates the severity contract sends none of these keys. That
 * used to read as zero blockers, which is how a run whose three reviewers listed
 * 21 findings reported 必须修复 0 · 重要改进 0 · 可选优化 0 at the top of the
 * page. So the reviews the client already received for that version are counted
 * instead, and zero is only reported when the run genuinely has no findings to
 * count -- inventing a blocker is still not allowed, but neither is erasing one.
 */
function severityFromPayload(
  payload: Record<string, unknown>,
  fromReviews: SeverityCounts | null,
): SeverityCounts {
  const reported = SEVERITY_PAYLOAD_KEYS.some(
    (key) => typeof payload[key] === "number",
  );
  if (!reported && fromReviews !== null) {
    return fromReviews;
  }
  return {
    mustFix: numberPayload(payload, "must_fix_count", 0),
    shouldFix: numberPayload(payload, "should_fix_count", 0),
    optional: numberPayload(payload, "optional_count", 0),
  };
}

/**
 * The outcome carried by a terminal scored event.
 *
 * Every field is read defensively: a snapshot written by an older backend has no
 * best-version keys, and the run must still render rather than throw.
 */
function outcomeFromPayload(
  payload: Record<string, unknown>,
  fallback: {
    completedIterations: number;
    qualityGatePassed: boolean;
    /** Counts recomputed from the final round's reviews, when the payload omits them. */
    severity: SeverityCounts | null;
  },
): RunOutcome {
  const thresholdMet = payload.threshold_met === true;
  return {
    thresholdMet,
    // An older backend sends no gate key at all. Falling back to the event that
    // carried the payload keeps its meaning: `run_completed` only ever fired for
    // a run the server considered finished.
    qualityGatePassed:
      typeof payload.quality_gate_passed === "boolean"
        ? payload.quality_gate_passed
        : fallback.qualityGatePassed && thresholdMet,
    qualityThreshold: numberPayload(payload, "quality_threshold", 0),
    completedIterations: numberPayload(
      payload,
      "completed_iterations",
      fallback.completedIterations,
    ),
    maxIterations: numberPayload(
      payload,
      "max_iterations",
      fallback.completedIterations,
    ),
    bestVersion: optionalNumberPayload(payload, "best_version"),
    bestScore: optionalNumberPayload(payload, "best_score"),
    severity: severityFromPayload(payload, fallback.severity),
  };
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
          tech: normalizeReview(evaluation.tech),
          ux: normalizeReview(evaluation.ux),
          biz: normalizeReview(evaluation.biz),
        },
      ]);
    }
  }
  if (Object.keys(snapshot.reviews).length > 0) {
    const live: Partial<Record<ReviewRole, RoleReview>> = {};
    for (const role of ["tech", "ux", "biz"] as const) {
      const review = snapshot.reviews[role];
      if (review) {
        live[role] = normalizeReview(review);
      }
    }
    entries.push([snapshot.current_iteration, live]);
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
            // Recounted from the stored reviews rather than read from a
            // persisted total, so the badge can never disagree with the
            // findings listed beneath it.
            severity: severitiesFromEvaluation(evaluation),
          },
        ];
      }),
  );
}

/**
 * The reviewed version a plan came from.
 *
 * `RevisionPlan.iteration` is the iteration the optimizer read, which is the
 * version whose reviews produced the plan. A server that omits it -- or sends
 * something that is not a usable version number -- falls back to the version
 * immediately before the one the plan produced.
 */
function planSourceVersion(plan: RevisionPlan, targetVersion: number): number {
  return typeof plan.iteration === "number" &&
    Number.isInteger(plan.iteration) &&
    plan.iteration >= 1
    ? plan.iteration
    : targetVersion - 1;
}

function revisionPlansFromSnapshot(
  snapshot: RunSnapshot,
): Record<number, VersionRevisionPlan> {
  const entries: Array<[number, VersionRevisionPlan]> = [];
  for (const version of snapshot.versions) {
    const plan = version.revision_plan;
    if (!plan) {
      continue;
    }
    const sourceVersion = planSourceVersion(plan, version.version);
    entries.push([
      sourceVersion,
      { sourceVersion, targetVersion: version.version, plan },
    ]);
  }
  const pending = snapshot.pending_revision_plan;
  if (pending) {
    // The optimizer has committed a plan but the generation it feeds has not
    // produced a version yet, so the target is the iteration the run moved to.
    const sourceVersion = planSourceVersion(
      pending,
      snapshot.current_iteration,
    );
    entries.push([
      sourceVersion,
      { sourceVersion, targetVersion: sourceVersion + 1, plan: pending },
    ]);
  }
  return Object.fromEntries(entries);
}

/**
 * Best version and score for a snapshot.
 *
 * The backend tracks both, but a snapshot stored before those fields existed has
 * neither, so they are recomputed from the per-version evaluations the snapshot
 * always carries. Ties keep the earlier version: equal quality for another round
 * of work is not an improvement.
 */
function bestFromSnapshot(snapshot: RunSnapshot): {
  bestVersion: number | null;
  bestScore: number | null;
} {
  if (
    typeof snapshot.best_version === "number" &&
    typeof snapshot.best_score === "number"
  ) {
    return {
      bestVersion: snapshot.best_version,
      bestScore: snapshot.best_score,
    };
  }
  let bestVersion: number | null = null;
  let bestScore: number | null = null;
  for (const version of snapshot.versions) {
    const score = version.evaluation?.overall_score;
    if (
      typeof score === "number" &&
      (bestScore === null || score > bestScore)
    ) {
      bestScore = score;
      bestVersion = version.version;
    }
  }
  return { bestVersion, bestScore };
}

/**
 * The outcome of an already-finished run being reopened.
 *
 * A reconnecting client never receives the terminal event again, so the outcome
 * has to be reconstructible from the snapshot alone. `COMPLETED` is the server's
 * own record that the gate passed; for a run that exhausted its budget the two
 * halves are recomputed from the final version's evaluation, because a score
 * that cleared the target while a blocker stayed open has to keep reading as
 * "target reached, gate not passed" rather than collapsing into a plain failure.
 */
function outcomeFromSnapshot(
  snapshot: RunSnapshot,
  best: { bestVersion: number | null; bestScore: number | null },
): RunOutcome | null {
  if (
    snapshot.status !== "COMPLETED" &&
    snapshot.status !== "MAX_ITERATIONS_REACHED"
  ) {
    return null;
  }
  const gatePassed = snapshot.status === "COMPLETED";
  const finalEvaluation =
    snapshot.latest_evaluation ?? snapshot.versions.at(-1)?.evaluation ?? null;
  const severity = finalEvaluation
    ? severitiesFromEvaluation(finalEvaluation)
    : EMPTY_SEVERITY_COUNTS;
  return {
    thresholdMet:
      gatePassed ||
      (finalEvaluation !== null &&
        finalEvaluation.overall_score >= snapshot.quality_threshold),
    qualityGatePassed: gatePassed,
    qualityThreshold: snapshot.quality_threshold,
    completedIterations: snapshot.current_iteration,
    maxIterations: snapshot.max_iterations,
    bestVersion: best.bestVersion,
    bestScore: best.bestScore,
    severity,
  };
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

/**
 * The findings the final round actually produced, for a terminal event that did
 * not report them.
 *
 * The reviews are preferred over the score badge because they are the same list
 * the Reviewer panel and the trace count, and the whole defect this closes was
 * those three views disagreeing about one set of feedback.
 */
function finalRoundSeverity(
  state: RunViewState,
  payload: Record<string, unknown>,
  iteration: number,
): SeverityCounts | null {
  const version = optionalNumberPayload(payload, "final_version") ?? iteration;
  return (
    severitiesFromReviews(state.reviewsByVersion[version]) ??
    state.scoresByVersion[version]?.severity ??
    null
  );
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
            // Normalized at the edge so every consumer downstream can rely on
            // structured findings, whatever the server actually sent.
            [review.role]: normalizeReview(review),
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
      // The backend decides which version is best and never rewrites a reviewer
      // score to get there, so the client just mirrors the pointer it is sent
      // and falls back to its own comparison for an older backend.
      const overall = numberPayload(payload, "overall", 0);
      const sentBestVersion = optionalNumberPayload(payload, "best_version");
      const sentBestScore = optionalNumberPayload(payload, "best_score");
      const improved = state.bestScore === null || overall > state.bestScore;
      return {
        ...next,
        scoresByVersion: {
          ...state.scoresByVersion,
          [event.iteration]: {
            version: event.iteration,
            tech: numberPayload(payload, "tech", 0),
            ux: numberPayload(payload, "ux", 0),
            biz: numberPayload(payload, "biz", 0),
            overall,
            severity: severityFromPayload(
              payload,
              severitiesFromReviews(state.reviewsByVersion[event.iteration]),
            ),
          },
        },
        bestVersion:
          sentBestVersion ?? (improved ? event.iteration : state.bestVersion),
        bestScore: sentBestScore ?? (improved ? overall : state.bestScore),
        snapshot: withNodeStatus(next.snapshot, "aggregator", "SUCCEEDED"),
      };
    }
    case "revision_planned": {
      const plan = payload.revision_plan as RevisionPlan | undefined;
      if (!plan) {
        return {
          ...next,
          pendingRevisionPlan: null,
          snapshot: withNodeStatus(next.snapshot, "optimizer", "SUCCEEDED"),
        };
      }
      // The optimizer increments the iteration in the same commit that emits
      // this event, so `event.iteration` is already the version the plan will
      // produce, while `plan.iteration` is the reviewed version it came from.
      const sourceVersion = planSourceVersion(plan, event.iteration);
      return {
        ...next,
        pendingRevisionPlan: plan,
        revisionPlansBySourceVersion: {
          ...state.revisionPlansBySourceVersion,
          [sourceVersion]: {
            sourceVersion,
            targetVersion: Math.max(event.iteration, sourceVersion + 1),
            plan,
          },
        },
        snapshot: withNodeStatus(next.snapshot, "optimizer", "SUCCEEDED"),
      };
    }
    case "telemetry_updated":
      return { ...next, snapshot: withTelemetry(next.snapshot, payload) };
    case "run_completed": {
      const outcome = outcomeFromPayload(payload, {
        completedIterations: event.iteration,
        qualityGatePassed: true,
        severity: finalRoundSeverity(state, payload, event.iteration),
      });
      return {
        ...next,
        status: "COMPLETED",
        connection: "closed",
        bestVersion: outcome.bestVersion ?? state.bestVersion,
        bestScore: outcome.bestScore ?? state.bestScore,
        outcome,
      };
    }
    case "max_iterations_reached": {
      const outcome = outcomeFromPayload(payload, {
        completedIterations: event.iteration,
        qualityGatePassed: false,
        // Exhausting the budget is a normal ending, so it may not blank the
        // findings the final round actually produced.
        severity: finalRoundSeverity(state, payload, event.iteration),
      });
      return {
        ...next,
        status: "MAX_ITERATIONS_REACHED",
        connection: "closed",
        bestVersion: outcome.bestVersion ?? state.bestVersion,
        bestScore: outcome.bestScore ?? state.bestScore,
        outcome,
      };
    }
    case "run_cancelled":
      return { ...next, status: "CANCELLED", connection: "closed" };
    case "run_failed":
      return {
        ...next,
        status: "FAILED",
        connection: "closed",
        // `RunManager.fail_run` sends `error_code`. Reading only `code` here is
        // what made every live failure render the generic fallback even though
        // the run had a specific, already-translated cause.
        error: localizedErrorMessage(
          stringPayload(payload, "error_code") ??
            stringPayload(payload, "code"),
        ),
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
      const streamed = snapshot.current_prd;
      // The attempt that owns `current_prd`. `prd_delta` is transient on the
      // backend, so this snapshot field is the only way a reconnecting client
      // learns it; a server that omits it -- or sends something that is not a
      // positive integer -- is read as attempt 1, the previous behaviour.
      const streamedAttempt =
        typeof snapshot.current_prd_attempt === "number" &&
        Number.isInteger(snapshot.current_prd_attempt) &&
        snapshot.current_prd_attempt >= 1
          ? snapshot.current_prd_attempt
          : 1;
      const lastCompleted = snapshot.versions.at(-1)?.content;
      if (
        drafts[snapshot.current_iteration] === undefined &&
        (streamed !== "" || streamedAttempt > 1) &&
        // Once a generation finishes, `current_prd` is a copy of the newest
        // version and belongs to an iteration that already has a draft.
        // Seeding from it again would make later deltas append onto finished
        // text instead of starting the new iteration's stream.
        streamed !== lastCompleted
      ) {
        drafts[snapshot.current_iteration] = {
          version: snapshot.current_iteration,
          attempt: streamedAttempt,
          content: streamed,
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
      const best = bestFromSnapshot(snapshot);
      return {
        ...state,
        runId: snapshot.run_id,
        snapshot,
        status: snapshot.status,
        latestSequence: snapshot.latest_event_sequence,
        drafts,
        reviewsByVersion: reviewsFromSnapshot(snapshot),
        scoresByVersion: scoresFromSnapshot(snapshot.versions),
        // Rebuilt rather than merged: every plan the run has ever committed is
        // durable in the snapshot, either on the version it produced or as the
        // pending plan, so a reconnect recovers the full history.
        revisionPlansBySourceVersion: revisionPlansFromSnapshot(snapshot),
        bestVersion: best.bestVersion,
        bestScore: best.bestScore,
        outcome: outcomeFromSnapshot(snapshot, best),
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
