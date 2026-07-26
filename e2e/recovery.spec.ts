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

test("three SSE connection failures recover through an atomic snapshot", async ({
  page,
  request,
}) => {
  let failures = 0;
  await page.route("**/api/runs/*/events?**", async (route) => {
    if (failures < 3) {
      failures += 1;
      await route.abort("connectionfailed");
      return;
    }
    await route.continue();
  });

  const runId = await startRun(page);
  await waitForStatus(page, "已完成");

  expect(failures).toBe(3);
  await expect(page.getByTestId("version-tab-v1")).toHaveCount(1);
  await expect(page.getByTestId("version-tab-v2")).toHaveCount(1);
  const snapshot = await getSnapshot(request, runId);
  const v2 = snapshot.versions[1]!;
  await expect(page.getByTestId("prd-content")).toContainText(
    "Reliability, Refunds, and Risk Controls",
  );
  expect(v2.content.match(/## Product Idea/g)).toHaveLength(1);
});

test("network loss between reviewer events replays without duplicates", async ({
  page,
  request,
  context,
}) => {
  const runId = await startRun(page);
  await expect(page.getByText("技术评审").first()).toBeVisible();
  const runUrl = page.url();
  await context.setOffline(true);
  await page.reload({ timeout: 1_000 }).catch(() => null);
  await context.setOffline(false);
  await page.goto(runUrl);
  await waitForStatus(page, "已完成");

  const snapshot = await getSnapshot(request, runId);
  const events = await getEvents(request, runId);
  const sequences = events.map((event) => event.sequence);
  expect(new Set(sequences).size).toBe(sequences.length);
  expect(snapshot.versions).toHaveLength(2);
  await expect(page.getByRole("tab")).toHaveCount(2);
  const renderedSequences = await page
    .getByTestId("trace-event")
    .evaluateAll((items) =>
      items.map((item) => Number(item.getAttribute("data-sequence"))),
    );
  expect(renderedSequences.length).toBeGreaterThan(0);
  expect(new Set(renderedSequences).size).toBe(renderedSequences.length);
  await expect(page.getByText("技术评审").first()).toBeVisible();
  await expect(page.getByText("体验评审").first()).toBeVisible();
  await expect(page.getByText("商业评审").first()).toBeVisible();
});
