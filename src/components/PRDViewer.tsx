import { AlertTriangle, Download, FileText, ListTree } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import ReactMarkdown, {
  type Components,
  type ExtraProps,
} from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  createMarkdownDownload,
  triggerMarkdownDownload,
} from "../lib/download";
import {
  headingId,
  parseOutline,
  type OutlineHeading,
} from "../lib/prdOutline";
import {
  isUsableDraft,
  type VersionDraft,
  type VersionScore,
} from "../lib/runReducer";
import type { PRDQualityReport } from "../lib/types";
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
  position?: { start?: { line?: number } };
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

/**
 * Headings get an id from their source line, which is also what the table of
 * contents and "定位到章节" use -- so the two can never disagree about which
 * heading is which, even when two share a title.
 */
function heading(level: 1 | 2 | 3 | 4 | 5 | 6) {
  const Tag = `h${level}` as const;
  return function Heading({
    node,
    children,
    ...props
  }: ComponentProps<typeof Tag> & ExtraProps) {
    const line = (node as HastNode | undefined)?.position?.start?.line;
    return (
      <Tag {...props} id={line ? headingId(line) : undefined}>
        {children}
      </Tag>
    );
  };
}

const HEADING_COMPONENTS: Components = {
  h1: heading(1),
  h2: heading(2),
  h3: heading(3),
  h4: heading(4),
  h5: heading(5),
  h6: heading(6),
};

const MARKDOWN_COMPONENTS: Components = {
  ...HEADING_COMPONENTS,
  pre: MarkdownPre,
};

