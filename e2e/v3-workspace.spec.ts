import { expect, test, type Page } from "@playwright/test";

// The V3 workspace end to end, on the real backend with the mock model.

const IDEA =
  "我想做一个云盘，支持磁力链接下载、在线播放和资源分享。目标用户是大学生。团队 3 人，预算有限。";

async function waitIdle(page: Page) {
  await expect(page.locator(".typing")).toHaveCount(0, { timeout: 20_000 });
}

async function createProject(page: Page): Promise<string> {
  await page.goto("/");
  await page.getByLabel("项目输入").fill(IDEA);
  await page.getByRole("button", { name: /^开始/ }).click();
  await page.waitForURL(/#\/p\/[a-f0-9]+\/explore/);
  await waitIdle(page);
  return /#\/p\/([a-f0-9]+)/.exec(page.url())![1]!;
}

test("idea → exploration → brief → PRD → review → optimise → export", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const projectId = await createProject(page);

  // AI items wait for the user; nothing is confirmed on its own.
  const panel = page.getByTestId("requirements");
  await expect(panel.getByRole("tab", { name: /待你决定/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(panel.locator(".irow")).not.toHaveCount(0);

  // One round: answer the first question, skip the rest.
  const answers = page.getByTestId("answers");
  await answers.locator("textarea").first().fill("大学生和刚工作的年轻人");
  for (let i = 0; i < 3; i++) {
    const skip = answers.getByRole("button", { name: "跳过" });
    if (await skip.count()) await skip.first().click();
  }
  await answers.getByRole("button", { name: "发送" }).click();
  await waitIdle(page);
  await expect(page.getByTestId("thread").locator(".msg")).toHaveCount(4);

  // Product analysis, then confirm everything.
  await page.getByRole("button", { name: "检查需求" }).click();
  await waitIdle(page);
  await expect(panel.locator(".insight")).not.toHaveCount(0);
  await panel.getByRole("button", { name: "全部确认" }).click();
  await expect(panel.getByRole("button", { name: "全部确认" })).toHaveCount(0);

  // Brief and outline.
  await page.getByRole("button", { name: "整理成 Brief" }).click();
  await page.getByRole("button", { name: "确认 Brief" }).click();
  await page.getByRole("button", { name: "生成 PRD 大纲" }).click();
  await expect(page.getByTestId("outline-editor")).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "确认大纲并生成" }).click();
  await expect(
    page.getByTestId("paper").locator(".sec__body").first(),
  ).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(/正在生成/)).toHaveCount(0, { timeout: 20_000 });

  // Four reviewers.
  if (!(await page.getByTestId("side-notes").count())) {
    await page.getByRole("button", { name: /^审查/ }).click();
  }
  await page.getByRole("button", { name: "开始审查" }).click();
  await expect(page.getByTestId("findings")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "各角色结论" }).click();
  await expect(
    page.getByTestId("review-summaries").locator(".summary"),
  ).toHaveCount(4);

  // Highlight in the text opens the finding.
  await page.locator(".anchor").first().click();
  const open = page.locator(".note.is-open");
  await expect(open).toBeVisible();
  await open.getByRole("button", { name: "采纳", exact: true }).click();

  // Proposal, then apply.
  await page.getByRole("button", { name: "按采纳的意见修改" }).click();
  await expect(page.getByTestId("proposal")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /应用 \d+ 处修改/ }).click();
  await expect(page.locator(".vbtn b")).toHaveText("v2");

  // Export without internal markers.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "导出" }).click(),
  ]);
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk as Buffer);
  const text = Buffer.concat(chunks).toString("utf8");
  expect(text).toMatch(/^# /);
  expect(text).not.toContain("PRD_COMPLETE");
  expect(text).not.toContain("[[");

  // The project persists and the home page points at the next step.
  await page.goto("/");
  const featured = page.getByTestId("featured-project");
  await expect(featured).toHaveAttribute("href", new RegExp(projectId));
});

