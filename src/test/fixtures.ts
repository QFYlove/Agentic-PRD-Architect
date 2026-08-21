import type {
  EvaluationResult,
  FeedbackItem,
  FeedbackSeverity,
  PRDVersion,
  RevisionItem,
  RevisionPlan,
  RoleReview,
  RunEvent,
  RunEventType,
  RunSnapshot,
  RunStatus,
} from "../lib/types";

export const RUN_ID = "0c98322f-51a5-47f0-8091-d8152df0e680";

export function makeFeedback(
  severity: FeedbackSeverity = "should_fix",
  issue = "Add an edge case",
): FeedbackItem {
  return { severity, issue, recommendation: `Close: ${issue}` };
}

export function makeReview(
  role: "tech" | "ux" | "biz",
  score = 80,
  feedback: FeedbackItem[] = [makeFeedback()],
): RoleReview {
  return {
    role,
    score,
    summary: `${role} review summary`,
    strengths: ["Clear goal"],
    feedback,
  };
}

/**
 * An evaluation whose combined findings are advice only.
 *
 * The default deliberately carries no `must_fix`: this fixture stands in for a
 * run that is allowed to finish, and seeding a blocker into it would make every
 * unrelated test assert a held quality gate. Pass `blockers` -- or a full
 * `combined_feedback` -- when a held gate is the point.
 */
export function makeEvaluation(
  tech = 80,
  ux = 82,
  biz = 78,
  overrides: Partial<EvaluationResult> & { blockers?: number } = {},
): EvaluationResult {
  const { blockers = 0, ...rest } = overrides;
  const mustFix = Array.from({ length: blockers }, (_, index) =>
    makeFeedback("must_fix", `Blocker ${index + 1}`),
  );
  return {
    // The blockers land on a real reviewer too, so grouped reviewer detail and
    // the aggregate counts cannot disagree.
    tech: makeReview("tech", tech, [...mustFix, makeFeedback()]),
    ux: makeReview("ux", ux),
    biz: makeReview("biz", biz),
    overall_score: Math.round(((tech + ux + biz) / 3) * 10) / 10,
    combined_feedback: [
      ...mustFix,
      makeFeedback("should_fix"),
      makeFeedback("optional", "Polish the empty state"),
    ],
    ...rest,
  };
}

export function makeRevisionItem(
  overrides: Partial<RevisionItem> = {},
): RevisionItem {
  const source = overrides.source_role ?? "tech";
  return {
    source_role: source,
    source_roles: [source],
    issue: "Payment failures are undefined",
    required_change: "Document idempotent retries for the payment gateway",
    target_section: "Requirements",
    priority: "high",
    ...overrides,
  };
}

/**
 * A plan as the backend stores it: `iteration` is the reviewed version whose
 * findings produced the plan, not the version the plan goes on to create.
 */
export function makeRevisionPlan(
  iteration = 1,
  overrides: Partial<RevisionPlan> = {},
): RevisionPlan {
  return {
    iteration,
    objective: `Resolve iteration ${iteration} review findings.`,
    items: [makeRevisionItem()],
    user_override: null,
    ...overrides,
  };
}

export function makeVersion(
  version: number,
  overrides: Partial<PRDVersion> = {},
): PRDVersion {
  return {
    version,
    content: `# Version ${version}`,
    created_at: `2026-07-26T10:0${version}:00Z`,
    evaluation: null,
    revision_plan: null,
    token_usage: { input_tokens: 1, output_tokens: 2, total_tokens: 3 },
    ...overrides,
  };
}

export function makeSnapshot(
  overrides: Partial<RunSnapshot> = {},
): RunSnapshot {
  return {
    run_id: RUN_ID,
    user_idea: "Build a podcast micro-subscription product.",
    target_audience: "Podcast listeners",
    user_constraints: "Mobile-first",
    current_iteration: 1,
    max_iterations: 3,
    quality_threshold: 85,
    status: "GENERATING",
    active_node: "generator",
    versions: [],
    current_prd: "",
    current_prd_attempt: 1,
    latest_evaluation: null,
    reviews: {},
    pending_revision_plan: null,
    pending_user_override: null,
    node_statuses: {
      generator: "RUNNING",
      tech_reviewer: "PENDING",
      ux_reviewer: "PENDING",
      biz_reviewer: "PENDING",
      aggregator: "PENDING",
      optimizer: "PENDING",
    },
    total_tokens: {
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
    },
    node_tokens: {},
    estimated_cost_usd: 0,
    cost_available: true,
    is_mock: true,
    elapsed_seconds: 1.25,
    created_at: "2026-07-26T10:00:00Z",
    updated_at: "2026-07-26T10:00:01Z",
    started_at: "2026-07-26T10:00:00Z",
    completed_at: null,
    error: null,
    latest_event_sequence: 0,
    ...overrides,
  };
}

export function makeEvent(
  sequence: number,
  event: RunEventType,
  payload: Record<string, unknown> = {},
  iteration = 1,
  runId = RUN_ID,
): RunEvent {
  return {
    run_id: runId,
    sequence,
    event,
    timestamp: `2026-07-26T10:00:${String(sequence).padStart(2, "0")}Z`,
    iteration,
    payload,
  };
}

export function withStatus(status: RunStatus): RunSnapshot {
  return makeSnapshot({ status });
}
