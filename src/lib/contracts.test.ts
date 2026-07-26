import { describe, expect, it } from "vitest";

import createRunRequest from "../../contracts/v1/create_run_request.json";
import errorResponse from "../../contracts/v1/error_response.json";
import runEvent from "../../contracts/v1/run_event.json";
import runEvents from "../../contracts/v1/run_events.json";
import runSnapshot from "../../contracts/v1/run_snapshot.json";
import terminalSnapshots from "../../contracts/v1/terminal_snapshots.json";
import {
  parseCreateRunRequest,
  parseErrorResponse,
  parseRunEvent,
  parseRunSnapshot,
} from "./contracts";
import {
  TERMINAL_RUN_STATUSES,
  type RunEventType,
  isTerminalRunStatus,
} from "./types";

describe("versioned API contracts", () => {
  it("parses the backend-validated examples", () => {
    expect(parseCreateRunRequest(createRunRequest).max_iterations).toBe(3);
    expect(parseRunSnapshot(runSnapshot).status).toBe("QUEUED");
    expect(parseRunEvent(runEvent).event).toBe("status_changed");
    expect(parseErrorResponse(errorResponse).error.code).toBe("RUN_NOT_FOUND");
  });

  it("rejects an invalid run snapshot", () => {
    expect(() =>
      parseRunSnapshot({ ...runSnapshot, status: "UNKNOWN" }),
    ).toThrow("Invalid RunSnapshot contract");
  });

  it("recognizes terminal run states", () => {
    const parsedStatuses = terminalSnapshots.map(
      (snapshot) => parseRunSnapshot(snapshot).status,
    );

    expect(new Set(parsedStatuses)).toEqual(TERMINAL_RUN_STATUSES);
    expect(isTerminalRunStatus("GENERATING")).toBe(false);
  });

  it("parses a fixture for every event type", () => {
    const parsedTypes = runEvents.map((event) => parseRunEvent(event).event);
    const expectedTypes = new Set<RunEventType>([
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

    expect(new Set(parsedTypes)).toEqual(expectedTypes);
  });
});
