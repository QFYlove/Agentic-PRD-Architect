import { ChevronDown, FileInput } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { digestRequest } from "../lib/prdOutline";
import type { RunSnapshot } from "../lib/types";

/**
 * What the user asked for, at the size it deserves.
 *
 * The run header used to print `user_idea` verbatim -- 4,993 characters for run
 * 9fa59292, collapsed into one unbroken paragraph with its `#` and `-` markers
 * showing, and the target audience and constraints nowhere. Now the header shows
 * a deterministic title and summary, and the original request -- rendered as
 * Markdown, never as HTML -- sits one click away, unmodified.
 */
export function RunRequest({ snapshot }: { snapshot: RunSnapshot }) {
  const digest = digestRequest(snapshot.user_idea);
  const tags = [
    snapshot.generation_mode === "compact" ? "精简模式" : null,
    snapshot.source_run_id
      ? snapshot.recovery_mode === "continue_from_best"
        ? `基于 v${snapshot.source_version ?? "?"} 继续`
        : "重新生成"
      : null,
    ...digest.topics.slice(0, 4),
  ].filter((tag): tag is string => Boolean(tag));

  return (
    <div className="min-w-0" data-testid="run-request">
      <h2
        className="text-lg font-semibold leading-snug text-ink sm:text-xl"
        data-testid="run-title"
        title={digest.title}
      >
        {digest.title}
      </h2>
      {digest.summary.replace(/[。.]$/, "") !== digest.title && (
        <p
          className="mt-1.5 max-w-reading text-sm leading-6 text-ink-muted"
          data-testid="run-summary"
        >
          {digest.summary}
        </p>
      )}
      {(tags.length > 0 || snapshot.target_audience) && (
        <ul className="mt-2.5 flex flex-wrap gap-1.5" aria-label="需求标签">
          {snapshot.target_audience && (
            <li className="tag" title={snapshot.target_audience}>
              目标用户：{snapshot.target_audience.slice(0, 24)}
              {snapshot.target_audience.length > 24 ? "…" : ""}
            </li>
          )}
          {tags.map((tag) => (
            <li key={tag} className="tag">
              {tag}
            </li>
          ))}
        </ul>
      )}
      <details className="group mt-3" data-testid="raw-request">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-xs font-medium text-ink-muted hover:text-ink">
          <FileInput aria-hidden="true" size={13} />
          查看原始需求
          <span className="text-ink-faint">
            （{digest.characters.toLocaleString()} 字）
          </span>
          <ChevronDown
            aria-hidden="true"
            size={13}
            className="transition group-open:rotate-180"
          />
        </summary>
        <div className="surface-sunken mt-2 max-h-[28rem] overflow-y-auto">
          <div
            className="prd-markdown prd-markdown-compact"
            data-testid="raw-request-content"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
              {snapshot.user_idea}
            </ReactMarkdown>
          </div>
          {(snapshot.target_audience || snapshot.user_constraints) && (
            <dl className="mt-4 grid gap-3 border-t border-line pt-3 text-sm sm:grid-cols-2">
              {snapshot.target_audience && (
                <div>
                  <dt className="meta-label">目标用户</dt>
                  <dd className="mt-1 whitespace-pre-wrap text-ink">
                    {snapshot.target_audience}
                  </dd>
                </div>
              )}
              {snapshot.user_constraints && (
                <div>
                  <dt className="meta-label">约束条件</dt>
                  <dd className="mt-1 whitespace-pre-wrap text-ink">
                    {snapshot.user_constraints}
                  </dd>
                </div>
              )}
            </dl>
          )}
        </div>
      </details>
    </div>
  );
}
