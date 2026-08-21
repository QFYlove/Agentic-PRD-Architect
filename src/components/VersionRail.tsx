import { Star } from "lucide-react";

import type { VersionScore } from "../lib/runReducer";

interface VersionRailProps {
  versions: number[];
  scores: Record<number, VersionScore>;
  selectedVersion: number | null;
  bestVersion: number | null;
  onSelectVersion(version: number): void;
}

/**
 * The version selector, hoisted out of the document panel.
 *
 * Every tab in the workspace reads one version at a time -- its text, its
 * reviews, the plan it produced, the diff it created -- so the selector belongs
 * to the run, not to the PRD panel that used to own it. Keeping it in the header
 * also means switching tabs never loses the version the reader was on.
 */
export function VersionRail({
  versions,
  scores,
  selectedVersion,
  bestVersion,
  onSelectVersion,
}: VersionRailProps) {
  if (versions.length === 0) {
    return null;
  }
  return (
    <div
      className="flex min-w-0 flex-wrap gap-1.5"
      role="tablist"
      aria-label="PRD 版本"
    >
      {versions.map((version) => {
        const score = scores[version];
        const selected = version === selectedVersion;
        const best = version === bestVersion;
        return (
          <button
            key={version}
            data-testid={`version-tab-v${version}`}
            data-best={best}
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-control border px-2.5 py-1.5 text-xs font-medium transition ${
              selected
                ? "border-accent bg-accent-soft text-accent"
                : "border-line bg-raised text-ink-muted hover:border-line-strong hover:text-ink"
            }`}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onSelectVersion(version)}
          >
            {/* The best version is marked in the rail itself, because the run's
                last version is frequently not its best one and a reader
                comparing versions should not have to remember which. */}
            {best && (
              <Star
                aria-hidden="true"
                size={11}
                className={selected ? "" : "text-ink-faint"}
                fill="currentColor"
              />
            )}
            v{version}
            {score && (
              <span className="font-mono text-[11px] opacity-80">
                {score.overall}
              </span>
            )}
            {best && <span className="sr-only">（最佳版本）</span>}
          </button>
        );
      })}
    </div>
  );
}
