import { GitCompare, Minus, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { diffLines, type DiffRow } from "../lib/diff";
import {
  readingDiff,
  type ReadingBlockRow,
  type ReadingChange,
  type ReadingSection,
} from "../lib/readingDiff";

interface VersionDiffProps {
  sourceVersion: number;
  targetVersion: number;
  sourceContent: string;
  targetContent: string;
}

type DiffMode = "reading" | "source";

const CHANGE_META: Record<
  ReadingChange,
  { label: string; className: string; accent: string }
> = {
  added: {
    label: "新增",
    className: "border-l-2 border-ok bg-ok/[0.07]",
    accent: "text-ok",
  },
  removed: {
    label: "删除",
    className: "border-l-2 border-danger bg-danger/[0.07] opacity-80",
    accent: "text-danger",
  },
  unchanged: {
    label: "未变化",
    className: "border-l-2 border-transparent",
    accent: "text-ink-faint",
  },
};

/**
 * One Markdown block, rendered.
 *
 * The change type is carried three ways at once -- a word, a strikethrough on
 * removals, and a coloured rule -- because a PM reading this needs to know what
 * changed without decoding a palette, and colour alone fails in greyscale, in
 * print, and for a reader who cannot separate green from red.
 */
function ReadingBlock({ row }: { row: ReadingBlockRow }) {
  const meta = CHANGE_META[row.change];
  return (
    <div
      className={`px-3 py-1.5 ${meta.className}`}
      data-testid={`reading-block-${row.change}`}
      data-change={row.change}
      data-kind={row.block.kind}
    >
      {row.change !== "unchanged" && (
        <p className={`meta-label ${meta.accent}`}>
          {meta.label}
          <span className="sr-only">：</span>
        </p>
      )}
      {row.change === "unchanged" && <span className="sr-only">未变化：</span>}
      <div
        className={`prd-markdown prd-markdown-compact ${
          row.change === "removed" ? "prd-markdown-removed" : ""
        }`}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
          {row.block.text}
        </ReactMarkdown>
      </div>
    </div>
  );
}

function ReadingSectionView({ section }: { section: ReadingSection }) {
  const headingMeta = CHANGE_META[section.change];
  return (
    <section
      className="border-t border-line first:border-t-0"
      data-testid="reading-section"
      data-changed={section.changed}
    >
      <header className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 bg-raised px-3 py-2">
        <h4
          className="min-w-0 text-[13px] font-semibold text-ink"
          data-testid="reading-section-heading"
        >
          {section.heading ?? "文档开头"}
        </h4>
        {section.change !== "unchanged" && (
          <span className={`meta-label ${headingMeta.accent}`}>
            标题{headingMeta.label}
          </span>
        )}
        <span className="meta-label" data-testid="reading-section-counts">
          {section.addedBlocks > 0 && `+${section.addedBlocks}`}
          {section.addedBlocks > 0 && section.removedBlocks > 0 && " "}
          {section.removedBlocks > 0 && `−${section.removedBlocks}`}
        </span>
      </header>
      {section.rows.length > 0 && (
        <div className="py-1.5">
          {section.rows.map((row, index) =>
            row.type === "skipped" ? (
              <p
                key={`skipped-${index}`}
                className="px-3 py-1 text-[11px] text-ink-faint"
                data-testid="reading-skipped"
              >
                已折叠 {row.count} 段未变化内容
              </p>
            ) : (
              <ReadingBlock key={`block-${index}`} row={row} />
            ),
          )}
        </div>
      )}
    </section>
  );
}

/** Untouched section names printed before the row falls back to a count. */
const MAX_NAMED_SECTIONS = 8;

/**
 * A run of consecutive untouched sections, named on one line.
 *
 * A real PRD has twenty-odd sections and a revision touches three of them. Given
 * a row per untouched section, the comparison opened on sixteen 「本节未变化」
 * stubs and the reader had to scroll past all of them to reach the first change.
 * Naming them together keeps the fact that they were left alone -- which is part
 * of reading a revision -- without letting it outweigh the revision itself.
 */
function UnchangedSectionRun({ headings }: { headings: string[] }) {
  // Subsections repeat their names across a long document ("范围", "开放问题"),
  // so a raw join reads as a stutter. The count is the fact; the names are only
  // there to orient, which the first few already do.
  const named = [...new Set(headings)].slice(0, MAX_NAMED_SECTIONS);
  return (
    <section
      className="border-t border-line first:border-t-0"
      data-testid="reading-section-unchanged"
      data-count={headings.length}
    >
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-3 py-2">
        <span className="meta-label shrink-0">
          {headings.length} 个章节未变化
        </span>
        <span className="min-w-0 text-[11px] leading-5 text-ink-faint">
          {named.join(" · ")}
          {named.length < new Set(headings).size && " 等"}
        </span>
      </div>
    </section>
  );
}

/** Document order, with each stretch of untouched sections folded into one row. */
function groupSections(
  sections: ReadingSection[],
): Array<ReadingSection | string[]> {
  const groups: Array<ReadingSection | string[]> = [];
  for (const section of sections) {
    if (section.changed) {
      groups.push(section);
      continue;
    }
    const last = groups.at(-1);
    const name = section.heading ?? "文档开头";
    if (Array.isArray(last)) {
      last.push(name);
    } else {
      groups.push([name]);
    }
  }
  return groups;
}

const ROW_META: Record<
  DiffRow["kind"],
  { marker: string; label: string; className: string }
> = {
  added: {
    marker: "+",
    label: "新增",
    className: "border-l-2 border-ok bg-ok/[0.08] text-ink",
  },
  removed: {
    marker: "−",
    label: "删除",
    className: "border-l-2 border-danger bg-danger/[0.08] text-ink",
  },
  context: {
    marker: " ",
    label: "未变化",
    className: "border-l-2 border-transparent text-ink-faint",
  },
};

function DiffLine({ row }: { row: DiffRow }) {
  const meta = ROW_META[row.kind];
  const blank = row.text.trim() === "";
  return (
    <div
      className={`flex gap-2 px-2.5 py-0.5 font-mono text-[12px] leading-5 sm:gap-3 sm:px-3 ${meta.className}`}
      data-testid={`diff-row-${row.kind}`}
      data-kind={row.kind}
    >
      {/* Two fixed columns rather than one "12 / 14" string: the eye follows a
          single side down the gutter instead of re-parsing a pair each line. */}
      <span
        aria-hidden="true"
        className="flex shrink-0 select-none gap-1.5 text-[11px] text-ink-faint"
      >
        <span className="w-6 text-right">{row.sourceLine ?? ""}</span>
        <span className="w-6 text-right">{row.targetLine ?? ""}</span>
      </span>
      {/* The marker is text, not just a colour, so the change type survives
          greyscale, colour blindness, and screen readers. */}
      <span
        aria-hidden="true"
        className="w-3 shrink-0 select-none font-semibold"
      >
        {meta.marker}
      </span>
      <span className="sr-only">{meta.label}：</span>
      {blank ? (
        // A wholly blank added or removed line would otherwise render as a
        // bare marker with nothing beside it, reading like a rendering fault.
        <span className="select-none text-[11px] italic text-ink-faint">
          {row.kind === "context" ? " " : "空行"}
        </span>
      ) : (
        <span className="min-w-0 whitespace-pre-wrap break-words">
          {row.text}
        </span>
      )}
    </div>
  );
}

const MODES: Array<{ id: DiffMode; label: string }> = [
  { id: "reading", label: "阅读对比" },
  { id: "source", label: "源码" },
];

export function VersionDiff({
  sourceVersion,
  targetVersion,
  sourceContent,
  targetContent,
}: VersionDiffProps) {
  /**
   * Reading is the default and source is the fallback.
   *
   * A PM opening a revision wants to know what the document now says. A line
   * diff answers a different question -- which characters moved -- and made
   * `##`, `|---|---|` and half a table the first thing on screen. The source
   * view stays for the cases where the exact text matters.
   */
  const [mode, setMode] = useState<DiffMode>("reading");

  // Only the two finalized documents feed these, so the memos hold for the whole
  // session and streaming updates elsewhere never recompute a historical diff.
  const reading = useMemo(
    () => readingDiff(sourceContent, targetContent),
    [sourceContent, targetContent],
  );
  const lines = useMemo(
    () => diffLines(sourceContent, targetContent),
    [sourceContent, targetContent],
  );
  const source = mode === "source";
  const unchanged = source ? lines.unchanged : reading.unchanged;

  return (
    <section
      aria-labelledby="version-diff-heading"
      data-testid="version-diff"
      data-mode={mode}
      data-source-version={sourceVersion}
      data-target-version={targetVersion}
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <GitCompare
            aria-hidden="true"
            size={16}
            className="shrink-0 text-ink-muted"
          />
          <div className="min-w-0">
            <h3
              id="version-diff-heading"
              className="text-sm font-semibold text-ink"
              data-testid="version-diff-lineage"
            >
              v{sourceVersion} → v{targetVersion} 修订对比
            </h3>
            <p className="mt-0.5 text-xs text-ink-muted">
              {source
                ? "逐行文本差异，用于核对精确改动。"
                : "按章节呈现这次修订新增和删除的内容。"}
            </p>
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-2">
          <span
            className="inline-flex items-center gap-1 text-xs text-ok"
            data-testid="diff-added-count"
          >
            <Plus aria-hidden="true" size={12} />
            新增{" "}
            {source ? `${lines.addedCount} 行` : `${reading.addedBlocks} 段`}
          </span>
          <span
            className="inline-flex items-center gap-1 text-xs text-danger"
            data-testid="diff-removed-count"
          >
            <Minus aria-hidden="true" size={12} />
            删除{" "}
            {source
              ? `${lines.removedCount} 行`
              : `${reading.removedBlocks} 段`}
          </span>
          <div
            className="inline-flex rounded-control border border-line p-0.5"
            role="tablist"
            aria-label="对比方式"
          >
            {MODES.map((entry) => (
              <button
                key={entry.id}
                data-testid={`diff-mode-${entry.id}`}
                className={`rounded-[4px] px-2.5 py-1 text-xs font-medium transition ${
                  mode === entry.id
                    ? "bg-accent-soft text-accent"
                    : "text-ink-muted hover:text-ink"
                }`}
                type="button"
                role="tab"
                aria-selected={mode === entry.id}
                onClick={() => setMode(entry.id)}
              >
                {entry.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {unchanged ? (
        <p className="empty-copy mt-4" data-testid="diff-unchanged">
          两个版本的内容完全一致。
        </p>
      ) : source ? (
        <div className="mt-4 overflow-hidden rounded-panel border border-line bg-canvas">
          {lines.segments.map((segment, index) =>
            segment.type === "skipped" ? (
              <p
                key={`skipped-${index}`}
                className="border-y border-line bg-raised px-3 py-1.5 text-[11px] text-ink-faint"
                data-testid="diff-skipped"
              >
                已折叠 {segment.count} 行未变化内容
              </p>
            ) : (
              <div key={`hunk-${index}`} data-testid="diff-hunk">
                {segment.heading && (
                  <p
                    className="bg-raised px-3 py-1.5 text-[11px] font-medium text-ink-muted"
                    data-testid="diff-hunk-heading"
                  >
                    {segment.heading}
                  </p>
                )}
                {segment.rows.map((row, rowIndex) => (
                  <DiffLine key={`${index}-${rowIndex}`} row={row} />
                ))}
              </div>
            ),
          )}
        </div>
      ) : (
        <div className="mt-4 overflow-hidden rounded-panel border border-line bg-canvas">
          {groupSections(reading.sections).map((group, index) =>
            Array.isArray(group) ? (
              <UnchangedSectionRun
                key={`unchanged-${index}`}
                headings={group}
              />
            ) : (
              <ReadingSectionView key={`section-${index}`} section={group} />
            ),
          )}
        </div>
      )}
    </section>
  );
}
