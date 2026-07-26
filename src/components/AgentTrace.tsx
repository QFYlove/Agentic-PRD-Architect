import { Activity } from "lucide-react";

import { toTraceItem } from "../lib/trace";
import type { RunEvent } from "../lib/types";

export function AgentTrace({ events }: { events: RunEvent[] }) {
  const items = events
    .map(toTraceItem)
    .filter((item): item is NonNullable<typeof item> => item !== null);

  return (
    <section className="panel" aria-labelledby="trace-heading">
      <div className="panel-heading">
        <Activity aria-hidden="true" size={18} />
        <h2 id="trace-heading">智能体轨迹</h2>
      </div>
      {items.length === 0 ? (
        <p className="empty-copy">结构化工作流事件将在这里实时显示。</p>
      ) : (
        <ol className="mt-5 space-y-4">
          {items.map((item) => (
            <li
              key={item.sequence}
              data-testid="trace-event"
              data-sequence={item.sequence}
              className="relative border-l border-white/10 pl-5"
            >
              <span
                aria-hidden="true"
                className={`absolute -left-1.5 top-1.5 h-3 w-3 rounded-full border-2 border-slate-950 ${
                  item.tone === "success"
                    ? "bg-emerald-400"
                    : item.tone === "error"
                      ? "bg-rose-400"
                      : item.tone === "warning"
                        ? "bg-amber-400"
                        : item.tone === "active"
                          ? "bg-cyan-400"
                          : "bg-slate-500"
                }`}
              />
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="text-sm font-medium text-slate-100">
                  {item.label}
                </h3>
                <span className="text-[10px] text-slate-600">
                  #{item.sequence}
                </span>
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-400">
                {item.detail}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
