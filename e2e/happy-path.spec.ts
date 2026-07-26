import { readFile } from "node:fs/promises";

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

test("Podcast case completes two reviewed versions and downloads Markdown", async ({
  page,
  request,
}) => {
  const runId = await startRun(page);

  await waitForStatus(page, "已完成");
  await expect(page.getByTestId("version-tab-v1")).toContainText("71");
  await expect(page.getByTestId("version-tab-v2")).toContainText("88");
  await expect(page.getByTestId("score-v1")).toContainText("71");
  await expect(page.getByTestId("score-v2")).toContainText("88");
  await expect(page.getByLabel("对比不同 PRD 版本评分的雷达图")).toBeVisible();
  await expect(page.getByText("技术评审").first()).toBeVisible();
  await expect(page.getByText("体验评审").first()).toBeVisible();
  await expect(page.getByText("商业评审").first()).toBeVisible();
  await expect(page.getByText("优化方案已生成").first()).toBeVisible();

  const snapshot = await getSnapshot(request, runId);
  expect(snapshot.status).toBe("COMPLETED");
  expect(snapshot.versions).toHaveLength(2);
  expect(
    snapshot.versions.map((item) => item.evaluation?.overall_score),
  ).toEqual([71, 88]);
  const v2 = snapshot.versions[1]!;
  expect(v2.revision_plan?.items.length).toBeGreaterThan(0);

  const events = await getEvents(request, runId);
  expect(events.map((event) => event.sequence)).toEqual(
    [...events.map((event) => event.sequence)].sort(
      (left, right) => left - right,
    ),
  );
  expect(new Set(events.map((event) => event.sequence)).size).toBe(
    events.length,
  );

  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("download-markdown").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`agentic-prd-${runId}-v2.md`);
  const path = await download.path();
  expect(path).not.toBeNull();
  expect(await readFile(path!, "utf8")).toBe(v2.content);
});
