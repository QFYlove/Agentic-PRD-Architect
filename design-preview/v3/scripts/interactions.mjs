// Smoke-test the prototype's interactions and capture state screenshots.
import { chromium } from "@playwright/test";
const out = process.argv[2] ?? "design-preview/v3/screenshots";
const base = "http://127.0.0.1:4341";
const browser = await chromium.launch();
const errors = [];
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

// 02: hover link line, then submit round 3.
await page.goto(`${base}/#/explore`);
await page
  .locator('.talk [data-ref="USR-01"]')
  .first()
  .scrollIntoViewIfNeeded();
await page.locator('.talk [data-ref="USR-01"]').first().hover();
await page.waitForTimeout(400);
const connector = await page.locator(".connector").count();
await page.screenshot({ path: `${out}/explore-1440-link.png` });
await page.locator(".now").scrollIntoViewIfNeeded();
await page.screenshot({ path: `${out}/explore-1440-round.png` });
await page.getByRole("button", { name: "跳过" }).last().click();
await page.getByRole("button", { name: /提交本轮/ }).click();
await page.waitForTimeout(1300);
const decisions = await page.locator('.baseline [data-item^="DEC-"]').count();
const round = await page.locator(".now__round").textContent();
await page.screenshot({ path: `${out}/explore-1440-after-submit.png` });
// Confirm an inferred item.
await page
  .locator('.baseline [data-item="POS-01"]')
  .getByRole("button", { name: "确认" })
  .click();
const posStatus = await page
  .locator('.baseline [data-item="POS-01"] .item__status')
  .textContent();
// Open a finding note.
await page.locator(".note__head").first().click();
await page.screenshot({ path: `${out}/explore-1440-finding.png` });

// 03: edit a section, diff mode, history version, TOC on narrow width.
await page.goto(`${base}/#/editor`);
await page.locator("#sec-s4-3").scrollIntoViewIfNeeded();
await page.locator("#sec-s4-3").hover();
await page.locator("#sec-s4-3 .sec__edit").click();
await page
  .locator("#sec-s4-3 textarea")
  .fill(
    "下载完成的视频可以直接播放。\n- 支持倍速、记忆播放进度。\n- 支持 MP4、MKV 两种格式 [假设]。",
  );
await page.screenshot({ path: `${out}/editor-1440-editing.png` });
await page.getByRole("button", { name: "保存章节" }).click();
await page.waitForTimeout(200);
const toast = await page.locator(".toast").textContent();
const origin = await page.locator("#sec-s4-3 .origin").textContent();
await page.screenshot({ path: `${out}/editor-1440-saved.png` });
await page.getByRole("tab", { name: "对比 v2" }).click();
await page.waitForTimeout(300);
await page.screenshot({ path: `${out}/editor-1440-diff.png` });
await page.getByRole("tab", { name: "正文" }).click();
await page.locator(".anchor").first().click();
await page.waitForTimeout(400);
await page.screenshot({ path: `${out}/editor-1440-finding.png` });
await page.getByRole("tab", { name: "需求追溯" }).click();
await page.screenshot({ path: `${out}/editor-1440-trace.png` });
await page.getByRole("radio", { name: /v1/ }).click();
const banner = await page.locator(".doc__banner").first().textContent();

const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
mobile.on("pageerror", (e) => errors.push(e.message));
await mobile.goto(`${base}/#/explore`);
await mobile.getByRole("tab", { name: /需求基线/ }).click();
await mobile.screenshot({ path: `${out}/explore-390-baseline.png` });
await mobile.goto(`${base}/#/editor`);
await mobile.getByRole("button", { name: /问题/ }).first().click();
await mobile.waitForTimeout(300);
await mobile.screenshot({ path: `${out}/editor-390-panel.png` });
await mobile.goto(`${base}/#/workspace`);
await mobile.evaluate(() => window.scrollTo(0, 1100));
await mobile.screenshot({ path: `${out}/workspace-390-list.png` });
const overflow = await mobile.evaluate(
  () => document.documentElement.scrollWidth - innerWidth,
);

await browser.close();
console.log(
  JSON.stringify(
    {
      connector,
      decisions,
      round,
      posStatus,
      toast,
      origin,
      banner,
      overflow,
      errors,
    },
    null,
    1,
  ),
);
