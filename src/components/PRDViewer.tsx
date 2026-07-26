import { Download, FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  createMarkdownDownload,
  triggerMarkdownDownload,
} from "../lib/download";
import type { VersionDraft, VersionScore } from "../lib/runReducer";

interface PRDViewerProps {
  runId: string;
  drafts: Record<number, VersionDraft>;
  scores: Record<number, VersionScore>;
  selectedVersion: number | null;
  onSelectVersion(version: number): void;
}

export function PRDViewer({
  runId,
  drafts,
  scores,
  selectedVersion,
  onSelectVersion,
}: PRDViewerProps) {
  const versions = Object.values(drafts).sort(
    (left, right) => left.version - right.version,
  );
  const selected =
    versions.find((version) => version.version === selectedVersion) ?? null;
  const selectedScore = selected ? scores[selected.version] : undefined;

  function download() {
    if (!selected) {
      return;
    }
    triggerMarkdownDownload(
      createMarkdownDownload(runId, selected.version, selected.content),
    );
  }

  return (
    <section
      className="flex min-h-[40rem] flex-col rounded-[2rem] border border-white/10 bg-slate-950/80 shadow-2xl shadow-black/20"
      aria-labelledby="prd-viewer-heading"
    >
      <header className="border-b border-white/10 px-5 py-4 sm:px-7">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="rounded-xl bg-violet-400/10 p-2 text-violet-300">
              <FileText aria-hidden="true" size={18} />
            </span>
            <div>
              <h2 id="prd-viewer-heading" className="font-semibold text-white">
                PRD 工作区
              </h2>
              <p className="text-xs text-slate-500">
                经过校准、支持版本切换的 Markdown 输出
              </p>
            </div>
          </div>
          <button
            data-testid="download-markdown"
            className="button-secondary"
            type="button"
            disabled={!selected || !selected.content}
            onClick={download}
          >
            <Download aria-hidden="true" size={16} />
            下载 Markdown
          </button>
        </div>

        {versions.length > 0 && (
          <div
            className="mt-4 flex gap-2 overflow-x-auto pb-1"
            role="tablist"
            aria-label="PRD 版本"
          >
            {versions.map((version) => (
              <button
                key={version.version}
                data-testid={`version-tab-v${version.version}`}
                className={`shrink-0 rounded-xl border px-3 py-2 text-sm font-medium transition ${
                  version.version === selectedVersion
                    ? "border-cyan-300/40 bg-cyan-300/10 text-cyan-100"
                    : "border-white/10 bg-white/[0.02] text-slate-400 hover:text-white"
                }`}
                type="button"
                role="tab"
                aria-selected={version.version === selectedVersion}
                onClick={() => onSelectVersion(version.version)}
              >
                v{version.version}
                {scores[version.version] && (
                  <span className="ml-2 text-xs opacity-70">
                    {scores[version.version]?.overall}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-5 py-6 sm:px-8">
        {!selected ? (
          <div className="flex min-h-96 flex-col items-center justify-center text-center">
            <FileText aria-hidden="true" className="text-slate-700" size={42} />
            <h3 className="mt-4 font-medium text-slate-300">等待首版草稿</h3>
            <p className="mt-2 max-w-sm text-sm leading-6 text-slate-500">
              生成器会将 PRD 实时输出到这里，左侧可以同步观察完整工作流。
            </p>
          </div>
        ) : (
          <>
            <div className="mb-5 flex flex-wrap items-center gap-3 text-xs text-slate-400">
              <span>版本 {selected.version}</span>
              {selectedScore && (
                <span>
                  综合评分{" "}
                  <strong className="font-semibold text-cyan-200">
                    {selectedScore.overall}
                  </strong>
                </span>
              )}
              {!selected.complete && (
                <span
                  className="inline-flex items-center gap-2 text-cyan-200"
                  role="status"
                >
                  <span
                    aria-hidden="true"
                    className="h-2 w-2 animate-pulse rounded-full bg-cyan-300"
                  />
                  正在生成
                </span>
              )}
            </div>
            <article className="prd-markdown" data-testid="prd-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
                {selected.content}
              </ReactMarkdown>
              {!selected.complete && (
                <span className="stream-cursor" aria-hidden="true" />
              )}
            </article>
          </>
        )}
      </div>
    </section>
  );
}
