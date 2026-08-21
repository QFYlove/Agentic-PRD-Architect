import { describe, expect, it } from "vitest";

import { diffLines, type DiffRow, type DiffSegment } from "./diff";

function rowsOf(segments: DiffSegment[]): DiffRow[] {
  return segments.flatMap((segment) =>
    segment.type === "hunk" ? segment.rows : [],
  );
}

function textsOf(segments: DiffSegment[], kind: DiffRow["kind"]): string[] {
  return rowsOf(segments)
    .filter((row) => row.kind === kind)
    .map((row) => row.text);
}

describe("diffLines", () => {
  it("reports an addition with surrounding context and no phantom removals", () => {
    const diff = diffLines(
      "# Title\n\n## Requirements\n- One\n",
      "# Title\n\n## Requirements\n- One\n- Two\n",
    );

    expect(diff.unchanged).toBe(false);
    expect(diff.addedCount).toBe(1);
    expect(diff.removedCount).toBe(0);
    expect(textsOf(diff.segments, "added")).toEqual(["- Two"]);
    expect(textsOf(diff.segments, "context")).toContain("- One");
  });

  it("reports a deletion", () => {
    const diff = diffLines("keep\ndrop\ntail\n", "keep\ntail\n");
    expect(diff.removedCount).toBe(1);
    expect(diff.addedCount).toBe(0);
    expect(textsOf(diff.segments, "removed")).toEqual(["drop"]);
  });

  it("emits the removal before the addition for a rewritten line", () => {
    const diff = diffLines("a\nold\nb\n", "a\nnew\nb\n");
    const changed = rowsOf(diff.segments).filter(
      (row) => row.kind !== "context",
    );
    expect(changed.map((row) => [row.kind, row.text])).toEqual([
      ["removed", "old"],
      ["added", "new"],
    ]);
  });

  it("tracks line numbers on the side each row belongs to", () => {
    const diff = diffLines("a\nb\n", "a\nx\nb\n");
    const added = rowsOf(diff.segments).find((row) => row.kind === "added")!;
    expect(added.sourceLine).toBeNull();
    expect(added.targetLine).toBe(2);
    const removed = diffLines("a\nb\n", "a\n").segments;
    const dropped = rowsOf(removed).find((row) => row.kind === "removed")!;
    expect(dropped.sourceLine).toBe(2);
    expect(dropped.targetLine).toBeNull();
  });

  it("collapses long unchanged runs instead of repeating the whole document", () => {
    const filler = Array.from({ length: 40 }, (_, index) => `line ${index}`);
    const diff = diffLines(
      ["head", ...filler, "tail"].join("\n"),
      ["head", ...filler, "tail", "appended"].join("\n"),
    );

    const skipped = diff.segments.filter(
      (segment) => segment.type === "skipped",
    );
    expect(skipped).toHaveLength(1);
    expect(skipped[0]).toMatchObject({ type: "skipped" });
    // Context survives around the change, but nowhere near all 42 lines.
    expect(rowsOf(diff.segments).length).toBeLessThan(12);
    expect(textsOf(diff.segments, "context")).toContain("tail");
  });

  it("labels a hunk with the nearest Markdown heading above it", () => {
    const diff = diffLines(
      "# Doc\n\n## Alpha\n- a\n\n## Beta\n- b\n",
      "# Doc\n\n## Alpha\n- a\n\n## Beta\n- b\n- c\n",
    );
    const hunks = diff.segments.filter((segment) => segment.type === "hunk");
    expect(hunks).toHaveLength(1);
    expect(hunks[0]).toMatchObject({ heading: "Beta" });
  });

  it("treats two identical documents as unchanged", () => {
    const diff = diffLines("# Same\n\nBody\n", "# Same\n\nBody\n");
    expect(diff.unchanged).toBe(true);
    expect(diff.segments).toEqual([]);
    expect(diff.addedCount).toBe(0);
    expect(diff.removedCount).toBe(0);
  });

  it("handles an empty source, an empty target, and two empty documents", () => {
    const created = diffLines("", "# New\nBody\n");
    expect(created.removedCount).toBe(0);
    expect(textsOf(created.segments, "added")).toEqual(["# New", "Body", ""]);

    const emptied = diffLines("# Old\n", "");
    expect(emptied.addedCount).toBe(0);
    expect(textsOf(emptied.segments, "removed")).toEqual(["# Old", ""]);

    expect(diffLines("", "").unchanged).toBe(true);
  });

  it("normalizes CRLF so a line ending change alone is not a diff", () => {
    expect(diffLines("a\r\nb\r\n", "a\nb\n").unchanged).toBe(true);
  });

  it("keeps HTML in the model output as inert text", () => {
    const diff = diffLines("safe\n", "safe\n<script>alert(1)</script>\n");
    expect(textsOf(diff.segments, "added")).toContain(
      "<script>alert(1)</script>",
    );
  });

  it("degrades to a wholesale replacement instead of hanging on a huge input", () => {
    const source = Array.from({ length: 600 }, (_, i) => `s${i}`).join("\n");
    const target = Array.from({ length: 600 }, (_, i) => `t${i}`).join("\n");
    const diff = diffLines(source, target);
    expect(diff.removedCount).toBe(600);
    expect(diff.addedCount).toBe(600);
  });
});
