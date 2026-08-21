import { describe, expect, it } from "vitest";

import {
  EMPTY_SEVERITY_COUNTS,
  initialRunViewState,
  runReducer,
  type RunViewState,
} from "./runReducer";
import {
  makeEvaluation,
  makeEvent,
  makeFeedback,
  makeReview,
  makeRevisionPlan,
  makeSnapshot,
  makeVersion,
  RUN_ID,
} from "../test/fixtures";

function loadedState(): RunViewState {
  return runReducer(initialRunViewState, {
    type: "SNAPSHOT_LOADED",
    snapshot: makeSnapshot(),
  });
}

function event(state: RunViewState, value: ReturnType<typeof makeEvent>) {
  return runReducer(state, { type: "EVENT_RECEIVED", event: value });
}

describe("runReducer event ordering", () => {
  it("ignores duplicate, old, foreign, and post-terminal events", () => {
    const initial = loadedState();
    const first = event(
      initial,
      makeEvent(2, "prd_delta", {
        version: 1,
        attempt: 1,
        delta: "A",
      }),
    );
    expect(event(first, makeEvent(2, "prd_delta", { delta: "A" }))).toBe(first);
    expect(
      event(first, makeEvent(3, "prd_delta", { delta: "B" }, 1, "foreign")),
    ).toBe(first);
    const terminal = event(first, makeEvent(3, "run_completed"));
    expect(terminal.status).toBe("COMPLETED");
    expect(
      event(
        terminal,
        makeEvent(4, "prd_delta", {
          version: 1,
          attempt: 1,
          delta: "late",
        }),
      ),
    ).toBe(terminal);
  });

  it("loads a snapshot without switching an available selected old version", () => {
    const evaluation = makeEvaluation();
    const state = {
      ...loadedState(),
      selectedVersion: 1,
      selectionPinned: true,
    };
    const updated = runReducer(state, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        current_iteration: 2,
        versions: [
          {
            version: 1,
            content: "# One",
            created_at: "2026-07-26T10:00:00Z",
            evaluation,
            revision_plan: null,
            token_usage: {
              input_tokens: 1,
              output_tokens: 2,
              total_tokens: 3,
            },
          },
          {
            version: 2,
            content: "# Two",
            created_at: "2026-07-26T10:01:00Z",
            evaluation,
            revision_plan: null,
            token_usage: {
              input_tokens: 1,
              output_tokens: 2,
              total_tokens: 3,
            },
          },
        ],
      }),
    });
    expect(updated.selectedVersion).toBe(1);
    expect(updated.scoresByVersion[2]?.overall).toBe(80);
  });

  it("follows a new streamed version until the user pins an older tab", () => {
    let state = event(
      loadedState(),
      makeEvent(1, "prd_delta", {
        version: 1,
        attempt: 1,
        delta: "v1",
      }),
    );
    state = event(
      state,
      makeEvent(2, "prd_delta", { version: 2, attempt: 1, delta: "v2" }, 2),
    );
    expect(state.selectedVersion).toBe(2);
    state = runReducer(state, { type: "VERSION_SELECTED", version: 1 });
    state = event(
      state,
      makeEvent(3, "prd_delta", { version: 2, attempt: 1, delta: " more" }, 2),
    );
    expect(state.selectedVersion).toBe(1);
  });
});

