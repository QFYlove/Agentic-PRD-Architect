import { describe, expect, it } from "vitest";

import { localizedErrorMessage } from "./errorMessages";
import { failureNotice } from "./failureNotice";
import { formatSeconds, nodeTimingRows, slowestSeconds } from "./nodeTimings";
import {
  initialRunViewState,
  runReducer,
  type RunViewState,
} from "./runReducer";
import {
  makeEvaluation,
  makeEvent,
  makeRevisionPlan,
  makeSnapshot,
  makeVersion,
} from "../test/fixtures";
import type { RunSnapshot } from "./types";

/** The state a client is actually in: a snapshot it loaded, then live events. */
function loaded(snapshot: RunSnapshot, ...events: RunEventList): RunViewState {
  return events.reduce(
    (state, event) => runReducer(state, { type: "EVENT_RECEIVED", event }),
    runReducer(initialRunViewState, { type: "SNAPSHOT_LOADED", snapshot }),
  );
}

type RunEventList = ReturnType<typeof makeEvent>[];

describe("incomplete-output messages", () => {
  /**
   * The three causes used to share one code, so a length problem and a
   * mid-stream service failure produced the same sentence -- and the reader was
   * told to retry an identical request that could only fail identically.
   */
  it("gives each incomplete cause its own actionable sentence", () => {
    const truncated = localizedErrorMessage("PROVIDER_OUTPUT_TRUNCATED");
    const unfinished = localizedErrorMessage("PROVIDER_OUTPUT_UNFINISHED");
    const interrupted = localizedErrorMessage("PROVIDER_OUTPUT_INTERRUPTED");

    expect(new Set([truncated, unfinished, interrupted]).size).toBe(3);
    expect(truncated).toContain("长度限制");
    expect(unfinished).toContain("提前结束");
    expect(interrupted).toContain("中断");
    for (const message of [truncated, unfinished, interrupted]) {
      expect(message).not.toBe("操作失败，请稍后重试。");
    }
  });

  it("still explains runs recorded under the old shared code", () => {
    expect(localizedErrorMessage("PROVIDER_OUTPUT_INCOMPLETE")).toContain(
      "不完整",
    );
  });

  it("falls back only for a code it has never seen", () => {
    expect(localizedErrorMessage("SOMETHING_NEW")).toBe(
      "操作失败，请稍后重试。",
    );
  });
});

