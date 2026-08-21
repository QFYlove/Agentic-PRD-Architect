import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";

import {
  getEvents,
  getSnapshot,
  PODCAST_IDEA,
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

  // The document is the default panel, so the reviewer cards and the score
  // chart are one tab away rather than beside it.
  await expect(page.getByTestId("workspace-panel-prd")).toBeVisible();
  await page.getByTestId("workspace-tab-review").click();
  await expect(page.getByText("技术评审").first()).toBeVisible();
  await expect(page.getByText("体验评审").first()).toBeVisible();
  await expect(page.getByText("商业评审").first()).toBeVisible();

  await page.getByTestId("workspace-tab-trace").click();
  await expect(page.getByTestId("score-v1")).toContainText("71");
  await expect(page.getByTestId("score-v2")).toContainText("88");
  await expect(page.getByLabel("对比不同 PRD 版本评分的雷达图")).toBeVisible();
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

  await page.getByTestId("workspace-tab-prd").click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("download-markdown").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`agentic-prd-${runId}-v2.md`);
  const path = await download.path();
  expect(path).not.toBeNull();
  expect(await readFile(path!, "utf8")).toBe(v2.content);

  await expect(
    page.getByRole("button", { name: new RegExp(PODCAST_IDEA) }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "新建对话" }).click();
  await expect(
    page.getByRole("heading", { name: /让每一份需求/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: new RegExp(PODCAST_IDEA) })
    .first()
    .click();
  await expect
    .poll(() => new URL(page.url()).searchParams.get("run_id"))
    .toBe(runId);
  await waitForStatus(page, "已完成");
});

test("A completed run states its gate outcome without reading as unfinished work", async ({
  page,
}) => {
  await startRun(page);
  await waitForStatus(page, "已完成");

  // The mock happy path clears its target with no blocker left, so the close
  // has to read as done -- not as "十几条需要修改".
  const outcome = page.getByTestId("run-outcome");
  await expect(outcome).toHaveAttribute("data-tone", "passed");
  await expect(outcome).toContainText("已达到目标质量");
  await expect(outcome).not.toContainText("需要修改");
  await expect(page.getByTestId("outcome-fact-必须修复")).toHaveText("0");
  await expect(page.getByTestId("outcome-fact-目标评分")).toHaveText("85");
  await expect(page.getByTestId("outcome-fact-最佳版本")).toContainText("v2");

  await page.getByTestId("workspace-tab-review").click();
  // Reviewer findings are grouped as advice, under the neutral 剩余问题 label.
  await expect(page.getByText("剩余问题").first()).toBeVisible();
  await expect(page.getByTestId("review-panel")).not.toContainText("需要修改");
});

test("Reviewer detail, revision plan, and the v1 to v2 diff follow the selected version", async ({
  page,
}) => {
  await startRun(page);
  await waitForStatus(page, "已完成");

  // v2 is the newest version: it was reviewed, but nothing was planned from it.
  await page.getByTestId("workspace-tab-review").click();
  const reviewPanel = page.getByTestId("review-panel");
  await expect(reviewPanel).toHaveAttribute("data-version", "2");
  for (const role of ["tech", "ux", "biz"]) {
    await expect(page.getByTestId(`reviewer-card-${role}`)).toBeVisible();
  }
  await expect(page.getByTestId("reviewer-score-tech")).toContainText("88");
  await expect(page.getByTestId("workspace-tab-plan")).toBeDisabled();

  await page.getByTestId("version-tab-v1").click();
  await expect(reviewPanel).toHaveAttribute("data-version", "1");
  await expect(page.getByTestId("reviewer-score-tech")).toContainText("65");
  await expect(page.getByTestId("reviewer-feedback-tech")).toBeVisible();

  // The plan built from v1's findings is what produced v2.
  await page.getByTestId("workspace-tab-plan").click();
  const planPanel = page.getByTestId("revision-plan-panel");
  await expect(planPanel).toHaveAttribute("data-source-version", "1");
  await expect(planPanel).toHaveAttribute("data-target-version", "2");
  await expect(page.getByTestId("revision-plan-lineage")).toContainText(
    "用于生成 v2",
  );
  await expect(
    page
      .getByTestId("revision-item")
      .first()
      .getByTestId("revision-item-priority"),
  ).toHaveText("高优先级");

  // v1 has no predecessor, so there is nothing for the comparison tab to show.
  await expect(page.getByTestId("workspace-tab-diff")).toBeDisabled();

  // Reviewer findings -> revision plan -> what v2's text actually changed.
  await page.getByTestId("version-tab-v2").click();
  await page.getByTestId("workspace-tab-diff").click();
  const diff = page.getByTestId("version-diff");
  await expect(diff).toHaveAttribute("data-source-version", "1");
  await expect(diff).toHaveAttribute("data-target-version", "2");
  // A PM opens the comparison on rendered prose, not on Markdown source.
  await expect(diff).toHaveAttribute("data-mode", "reading");
  await expect(page.getByTestId("diff-row-added")).toHaveCount(0);
  // The mock optimizer's v2 adds a refund section that v1 does not have.
  await expect(
    page
      .getByTestId("reading-block-added")
      .filter({ hasText: "Refund requests" })
      .first(),
  ).toBeVisible();
  // Markdown table pipes and heading hashes are rendered, never printed.
  await expect(diff).not.toContainText("| --- |");

  await page.getByTestId("diff-mode-source").click();
  await expect(diff).toHaveAttribute("data-mode", "source");
  await expect(
    page.getByTestId("diff-row-added").filter({ hasText: "Refund requests" }),
  ).toBeVisible();

  await page.getByTestId("workspace-tab-prd").click();
  await expect(page.getByTestId("version-diff")).toHaveCount(0);
  await expect(page.getByTestId("prd-content")).toContainText(
    "Reliability, Refunds, and Risk Controls",
  );
});

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
] as const;

for (const viewport of VIEWPORTS) {
  test(`The workspace fits ${viewport.name} without horizontal overflow`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await startRun(page);
    await waitForStatus(page, "已完成");

    for (const tab of ["prd", "review", "diff", "trace"]) {
      if (tab === "diff" || tab === "review") {
        await page.getByTestId("version-tab-v2").click();
      }
      await page.getByTestId(`workspace-tab-${tab}`).click();
      await expect(page.getByTestId(`workspace-panel-${tab}`)).toBeVisible();
      // A document tool that makes the page scroll sideways is broken on a
      // phone and sloppy on a desktop, so this is checked on every panel.
      const overflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      );
      expect(overflow, `${tab} overflows horizontally`).toBeLessThanOrEqual(1);
    }
  });
}
