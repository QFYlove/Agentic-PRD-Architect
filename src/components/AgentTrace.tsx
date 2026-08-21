import { Activity } from "lucide-react";
import { useEffect, useRef } from "react";

import { toTraceItem } from "../lib/trace";
import type { RunEvent } from "../lib/types";

export function AgentTrace({ events }: { events: RunEvent[] }) {
  const items = events
    .map(toTraceItem)
    .filter((item): item is NonNullable<typeof item> => item !== null);

  /**
   * A finished two-round run emits ~30 trace entries. Left unbounded the panel
   * grew taller than the PRD itself and pushed the document that the run exists
   * to produce below the fold, so the log scrolls inside a fixed frame and tails
   * the newest entry the way a console does -- unless the reader has scrolled up
   * to inspect an earlier step, which is left alone.
   */
  const listRef = useRef<HTMLOListElement>(null);
  const pinned = useRef(true);
  useEffect(() => {
    const list = listRef.current;
    if (list && pinned.current) {
      list.scrollTop = list.scrollHeight;
    }
  }, [items.length]);

  return (
    <section className="panel" aria-labelledby="trace-heading">
      <div className="panel-heading">
        <Activity aria-hidden="true" size={18} />
        <h2 id="trace-heading">智能体轨迹</h2>
        {items.length > 0 && (
          <span className="ml-auto text-[11px] font-medium text-ink-faint">
            {items.length} 条事件
          </span>
        )}
      </div>
      {items.length === 0 ? (
        <p className="empty-copy">结构化工作流事件将在这里实时显示。</p>
      ) : (
        <ol
          ref={listRef}
          className="mt-4 max-h-[22rem] space-y-3 overflow-y-auto pr-1"
          onScroll={(event) => {
            const list = event.currentTarget;
            pinned.current =
              list.scrollHeight - list.scrollTop - list.clientHeight < 24;
          }}
        >
          {items.map((item) => (
            <li
              key={item.sequence}
              data-testid="trace-event"
              data-sequence={item.sequence}
              className="relative border-l border-line pl-4"
            >
              <span
                aria-hidden="true"
                className={`absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-surface ${
                  item.tone === "success"
                    ? "bg-ok"
                    : item.tone === "error"
                      ? "bg-danger"
                      : item.tone === "warning"
                        ? "bg-warn"
                        : item.tone === "active"
                          ? "bg-accent"
                          : "bg-line-strong"
                }`}
              />
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="text-[13px] font-medium leading-5 text-ink">
                  {item.label}
                </h3>
                <span className="shrink-0 font-mono text-[10px] text-ink-faint">
                  #{item.sequence}
                </span>
              </div>
              <p className="text-xs leading-5 text-ink-muted">{item.detail}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