describe("runReducer PRD attempts and reviews", () => {
  it("assembles current-attempt deltas, resets, rejects stale deltas, and calibrates", () => {
    let state = loadedState();
    state = event(
      state,
      makeEvent(1, "prd_delta", {
        version: 1,
        attempt: 1,
        delta: "# First",
      }),
    );
    state = event(
      state,
      makeEvent(2, "prd_stream_reset", { version: 1, attempt: 2 }),
    );
    state = event(
      state,
      makeEvent(3, "prd_delta", {
        version: 1,
        attempt: 1,
        delta: " stale",
      }),
    );
    state = event(
      state,
      makeEvent(4, "prd_delta", {
        version: 1,
        attempt: 2,
        delta: "# Retry",
      }),
    );
    state = event(
      state,
      makeEvent(5, "prd_generated", {
        version: 1,
        attempt: 2,
        content: "# Canonical",
      }),
    );

    expect(state.drafts[1]).toEqual({
      version: 1,
      attempt: 2,
      content: "# Canonical",
      complete: true,
    });
    expect(state.snapshot?.node_statuses.generator).toBe("SUCCEEDED");
  });

  it("merges reviewers in arbitrary order and records server scores", () => {
    let state = loadedState();
    for (const [sequence, role] of [
      [1, "biz"],
      [2, "tech"],
      [3, "ux"],
    ] as const) {
      state = event(
        state,
        makeEvent(sequence, "review_completed", {
          ...makeReview(role, 70 + sequence),
        }),
      );
    }
    state = event(
      state,
      makeEvent(4, "scores_updated", {
        tech: 72,
        ux: 73,
        biz: 71,
        overall: 72,
      }),
    );

    expect(Object.keys(state.reviewsByVersion[1] ?? {})).toHaveLength(3);
    expect(state.scoresByVersion[1]).toEqual({
      version: 1,
      tech: 72,
      ux: 73,
      biz: 71,
      overall: 72,
      // No `*_count` keys were sent, so the three reviews the client just
      // received are counted instead: one advisory finding each. Reporting zero
      // here is what made the badge contradict the list rendered beneath it.
      severity: { mustFix: 0, shouldFix: 3, optional: 0 },
    });
    expect(state.snapshot?.node_statuses.aggregator).toBe("SUCCEEDED");
  });

  it("fully resets identity, versions, selection, and late-event acceptance", () => {
    const state = event(
      loadedState(),
      makeEvent(1, "prd_delta", {
        version: 1,
        attempt: 1,
        delta: "content",
      }),
    );
    const reset = runReducer(state, { type: "RESET" });
    expect(reset).toEqual(initialRunViewState);
    expect(
      event(reset, makeEvent(2, "prd_delta", { delta: "late" }, 1, RUN_ID)),
    ).toBe(reset);
  });
});

