import { chromium } from "@playwright/test";
const out = process.argv[2] ?? "design-preview/v3/screenshots";
const widths = [1440, 1280, 1024, 390];
const pages = ["workspace", "explore", "editor"];
const browser = await chromium.launch();
const errors = [];
for (const w of widths) {
  const ctx = await browser.newContext({
    viewport: { width: w, height: w === 390 ? 844 : 900 },
    deviceScaleFactor: 1,
  });
  const page = await ctx.newPage();
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`${w} ${m.text()}`);
  });
  page.on("pageerror", (e) => errors.push(`${w} ${e.message}`));
  for (const p of pages) {
    await page.goto(`http://127.0.0.1:4341/#/${p}`);
    await page.waitForTimeout(500);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    if (overflow > 0)
      errors.push(`${w} ${p} horizontal overflow ${overflow}px`);
    await page.screenshot({ path: `${out}/${p}-${w}.png`, fullPage: false });
  }
  await ctx.close();
}
await browser.close();
console.log(
  errors.length ? errors.join("\n") : "no console errors, no overflow",
);
