import { expect, test } from "@playwright/test";

import {
  getEvents,
  getSnapshot,
  setScenario,
  startRun,
  waitForStatus,
} from "./helpers";

test.beforeEach(async ({ request }) => {
  await setScenario(request, "happy");
});

test("pause at review safe point and resume with user requirement", async ({
  page,
  request,
}) => {
  const runId = await startRun(page);
  await waitForStatus(page, "评审中");
  await page.getByRole("button", { name: "暂停" }).click();
  await waitForStatus(page, "安全暂停中");
  await waitForStatus(page, "已暂停");

  const paused = await getSnapshot(request, runId);
  expect(paused.versions).toHaveLength(1);
  const pausedV1 = paused.versions[0]!;
  expect(pausedV1.evaluation).not.toBeNull();
  expect(paused.node_statuses.optimizer).toBe("PENDING");

  const requirement = "Add explicit refund and creator payout reconciliation.";
  await page.getByLabel(/补充优化要求/).fill(requirement);
  await page.getByRole("button", { name: "继续运行" }).click();
  await waitForStatus(page, "已完成");

  const completed = await getSnapshot(request, runId);
  expect(completed.versions).toHaveLength(2);
  const completedV2 = completed.versions[1]!;
  expect(completedV2.revision_plan?.user_override).toBe(requirement);
  expect(completedV2.content).toContain(requirement);

  const events = await getEvents(request, runId);
  const names = events.map((event) => event.event);
  expect(names.indexOf("pause_requested")).toBeLessThan(
    names.indexOf("run_paused"),
  );
  expect(names.indexOf("run_paused")).toBeLessThan(
    names.indexOf("run_resumed"),
  );
  const optimizerStart = events.findIndex(
    (event) =>
      event.event === "node_started" && event.payload.node === "optimizer",
  );
  expect(optimizerStart).toBeGreaterThan(names.indexOf("run_resumed"));
});

for (const stage of ["generation", "review"] as const) {
  test(`cancel during ${stage} rejects late results`, async ({
    page,
    request,
  }) => {
    const runId = await startRun(page);
    await waitForStatus(page, stage === "generation" ? "生成中" : "评审中");
    await page.getByRole("button", { name: "取消", exact: true }).click();
    await waitForStatus(page, "已取消");
    await expect(page.getByTestId("connection-status")).toContainText("已关闭");
    await expect(
      page.getByRole("button", { name: "取消", exact: true }),
    ).toHaveCount(0);
    await expect(page.getByRole("button", { name: "新建任务" })).toBeEnabled();

    const snapshot = await getSnapshot(request, runId);
    expect(snapshot.status).toBe("CANCELLED");

    // `finish_generation` appends version 1 atomically, so a cancel issued
    // during generation legitimately lands on either side of that commit: 0
    // versions if it won the race, 1 if generation had already finished.
    // Asserting a fixed 0 here is what made this case ~5% flaky. Reaching
    // 评审中 means the commit is already durable, so there 1 is exact.
    expect(stage === "generation" ? [0, 1] : [1]).toContain(
      snapshot.versions.length,
    );

    // Whatever survived the race must be a whole generation result: the
    // complete document, mirrored into `current_prd`, carrying none of the
    // review output that a late reviewer would have written into it.
    for (const version of snapshot.versions) {
      expect(version.version).toBe(1);
      expect(version.content).toBe(snapshot.current_prd);
      expect(version.content).toContain(
        "# Product Requirements Document — Version 1",
      );
      expect(version.content).toContain("## Acceptance Criteria");
      expect(version.revision_plan).toBeNull();
    }
    if (stage === "generation") {
      // No reviewer can have run: they all check the cancel signal on entry,
      // and it is set before `run_cancelled` reaches the browser.
      expect(snapshot.versions[0]?.evaluation ?? null).toBeNull();
    }

    const events = await getEvents(request, runId);
    const names = events.map((event) => event.event);
    expect(names).toContain("run_cancelled");
    expect(names).not.toContain("run_completed");
    expect(names).not.toContain("max_iterations_reached");
    // Cancellation is a hard stop for business results. Telemetry may still
    // flush the tokens already spent, so the invariant is about what the run
    // produces, not about `run_cancelled` being the very last frame.
    const afterCancel = names.slice(names.indexOf("run_cancelled") + 1);
    expect(afterCancel).not.toContain("prd_delta");
    expect(afterCancel).not.toContain("prd_generated");
    expect(afterCancel).not.toContain("review_completed");
    expect(afterCancel).not.toContain("scores_updated");
    expect(afterCancel).not.toContain("revision_planned");

    // Pin the observed result, then prove nothing further accretes onto it.
    const sequence = snapshot.latest_event_sequence;
    const contents = snapshot.versions.map((version) => version.content);
    await page.waitForTimeout(300);
    const stable = await getSnapshot(request, runId);
    expect(stable.status).toBe("CANCELLED");
    expect(stable.versions.map((version) => version.content)).toEqual(contents);
    expect(stable.latest_event_sequence).toBe(sequence);
  });
}