export function scrollToHeading(id: string): void {
  const target = document.getElementById(id);
  if (target && typeof target.scrollIntoView === "function") {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function Outline({ headings }: { headings: OutlineHeading[] }) {
  const visible = headings.filter((item) => item.level >= 2 && item.level <= 3);
  if (visible.length < 2) {
    return null;
  }
  return (
    <nav
      aria-label="PRD 目录"
      className="hidden xl:block"
      data-testid="prd-outline"
    >
      <div className="sticky top-6 max-h-[calc(100vh-3rem)] overflow-y-auto pr-2">
        <p className="meta-label flex items-center gap-1.5">
          <ListTree aria-hidden="true" size={12} />
          目录
        </p>
        <ol className="mt-2 space-y-0.5">
          {visible.map((item) => (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                className={`block truncate rounded-control px-2 py-1 text-xs leading-5 text-ink-muted hover:bg-raised hover:text-ink ${
                  item.level === 3 ? "pl-5" : ""
                }`}
                title={item.text}
                onClick={(event) => {
                  event.preventDefault();
                  scrollToHeading(item.id);
                }}
              >
                {item.text}
              </a>
            </li>
          ))}
        </ol>
      </div>
    </nav>
  );
}

function QualityNote({ quality }: { quality: PRDQualityReport }) {
  const problems = quality.issues.filter((issue) => issue.severity !== "info");
  if (quality.structure_complete && problems.length === 0) {
    return null;
  }
  const counts = [
    quality.missing_sections.length > 0
      ? `缺少章节：${quality.missing_sections.join("、")}`
      : null,
    quality.long_paragraphs > 0
      ? `${quality.long_paragraphs} 个超长段落`
      : null,
    quality.unlabeled_figures
      ? `${quality.unlabeled_figures} 处数值未标注来源或假设`
      : null,
    problems.some((issue) => issue.code === "fabricated_source")
      ? "引用了用户未提供的数据来源"
      : null,
  ].filter(Boolean);
  return (
    <details className="callout-warn mt-4" data-testid="prd-quality">
      <summary className="cursor-pointer list-none text-xs font-medium text-warn">
        <AlertTriangle
          aria-hidden="true"
          size={13}
          className="mr-1 inline align-[-2px]"
        />
        结构检查：
        {counts.length > 0 ? counts.join(" · ") : `${problems.length} 个提示`}
      </summary>
      <ul className="mt-2 space-y-1 text-xs leading-5 text-ink-muted">
        {problems.slice(0, 12).map((issue, index) => (
          <li key={`${issue.code}-${index}`}>
            {issue.message}
            {issue.section ? `（${issue.section}）` : ""}
          </li>
        ))}
      </ul>
    </details>
  );
}

interface PRDViewerProps {
  runId: string;
  draft: VersionDraft | null;
  score: VersionScore | undefined;
  quality?: PRDQualityReport | undefined;
  /** Optional right-hand column, e.g. the open findings for this version. */
  aside?: ReactNode;
}

/**
 * The document, with a table of contents and an optional findings column.
 *
 * Three states, kept visibly apart: a finished version (downloadable), a live
 * draft (「正在生成」), and an interrupted draft -- the text a failed generation
 * streamed before it stopped. Run 9fa59292's half v2 used to show as the live
 * state, with the download button handing out the fragment as `-v2.md`.
 */
export function PRDViewer({
  runId,
  draft,
  score,
  quality,
  aside,
}: PRDViewerProps) {
  const usable = isUsableDraft(draft);
  const interrupted = Boolean(draft?.interrupted);
  const headings = draft && usable ? parseOutline(draft.content) : [];

  function download() {
    if (!draft || !isUsableDraft(draft)) {
      return;
    }
    triggerMarkdownDownload(
      createMarkdownDownload(runId, draft.version, draft.content),
    );
  }

  return (
    <div
      className={`grid min-w-0 gap-6 ${
        headings.length >= 2 ? "xl:grid-cols-[12rem_minmax(0,1fr)]" : ""
      } ${aside ? "2xl:grid-cols-[12rem_minmax(0,1fr)_20rem]" : ""}`}
    >
      {headings.length >= 2 && <Outline headings={headings} />}
      <section className="panel min-w-0" aria-labelledby="prd-viewer-heading">
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
            {draft && !draft.complete && !interrupted && (
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
            {interrupted && (
              <span
                className="tag border-danger/50 text-danger"
                data-testid="prd-incomplete-label"
              >
                未完成 · 已中断
              </span>
            )}
            <button
              data-testid="download-markdown"
              className="button-secondary"
              type="button"
              disabled={!usable}
              title={interrupted ? "未完成的草稿不能作为 PRD 下载" : undefined}
              onClick={download}
            >
              <Download aria-hidden="true" size={15} />
              下载 Markdown
            </button>
          </div>
        </div>

        {interrupted && draft && (
          <p
            className="callout-danger mt-4 text-xs leading-5"
            data-testid="prd-incomplete-notice"
          >
            这是 v{draft.version} 生成中断前输出的
            {draft.content.length.toLocaleString()}
            字草稿，内容不完整，没有经过评审，也不会计入评分、对比或下载。请切换到已完成的版本阅读。
          </p>
        )}

        {quality && usable && <QualityNote quality={quality} />}

        {!draft ? (
          <div className="flex min-h-72 flex-col items-center justify-center text-center">
            <FileText
              aria-hidden="true"
              className="text-line-strong"
              size={34}
            />
            <h3 className="mt-3 text-sm font-medium text-ink">等待首版草稿</h3>
            <p className="mt-1.5 max-w-sm text-xs leading-6 text-ink-muted">
              生成器会将 PRD 实时输出到这里，运行记录标签页可以观察完整工作流。
            </p>
          </div>
        ) : (
          <article
            className={`prd-markdown mx-auto mt-5 max-w-reading ${
              interrupted ? "opacity-70" : ""
            }`}
            data-testid="prd-content"
          >
            {/* Diagrams are only drawn once the document is finished. A fence that
                is still streaming is, by definition, invalid Mermaid, and rendering
                it would flash 「图表渲染失败」 at the reader on the way to a valid
                diagram. Until then the source shows as an ordinary code block. */}
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              skipHtml
              components={usable ? MARKDOWN_COMPONENTS : HEADING_COMPONENTS}
            >
              {draft.content}
            </ReactMarkdown>
            {!draft.complete && !interrupted && (
              <span className="stream-cursor" aria-hidden="true" />
            )}
          </article>
        )}
      </section>
      {aside && <aside className="hidden min-w-0 2xl:block">{aside}</aside>}
    </div>
  );
}
