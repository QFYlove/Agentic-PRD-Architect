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
        feedback: ["one"],
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
});
