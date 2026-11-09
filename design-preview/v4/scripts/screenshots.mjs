// Capture each page at four widths; report console errors and horizontal overflow.
import { chromium } from "@playwright/test";
const out = process.argv[2] ?? "design-preview/v4/screenshots";
const base = "http://127.0.0.1:4342";
const widths = [1440, 1280, 1024, 390];
const pages = [
  ["home", ""],
  ["explore", "p7/explore"],
  ["document", "p7/document"],
];
const browser = await chromium.launch();
const problems = [];
for (const w of widths) {
  const ctx = await browser.newContext({
    viewport: { width: w, height: w === 390 ? 844 : 900 },
  });
  const page = await ctx.newPage();
  page.on(
    "console",
    (m) => m.type() === "error" && problems.push(`${w} ${m.text()}`),
  );
  page.on("pageerror", (e) => problems.push(`${w} ${e.message}`));
  for (const [name, hash] of pages) {
    await page.goto(`${base}/#/${hash}`);
    await page.reload();
    await page.waitForTimeout(500);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - innerWidth,
    );
    if (overflow > 0) problems.push(`${w} ${name} overflows by ${overflow}px`);
    await page.screenshot({ path: `${out}/${name}-${w}.png` });
  }
  await ctx.close();
}
await browser.close();
console.log(
  problems.length ? problems.join("\n") : "no console errors, no overflow",
);
