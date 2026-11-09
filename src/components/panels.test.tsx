import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  initialRunViewState,
  runReducer,
  type RunViewState,
} from "../lib/runReducer";
import {
  makeEvaluation,
  makeFeedback,
  makeReview,
  makeRevisionItem,
  makeRevisionPlan,
  makeSnapshot,
  makeVersion,
} from "../test/fixtures";
import { ReviewPanel } from "./ReviewPanel";
import { RevisionPlanPanel } from "./RevisionPlanPanel";

function listTexts(container: HTMLElement): string[] {
  return within(container)
    .getAllByRole("listitem")
    .map((item) => item.textContent?.trim() ?? "");
}

describe("ReviewPanel", () => {
  it("renders all three reviewers with score, summary, strengths, and findings", () => {
    render(
      <ReviewPanel
        version={1}
        reviews={{
          tech: makeReview("tech", 65),
          ux: makeReview("ux", 70),
          biz: makeReview("biz", 78),
        }}
      />,
    );

    const panel = screen.getByTestId("review-panel");
    expect(panel.dataset.version).toBe("1");
    expect(within(panel).getByText(/三位评审独立审阅 v1/)).toBeTruthy();

    for (const [role, label, score] of [
      ["tech", "技术评审", "65"],
      ["ux", "体验评审", "70"],
      ["biz", "商业评审", "78"],
    ] as const) {
      const card = screen.getByTestId(`reviewer-card-${role}`);
      expect(within(card).getByRole("heading", { name: label })).toBeTruthy();
      expect(
        screen.getByTestId(`reviewer-score-${role}`).textContent,
      ).toContain(score);
      expect(within(card).getByText(`${role} review summary`)).toBeTruthy();
      expect(
        listTexts(screen.getByTestId(`reviewer-strengths-${role}`)),
      ).toEqual(["Clear goal"]);
      // Legacy reviews say so instead of inventing dimension scores.
      expect(screen.getByTestId(`reviewer-legacy-${role}`)).toBeTruthy();
    }
    // One list for all reviewers, not three narrow columns of prose.
    const items = within(screen.getByTestId("findings-list")).getAllByTestId(
      "feedback-item",
    );
    expect(items).toHaveLength(3);
    expect(items.map((item) => item.dataset.roles)).toEqual([
      "tech",
      "ux",
      "biz",
    ]);
  });

  it("shows dimension scores, weights and reasons for rubric-scored reviews", () => {
    render(
      <ReviewPanel
        version={1}
        overall={76}
        qualityThreshold={85}
        reviews={{
          tech: {
            ...makeReview("tech", 78),
            dimension_scores: [
              {
                dimension: "feasibility",
                score: 4,
                rationale: "Buildable.",
                weight: 0.3,
              },
              {
                dimension: "architecture_data",
                score: 4,
                rationale: "Clear.",
                weight: 0.25,
              },
              {
                dimension: "reliability",
                score: 4,
                rationale: "Retries.",
                weight: 0.25,
              },
              {
                dimension: "security_constraints",
                score: 3,
                rationale: "Gaps.",
                weight: 0.2,
              },
            ],
          },
          ux: makeReview("ux", 76),
          biz: makeReview("biz", 74),
        }}
        findings={{
          combined: [],
          beforeDedup: 0,
          gateStatus: "NEEDS_REVISION",
          rubricVersion: "2026-11-v2",
          resolutions: [],
        }}
      />,
    );

    const dims = screen.getByTestId("reviewer-dimensions-tech");
    expect(dims.textContent).toContain("技术可行性");
    expect(dims.textContent).toContain("30%");
    expect(dims.textContent).toContain("4/5");
    expect(dims.textContent).toContain("Buildable.");
    expect(screen.getByTestId("review-overall").textContent).toContain(
      "(78 + 76 + 74) / 3",
    );
    expect(screen.getByTestId("review-gate").textContent).toBe("需要修订");
    const rules = screen.getByTestId("rubric-rules");
    expect(rules.textContent).toContain("Σ(维度分 / 5 × 权重) × 100");
    expect(rules.textContent).toContain("用户需求与场景匹配 · 25%");
    // An empty review is a valid answer, stated plainly.
    expect(screen.getByTestId("findings-empty")).toBeTruthy();
  });

  /**
   * A blocking finding and a piece of advice must never render the same, and the
   * tier has to be legible as text -- colour alone would strand a reader who
   * cannot separate the hues on exactly the decision that matters most.
   */
  it("lists findings blockers first, labels each tier in text, and filters", async () => {
    render(
      <ReviewPanel
        version={2}
        reviews={{
          tech: makeReview("tech", 91, [
            makeFeedback("optional", "Nice-to-have polish"),
            makeFeedback("must_fix", "Checkout cannot be built"),
          ]),
          ux: makeReview("ux", 90, [
            makeFeedback("should_fix", "Quantify the metric"),
          ]),
        }}
      />,
    );

    const items = screen.getAllByTestId("feedback-item");
    expect(items.map((item) => item.dataset.severity)).toEqual([
      "must_fix",
      "should_fix",
      "optional",
    ]);
    expect(items[0]!.textContent).toContain("必须修复");
    expect(items[0]!.textContent).toContain("Checkout cannot be built");
    expect(items[1]!.textContent).toContain("重要改进");
    expect(items[2]!.textContent).toContain("可选优化");

    await userEvent.click(screen.getByTestId("filter-role-ux"));
    expect(
      screen.getAllByTestId("feedback-item").map((item) => item.dataset.roles),
    ).toEqual(["ux"]);
    await userEvent.click(screen.getByTestId("filter-role-all"));
    await userEvent.click(screen.getByTestId("filter-severity-must_fix"));
    expect(screen.getAllByTestId("feedback-item")).toHaveLength(1);
  });

  it("shows a merged finding once, with every reviewer's evidence, and can locate it", async () => {
    const onLocate = vi.fn();
    render(
      <ReviewPanel
        version={1}
        reviews={{ tech: makeReview("tech"), ux: makeReview("ux") }}
        onLocate={onLocate}
        findings={{
          combined: [
            {
              severity: "must_fix",
              issue: "Gateway failures have no handling.",
              recommendation: "建议：Specify retries.",
              title: "Payment failure handling",
              section: "5.1 Purchase Flow",
              evidence: "5.1 never says what happens on failure.",
              user_impact: "Listeners may be charged twice.",
              finding_id: "v1-tech-1",
              source_role: "tech",
              source_roles: ["tech", "ux"],
              merged_from: ["v1-ux-1"],
              observations: [
                {
                  finding_id: "v1-ux-1",
                  role: "ux",
                  severity: "must_fix",
                  problem: "No failure screen.",
                },
              ],
            },
          ],
          beforeDedup: 2,
          gateStatus: "NEEDS_REVISION",
          rubricVersion: null,
          resolutions: [],
        }}
      />,
    );

    const [item] = screen.getAllByTestId("feedback-item");
    expect(item!.dataset.roles).toBe("tech,ux");
    expect(item!.textContent).toContain("2 位评审都提到");
    expect(item!.textContent).toContain("5.1 never says");
    expect(item!.textContent).toContain("No failure screen.");
    // The 「建议：」 prefix is not doubled.
    expect(item!.textContent).not.toContain("建议：建议");
    expect(screen.getByText(/2 条评审意见合并为 1 条/)).toBeTruthy();
    await userEvent.click(screen.getByText("Payment failure handling"));
    await userEvent.click(screen.getByTestId("feedback-locate"));
    expect(onLocate).toHaveBeenCalledWith("5.1 Purchase Flow");
  });

  it("degrades gracefully when a reviewer has empty summary and lists", () => {
    render(
      <ReviewPanel
        version={2}
        reviews={{
          tech: {
            role: "tech",
            score: 0,
            summary: "   ",
            strengths: [],
            feedback: [
              { severity: "should_fix", issue: "  ", recommendation: "" },
            ],
          },
        }}
      />,
    );

    // The score is real data even at zero, so it still renders.
    expect(screen.getByTestId("reviewer-score-tech").textContent).toContain(
      "0",
    );
    expect(screen.queryByTestId("reviewer-strengths-tech")).toBeNull();
    expect(screen.queryByTestId("feedback-item")).toBeNull();
    expect(screen.queryByText("做得好")).toBeNull();
    expect(screen.getByTestId("findings-empty")).toBeTruthy();
  });

  it("marks reviewers that have not reported yet instead of inventing content", () => {
    render(<ReviewPanel version={1} reviews={{ tech: makeReview("tech") }} />);

    expect(screen.getByTestId("reviewer-score-tech")).toBeTruthy();
    expect(screen.getByTestId("reviewer-pending-ux").textContent).toContain(
      "评审进行中",
    );
    expect(screen.getByTestId("reviewer-pending-biz")).toBeTruthy();
    expect(screen.queryByTestId("reviewer-score-ux")).toBeNull();
    expect(screen.queryByText(/ux review summary/)).toBeNull();
  });

  it("renders nothing for a version with no reviews and no selection", () => {
    const { container, rerender } = render(
      <ReviewPanel version={1} reviews={undefined} />,
    );
    expect(container.innerHTML).toBe("");

    rerender(<ReviewPanel version={1} reviews={{}} />);
    expect(container.innerHTML).toBe("");

    rerender(
      <ReviewPanel version={null} reviews={{ tech: makeReview("tech") }} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("shows the selected version's own reviewers when switching versions", () => {
    const v1 = {
      tech: { ...makeReview("tech", 65), summary: "v1 tech summary" },
      ux: { ...makeReview("ux", 70), summary: "v1 ux summary" },
      biz: { ...makeReview("biz", 78), summary: "v1 biz summary" },
    };
    const v2 = {
      tech: { ...makeReview("tech", 88), summary: "v2 tech summary" },
      ux: { ...makeReview("ux", 89), summary: "v2 ux summary" },
      biz: { ...makeReview("biz", 87), summary: "v2 biz summary" },
    };
    const { rerender } = render(<ReviewPanel version={1} reviews={v1} />);
    expect(screen.getByText("v1 tech summary")).toBeTruthy();
    expect(screen.getByTestId("reviewer-score-tech").textContent).toContain(
      "65",
    );

    rerender(<ReviewPanel version={2} reviews={v2} />);
    expect(screen.getByText("v2 tech summary")).toBeTruthy();
    expect(screen.queryByText("v1 tech summary")).toBeNull();
    expect(screen.getByTestId("reviewer-score-tech").textContent).toContain(
      "88",
    );
    expect(screen.getByTestId("review-panel").dataset.version).toBe("2");
  });
});

describe("RevisionPlanPanel", () => {
  it("renders the objective, items, and the version chain the plan belongs to", () => {
    render(
      <RevisionPlanPanel
        entry={{
          sourceVersion: 1,
          targetVersion: 2,
          plan: makeRevisionPlan(1, {
            objective: "Resolve all high-priority review findings.",
            items: [
              makeRevisionItem({
                source_role: "tech",
                source_roles: ["tech", "biz"],
                issue: "Payment failures are undefined",
                required_change: "Document idempotent retries",
                target_section: "Requirements",
                priority: "high",
              }),
              makeRevisionItem({
                source_role: "ux",
                source_roles: ["ux"],
                issue: "Refund status is unclear",
                required_change: "Add an accessible refund journey",
                target_section: "User Journeys",
                priority: "medium",
              }),
            ],
          }),
        }}
      />,
    );

    const panel = screen.getByTestId("revision-plan-panel");
    expect(panel.dataset.sourceVersion).toBe("1");
    expect(panel.dataset.targetVersion).toBe("2");
    const lineage = screen.getByTestId("revision-plan-lineage").textContent;
    expect(lineage).toContain("v1 评审反馈");
    expect(lineage).toContain("用于生成 v2");
    expect(screen.getByTestId("revision-plan-objective").textContent).toContain(
      "Resolve all high-priority review findings.",
    );

    const items = screen.getAllByTestId("revision-item");
    expect(items).toHaveLength(2);
    expect(
      within(items[0]!).getByTestId("revision-item-priority").textContent,
    ).toBe("高优先级");
    expect(
      within(items[0]!).getByTestId("revision-item-section").textContent,
    ).toBe("Requirements");
    expect(
      within(items[0]!).getByTestId("revision-item-sources").textContent,
    ).toContain("技术评审 · 商业评审");
    expect(within(items[0]!).getByText("Payment failures are undefined"));
    expect(within(items[0]!).getByText(/Document idempotent retries/));
    expect(
      within(items[1]!).getByTestId("revision-item-priority").textContent,
    ).toBe("中优先级");
    expect(
      within(items[1]!).getByTestId("revision-item-sources").textContent,
    ).toContain("体验评审");
  });

  it("labels a user-supplied requirement as the user's own", () => {
    render(
      <RevisionPlanPanel
        entry={{
          sourceVersion: 1,
          targetVersion: 2,
          plan: makeRevisionPlan(1, {
            user_override: "Add refund reconciliation.",
            items: [
              makeRevisionItem({
                source_role: "user",
                source_roles: ["user"],
                issue: "User-requested refinement",
                required_change: "Add refund reconciliation.",
                target_section: "User Requirements",
                priority: "low",
              }),
            ],
          }),
        }}
      />,
    );

    expect(
      screen.getByTestId("revision-plan-user-override").textContent,
    ).toContain("Add refund reconciliation.");
    expect(screen.getByTestId("revision-item-sources").textContent).toContain(
      "用户补充",
    );
    expect(screen.getByTestId("revision-item-priority").textContent).toBe(
      "低优先级",
    );
  });

  it("omits an empty objective and an item's duplicated change text", () => {
    render(
      <RevisionPlanPanel
        entry={{
          sourceVersion: 2,
          targetVersion: 3,
          plan: {
            iteration: 2,
            objective: "   ",
            items: [
              makeRevisionItem({
                issue: "Same text",
                required_change: "Same text",
              }),
            ],
            user_override: "  ",
          },
        }}
      />,
    );

    expect(screen.queryByTestId("revision-plan-objective")).toBeNull();
    expect(screen.queryByTestId("revision-plan-user-override")).toBeNull();
    expect(screen.queryByText(/修改要求/)).toBeNull();
    expect(screen.getByText("Same text")).toBeTruthy();
  });

  it("renders nothing when the selected version produced no plan", () => {
    const { container } = render(<RevisionPlanPanel entry={undefined} />);
    expect(container.innerHTML).toBe("");
  });
});

function loadSnapshot(
  snapshot: Parameters<typeof makeSnapshot>[0],
): RunViewState {
  return runReducer(initialRunViewState, {
    type: "SNAPSHOT_LOADED",
    snapshot: makeSnapshot(snapshot),
  });
}

describe("panels wired to reducer state", () => {
  const restored = () =>
    loadSnapshot({
      status: "MAX_ITERATIONS_REACHED",
      current_iteration: 3,
      versions: [
        makeVersion(1, { evaluation: makeEvaluation(65, 70, 78) }),
        makeVersion(2, {
          evaluation: makeEvaluation(88, 89, 87),
          revision_plan: makeRevisionPlan(1, { objective: "Fix v1 findings." }),
        }),
        makeVersion(3, {
          evaluation: makeEvaluation(90, 91, 89),
          revision_plan: makeRevisionPlan(2, { objective: "Fix v2 findings." }),
        }),
      ],
    });

  it("keeps reviews and plans on their own versions after a snapshot restore", () => {
    const state = restored();

    function Panels({ version }: { version: number }) {
      return (
        <>
          <ReviewPanel
            version={version}
            reviews={state.reviewsByVersion[version]}
          />
          <RevisionPlanPanel
            entry={state.revisionPlansBySourceVersion[version]}
          />
        </>
      );
    }

    const { rerender } = render(<Panels version={1} />);
    expect(screen.getByTestId("reviewer-score-tech").textContent).toContain(
      "65",
    );
    let plan = screen.getByTestId("revision-plan-panel");
    expect(plan.dataset.sourceVersion).toBe("1");
    expect(plan.dataset.targetVersion).toBe("2");
    expect(screen.getByTestId("revision-plan-objective").textContent).toContain(
      "Fix v1 findings.",
    );

    rerender(<Panels version={2} />);
    expect(screen.getByTestId("reviewer-score-tech").textContent).toContain(
      "88",
    );
    plan = screen.getByTestId("revision-plan-panel");
    // The v1 -> v2 plan must not resurface here as if it were v2 -> v3.
    expect(plan.dataset.sourceVersion).toBe("2");
    expect(plan.dataset.targetVersion).toBe("3");
    expect(screen.getByTestId("revision-plan-objective").textContent).toContain(
      "Fix v2 findings.",
    );

    rerender(<Panels version={3} />);
    expect(screen.getByTestId("reviewer-score-tech").textContent).toContain(
      "90",
    );
    // v3 is the last version, so nothing was planned from its reviews.
    expect(screen.queryByTestId("revision-plan-panel")).toBeNull();
  });

  it("shows no reviewer panel for a version that has not been reviewed", () => {
    const state = loadSnapshot({
      status: "REVIEWING",
      current_iteration: 2,
      versions: [
        makeVersion(1, { evaluation: makeEvaluation(65, 70, 78) }),
        makeVersion(2),
      ],
    });
    const { container } = render(
      <ReviewPanel version={2} reviews={state.reviewsByVersion[2]} />,
    );
    expect(container.innerHTML).toBe("");
  });
});
