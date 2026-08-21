import type { ReactNode } from "react";

export interface WorkspaceTab {
  id: string;
  label: string;
  /** Shown after the label when there is something to count. */
  badge?: string | undefined;
  disabled?: boolean;
  panel: ReactNode;
}

/**
 * The workspace's top-level navigation.
 *
 * Everything the run produces used to be on screen at once, which meant the PRD
 * -- the only artifact the run exists to produce -- competed with the workflow
 * diagram, the event log and the telemetry grid for the same first screen. These
 * tabs keep all of it, and let the document be the default.
 */
export function WorkspaceTabs({
  tabs,
  activeId,
  onSelect,
}: {
  tabs: WorkspaceTab[];
  activeId: string;
  onSelect(id: string): void;
}) {
  const active = tabs.find((tab) => tab.id === activeId) ?? tabs[0];
  return (
    <div>
      <div
        className="-mx-1 flex min-w-0 gap-1 overflow-x-auto border-b border-line px-1"
        role="tablist"
        aria-label="工作区视图"
      >
        {tabs.map((tab) => {
          const selected = tab.id === active?.id;
          return (
            <button
              key={tab.id}
              id={`workspace-tab-${tab.id}`}
              data-testid={`workspace-tab-${tab.id}`}
              // A border on the selected tab rather than a filled pill: the
              // tab strip is navigation, not a row of status chips.
              className={`-mb-px inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition ${
                selected
                  ? "border-accent text-ink"
                  : "border-transparent text-ink-muted hover:text-ink"
              } disabled:cursor-not-allowed disabled:opacity-40`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`workspace-panel-${tab.id}`}
              disabled={tab.disabled ?? false}
              onClick={() => onSelect(tab.id)}
            >
              {tab.label}
              {tab.badge !== undefined && tab.badge !== "" && (
                <span className="font-mono text-[11px] text-ink-faint">
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {active && (
        <div
          key={active.id}
          id={`workspace-panel-${active.id}`}
          className="mt-4 min-w-0"
          role="tabpanel"
          aria-labelledby={`workspace-tab-${active.id}`}
          data-testid={`workspace-panel-${active.id}`}
        >
          {active.panel}
        </div>
      )}
    </div>
  );
}
