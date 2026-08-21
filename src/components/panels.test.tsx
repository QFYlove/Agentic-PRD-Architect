import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
  it("renders all three reviewers with score, summary, strengths, and feedback", () => {
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
      const feedback = screen.getByTestId(`reviewer-feedback-${role}`);
      expect(within(feedback).getByText("Add an edge case")).toBeTruthy();
      expect(within(feedback).getByText("重要改进")).toBeTruthy();
    }
  });

  /**
   * The three cards deliberately share one surface now -- per-role accent borders
   * were part of what read as a template. Identity has to survive that, so it is
   * carried by the icon, the heading, and a machine-readable role attribute.
   */
  it("keeps every reviewer identifiable without a per-role accent", () => {
    render(
      <ReviewPanel
        version={1}
        reviews={{
          tech: makeReview("tech"),
          ux: makeReview("ux"),
          biz: makeReview("biz"),
        }}
      />,
    );
    const roles = (["tech", "ux", "biz"] as const).map(
      (role) => screen.getByTestId(`reviewer-card-${role}`).dataset.role,
    );
    expect(roles).toEqual(["tech", "ux", "biz"]);
    for (const label of ["技术评审", "体验评审", "商业评审"]) {
      expect(screen.getByRole("heading", { name: label })).toBeTruthy();
    }
  });

  /**
   * A blocking finding and a piece of advice must never render the same, and the
   * tier has to be legible as text -- colour alone would strand a reader who
   * cannot separate the hues on exactly the decision that matters most.
   */
  it("groups findings by severity, blockers first, and labels each tier in text", () => {
    render(
      <ReviewPanel
        version={2}
        reviews={{
          tech: makeReview("tech", 91, [
            makeFeedback("optional", "Nice-to-have polish"),
            makeFeedback("must_fix", "Checkout cannot be built"),
            makeFeedback("should_fix", "Quantify the metric"),
          ]),
        }}
      />,
    );

    const items = within(
      screen.getByTestId("reviewer-feedback-tech"),
    ).getAllByTestId("feedback-item");
    expect(items.map((item) => item.dataset.severity)).toEqual([
      "must_fix",
      "should_fix",
      "optional",
    ]);
    expect(items[0]!.textContent).toContain("必须修复");
    expect(items[0]!.textContent).toContain("Checkout cannot be built");
    expect(items[1]!.textContent).toContain("重要改进");
    expect(items[2]!.textContent).toContain("可选优化");
  });

  it("shows no blocking label when a reviewer only left advice", () => {
    render(
      <ReviewPanel
        version={2}
        reviews={{
          tech: makeReview("tech", 91, [
            makeFeedback("should_fix", "Quantify the metric"),
            makeFeedback("optional", "Nice-to-have polish"),
          ]),
        }}
      />,
    );
    expect(screen.queryByText("必须修复")).toBeNull();
    expect(screen.getByText("剩余问题")).toBeTruthy();
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
    expect(screen.queryByTestId("reviewer-feedback-tech")).toBeNull();
    expect(screen.queryByText("做得好")).toBeNull();
    expect(screen.queryByText("剩余问题")).toBeNull();
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
