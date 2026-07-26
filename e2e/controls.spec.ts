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
    await page.getByRole("button", { name: "取消" }).click();
    await waitForStatus(page, "已取消");
    await expect(page.getByTestId("connection-status")).toContainText("已关闭");
    await expect(page.getByRole("button", { name: "取消" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "新建任务" })).toBeEnabled();

    const snapshot = await getSnapshot(request, runId);
    const expectedVersions = stage === "generation" ? 0 : 1;
    expect(snapshot.versions).toHaveLength(expectedVersions);
    expect(snapshot.status).toBe("CANCELLED");
    const sequence = snapshot.latest_event_sequence;
    await page.waitForTimeout(300);
    const stable = await getSnapshot(request, runId);
    expect(stable.versions).toHaveLength(expectedVersions);
    expect(stable.latest_event_sequence).toBe(sequence);
  });
}