describe("what a failed run still has", () => {
  /** A run that dies on v3 must not read as "everything is gone". */
  it("names the lost version and lists every version that survived it", () => {
    const notice = failureNotice(
      loaded(
        makeSnapshot({
          status: "FAILED",
          current_iteration: 3,
          best_version: 2,
          best_score: 80.7,
          versions: [
            makeVersion(1, { evaluation: makeEvaluation(60, 64, 68) }),
            makeVersion(2, {
              evaluation: makeEvaluation(78, 82, 82),
              revision_plan: makeRevisionPlan(1),
            }),
          ],
          pending_revision_plan: makeRevisionPlan(2),
        }),
      ),
    );

    expect(notice?.headline).toBe("v3 生成失败");
    // Both survivors, not just the newest one.
    expect(notice?.detail).toBe(
      "v1、v2 及已有评审和修订计划已保留。最佳可用版本：v2 · 80.7",
    );
  });

  /**
   * The real regression: the client opened the run while it was still on v1, then
   * watched v1 and v2 arrive as events. Deriving the failing version from that
   * first snapshot reported 「首版 PRD 生成失败」 with two finished documents on
   * screen.
   */
  it("counts versions that arrived as events, not just the snapshot it opened with", () => {
    const state = loaded(
      makeSnapshot({ status: "GENERATING", current_iteration: 1 }),
      makeEvent(1, "prd_generated", { version: 1, content: "# v1" }, 1),
      makeEvent(
        2,
        "scores_updated",
        { tech: 60, ux: 64, biz: 68, overall: 64 },
        1,
      ),
      makeEvent(
        3,
        "revision_planned",
        { revision_plan: makeRevisionPlan(1) },
        2,
      ),
      makeEvent(4, "prd_generated", { version: 2, content: "# v2" }, 2),
      makeEvent(
        5,
        "scores_updated",
        {
          tech: 78,
          ux: 82,
          biz: 82,
          overall: 80.7,
          best_version: 2,
          best_score: 80.7,
        },
        2,
      ),
      makeEvent(
        6,
        "revision_planned",
        { revision_plan: makeRevisionPlan(2) },
        3,
      ),
      makeEvent(7, "prd_stream_reset", { version: 3, attempt: 1 }, 3),
      makeEvent(8, "run_failed", { error_code: "RUN_TIMEOUT" }, 3),
    );

    const notice = failureNotice(state);
    expect(notice?.headline).toBe("v3 生成失败");
    expect(notice?.detail).toContain("v1、v2");
    expect(notice?.detail).toContain("最佳可用版本：v2 · 80.7");
    expect(notice?.headline).not.toBe("首版 PRD 生成失败");
  });

  it("claims nothing survived only when the first version never landed", () => {
    const notice = failureNotice(
      loaded(
        makeSnapshot({ status: "FAILED", current_iteration: 1, versions: [] }),
      ),
    );

    expect(notice).toEqual({ headline: "首版 PRD 生成失败", detail: null });
  });

  it("stays silent for a healthy run and for a version that did commit", () => {
    const committed = loaded(
      makeSnapshot({
        status: "FAILED",
        current_iteration: 1,
        versions: [makeVersion(1)],
      }),
    );

    expect(failureNotice(committed)).toBeNull();
    expect(failureNotice(loaded(makeSnapshot()))).toBeNull();
    expect(failureNotice(initialRunViewState)).toBeNull();
  });

  /**
   * `fail_run` sends the cause as `error_code`. The banner read `code`, so every
   * live failure showed the generic fallback even when the run had a specific,
   * already-translated cause -- and no raw provider text may take its place.
   */
  it("shows the specific cause of a live failure in the top banner", () => {
    for (const [code, expected] of [
      ["RUN_TIMEOUT", "任务运行超时，请缩小需求范围后重试。"],
      [
        "PROVIDER_OUTPUT_TRUNCATED",
        localizedErrorMessage("PROVIDER_OUTPUT_TRUNCATED"),
      ],
    ] as const) {
      const state = loaded(
        makeSnapshot({ status: "GENERATING" }),
        makeEvent(
          1,
          "run_failed",
          { error_code: code, message: "raw provider text", retryable: true },
          1,
        ),
      );

      expect(state.status).toBe("FAILED");
      expect(state.error).toBe(expected);
      expect(state.error).not.toBe("操作失败，请稍后重试。");
      expect(state.error).not.toContain("raw provider text");
    }
  });

  it("falls back for a failure whose code it cannot read", () => {
    const state = loaded(
      makeSnapshot({ status: "GENERATING" }),
      makeEvent(1, "run_failed", { message: "boom" }, 1),
    );

    expect(state.error).toBe("操作失败，请稍后重试。");
  });
});

describe("per-node timings", () => {
  it("labels every call with its node and the version it was working on", () => {
    const rows = nodeTimingRows([
      {
        node: "generator",
        version: 1,
        attempt: 1,
        seconds: 62.5,
        succeeded: true,
        input_tokens: 500,
        output_tokens: 1700,
      },
      {
        node: "tech_reviewer",
        version: 1,
        attempt: 1,
        seconds: 11.25,
        succeeded: true,
        input_tokens: 2000,
        output_tokens: 400,
      },
      {
        node: "optimizer",
        version: 1,
        attempt: 1,
        seconds: 9,
        succeeded: true,
        input_tokens: 3000,
        output_tokens: 600,
      },
      {
        node: "generator",
        version: 2,
        attempt: 2,
        seconds: 120,
        succeeded: false,
        input_tokens: 800,
        output_tokens: 1200,
      },
    ]);

    expect(rows.map((row) => row.label)).toEqual([
      "Generator v1",
      "Tech Reviewer v1",
      "Optimizer v1",
      "Generator v2",
    ]);
    // A first attempt needs no annotation; a retry does, or the repeated label
    // looks like a duplicate row.
    expect(rows[0]?.attempt).toBeNull();
    expect(rows[3]?.attempt).toBe(2);
    expect(rows[3]?.succeeded).toBe(false);
    expect(rows[3]?.outputTokens).toBe(1200);
    expect(formatSeconds(rows[1]?.seconds ?? 0)).toBe("11.3 s");
    expect(slowestSeconds(rows)).toBe(120);
  });

  /**
   * `parseRunSnapshot` does not validate this field, and a run recorded before
   * timings existed has no such key. A telemetry list must never be the thing
   * that stops a finished PRD from rendering.
   */
  it("drops what it cannot read instead of throwing", () => {
    expect(nodeTimingRows(undefined)).toEqual([]);
    expect(nodeTimingRows("not an array")).toEqual([]);
    expect(nodeTimingRows([null, 7, { version: 1 }])).toEqual([]);

    const rows = nodeTimingRows([
      { node: "mystery_node", seconds: -4, version: "x" },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.label).toBe("mystery_node");
    expect(rows[0]?.seconds).toBe(0);
    // Bars divide by this, so it can never be zero.
    expect(slowestSeconds(rows)).toBe(1);
  });
});
