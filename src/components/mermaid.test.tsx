import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RUN_ID } from "../test/fixtures";
import { MermaidBlock, mermaidDiagramType } from "./MermaidBlock";
import { PRDViewer } from "./PRDViewer";

/**
 * The real runtime is a ~500 KB async chunk that needs layout APIs jsdom does not
 * have. Mocking it keeps the test about this component's contract: what it asks
 * Mermaid to do, and what it renders when Mermaid refuses.
 */
const initialize = vi.fn();
const parse = vi.fn();
const renderDiagram = vi.fn();

vi.mock("mermaid", () => ({
  default: {
    initialize: (...args: unknown[]) => initialize(...args),
    parse: (source: string) => parse(source),
    render: (id: string, source: string) => renderDiagram(id, source),
  },
}));

beforeEach(() => {
  initialize.mockReset();
  parse.mockReset().mockResolvedValue(true);
  renderDiagram
    .mockReset()
    .mockResolvedValue({ svg: "<svg><title>购买流程</title></svg>" });
});

const FLOWCHART = "flowchart TD\n  A[内容页] --> B[价格确认]";

describe("allowed diagram types", () => {
  it.each([
    ["flowchart TD\n  A --> B", "flowchart"],
    // Mermaid's own older alias for the same renderer; models emit it constantly.
    ["graph LR\n  A --> B", "graph"],
    ["sequenceDiagram\n  A ->> B: hi", "sequenceDiagram"],
    ["stateDiagram-v2\n  [*] --> 待处理", "stateDiagram-v2"],
    ["mindmap\n  root((PRD))", "mindmap"],
    ["erDiagram\n  USER ||--o{ ORDER : places", "erDiagram"],
    ["%% a comment first\nflowchart TD\n  A --> B", "flowchart"],
  ])("recognizes %s", (source, expected) => {
    expect(mermaidDiagramType(source)).toBe(expected);
  });

  /** A whitelist, because a decorative gantt rendering badly is worse than not
   * rendering: the source is at least readable. */
  it.each(["gantt\n  title x", 'pie\n  "a" : 10', "gitGraph\n  commit", ""])(
    "refuses %s",
    (source) => {
      expect(mermaidDiagramType(source)).toBeNull();
    },
  );
});

describe("MermaidBlock", () => {
  it("draws a valid diagram in strict mode with model HTML disabled", async () => {
    const { container } = render(<MermaidBlock source={FLOWCHART} />);

    await waitFor(() =>
      expect(screen.getByTestId("mermaid-diagram")).toBeTruthy(),
    );
    expect(container.querySelector("svg")).toBeTruthy();
    expect(screen.getByTestId("mermaid-diagram").dataset.diagramType).toBe(
      "flowchart",
    );
    // Nothing the model writes may be parsed as markup, in labels or anywhere.
    expect(initialize).toHaveBeenCalledWith(
      expect.objectContaining({ securityLevel: "strict", htmlLabels: false }),
    );
    // Parsed before rendering: `render` injects its own red error graphic for
    // invalid input, which is a worse fallback than the readable source.
    expect(parse).toHaveBeenCalledWith(FLOWCHART);
  });

  it("shows the source instead of crashing when the syntax is invalid", async () => {
    parse.mockRejectedValue(new Error("Parse error on line 2"));
    render(<MermaidBlock source={"flowchart TD\n  A[[[--> ???"} />);

    await waitFor(() =>
      expect(screen.getByTestId("mermaid-error").textContent).toContain(
        "图表渲染失败",
      ),
    );
    expect(screen.getByText("查看 Mermaid 源码")).toBeTruthy();
    expect(screen.getByText(/A\[\[\[/)).toBeTruthy();
    expect(screen.queryByTestId("mermaid-diagram")).toBeNull();
  });

  it("shows the source for a type outside the whitelist without loading Mermaid", () => {
    render(<MermaidBlock source={"gantt\n  title Roadmap"} />);

    expect(screen.getByTestId("mermaid-error").textContent).toContain(
      "不支持的图表类型",
    );
    expect(initialize).not.toHaveBeenCalled();
    expect(parse).not.toHaveBeenCalled();
  });
});

describe("PRDViewer diagrams and tables", () => {
  const TABLE =
    "## 功能需求\n\n| 功能 | 描述 | 优先级 | 验收标准 |\n| --- | --- | --- | --- |\n| JD 分析 | 提取核心要求 | P0 | 15 秒内返回 |";

  it("renders a GFM table and a fenced diagram from one document", async () => {
    const { container } = render(
      <PRDViewer
        runId={RUN_ID}
        draft={{
          version: 1,
          attempt: 1,
          content: `# PRD\n\n${TABLE}\n\n\`\`\`mermaid\n${FLOWCHART}\n\`\`\`\n`,
          complete: true,
        }}
        score={undefined}
      />,
    );

    const table = container.querySelector("table");
    expect(table).toBeTruthy();
    expect(table?.querySelectorAll("th")).toHaveLength(4);
    expect(screen.getByText("15 秒内返回")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByTestId("mermaid-diagram")).toBeTruthy(),
    );
  });

  /** The whole point of the lazy import: the runtime is a cost a text-only PRD
   * must not pay. */
  it("never touches the Mermaid runtime for a PRD without diagrams", async () => {
    const { container } = render(
      <PRDViewer
        runId={RUN_ID}
        draft={{
          version: 1,
          attempt: 1,
          content: `# PRD\n\n${TABLE}\n\n\`\`\`json\n{"a": 1}\n\`\`\`\n`,
          complete: true,
        }}
        score={undefined}
      />,
    );

    await waitFor(() => expect(container.querySelector("table")).toBeTruthy());
    // The JSON fence stays a code block, and nothing was asked of Mermaid.
    expect(container.querySelector("pre")).toBeTruthy();
    expect(screen.queryByTestId("mermaid-diagram")).toBeNull();
    expect(screen.queryByTestId("mermaid-error")).toBeNull();
    expect(initialize).not.toHaveBeenCalled();
  });

  /**
   * A half-streamed fence is, by definition, invalid Mermaid. Drawing it would
   * flash 「图表渲染失败」 on the way to a diagram that is about to be valid.
   */
  it("leaves a still-streaming fence as source until the draft completes", () => {
    render(
      <PRDViewer
        runId={RUN_ID}
        draft={{
          version: 1,
          attempt: 1,
          content: "# PRD\n\n```mermaid\nflowchart TD\n  A[内容页] -->",
          complete: false,
        }}
        score={undefined}
      />,
    );

    expect(screen.queryByTestId("mermaid-diagram")).toBeNull();
    expect(screen.queryByTestId("mermaid-error")).toBeNull();
    expect(initialize).not.toHaveBeenCalled();
  });
});
