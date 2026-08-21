import { Download, FileText } from "lucide-react";
import type { ComponentProps } from "react";
import ReactMarkdown, {
  type Components,
  type ExtraProps,
} from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  createMarkdownDownload,
  triggerMarkdownDownload,
} from "../lib/download";
import type { VersionDraft, VersionScore } from "../lib/runReducer";
import { MermaidBlock } from "./MermaidBlock";

/*
 * The two hast shapes this file reads, declared locally.
 *
 * `@types/hast` is only present as a transitive dependency of react-markdown, so
 * importing from it would be a phantom import that a future dependency bump could
 * silently remove. Both fields are read defensively anyway.
 */
interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: { className?: unknown };
  children?: HastNode[];
}

function textOf(children: HastNode[]): string {
  return children
    .map((child) => (child.type === "text" ? (child.value ?? "") : ""))
    .join("");
}

function mermaidSource(node: unknown): string | null {
  const children = (node as HastNode | undefined)?.children ?? [];
  const code = children.find(
    (child) => child.type === "element" && child.tagName === "code",
  );
  if (!code) {
    return null;
  }
  const classes = code.properties?.className;
  return Array.isArray(classes) && classes.includes("language-mermaid")
    ? textOf(code.children ?? [])
    : null;
}

/**
 * A ```mermaid fence becomes a diagram; every other fence stays a code block.
 *
 * Overriding `pre` rather than `code` because the diagram replaces the whole
 * block: rendering a `<figure>` inside the `<pre>` that react-markdown emits
 * would nest it in the code-block frame and inherit monospace styling.
 */
function MarkdownPre({
  node,
  children,
  ...props
}: ComponentProps<"pre"> & ExtraProps) {
  const source = mermaidSource(node);
  return source === null ? (
    <pre {...props}>{children}</pre>
  ) : (
    <MermaidBlock source={source} />
  );
}

const MARKDOWN_COMPONENTS: Components = { pre: MarkdownPre };

interface PRDViewerProps {
  runId: string;
  draft: VersionDraft | null;
  score: VersionScore | undefined;
}

/**
 * The document, and nothing else.
 *
 * Version selection and the revision comparison both used to live in this
 * panel's header, which made the PRD share its frame with two control strips.
 * The version rail is now part of the run header and the comparison is its own
 * tab, so this renders one version of one document.
 */
export function PRDViewer({ runId, draft, score }: PRDViewerProps) {
  function download() {
    if (!draft) {
      return;
    }
    triggerMarkdownDownload(
      createMarkdownDownload(runId, draft.version, draft.content),
    );
  }

  return (
    <section className="panel" aria-labelledby="prd-viewer-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="panel-heading">
          <FileText aria-hidden="true" size={18} />
          <h2 id="prd-viewer-heading">PRD 文档</h2>
          {draft && (
            <span className="meta-label" data-testid="prd-version-label">
              v{draft.version}
              {score && ` · 综合 ${score.overall}`}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {draft && !draft.complete && (
            <span
              className="inline-flex items-center gap-1.5 text-xs text-accent"
              role="status"
            >
              <span
                aria-hidden="true"
                className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent"
              />
              正在生成
            </span>
          )}
          <button
            data-testid="download-markdown"
            className="button-secondary"
            type="button"
            disabled={!draft || !draft.content}
            onClick={download}
          >
            <Download aria-hidden="true" size={15} />
            下载 Markdown
          </button>
        </div>
      </div>

      {!draft ? (
        <div className="flex min-h-72 flex-col items-center justify-center text-center">
          <FileText aria-hidden="true" className="text-line-strong" size={34} />
          <h3 className="mt-3 text-sm font-medium text-ink">等待首版草稿</h3>
          <p className="mt-1.5 max-w-sm text-xs leading-6 text-ink-muted">
            生成器会将 PRD 实时输出到这里，运行记录标签页可以观察完整工作流。
          </p>
        </div>
      ) : (
        <article
          className="prd-markdown mt-4 max-w-reading"
          data-testid="prd-content"
        >
          {/* Diagrams are only drawn once the document is finished. A fence that
              is still streaming is, by definition, invalid Mermaid, and rendering
              it would flash 「图表渲染失败」 at the reader on the way to a valid
              diagram. Until then the source shows as an ordinary code block. */}
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            skipHtml
            components={draft.complete ? MARKDOWN_COMPONENTS : undefined}
          >
            {draft.content}
          </ReactMarkdown>
          {!draft.complete && (
            <span className="stream-cursor" aria-hidden="true" />
          )}
        </article>
      )}
    </section>
  );
}
