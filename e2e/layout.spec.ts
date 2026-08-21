/**
 * Layout verification against a realistically long PRD.
 *
 * Every other spec drives the mock provider, whose PRD is ~40 short lines. That
 * is enough to prove the tabs work and nothing overflows, and not enough to
 * prove the layout holds: the things that actually break a reading column are
 * six-column GFM tables, 100-character URLs, fenced JSON and deep lists, none of
 * which the mock document contains.
 *
 * So this spec stubs the run API with a long two-version document and checks the
 * geometry the brief asks about -- no horizontal overflow, a bounded reading
 * measure, and a workspace that actually uses the width next to the sidebar --
 * at 1440x900 and at 390x844. Screenshots land in `test-results/layout/`.
 */

import { expect, test, type Page } from "@playwright/test";

import { LONG_PRD_V1, LONG_PRD_V2 } from "./fixtures/longPrd";

const RUN_ID = "6b1f0b7e-77a0-4f0e-9a2b-0d6b5c2f1a34";

interface Feedback {
  severity: "must_fix" | "should_fix" | "optional";
  issue: string;
  recommendation: string;
}

function feedback(
  severity: Feedback["severity"],
  issue: string,
  count = 1,
): Feedback[] {
  return Array.from({ length: count }, (_, index) => ({
    severity,
    issue: `${issue} #${index + 1}`,
    recommendation: `建议：针对「${issue} #${index + 1}」补充可验证的定义、责任人与验收标准。`,
  }));
}

function review(role: "tech" | "ux" | "biz", score: number, blockers: number) {
  return {
    role,
    score,
    summary: `${role} 评审：主流程定义完整，异常路径仍有可量化空间。`,
    strengths: ["主流程与异常状态区分清晰", "指标有明确口径", "验收标准可测试"],
    feedback: [
      ...feedback("must_fix", `${role} 阻塞项`, blockers),
      ...feedback("should_fix", `${role} 重要改进`, 2),
      ...feedback("optional", `${role} 可选优化`, 3),
    ],
  };
}

function evaluation(tech: number, ux: number, biz: number, blockers: number) {
  const reviews = [
    review("tech", tech, blockers),
    review("ux", ux, 0),
    review("biz", biz, 0),
  ];
  return {
    tech: reviews[0]!,
    ux: reviews[1]!,
    biz: reviews[2]!,
    overall_score: Math.round(((tech + ux + biz) / 3) * 10) / 10,
    combined_feedback: reviews.flatMap((item) => item.feedback),
  };
}

const TOKENS = { input_tokens: 4210, output_tokens: 8830, total_tokens: 13040 };

