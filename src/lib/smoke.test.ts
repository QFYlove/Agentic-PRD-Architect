import { describe, expect, it } from "vitest";

import { isRunEventType, isRunStatus } from "./contracts";

describe("frontend test foundation", () => {
  it("loads the shared contract helpers", () => {
    expect(isRunStatus("QUEUED")).toBe(true);
    expect(isRunEventType("run_started")).toBe(true);
  });
});