test("a human edit is saved with its impact and never lost on reload", async ({
  page,
}) => {
  await createProject(page);
  const panel = page.getByTestId("requirements");
  await panel.getByRole("button", { name: "全部确认" }).click();
  await page.getByRole("button", { name: "整理成 Brief" }).click();
  await page.getByRole("button", { name: "确认 Brief" }).click();
  await page.getByRole("button", { name: "生成 PRD 大纲" }).click();
  await page
    .getByRole("button", { name: "确认大纲并生成" })
    .click({ timeout: 20_000 });
  await expect(page.getByText(/正在生成/)).toHaveCount(0, { timeout: 20_000 });

  const section = page
    .locator("section.sec")
    .filter({ hasText: "异常处理" })
    .first();
  await section.hover();
  await section.getByRole("button", { name: "编辑" }).click();
  const editor = section.locator("textarea");
  await editor.fill(
    (await editor.inputValue()) + "\n- 我自己加的规则：最多重试 3 次。",
  );
  await section.getByRole("button", { name: "保存" }).click();
  await expect(page.getByTestId("toast")).toContainText("已保存");
  await expect(section.locator(".sec__by")).toHaveText("你写的");

  await page.reload();
  await expect(
    page.locator("section.sec").filter({ hasText: "我自己加的规则" }),
  ).toBeVisible();
});

test("deleting a project removes it from the list and its link", async ({
  page,
}) => {
  const projectId = await createProject(page);
  await page.goto("/");
  const manage = page.locator(".prow--manage");
  await manage.getByRole("button", { name: "删除" }).click();
  await page.getByRole("button", { name: "删除", exact: true }).last().click();
  await expect(page.getByTestId("toast")).toContainText("已删除");
  await page.goto(`/#/p/${projectId}/explore`);
  await expect(page.getByText("这个项目不存在，或已经删除。")).toBeVisible();
});

test("the V2 run history stays readable at /runs", async ({ page }) => {
  await page.goto("/runs");
  await expect(page.getByLabel("产品想法")).toBeVisible();
});

for (const width of [1440, 1280, 1024, 390]) {
  test(`the three V3 pages fit ${width}px without sideways scroll`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const projectId = await createProject(page);
    for (const url of [
      "/",
      `/#/p/${projectId}/explore`,
      `/#/p/${projectId}/document`,
    ]) {
      await page.goto(url);
      await page.waitForTimeout(400);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow, url).toBeLessThanOrEqual(0);
    }
  });
}

test("an idea project can check its Brief, and the Brief shows no internal codes", async ({
  page,
}) => {
  await createProject(page);
  await page.getByRole("button", { name: "整理成 Brief" }).click();
  await expect(page.getByRole("button", { name: "确认 Brief" })).toBeVisible();
  const brief = page.locator(".brief");
  await expect(brief).not.toContainText(/\b(POS|USR|PRB|SCN|GOAL|FR)-\d+\b/);

  await page.getByRole("button", { name: "检查 Brief" }).click();
  await expect(page.getByTestId("brief-check")).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByTestId("brief-check").locator(".insight"),
  ).not.toHaveCount(0);

  // The PRD review is offered once the PRD exists, and runs all four reviewers.
  await page.getByRole("button", { name: "确认 Brief" }).click();
  await page.getByRole("button", { name: "生成 PRD 大纲" }).click();
  await page
    .getByRole("button", { name: "确认大纲并生成" })
    .click({ timeout: 20_000 });
  await expect(page.getByText(/正在生成/)).toHaveCount(0, { timeout: 20_000 });
  await expect(page.getByTestId("paper")).not.toContainText(
    /\b(POS|USR|PRB|SCN|GOAL|FR)-\d+\b/,
  );
  if (!(await page.getByTestId("side-notes").count())) {
    await page.getByRole("button", { name: /^审查/ }).click();
  }
  await page.getByRole("button", { name: "开始审查" }).click();
  await page
    .getByRole("button", { name: "各角色结论" })
    .click({ timeout: 20_000 });
  await expect(
    page.getByTestId("review-summaries").locator(".summary"),
  ).toHaveCount(4);
  await expect(page.getByTestId("review-summaries")).not.toContainText(
    "没有完成",
  );
});
