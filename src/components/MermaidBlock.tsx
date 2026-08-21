import { useEffect, useId, useRef, useState } from "react";

/**
 * The only diagram types a PRD is allowed to draw.
 *
 * A whitelist rather than a blocklist: Mermaid ships types (gantt, pie, gitGraph,
 * quadrantChart …) that a model reaches for to decorate rather than to explain,
 * and one of them rendering badly is worse than it not rendering at all. Anything
 * outside this list falls back to its source, which is still readable.
 */
const ALLOWED_TYPES = [
  "flowchart",
  "graph",
  "sequenceDiagram",
  "stateDiagram-v2",
  "mindmap",
  "erDiagram",
] as const;

/**
 * `flowchart` is what the prompt asks for; `graph` is Mermaid's own older alias
 * for the same renderer and models emit it constantly. Rejecting it would fail a
 * diagram that is otherwise exactly what was requested.
 */
export function mermaidDiagramType(source: string): string | null {
  for (const raw of source.split("\n")) {
    const line = raw.trim();
    if (line === "" || line.startsWith("%%")) {
      continue;
    }
    const keyword = line.split(/[\s{]/, 1)[0] ?? "";
    return (
      ALLOWED_TYPES.find(
        (allowed) => allowed.toLowerCase() === keyword.toLowerCase(),
      ) ?? null
    );
  }
  return null;
}

type RenderState =
  | { kind: "pending" }
  | { kind: "ready"; svg: string }
  | { kind: "failed" };

function SourceFallback({ source, note }: { source: string; note: string }) {
  return (
    <div className="my-3 rounded-control border border-line bg-canvas p-3">
      <p className="text-xs text-ink-muted" data-testid="mermaid-error">
        {note}
      </p>
      <details className="mt-2">
        <summary className="cursor-pointer text-xs text-ink-muted underline underline-offset-4 hover:text-ink">
          查看 Mermaid 源码
        </summary>
        <pre className="mt-2 overflow-x-auto text-xs text-ink-muted">
          <code>{source}</code>
        </pre>
      </details>
    </div>
  );
}

/**
 * One Mermaid diagram from a PRD, rendered defensively.
 *
 * Three things make this safe to point at model output. The runtime arrives via
 * `await import("mermaid")` inside the effect, so a PRD with no diagrams never
 * downloads it. `securityLevel: "strict"` with `htmlLabels: false` means a label
 * containing markup is drawn as text rather than parsed, so nothing the model
 * writes can execute. And every failure path -- an unsupported type, a syntax
 * error, a runtime that will not load -- ends in the source being shown instead
 * of an exception escaping into the document's render tree.
 */
export function MermaidBlock({ source }: { source: string }) {
  const [state, setState] = useState<RenderState>({ kind: "pending" });
  const domId = `mermaid-${useId().replace(/[^a-zA-Z0-9-]/g, "")}`;
  const idRef = useRef(domId);
  const type = mermaidDiagramType(source);

  useEffect(() => {
    if (type === null) {
      return;
    }
    let cancelled = false;

    async function draw(): Promise<void> {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          // No model-authored HTML is ever parsed, in labels or anywhere else.
          securityLevel: "strict",
          htmlLabels: false,
          theme: "dark",
          themeVariables: {
            background: "#10151c",
            primaryColor: "#1a2230",
            primaryTextColor: "#e6ebf2",
            primaryBorderColor: "#2c3644",
            lineColor: "#63718a",
            secondaryColor: "#161d27",
            tertiaryColor: "#161d27",
            fontSize: "13px",
          },
          flowchart: { htmlLabels: false },
        });
        // Parsed before rendering: `render` draws its own error diagram into the
        // document for invalid input, and a red "Syntax error" graphic is a worse
        // fallback than the source the author can actually read.
        await mermaid.parse(source);
        const { svg } = await mermaid.render(idRef.current, source);
        if (!cancelled) {
          setState({ kind: "ready", svg });
        }
      } catch {
        // Deliberately swallowed: a syntax error in a generated diagram is an
        // expected outcome, not an exception the page should propagate.
        if (!cancelled) {
          setState({ kind: "failed" });
        }
      }
    }

    void draw();
    return () => {
      cancelled = true;
    };
  }, [source, type]);

  if (type === null) {
    return (
      <SourceFallback source={source} note="不支持的图表类型，已显示源码。" />
    );
  }
  if (state.kind === "failed") {
    return <SourceFallback source={source} note="图表渲染失败，已显示源码。" />;
  }
  if (state.kind === "pending") {
    return (
      <div
        className="my-3 h-24 animate-pulse rounded-control bg-raised"
        role="status"
      >
        <span className="sr-only">正在渲染图表…</span>
      </div>
    );
  }
  return (
    <figure
      className="prd-mermaid my-3"
      data-testid="mermaid-diagram"
      data-diagram-type={type}
      // Mermaid's own output, produced under `securityLevel: "strict"`; the model
      // never contributes markup, only node text.
      dangerouslySetInnerHTML={{ __html: state.svg }}
    />
  );
}
