import { describe, expect, it } from "vitest";

import {
  initialRunViewState,
  runReducer,
  type RunViewState,
} from "./runReducer";
import {
  makeEvaluation,
  makeEvent,
  makeReview,
  makeSnapshot,
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
