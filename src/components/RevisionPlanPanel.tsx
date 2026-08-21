import { ArrowRight, ListChecks, Target, UserPen } from "lucide-react";

import type { VersionRevisionPlan } from "../lib/runReducer";
import type { RevisionPriority, RevisionSource } from "../lib/types";

const PRIORITY_META: Record<
  RevisionPriority,
  { label: string; className: string; dot: string }
> = {
  high: {
    label: "高优先级",
    className: "text-danger",
    dot: "bg-danger",
  },
  medium: {
    label: "中优先级",
    className: "text-warn",
    dot: "bg-warn",
  },
  low: {
    label: "低优先级",
    className: "text-ink-muted",
    dot: "bg-line-strong",
  },
};

const SOURCE_LABELS: Record<RevisionSource, string> = {
  tech: "技术评审",
  ux: "体验评审",
  biz: "商业评审",
  user: "用户补充",
};

function sourceLabels(sources: RevisionSource[]): string[] {
  return [...new Set(sources)]
    .filter((source) => source in SOURCE_LABELS)
    .map((source) => SOURCE_LABELS[source]);
}

export function RevisionPlanPanel({
  entry,
}: {
  entry: VersionRevisionPlan | undefined;
}) {
  // A version only has a plan once the optimizer ran on its reviews, so the
  // panel is absent for the newest version and for runs that never iterated.
  if (!entry) {
    return null;
  }
  const { sourceVersion, targetVersion, plan } = entry;
  const objective = plan.objective.trim();
  const override = plan.user_override?.trim() ?? "";

  return (
    <section
      className="panel"
      aria-labelledby="revision-plan-heading"
      data-testid="revision-plan-panel"
      data-source-version={sourceVersion}
      data-target-version={targetVersion}
    >
      <div className="panel-heading">
        <ListChecks aria-hidden="true" size={18} />
        <h2 id="revision-plan-heading">修订计划</h2>
      </div>
      <p
        className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-ink-muted"
        data-testid="revision-plan-lineage"
      >
        <span>v{sourceVersion} 评审反馈</span>
        <ArrowRight aria-hidden="true" size={12} className="text-ink-faint" />
        <span className="text-ink">优化器修订计划</span>
        <ArrowRight aria-hidden="true" size={12} className="text-ink-faint" />
        <span>用于生成 v{targetVersion}</span>
      </p>

      {objective !== "" && (
        <p
          className="block-inset mt-4 flex gap-2 text-xs leading-5 text-ink"
          data-testid="revision-plan-objective"
        >
          <Target
            aria-hidden="true"
            size={14}
            className="mt-0.5 shrink-0 text-ink-muted"
          />
          <span className="min-w-0">{objective}</span>
        </p>
      )}

      {override !== "" && (
        <p
          className="mt-3 flex gap-2 rounded-control border-l-2 border-accent bg-accent-soft px-3.5 py-3 text-xs leading-5 text-ink"
          data-testid="revision-plan-user-override"
        >
          <UserPen aria-hidden="true" size={14} className="mt-0.5 shrink-0" />
          <span className="min-w-0">
            <strong className="font-semibold">你补充的优化要求：</strong>
            {override}
          </span>
        </p>
      )}

      {plan.items.length > 0 && (
        <ol className="mt-4 grid gap-2 lg:grid-cols-2">
          {plan.items.map((item, index) => {
            const priority = PRIORITY_META[item.priority];
            const sources = sourceLabels(item.source_roles);
            return (
              <li
                key={`${item.target_section}-${item.issue}-${index}`}
                className="block-inset flex gap-3"
                data-testid="revision-item"
              >
                <span
                  aria-hidden="true"
                  className="mt-0.5 shrink-0 font-mono text-[11px] text-ink-faint"
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0">
                  <p className="text-xs font-medium leading-5 text-ink">
                    {item.issue}
                  </p>
                  {item.required_change.trim() !== "" &&
                    item.required_change !== item.issue && (
                      <p className="mt-1 text-xs leading-5 text-ink-muted">
                        修改要求：{item.required_change}
                      </p>
                    )}
                  {/* One muted meta line instead of three filled badges: with
                      six items sharing the same priority and section, repeated
                      badges read as decoration rather than information. */}
                  <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-ink-faint">
                    {priority && (
                      <span
                        className={`inline-flex items-center gap-1 font-semibold ${priority.className}`}
                        data-testid="revision-item-priority"
                      >
                        <span
                          aria-hidden="true"
                          className={`h-1.5 w-1.5 rounded-full ${priority.dot}`}
                        />
                        {priority.label}
                      </span>
                    )}
                    <span aria-hidden="true">·</span>
                    <span
                      className="font-mono text-ink-muted"
                      data-testid="revision-item-section"
                    >
                      {item.target_section}
                    </span>
                    {sources.length > 0 && (
                      <>
                        <span aria-hidden="true">·</span>
                        <span data-testid="revision-item-sources">
                          来自 {sources.join(" · ")}
                        </span>
                      </>
                    )}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
