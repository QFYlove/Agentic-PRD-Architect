import type {
  EvaluationResult,
  RoleReview,
  RunEvent,
  RunEventType,
  RunSnapshot,
  RunStatus,
} from "../lib/types";

export const RUN_ID = "0c98322f-51a5-47f0-8091-d8152df0e680";

export function makeReview(
  role: "tech" | "ux" | "biz",
  score = 80,
): RoleReview {
  return {
    role,
    score,
    summary: `${role} review summary`,
    strengths: ["Clear goal"],
    feedback: ["Add an edge case"],
  };
}

export function makeEvaluation(tech = 80, ux = 82, biz = 78): EvaluationResult {
  return {
    tech: makeReview("tech", tech),
    ux: makeReview("ux", ux),
    biz: makeReview("biz", biz),
    overall_score: Math.round(((tech + ux + biz) / 3) * 10) / 10,
    combined_feedback: ["Add an edge case"],
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
