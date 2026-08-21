import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { VersionDiff } from "./VersionDiff";

const V1 = [
  "# PRD v1",
  "",
  "## Requirements",
  "- Buy a single episode.",
  "",
  "## Metrics",
  "- Conversion rate.",
].join("\n");

const V2 = [
  "# PRD v1",
  "",
  "## Requirements",
  "- Buy a single episode.",
  "- Refund a purchase within 14 days.",
  "",
  "## Metrics",
  "- Refund completion time.",
].join("\n");

function diff(source = V1, target = V2) {
  return render(
    <VersionDiff
      sourceVersion={1}
      targetVersion={2}
      sourceContent={source}
      targetContent={target}
    />,
  );
}

/** The line view is now the secondary mode, reached through the toggle. */
async function showSource() {
  await userEvent.click(screen.getByTestId("diff-mode-source"));
}

describe("VersionDiff reading comparison", () => {
  it("opens on the rendered comparison rather than Markdown source", () => {
    diff();
    expect(screen.getByTestId("version-diff").dataset.mode).toBe("reading");
    expect(
      screen.getByTestId("diff-mode-reading").getAttribute("aria-selected"),
    ).toBe("true");
    expect(screen.queryByTestId("diff-row-added")).toBeNull();
    expect(screen.getAllByTestId("reading-section").length).toBeGreaterThan(0);
  });

  it("renders headings, lists and tables instead of printing their syntax", () => {
    const { container } = diff(
      "## Metrics\n\n- Conversion rate.\n",
      [
        "## Metrics",
        "",
        "- Conversion rate.",
        "",
        "| 指标 | 目标 |",
        "| --- | --- |",
        "| 退款时长 | < 2 天 |",
      ].join("\n"),
    );
    // The section heading is a heading, and the added block is a real table.
    expect(screen.getByTestId("reading-section-heading").textContent).toBe(
      "Metrics",
    );
    expect(container.querySelector("table")).toBeTruthy();
    const added = screen.getAllByTestId("reading-block-added");
    expect(added.length).toBeGreaterThan(0);
    expect(added.map((row) => row.textContent ?? "").join("")).not.toContain(
      "| --- |",
    );
    expect(container.querySelector("li")).toBeTruthy();
  });

  it("labels every change in words, not by colour alone", () => {
    diff();
    const added = screen.getAllByTestId("reading-block-added")[0]!;
    expect(within(added).getByText("新增")).toBeTruthy();
    const removed = screen.getAllByTestId("reading-block-removed")[0]!;
    expect(within(removed).getByText("删除")).toBeTruthy();
    // Removals also carry a strikethrough, so the tier survives greyscale.
    expect(removed.querySelector(".prd-markdown-removed")).toBeTruthy();
  });

  it("counts changed blocks and names sections that did not change", () => {
    diff();
    expect(screen.getByTestId("diff-added-count").textContent).toContain("段");
    expect(screen.getByTestId("diff-removed-count").textContent).toContain(
      "段",
    );
    const sections = screen.getAllByTestId("reading-section");
    expect(sections.some((section) => section.dataset.changed === "true")).toBe(
      true,
    );
    expect(
      screen.getAllByTestId("reading-section-counts").length,
    ).toBeGreaterThan(0);
  });

  it("collapses unchanged context inside a section it does report", () => {
    const filler = Array.from({ length: 12 }, (_, i) => `- item ${i}`);
    diff(
      ["# Doc", "", "## Scope", ...filler].join("\n"),
      ["# Doc", "", "## Scope", ...filler, "- appended"].join("\n"),
    );
    expect(screen.getByTestId("reading-skipped").textContent).toMatch(
      /已折叠 \d+ 段/,
    );
    expect(screen.getAllByTestId("reading-block-added").length).toBe(1);
  });

  it("names untouched sections on one line instead of listing them one by one", () => {
    const untouched = ["## A", "- a", "## B", "- b", "## C", "- c"];
    diff(
      ["# Doc", ...untouched].join("\n"),
      ["# Doc", ...untouched, "", "## New", "- appended"].join("\n"),
    );
    // Three untouched sections, one row -- a real PRD leaves twenty alone and a
    // stub each would bury the one section that actually changed.
    const run = screen.getByTestId("reading-section-unchanged");
    expect(run.dataset.count).toBe("3");
    expect(run.textContent).toContain("3 个章节未变化");
    expect(run.textContent).toContain("A · B · C");
    expect(screen.getAllByTestId("reading-section").length).toBe(1);
    expect(screen.getByTestId("reading-section-heading").textContent).toBe(
      "New",
    );
  });

  it("renders comparison text inertly instead of executing embedded HTML", () => {
    const { container } = diff("safe\n", "safe\n\n<script>alert(1)</script>\n");
    expect(container.querySelector("script")).toBeNull();
  });

  it("says so plainly when the two versions are identical", () => {
    diff(V2, V2);
    expect(screen.getByTestId("diff-unchanged")).toBeTruthy();
    expect(screen.queryByTestId("reading-section")).toBeNull();
    expect(screen.queryByTestId("diff-hunk")).toBeNull();
  });

  it("handles a version created from nothing and one emptied out", () => {
    const { rerender } = diff("", "# Fresh\n");
    expect(screen.getAllByTestId("reading-block-added").length).toBeGreaterThan(
      0,
    );
    expect(screen.queryByTestId("reading-block-removed")).toBeNull();

    rerender(
      <VersionDiff
        sourceVersion={1}
        targetVersion={2}
        sourceContent={"# Gone\n"}
        targetContent=""
      />,
    );
    expect(
      screen.getAllByTestId("reading-block-removed").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByTestId("reading-block-added")).toBeNull();
  });
});