describe("runReducer attempt recovery from a snapshot", () => {
  it("streams attempt 1 normally and keeps the draft incomplete until generated", () => {
    let state = loadedState();
    state = event(
      state,
      makeEvent(1, "prd_delta", { version: 1, attempt: 1, delta: "# A" }),
    );
    expect(state.drafts[1]).toEqual({
      version: 1,
      attempt: 1,
      content: "# A",
      complete: false,
    });
    state = event(
      state,
      makeEvent(2, "prd_delta", { version: 1, attempt: 1, delta: " tail" }),
    );
    expect(state.drafts[1]?.content).toBe("# A tail");
    expect(state.drafts[1]?.complete).toBe(false);
  });

  it("resumes an attempt-2 stream after a reconnect and rejects attempt-1 stragglers", () => {
    let state = loadedState();
    state = event(
      state,
      makeEvent(1, "prd_delta", { version: 1, attempt: 1, delta: "# Doomed" }),
    );
    state = event(
      state,
      makeEvent(2, "prd_stream_reset", { version: 1, attempt: 2 }),
    );
    state = event(
      state,
      makeEvent(3, "prd_delta", { version: 1, attempt: 2, delta: "# Retry" }),
    );
    expect(state.drafts[1]).toMatchObject({ attempt: 2, content: "# Retry" });

    // The reconnect: `prd_delta` is transient server-side, so the snapshot's
    // `current_prd` plus `current_prd_attempt` is all the client gets back.
    state = runReducer(state, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        current_prd: "# Retry",
        current_prd_attempt: 2,
        latest_event_sequence: 3,
      }),
    });
    expect(state.drafts[1]).toEqual({
      version: 1,
      attempt: 2,
      content: "# Retry",
      complete: false,
    });

    state = event(
      state,
      makeEvent(4, "prd_delta", { version: 1, attempt: 2, delta: " resumed" }),
    );
    expect(state.drafts[1]?.content).toBe("# Retry resumed");

    state = event(
      state,
      makeEvent(5, "prd_delta", { version: 1, attempt: 1, delta: " stale" }),
    );
    expect(state.drafts[1]?.content).toBe("# Retry resumed");

    state = event(
      state,
      makeEvent(6, "prd_generated", {
        version: 1,
        attempt: 2,
        content: "# Retry resumed and finished",
      }),
    );
    expect(state.drafts[1]).toEqual({
      version: 1,
      attempt: 2,
      content: "# Retry resumed and finished",
      complete: true,
    });
    expect(state.latestSequence).toBe(6);
  });

  it("recovers an attempt-2 stream that had produced no text yet", () => {
    const state = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({ current_prd: "", current_prd_attempt: 2 }),
    });
    expect(state.drafts[1]).toEqual({
      version: 1,
      attempt: 2,
      content: "",
      complete: false,
    });
    expect(
      event(
        state,
        makeEvent(1, "prd_delta", { version: 1, attempt: 2, delta: "# Fresh" }),
      ).drafts[1]?.content,
    ).toBe("# Fresh");
  });

  it("reads a server that omits the attempt field as attempt 1", () => {
    const snapshot = makeSnapshot({ current_prd: "# Legacy" });
    delete snapshot.current_prd_attempt;
    const state = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot,
    });
    expect(state.drafts[1]?.attempt).toBe(1);
    expect(
      event(
        state,
        makeEvent(1, "prd_delta", { version: 1, attempt: 1, delta: " more" }),
      ).drafts[1]?.content,
    ).toBe("# Legacy more");
  });

  it("does not reseed a finished version from the mirrored current_prd", () => {
    const state = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        status: "REVIEWING",
        current_prd: "# Done",
        current_prd_attempt: 2,
        versions: [
          {
            version: 1,
            content: "# Done",
            created_at: "2026-07-26T10:00:00Z",
            evaluation: null,
            revision_plan: null,
            token_usage: {
              input_tokens: 1,
              output_tokens: 2,
              total_tokens: 3,
            },
          },
        ],
      }),
    });
    expect(state.drafts[1]).toEqual({
      version: 1,
      attempt: 1,
      content: "# Done",
      complete: true,
    });
  });

  it("keeps duplicate and old-sequence rules after an attempt recovery", () => {
    const state = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        current_prd: "# Retry",
        current_prd_attempt: 2,
        latest_event_sequence: 9,
      }),
    });
    const replayed = event(
      state,
      makeEvent(9, "prd_delta", { version: 1, attempt: 2, delta: "dup" }),
    );
    expect(replayed).toBe(state);
    expect(
      event(
        state,
        makeEvent(4, "prd_delta", { version: 1, attempt: 2, delta: "old" }),
      ),
    ).toBe(state);
    const accepted = event(
      state,
      makeEvent(10, "prd_delta", { version: 1, attempt: 2, delta: "!" }),
    );
    expect(accepted.drafts[1]?.content).toBe("# Retry!");
  });
});