const SNAPSHOT = {
  run_id: RUN_ID,
  user_idea:
    "打造一个移动端优先的播客单集订阅产品，让听众可以只为感兴趣的单集付费，" +
    "同时让独立创作者获得可预测、可对账的收入。",
  target_audience: "中文播客听众与独立内容创作者",
  user_constraints: "移动端优先、无障碍、隐私最小化收集的 MVP",
  current_iteration: 2,
  max_iterations: 4,
  quality_threshold: 85,
  status: "COMPLETED",
  active_node: null,
  versions: [
    {
      version: 1,
      content: LONG_PRD_V1,
      created_at: "2026-08-19T10:02:00Z",
      evaluation: evaluation(70, 74, 72, 1),
      revision_plan: null,
      token_usage: TOKENS,
    },
    {
      version: 2,
      content: LONG_PRD_V2,
      created_at: "2026-08-19T10:07:00Z",
      evaluation: evaluation(92, 88, 92, 0),
      revision_plan: {
        iteration: 1,
        objective: "补齐支付异常、退款状态机与创作者结算对账的可验证定义。",
        items: [
          {
            source_role: "tech",
            source_roles: ["tech", "biz"],
            issue: "支付网关失败后的重试与幂等行为没有定义",
            required_change:
              "补充幂等键、重试次数上限与退避窗口，并给出可测试的验收标准。",
            target_section: "功能需求",
            priority: "high",
          },
          {
            source_role: "ux",
            source_roles: ["ux"],
            issue: "退款状态对用户不可见",
            required_change:
              "在应用内暴露待处理、已批准、已拒绝、已到账四种状态。",
            target_section: "功能需求",
            priority: "medium",
          },
        ],
        user_override: null,
      },
      token_usage: TOKENS,
    },
  ],
  current_prd: LONG_PRD_V2,
  current_prd_attempt: 1,
  latest_evaluation: evaluation(92, 88, 92, 0),
  best_version: 2,
  best_score: 90.7,
  reviews: {},
  pending_revision_plan: null,
  pending_user_override: null,
  node_statuses: {
    generator: "SUCCEEDED",
    tech_reviewer: "SUCCEEDED",
    ux_reviewer: "SUCCEEDED",
    biz_reviewer: "SUCCEEDED",
    aggregator: "SUCCEEDED",
    optimizer: "SUCCEEDED",
  },
  total_tokens: {
    input_tokens: 8420,
    output_tokens: 17660,
    total_tokens: 26080,
  },
  node_tokens: { generator: TOKENS },
  // Two versions' worth of calls, including the retried generator attempt that
  // burned two minutes on the way to v2.
  node_timings: [
    {
      node: "generator",
      version: 1,
      attempt: 1,
      seconds: 68.4,
      succeeded: true,
      input_tokens: 493,
      output_tokens: 1717,
    },
    {
      node: "tech_reviewer",
      version: 1,
      attempt: 1,
      seconds: 12.1,
      succeeded: true,
      input_tokens: 4210,
      output_tokens: 880,
    },
    {
      node: "ux_reviewer",
      version: 1,
      attempt: 1,
      seconds: 10.7,
      succeeded: true,
      input_tokens: 4210,
      output_tokens: 810,
    },
    {
      node: "biz_reviewer",
      version: 1,
      attempt: 1,
      seconds: 11.9,
      succeeded: true,
      input_tokens: 4210,
      output_tokens: 795,
    },
    {
      node: "optimizer",
      version: 1,
      attempt: 1,
      seconds: 14.6,
      succeeded: true,
      input_tokens: 6120,
      output_tokens: 1210,
    },
    {
      node: "generator",
      version: 2,
      attempt: 1,
      seconds: 121.3,
      succeeded: false,
      input_tokens: 800,
      output_tokens: 1200,
    },
    {
      node: "generator",
      version: 2,
      attempt: 2,
      seconds: 74.8,
      succeeded: true,
      input_tokens: 812,
      output_tokens: 2048,
    },
  ],
  estimated_cost_usd: 0.0412,
  cost_available: true,
  is_mock: false,
  elapsed_seconds: 96.4,
  created_at: "2026-08-19T10:00:00Z",
  updated_at: "2026-08-19T10:07:30Z",
  started_at: "2026-08-19T10:00:01Z",
  completed_at: "2026-08-19T10:07:30Z",
  error: null,
  latest_event_sequence: 84,
};

const SUMMARY = {
  run_id: RUN_ID,
  user_idea: SNAPSHOT.user_idea,
  status: "COMPLETED",
  current_iteration: 2,
  max_iterations: 4,
  latest_score: 90.7,
  best_version: 2,
  best_score: 90.7,
  created_at: SNAPSHOT.created_at,
  updated_at: SNAPSHOT.updated_at,
};

/** Serve the long run from the client, so no backend fixture has to grow. */
async function stubLongRun(page: Page): Promise<void> {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === `/api/runs/${RUN_ID}`) {
      await route.fulfill({ json: SNAPSHOT });
      return;
    }
    if (path === "/api/runs") {
      await route.fulfill({ json: { items: [SUMMARY], total: 1 } });
      return;
    }
    // A COMPLETED run never opens a stream; anything else is not this test's
    // business and must not reach the real backend.
    await route.abort();
  });
}

async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
}

const TABS = ["prd", "review", "plan", "diff", "trace"] as const;

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900, maxReading: 960 },
  { name: "mobile", width: 390, height: 844, maxReading: 390 },
] as const;

