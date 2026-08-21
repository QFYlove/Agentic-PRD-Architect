import { describe, expect, it, vi } from "vitest";

import { createMarkdownDownload, triggerMarkdownDownload } from "./download";
import { toTraceItem } from "./trace";
import { makeEvent, RUN_ID } from "../test/fixtures";

function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result)));
    reader.addEventListener("error", () => reject(reader.error));
    reader.readAsText(blob, "utf-8");
  });
}

describe("Markdown download", () => {
  it("uses selected raw Markdown, UTF-8 type, and deterministic naming", async () => {
    const download = createMarkdownDownload(RUN_ID, 2, "# Raw\n\n**Markdown**");
    expect(download.filename).toBe(`agentic-prd-${RUN_ID}-v2.md`);
    expect(download.blob.type).toBe("text/markdown;charset=utf-8");
    expect(await readBlob(download.blob)).toBe("# Raw\n\n**Markdown**");
  });

  it("revokes the generated object URL", () => {
    const create = vi.fn().mockReturnValue("blob:test");
    const revoke = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: create,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revoke,
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    triggerMarkdownDownload(createMarkdownDownload(RUN_ID, 1, "# One"));
    expect(click).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith("blob:test");
  });
});

describe("safe trace projection", () => {
  it("keeps sequence order and excludes unrecognized sensitive payloads", () => {
    const item = toTraceItem(
      makeEvent(3, "review_completed", {
        role: "tech",
        summary: "Safe summary",
        feedback: [
          { severity: "should_fix", issue: "one", recommendation: "one" },
        ],
        chain_of_thought: "must never appear",
        raw_provider_response: "<secret>",
      }),
    );
    expect(item).toMatchObject({
      sequence: 3,
      label: "技术评审",
    });
    expect(JSON.stringify(item)).not.toContain("must never appear");
    expect(JSON.stringify(item)).not.toContain("<secret>");
  });

  /**
   * The trace projects counts, never the finding text -- and it separates the
   * blocking tally from the total, because "3 条反馈" with no tier is what made a
   * run that had legitimately finished read as unfinished.
   */
  it("names the blocking count without leaking the finding text", () => {
    const item = toTraceItem(
      makeEvent(4, "review_completed", {
        role: "ux",
        summary: "Safe summary",
        feedback: [
          {
            severity: "must_fix",
            issue: "Checkout cannot be built",
            recommendation: "Define the flow",
          },
          {
            severity: "should_fix",
            issue: "Quantify",
            recommendation: "Add a number",
          },
        ],
      }),
    );
    expect(item?.detail).toContain("2 条反馈");
    expect(item?.detail).toContain("1 项必须修复");
    expect(JSON.stringify(item)).not.toContain("Checkout cannot be built");
  });

  it("says nothing about blockers when a review left only advice", () => {
    const item = toTraceItem(
      makeEvent(5, "review_completed", {
        role: "biz",
        summary: "Safe summary",
        feedback: [
          { severity: "optional", issue: "Polish", recommendation: "Polish" },
        ],
      }),
    );
    expect(item?.detail).toContain("1 条反馈");
    expect(item?.detail).not.toContain("必须修复");
  });

  it("reports a passed gate and a held one differently at the end of a run", () => {
    expect(toTraceItem(makeEvent(9, "run_completed", {}))?.label).toBe(
      "质量门禁已通过",
    );
    expect(
      toTraceItem(makeEvent(9, "max_iterations_reached", { must_fix_count: 1 }))
        ?.detail,
    ).toContain("仍有 1 项必须修复问题未解决");
    expect(
      toTraceItem(makeEvent(9, "max_iterations_reached", { must_fix_count: 0 }))
        ?.detail,
    ).not.toContain("必须修复");
  });
});
