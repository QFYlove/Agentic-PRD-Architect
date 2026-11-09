// Walk through the main interactions and capture state screenshots.
import { chromium } from "@playwright/test";
const out = process.argv[2] ?? "design-preview/v4/screenshots";
const base = "http://127.0.0.1:4342";
const browser = await chromium.launch();
const errors = [];
const result = {};
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

// Home: type an idea.
await page.goto(`${base}/#/`);
await page
  .getByLabel("项目输入")
  .fill("我想做一个帮助独立咖啡馆管理会员储值和积分的小程序。");
await page.screenshot({ path: `${out}/i01-home-typing.png` });

// Explore: hover a trace, open an insight, answer and send.
await page.goto(`${base}/#/p7/explore`);
await page.waitForTimeout(400);
await page.screenshot({ path: `${out}/i02-explore-round.png` });
await page.getByRole("tab", { name: "全部需求" }).click();
const trace = page.locator(".trace").nth(1);
await trace.scrollIntoViewIfNeeded();
await trace.hover();
await page.waitForTimeout(200);
result.lit = await page.locator(".irow.is-lit").count();
await page.screenshot({ path: `${out}/i03-explore-trace.png` });
await page.getByRole("tab", { name: /待你决定/ }).click();
await page.locator(".req .insight__head").first().click();
await page.screenshot({ path: `${out}/i04-explore-insight.png` });
await page
  .locator(".req .insight")
  .first()
  .getByRole("button", { name: "采纳" })
  .click();
await page
  .locator(".req [data-item='POS-01']")
  .getByRole("button", { name: "确认" })
  .click();
result.pendingAfter = await page.locator(".req .seg .count").textContent();
await page.locator(".answers").scrollIntoViewIfNeeded();
await page.locator(".answers").getByRole("button", { name: "跳过" }).click();
await page.screenshot({ path: `${out}/i05-explore-answered.png` });
await page.getByRole("button", { name: /发送回答/ }).click();
await page.waitForTimeout(1500);
result.round = await page.locator(".talk__status").textContent();
await page.screenshot({ path: `${out}/i06-explore-next-round.png` });

// Document: open a note from the text, accept with a modification, edit a section, compare.
await page.goto(`${base}/#/p7/document`);
await page.locator(".anchor").first().click();
await page.waitForTimeout(400);
await page.screenshot({ path: `${out}/i07-document-note.png` });
await page.getByRole("button", { name: "修改后采纳" }).click();
await page.getByLabel("修改意见").fill("状态里加上「已取消」。");
await page.getByRole("button", { name: "按我的意见采纳" }).click();
const sec = page.locator("#sec-s4-3");
await sec.scrollIntoViewIfNeeded();
await sec.hover();
await sec.getByRole("button", { name: "编辑" }).click();
await sec
  .locator("textarea")
  .fill(
    "下载完成的视频可以直接播放，不需要先转存。\n- 支持倍速，记忆播放进度。\n- 支持 MP4 和 MKV，其他格式提示下载后本地播放 [假设]。",
  );
await page.screenshot({ path: `${out}/i08-document-editing.png` });
await sec.getByRole("button", { name: "保存" }).click();
await page.waitForTimeout(250);
result.toast = await page.locator(".toast").textContent();
await page.screenshot({ path: `${out}/i09-document-saved.png` });
await page.locator(".vbtn").click();
await page.screenshot({ path: `${out}/i10-document-versions.png` });
await page.getByRole("menuitem", { name: /对比/ }).click();
await page.waitForTimeout(300);
await page.screenshot({ path: `${out}/i11-document-compare.png` });
await page.getByRole("button", { name: "退出对比" }).click();
await page.locator("#sec-s4-1").hover();
await page.locator("#sec-s4-1").getByRole("button", { name: "来源" }).click();
await page.waitForTimeout(250);
await page.screenshot({ path: `${out}/i12-document-sources.png` });

// Narrow screens.
const m = await browser.newPage({ viewport: { width: 390, height: 844 } });
m.on("pageerror", (e) => errors.push(e.message));
await m.goto(`${base}/#/p7/explore`);
await m.waitForTimeout(300);
await m.screenshot({ path: `${out}/i13-mobile-explore.png` });
await m.getByRole("button", { name: /^需求/ }).click();
await m.waitForTimeout(250);
await m.screenshot({ path: `${out}/i14-mobile-requirements.png` });
await m.goto(`${base}/#/p7/document`);
await m.getByRole("button", { name: /审查意见/ }).click();
await m.waitForTimeout(250);
await m.screenshot({ path: `${out}/i15-mobile-notes.png` });
result.overflow = await m.evaluate(
  () => document.documentElement.scrollWidth - innerWidth,
);

await browser.close();
console.log(JSON.stringify({ ...result, errors }, null, 1));