for (const viewport of VIEWPORTS) {
  test(`A long PRD lays out on ${viewport.name} without sideways scroll`, async ({
    page,
  }) => {
    await stubLongRun(page);
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await page.goto(`/?run_id=${RUN_ID}`);
    await expect(page.getByTestId("run-status")).toHaveText("已完成");

    // The long document really is long: if the fixture ever shrinks, the rest of
    // this test stops meaning anything.
    await expect(page.getByTestId("prd-content")).toContainText("护栏指标");
    const prd = page.getByTestId("prd-content");
    const box = (await prd.boundingBox())!;
    expect(box.height).toBeGreaterThan(3_000);

    // A PRD is prose, so the measure is capped -- on a wide screen the text must
    // not run the full 1440px, and it must not exceed the viewport on a phone.
    expect(box.width).toBeLessThanOrEqual(viewport.maxReading);

    if (viewport.name === "desktop") {
      // ...and the workspace still uses the width next to the sidebar, rather
      // than leaving the document floating in a narrow column.
      const workspace = (await page.locator("#workspace").boundingBox())!;
      expect(workspace.width).toBeGreaterThan(900);
    } else {
      // On a phone the opening screen has to answer "is this done, and which
      // version am I reading" -- the conversation list and the run observability
      // belong below that, not above it.
      const workspace = (await page.locator("#workspace").boundingBox())!;
      const sidebar = (await page
        .getByRole("complementary", { name: "对话记录" })
        .boundingBox())!;
      expect(workspace.y).toBeLessThan(sidebar.y);
      expect(await page.getByTestId("run-outcome").boundingBox()).toBeTruthy();
    }

    for (const tab of TABS) {
      if (tab === "plan") {
        // The plan that produced v2 hangs off v1's findings.
        await page.getByTestId("version-tab-v1").click();
      }
      if (tab === "diff") {
        await page.getByTestId("version-tab-v2").click();
      }
      await page.getByTestId(`workspace-tab-${tab}`).click();
      await expect(page.getByTestId(`workspace-panel-${tab}`)).toBeVisible();
      expect(
        await horizontalOverflow(page),
        `${tab} overflows horizontally at ${viewport.name}`,
      ).toBeLessThanOrEqual(1);
      await page.screenshot({
        path: `test-results/layout/${viewport.name}-${tab}.png`,
        fullPage: false,
      });
    }

    // Wide tables are the usual culprit: they may scroll inside their own frame,
    // never by dragging the page.
    await page.getByTestId("workspace-tab-prd").click();
    const tableOverflow = await page.evaluate(() => {
      const tables = [
        ...document.querySelectorAll("[data-testid='prd-content'] table"),
      ];
      return tables.map((table) => {
        const frame = table.parentElement!;
        return frame.scrollWidth - frame.clientWidth > 0
          ? getComputedStyle(frame).overflowX
          : "fits";
      });
    });
    expect(tableOverflow.length).toBeGreaterThan(0);
    for (const state of tableOverflow) {
      expect(["fits", "auto", "scroll"]).toContain(state);
    }

    // The two valid diagrams draw, the deliberately broken one degrades to its
    // source, and neither can widen the page: a diagram scrolls in its own frame
    // exactly like a wide table.
    const diagrams = page.getByTestId("mermaid-diagram");
    await expect(diagrams).toHaveCount(2);
    await expect(diagrams.first()).toHaveAttribute(
      "data-diagram-type",
      "flowchart",
    );
    await expect(diagrams.nth(1)).toHaveAttribute(
      "data-diagram-type",
      "stateDiagram-v2",
    );
    await expect(page.getByTestId("mermaid-error")).toHaveText(/图表渲染失败/);
    await expect(page.getByText("查看 Mermaid 源码").first()).toBeVisible();
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);

    const svgFits = await page.evaluate(() =>
      [...document.querySelectorAll(".prd-mermaid")].map((frame) => ({
        overflowX: getComputedStyle(frame).overflowX,
        wider: frame.getBoundingClientRect().width > window.innerWidth,
      })),
    );
    expect(svgFits.length).toBe(2);
    for (const frame of svgFits) {
      expect(frame.wider).toBe(false);
      expect(["auto", "scroll"]).toContain(frame.overflowX);
    }

    // Which node owned the run's time, in 运行记录 rather than beside the document.
    await page.getByTestId("workspace-tab-trace").click();
    await expect(page.getByTestId("node-timings")).toBeVisible();
    const timings = page.getByTestId("node-timing-row");
    await expect(timings).toHaveCount(7);
    await expect(timings.first()).toContainText("Generator v1");
    await expect(timings.first()).toContainText("68.4 s");
    await expect(timings.nth(5)).toContainText("Generator v2");
    await expect(timings.nth(5)).toContainText("失败");
    await expect(timings.nth(6)).toContainText("第 2 次");
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);
    await page.screenshot({
      path: `test-results/layout/${viewport.name}-node-timings.png`,
      fullPage: false,
    });
  });
}

test("The long v1 to v2 comparison reads as a document, not as Markdown source", async ({
  page,
}) => {
  await stubLongRun(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/?run_id=${RUN_ID}`);
  await expect(page.getByTestId("run-status")).toHaveText("已完成");

  await page.getByTestId("workspace-tab-diff").click();
  const diff = page.getByTestId("version-diff");
  await expect(diff).toHaveAttribute("data-mode", "reading");

  // The added section is rendered prose, and the table pipes that a line diff
  // would have printed are gone.
  await expect(
    page
      .getByTestId("reading-block-added")
      .filter({ hasText: "幂等键" })
      .first(),
  ).toBeVisible();
  await expect(diff).not.toContainText("| --- |");
  await expect(diff.locator("table").first()).toBeVisible();

  // 16 sections are identical between the two versions; reprinting them would
  // make the comparison longer than the PRD.
  await expect(
    page.getByTestId("reading-section-unchanged").first(),
  ).toBeVisible();
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);
  await page.screenshot({
    path: "test-results/layout/desktop-diff-reading.png",
    fullPage: false,
  });

  await page.getByTestId("diff-mode-source").click();
  await expect(diff).toHaveAttribute("data-mode", "source");
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);
});