describe("runReducer revision plan ownership", () => {
  it("keys a live plan by the reviewed version, not the version it produces", () => {
    // The optimizer bumps the iteration in the same commit that emits the
    // event, so `event.iteration` is 2 while the plan reviewed v1.
    const state = event(
      loadedState(),
      makeEvent(
        5,
        "revision_planned",
        { revision_plan: makeRevisionPlan(1) },
        2,
      ),
    );

    expect(state.revisionPlansBySourceVersion[1]).toMatchObject({
      sourceVersion: 1,
      targetVersion: 2,
    });
    expect(state.revisionPlansBySourceVersion[2]).toBeUndefined();
    expect(state.pendingRevisionPlan?.iteration).toBe(1);
    expect(state.snapshot?.node_statuses.optimizer).toBe("SUCCEEDED");
  });

  it("keeps every round's plan so a later one never overwrites an earlier one", () => {
    let state = event(
      loadedState(),
      makeEvent(
        5,
        "revision_planned",
        { revision_plan: makeRevisionPlan(1, { objective: "From v1." }) },
        2,
      ),
    );
    state = event(
      state,
      makeEvent(
        9,
        "revision_planned",
        { revision_plan: makeRevisionPlan(2, { objective: "From v2." }) },
        3,
      ),
    );

    expect(state.revisionPlansBySourceVersion[1]).toMatchObject({
      sourceVersion: 1,
      targetVersion: 2,
    });
    expect(state.revisionPlansBySourceVersion[1]?.plan.objective).toBe(
      "From v1.",
    );
    expect(state.revisionPlansBySourceVersion[2]).toMatchObject({
      sourceVersion: 2,
      targetVersion: 3,
    });
    expect(state.revisionPlansBySourceVersion[2]?.plan.objective).toBe(
      "From v2.",
    );
  });

  it("rebuilds the full plan history from a restored snapshot", () => {
    const state = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        status: "MAX_ITERATIONS_REACHED",
        current_iteration: 3,
        versions: [
          makeVersion(1, { evaluation: makeEvaluation(65, 70, 78) }),
          makeVersion(2, {
            evaluation: makeEvaluation(88, 89, 87),
            revision_plan: makeRevisionPlan(1, { objective: "From v1." }),
          }),
          makeVersion(3, {
            evaluation: makeEvaluation(90, 91, 89),
            revision_plan: makeRevisionPlan(2, { objective: "From v2." }),
          }),
        ],
      }),
    });

    expect(Object.keys(state.revisionPlansBySourceVersion)).toEqual(["1", "2"]);
    expect(state.revisionPlansBySourceVersion[1]).toMatchObject({
      sourceVersion: 1,
      targetVersion: 2,
    });
    expect(state.revisionPlansBySourceVersion[2]).toMatchObject({
      sourceVersion: 2,
      targetVersion: 3,
    });
    expect(state.revisionPlansBySourceVersion[3]).toBeUndefined();
  });

  it("attributes a pending plan to the version it will generate", () => {
    const state = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        status: "GENERATING",
        current_iteration: 2,
        versions: [makeVersion(1, { evaluation: makeEvaluation(65, 70, 78) })],
        pending_revision_plan: makeRevisionPlan(1),
      }),
    });

    expect(state.revisionPlansBySourceVersion[1]).toMatchObject({
      sourceVersion: 1,
      targetVersion: 2,
    });
    expect(state.pendingRevisionPlan?.iteration).toBe(1);
  });

  it("drops a plan that a reconnect no longer reports", () => {
    let state = event(
      loadedState(),
      makeEvent(
        5,
        "revision_planned",
        { revision_plan: makeRevisionPlan(1) },
        2,
      ),
    );
    state = runReducer(state, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        status: "CANCELLED",
        current_iteration: 2,
        versions: [makeVersion(1, { evaluation: makeEvaluation(65, 70, 78) })],
        pending_revision_plan: null,
        latest_event_sequence: 6,
      }),
    });

    expect(state.revisionPlansBySourceVersion).toEqual({});
    expect(state.pendingRevisionPlan).toBeNull();
  });

  it("falls back to the preceding version when a plan omits its iteration", () => {
    const plan = makeRevisionPlan(1);
    delete (plan as { iteration?: number }).iteration;
    const state = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        current_iteration: 2,
        versions: [
          makeVersion(1, { evaluation: makeEvaluation(65, 70, 78) }),
          makeVersion(2, { revision_plan: plan }),
        ],
      }),
    });

    expect(state.revisionPlansBySourceVersion[1]).toMatchObject({
      sourceVersion: 1,
      targetVersion: 2,
    });
  });
});

