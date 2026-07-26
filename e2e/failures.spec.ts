import { expect, test } from "@playwright/test";

import {
  apiUrl,
  getSnapshot,
  setScenario,
  startRun,
  waitForStatus,
  waitForTerminalSnapshot,
} from "./helpers";

for (const failure of [
  {
    scenario: "malformed_structured",
    code: "STRUCTURED_OUTPUT_INVALID",
  },
  {
    scenario: "provider_timeout",
    code: "RUN_TIMEOUT",
  },
  {
    scenario: "reviewer_failure",
    code: "PROVIDER_AUTHENTICATION_FAILED",
  },
]) {
  test(`${failure.scenario} ends safely without infinite loading`, async ({
    page,
    request,
  }) => {
    await setScenario(request, failure.scenario);
    const runId = await startRun(page);
    await waitForStatus(page, "运行失败");
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByTestId("connection-status")).toContainText("已关闭");
    const snapshot = await getSnapshot(request, runId);
    expect(snapshot.status).toBe("FAILED");
    expect(snapshot.error?.code).toBe(failure.code);
    expect(snapshot.error?.message).not.toMatch(/key|credential|Injected/i);
  });
}

test("maximum iteration limit is a distinct non-error terminal", async ({
  page,
  request,
}) => {
  await setScenario(request, "happy");
  const runId = await startRun(page, { threshold: 100, maxIterations: 1 });
  await waitForStatus(page, "已达迭代上限");
  const snapshot = await getSnapshot(request, runId);
  expect(snapshot.status).toBe("MAX_ITERATIONS_REACHED");
  expect(snapshot.versions).toHaveLength(1);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("fifth concurrent run returns 429 within one second", async ({
  request,
}) => {
  await setScenario(request, "provider_timeout");
  const payload = {
    user_idea: "Build a capacity validation product.",
    quality_threshold: 85,
    max_iterations: 2,
  };
  const accepted = await Promise.all(
    Array.from({ length: 4 }, () =>
      request.post(apiUrl("/api/runs"), { data: payload }),
    ),
  );
  const started = Date.now();
  const rejected = await request.post(apiUrl("/api/runs"), { data: payload });
  const durationMs = Date.now() - started;

  expect(accepted.every((response) => response.status() === 202)).toBeTruthy();
  expect(rejected.status()).toBe(429);
  expect((await rejected.json()).error.code).toBe("RUN_CAPACITY_REACHED");
  expect(durationMs).toBeLessThan(1000);

  for (const response of accepted) {
    const runId = (await response.json()).run_id as string;
    await request.post(apiUrl(`/api/runs/${runId}/cancel`));
    const terminal = await waitForTerminalSnapshot(request, runId);
    expect(terminal.status).toBe("CANCELLED");
  }
  await setScenario(request, "happy");
});