describe("VersionDiff source mode", () => {
  it("labels the source and target and counts both sides of the change", async () => {
    diff();
    const panel = screen.getByTestId("version-diff");
    expect(panel.dataset.sourceVersion).toBe("1");
    expect(panel.dataset.targetVersion).toBe("2");
    expect(screen.getByTestId("version-diff-lineage").textContent).toContain(
      "v1 → v2",
    );

    await showSource();
    expect(panel.dataset.mode).toBe("source");
    expect(screen.getByTestId("diff-added-count").textContent).toContain("2");
    expect(screen.getByTestId("diff-removed-count").textContent).toContain("1");
  });

  it("shows additions, deletions, and the unchanged context around them", async () => {
    diff();
    await showSource();

    const added = screen
      .getAllByTestId("diff-row-added")
      .map((row) => row.textContent ?? "");
    expect(added.some((text) => text.includes("Refund a purchase"))).toBe(true);
    const removed = screen
      .getAllByTestId("diff-row-removed")
      .map((row) => row.textContent ?? "");
    expect(removed.some((text) => text.includes("Conversion rate"))).toBe(true);
    const context = screen
      .getAllByTestId("diff-row-context")
      .map((row) => row.textContent ?? "");
    expect(context.some((text) => text.includes("Buy a single episode"))).toBe(
      true,
    );
    expect(screen.getAllByTestId("diff-hunk-heading").length).toBeGreaterThan(
      0,
    );
  });

  it("signals each change with a marker and a text label, not colour alone", async () => {
    diff();
    await showSource();
    const addedRow = screen.getAllByTestId("diff-row-added")[0]!;
    expect(addedRow.textContent).toContain("+");
    expect(within(addedRow).getByText("新增：")).toBeTruthy();
    const removedRow = screen.getAllByTestId("diff-row-removed")[0]!;
    expect(removedRow.textContent).toContain("−");
    expect(within(removedRow).getByText("删除：")).toBeTruthy();
  });

  it("collapses long unchanged stretches rather than reprinting the PRD", async () => {
    const filler = Array.from({ length: 40 }, (_, i) => `- item ${i}`);
    diff(
      ["# Doc", ...filler].join("\n"),
      ["# Doc", ...filler, "- appended"].join("\n"),
    );
    await showSource();
    expect(screen.getByTestId("diff-skipped").textContent).toMatch(
      /已折叠 \d+ 行/,
    );
    expect(screen.getAllByTestId(/^diff-row-/).length).toBeLessThan(12);
  });

  it("renders diff text inertly instead of executing embedded HTML", async () => {
    const { container } = diff("safe\n", "safe\n<script>alert(1)</script>\n");
    await showSource();
    expect(container.querySelector("script")).toBeNull();
    expect(
      screen
        .getAllByTestId("diff-row-added")
        .some((row) => row.textContent?.includes("<script>alert(1)</script>")),
    ).toBe(true);
  });

  it("returns to the reading comparison", async () => {
    diff();
    await showSource();
    await userEvent.click(screen.getByTestId("diff-mode-reading"));
    expect(screen.getByTestId("version-diff").dataset.mode).toBe("reading");
    expect(screen.queryByTestId("diff-row-added")).toBeNull();
  });
});