describe("runReducer best version and run outcome", () => {
  it("keeps the best version when a later one scores lower", () => {
    let state = loadedState();
    state = event(
      state,
      makeEvent(1, "scores_updated", {
        tech: 65,
        ux: 66,
        biz: 69,
        overall: 66.7,
        version: 1,
        delta_vs_best: null,
        best_version: 1,
        best_score: 66.7,
      }),
    );
    state = event(
      state,
      makeEvent(
        2,
        "scores_updated",
        {
          tech: 80,
          ux: 82,
          biz: 83,
          overall: 81.7,
          version: 2,
          delta_vs_best: 15,
          best_version: 2,
          best_score: 81.7,
        },
        2,
      ),
    );
    state = event(
      state,
      makeEvent(
        3,
        "scores_updated",
        {
          tech: 77,
          ux: 78,
          biz: 80,
          overall: 78.3,
          version: 3,
          delta_vs_best: -3.4,
          best_version: 2,
          best_score: 81.7,
        },
        3,
      ),
    );

    // Every reviewer score is kept exactly as sent -- the best is a pointer.
    expect(state.scoresByVersion[3]?.overall).toBe(78.3);
    expect(state.bestVersion).toBe(2);
    expect(state.bestScore).toBe(81.7);
  });

  it("compares locally when a server omits the best-version pointer", () => {
    let state = loadedState();
    state = event(
      state,
      makeEvent(1, "scores_updated", {
        tech: 80,
        ux: 82,
        biz: 83,
        overall: 81.7,
      }),
    );
    state = event(
      state,
      makeEvent(
        2,
        "scores_updated",
        { tech: 77, ux: 78, biz: 80, overall: 78.3 },
        2,
      ),
    );

    expect(state.bestVersion).toBe(1);
    expect(state.bestScore).toBe(81.7);
  });

  it("records an unmet threshold on max_iterations_reached", () => {
    const state = event(
      loadedState(),
      makeEvent(
        5,
        "max_iterations_reached",
        {
          final_version: 3,
          final_score: 78.3,
          best_version: 2,
          best_score: 81.7,
          quality_threshold: 85,
          completed_iterations: 3,
          max_iterations: 3,
          threshold_met: false,
        },
        3,
      ),
    );

    expect(state.status).toBe("MAX_ITERATIONS_REACHED");
    expect(state.outcome).toEqual({
      thresholdMet: false,
      qualityGatePassed: false,
      qualityThreshold: 85,
      completedIterations: 3,
      maxIterations: 3,
      bestVersion: 2,
      bestScore: 81.7,
      severity: EMPTY_SEVERITY_COUNTS,
    });
  });

  /**
   * The state the gate exists for: the score cleared 85, so the run looks
   * successful, but a blocking finding is still open and the budget is gone. It
   * must land as "threshold met, gate not passed" -- not as a pass, and not as a
   * plain failure either.
   */
  it("keeps a met threshold and a held gate as two separate facts", () => {
    const state = event(
      loadedState(),
      makeEvent(
        5,
        "max_iterations_reached",
        {
          best_version: 3,
          best_score: 91,
          quality_threshold: 85,
          completed_iterations: 4,
          max_iterations: 4,
          threshold_met: true,
          quality_gate_passed: false,
          must_fix_count: 1,
          should_fix_count: 3,
          optional_count: 8,
        },
        4,
      ),
    );

    expect(state.outcome?.thresholdMet).toBe(true);
    expect(state.outcome?.qualityGatePassed).toBe(false);
    expect(state.outcome?.severity).toEqual({
      mustFix: 1,
      shouldFix: 3,
      optional: 8,
    });
  });

  /**
   * The real regression: the backend that produced the run sent no count keys on
   * `max_iterations_reached`, so a run whose three reviewers listed 21 findings
   * reported 必须修复 0 · 重要改进 0 · 可选优化 0 at the top of the page while the
   * trace listed 6 / 5 / 10 beneath it. Exhausting the budget is a normal ending
   * and may not blank the findings the final round actually produced.
   */
  it("keeps the final round's findings when a terminal event omits the counts", () => {
    const feedbackFor = (must: number, should: number, optional: number) => [
      ...Array.from({ length: must }, () => makeFeedback("must_fix")),
      ...Array.from({ length: should }, () => makeFeedback("should_fix")),
      ...Array.from({ length: optional }, () => makeFeedback("optional")),
    ];
    let state = loadedState();
    for (const [sequence, review] of [
      [1, makeReview("tech", 80, feedbackFor(0, 4, 2))],
      [2, makeReview("ux", 82, feedbackFor(0, 3, 2))],
      [3, makeReview("biz", 86, feedbackFor(0, 5, 5))],
    ] as const) {
      state = event(
        state,
        makeEvent(sequence, "review_completed", { ...review }, 3),
      );
    }
    state = event(
      state,
      makeEvent(
        4,
        "scores_updated",
        { tech: 80, ux: 82, biz: 86, overall: 82.7 },
        3,
      ),
    );
    state = event(
      state,
      makeEvent(
        5,
        "max_iterations_reached",
        {
          final_version: 3,
          final_score: 82.7,
          best_version: 3,
          best_score: 82.7,
          quality_threshold: 91,
          completed_iterations: 3,
          max_iterations: 3,
          threshold_met: false,
        },
        3,
      ),
    );

    expect(state.status).toBe("MAX_ITERATIONS_REACHED");
    expect(state.outcome?.severity).toEqual({
      mustFix: 0,
      shouldFix: 12,
      optional: 9,
    });
    // The score badge counts the same findings, so no two views can disagree.
    expect(state.scoresByVersion[3]?.severity).toEqual({
      mustFix: 0,
      shouldFix: 12,
      optional: 9,
    });
    // And the semantics the user asked to keep: not met, and stopped anyway.
    expect(state.outcome?.thresholdMet).toBe(false);
    expect(state.outcome?.qualityGatePassed).toBe(false);
  });

  /** The same run reopened must report the same numbers it reported live. */
  it("reports the same counts live and after a restore", () => {
    const evaluation = makeEvaluation(80, 82, 86, {
      combined_feedback: [
        ...Array.from({ length: 12 }, () => makeFeedback("should_fix")),
        ...Array.from({ length: 9 }, () => makeFeedback("optional")),
      ],
    });
    const restored = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        status: "MAX_ITERATIONS_REACHED",
        current_iteration: 3,
        max_iterations: 3,
        quality_threshold: 91,
        best_version: 3,
        best_score: 82.7,
        latest_evaluation: evaluation,
        versions: [
          makeVersion(1, { evaluation: makeEvaluation(45, 46, 49) }),
          makeVersion(2, { evaluation: makeEvaluation(78, 79, 80) }),
          makeVersion(3, { evaluation: evaluation }),
        ],
      }),
    });

    expect(restored.outcome?.severity).toEqual({
      mustFix: 0,
      shouldFix: 12,
      optional: 9,
    });
    expect(restored.outcome?.thresholdMet).toBe(false);
  });

  it("records a passed gate on run_completed", () => {
    const state = event(
      loadedState(),
      makeEvent(
        4,
        "run_completed",
        {
          best_version: 2,
          best_score: 88,
          quality_threshold: 85,
          completed_iterations: 2,
          max_iterations: 3,
          threshold_met: true,
          quality_gate_passed: true,
          must_fix_count: 0,
          should_fix_count: 3,
          optional_count: 8,
        },
        2,
      ),
    );

    expect(state.outcome?.thresholdMet).toBe(true);
    expect(state.outcome?.qualityGatePassed).toBe(true);
    expect(state.outcome?.severity.mustFix).toBe(0);
    expect(state.bestVersion).toBe(2);
  });

  /**
   * A backend that predates the gate sends neither `quality_gate_passed` nor the
   * severity counts. `run_completed` was itself the server's statement that the
   * run finished, so the gate reads as passed and no blocker is invented -- the
   * alternative would retroactively un-complete every historical run.
   */
  it("treats a pre-gate run_completed as passed with no blockers", () => {
    const state = event(
      loadedState(),
      makeEvent(
        4,
        "run_completed",
        {
          best_version: 2,
          best_score: 88,
          quality_threshold: 85,
          completed_iterations: 2,
          max_iterations: 3,
          threshold_met: true,
        },
        2,
      ),
    );

    expect(state.outcome?.qualityGatePassed).toBe(true);
    expect(state.outcome?.severity).toEqual(EMPTY_SEVERITY_COUNTS);
  });

  it("rebuilds the outcome from a reopened terminal snapshot", () => {
    const state = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        status: "MAX_ITERATIONS_REACHED",
        current_iteration: 3,
        max_iterations: 3,
        quality_threshold: 85,
        best_version: 2,
        best_score: 81.7,
        versions: [
          makeVersion(1, { evaluation: makeEvaluation(65, 66, 69) }),
          makeVersion(2, { evaluation: makeEvaluation(80, 82, 83) }),
          makeVersion(3, { evaluation: makeEvaluation(77, 78, 80) }),
        ],
      }),
    });

    expect(state.outcome).toEqual({
      thresholdMet: false,
      qualityGatePassed: false,
      qualityThreshold: 85,
      completedIterations: 3,
      maxIterations: 3,
      bestVersion: 2,
      bestScore: 81.7,
      // Recounted from the final version's own findings, so the badge can never
      // disagree with the list of items rendered beneath it.
      severity: { mustFix: 0, shouldFix: 1, optional: 1 },
    });
  });

  /**
   * A reconnecting client never receives the terminal event again, so a restored
   * `COMPLETED` snapshot has to keep reading as a passed gate -- and a restored
   * `MAX_ITERATIONS_REACHED` whose final score cleared the target has to keep
   * reading as "target reached, gate held".
   */
  it("restores the gate for both terminal statuses from a snapshot alone", () => {
    const passed = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        status: "COMPLETED",
        current_iteration: 2,
        quality_threshold: 85,
        versions: [makeVersion(1, { evaluation: makeEvaluation(90, 91, 91) })],
      }),
    });
    expect(passed.outcome?.qualityGatePassed).toBe(true);
    expect(passed.outcome?.thresholdMet).toBe(true);

    const held = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        status: "MAX_ITERATIONS_REACHED",
        current_iteration: 3,
        quality_threshold: 85,
        versions: [makeVersion(1, { evaluation: makeEvaluation(90, 91, 91) })],
      }),
    });
    expect(held.outcome?.thresholdMet).toBe(true);
    expect(held.outcome?.qualityGatePassed).toBe(false);
  });

  it("recomputes the best version for a snapshot that predates the field", () => {
    const snapshot = makeSnapshot({
      status: "MAX_ITERATIONS_REACHED",
      current_iteration: 3,
      versions: [
        makeVersion(1, { evaluation: makeEvaluation(65, 66, 69) }),
        makeVersion(2, { evaluation: makeEvaluation(80, 82, 83) }),
        makeVersion(3, { evaluation: makeEvaluation(77, 78, 80) }),
      ],
    });
    delete (snapshot as { best_version?: number | null }).best_version;
    delete (snapshot as { best_score?: number | null }).best_score;

    const state = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot,
    });

    expect(state.bestVersion).toBe(2);
    expect(state.bestScore).toBe(81.7);
  });

  it("leaves the outcome unset for a cancelled or still-running snapshot", () => {
    for (const status of ["CANCELLED", "FAILED", "GENERATING"] as const) {
      const state = runReducer(initialRunViewState, {
        type: "SNAPSHOT_LOADED",
        snapshot: makeSnapshot({ status }),
      });
      expect(state.outcome).toBeNull();
    }
  });

  it("counts a snapshot's blocking findings by tier", () => {
    const state = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        status: "MAX_ITERATIONS_REACHED",
        current_iteration: 1,
        quality_threshold: 85,
        versions: [
          makeVersion(1, {
            evaluation: makeEvaluation(90, 91, 91, {
              combined_feedback: [
                makeFeedback("must_fix", "Checkout cannot be built"),
                makeFeedback("should_fix"),
                makeFeedback("optional", "Polish"),
                makeFeedback("optional", "More polish"),
              ],
            }),
          }),
        ],
      }),
    });

    expect(state.outcome?.severity).toEqual({
      mustFix: 1,
      shouldFix: 1,
      optional: 2,
    });
    expect(state.scoresByVersion[1]?.severity).toEqual({
      mustFix: 1,
      shouldFix: 1,
      optional: 2,
    });
  });

  /**
   * A run finished before severity existed stored plain strings. Reading one of
   * those as a blocker would un-complete a document the product already
   * delivered, so they are all counted as advice.
   */
  it("never promotes a legacy string finding to a blocker", () => {
    const evaluation = makeEvaluation(90, 91, 91);
    (
      evaluation as unknown as { combined_feedback: unknown }
    ).combined_feedback = ["Add an edge case", "Quantify the metric"];

    const state = runReducer(initialRunViewState, {
      type: "SNAPSHOT_LOADED",
      snapshot: makeSnapshot({
        status: "COMPLETED",
        current_iteration: 1,
        versions: [makeVersion(1, { evaluation })],
      }),
    });

    expect(state.outcome?.severity).toEqual({
      mustFix: 0,
      shouldFix: 2,
      optional: 0,
    });
    expect(state.outcome?.qualityGatePassed).toBe(true);
  });
});
