// Drives the formal V3 app through the full workflow in a real browser and
// saves screenshots. Needs the backend (mock model) and Astro dev server up.
//   node scripts/v3/walkthrough.mjs [baseUrl] [outDir]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const base = process.argv[2] ?? "http://127.0.0.1:4351";
const out = process.argv[3] ?? "docs/v3-screenshots";
mkdirSync(out, { recursive: true });

const errors = [];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));
const shot = (name) => page.screenshot({ path: `${out}/${name}.png` });
const idle = async () => {
  // Wait until no AI task is shown as running.
  await page.waitForTimeout(400);
  await page.waitForFunction(
    () =>
      !document.querySelector(".typing") &&
      !/正在(生成|审查|检查)/.test(document.body.innerText),
    null,
    { timeout: 20_000 },
  );
  await page.waitForTimeout(300);
};

await page.goto(base);
await page
  .getByLabel("项目输入")
  .fill(
    "我想做一个云盘，支持磁力链接下载、在线播放和资源分享。目标用户是大学生。团队 3 人，预算有限。",
  );
await shot("01-home-typing");
await page.getByRole("button", { name: /^开始/ }).click();
await page.waitForURL(/#\/p\/.+\/explore/);
await idle();
await shot("02-explore-round1");

// Answer the first question, skip the rest.
const answers = page.getByTestId("answers");
await answers
  .locator("textarea")
  .first()
  .fill("大学生和刚工作的年轻人，宿舍网络慢，经常被限速");
await answers
  .getByRole("button", { name: /下一题|完成/ })
  .first()
  .click();
for (let i = 0; i < 3; i++) {
  const skip = answers.getByRole("button", { name: "跳过" });
  if (await skip.count()) await skip.first().click();
}
await answers.getByRole("button", { name: "发送" }).click();
await idle();
await page.locator(".trace").last().hover();
await page.waitForTimeout(200);
await shot("03-explore-round2-trace");

// Run the analyst and accept one finding.
await page.getByRole("button", { name: "检查需求" }).click();
await idle();
await shot("04-analyst-findings");
const req = page.getByTestId("requirements");
const accept = req.getByRole("button", { name: "采纳" });
if (await accept.count()) await accept.first().click();
await page.waitForTimeout(400);

// Confirm all items.
const all = req.getByRole("button", { name: "全部确认" });
if (await all.count()) await all.click();
await page.waitForTimeout(600);
await req.getByRole("tab", { name: "全部需求" }).click();
await shot("05-baseline-all");

// Brief.
await page.getByRole("button", { name: "整理成 Brief" }).click();
await page.waitForURL(/document/);
await page.waitForTimeout(600);
await shot("06-brief-draft");
await page.getByRole("button", { name: "检查 Brief" }).click();
await page.getByTestId("brief-check").waitFor({ timeout: 20_000 });
await page.waitForTimeout(300);
await shot("06b-brief-check");
const internal = /\b(POS|GOAL|USR|PRB|SCN|ALT|SOL|FR|CON|ASM|DEC|OPEN)-\d+\b/;
const briefCodes = internal.test(await page.locator(".brief").innerText());
await page.getByRole("button", { name: "确认 Brief" }).click();
await page.waitForTimeout(600);
await page.getByRole("button", { name: "生成 PRD 大纲" }).click();
await idle();
await shot("07-outline");
await page.getByRole("button", { name: "确认大纲并生成" }).click();
await page.waitForTimeout(500);
await shot("08-generating");
await idle();
await page.waitForSelector(".sec__body");
await shot("09-prd");

// Review.
const side = page.getByTestId("side-notes");
if (!(await side.count()))
  await page.getByRole("button", { name: /^审查/ }).click();
await page.getByRole("button", { name: "开始审查" }).click();
await idle();
await shot("10-review");
await page.locator(".anchor").first().click();
await page.waitForTimeout(300);
await shot("11-finding-detail");
await page.getByRole("button", { name: "各角色结论" }).click();
await page.waitForTimeout(200);
await shot("12-reviewer-summaries");
await page.getByRole("button", { name: "各角色结论" }).click();

// Accept the must-fix finding and optimize.
const must = page
  .locator(".note[data-finding]")
  .filter({ hasText: "必须修改" })
  .first();
await must.locator(".note__head").click();
await must.getByRole("button", { name: "采纳", exact: true }).click();
await page.waitForTimeout(500);
await page.getByRole("button", { name: "按采纳的意见修改" }).click();
await idle();
await page.getByTestId("proposal").scrollIntoViewIfNeeded();
await shot("13-proposal");
await page.getByRole("button", { name: /应用 \d+ 处修改/ }).click();
await page.waitForTimeout(800);
await shot("14-applied");

// Human edit with impact.
const exception = page
  .locator("section.sec")
  .filter({ hasText: "异常处理" })
  .first();
await exception.hover();
await exception.getByRole("button", { name: "编辑" }).click();
const editor = exception.locator("textarea");
await editor.fill(
  (await editor.inputValue()).replace("长时间没有响应", "超过 30 分钟没有进度"),
);
await exception.getByRole("button", { name: "保存" }).click();
await page.waitForTimeout(600);
await shot("15-saved-impact");

// Versions and compare.
await page.locator(".vbtn").click();
await page.waitForTimeout(200);
await shot("16-version-menu");
const cmp = page.getByRole("menuitem", { name: /对比/ });
if (await cmp.count()) {
  await cmp.click();
  await page.waitForTimeout(500);
  await shot("17-compare");
  await page.getByRole("button", { name: "退出对比" }).click();
}

// Quality.
await page.getByRole("button", { name: "质量" }).click();
await page.waitForTimeout(500);
await shot("18-quality");

// Export.
const [download] = await Promise.all([
  page.waitForEvent("download"),
  page.getByRole("button", { name: "导出" }).click(),
]);
const path = `${out}/export.md`;
await download.saveAs(path);

// Home with a real project.
await page.goto(base);
await page.waitForSelector('[data-testid="featured-project"]');
await shot("19-home-projects");

// Responsive checks of the three pages.
const projectUrl = await page
  .getByTestId("featured-project")
  .getAttribute("href");
const overflow = {};
for (const [w, h] of [
  [1440, 900],
  [1280, 800],
  [1024, 768],
  [390, 844],
]) {
  await page.setViewportSize({ width: w, height: h });
  for (const [name, url] of [
    ["home", base + "/"],
    ["explore", base + "/" + projectUrl.replace("document", "explore")],
    ["document", base + "/" + projectUrl.replace("explore", "document")],
  ]) {
    await page.goto(url);
    await page.waitForTimeout(900);
    overflow[`${name}-${w}`] = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    await shot(`size-${name}-${w}`);
  }
}

const { readFileSync } = await import("node:fs");
const exportCodes = internal.test(readFileSync(path, "utf8"));
console.log(
  JSON.stringify(
    { errors, overflow, briefCodes, exportCodes, export: path },
    null,
    1,
  ),
);
await browser.close();
