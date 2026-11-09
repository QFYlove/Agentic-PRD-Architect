import { ArrowRight, ListChecks, Target, UserPen } from "lucide-react";

import type { VersionRevisionPlan } from "../lib/runReducer";
import type {
  ChangeType,
  FindingResolution,
  FindingStatus,
  RevisionPriority,
  RevisionSource,
} from "../lib/types";

const CHANGE_LABELS: Record<ChangeType, string> = {
  ADD: "新增",
  UPDATE: "修改",
  REMOVE: "删除",
  CONSOLIDATE: "合并",
  RETAIN: "保留",
};

const STATUS_LABELS: Record<
  FindingStatus,
  { label: string; className: string }
> = {
  resolved: { label: "已解决", className: "text-ok" },
  partially_resolved: { label: "部分解决", className: "text-warn" },
  unresolved: { label: "未解决", className: "text-danger" },
  declined: { label: "未采纳", className: "text-ink-muted" },
  not_checked: { label: "未复查", className: "text-ink-faint" },
};

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
  optimizer: "优化器（去重 / 精简）",
};

function sourceLabels(sources: RevisionSource[]): string[] {
  return [...new Set(sources)]
    .filter((source) => source in SOURCE_LABELS)
    .map((source) => SOURCE_LABELS[source]);
}

/**
 * One plan item's outcome, read from the next version's review: the least
 * resolved status among the findings it addressed.
 */
function itemStatus(
  findingIds: string[] | undefined,
  resolutions: FindingResolution[],
): FindingStatus | null {
  if (!findingIds || findingIds.length === 0 || resolutions.length === 0) {
    return null;
  }
  const rank: FindingStatus[] = [
    "unresolved",
    "partially_resolved",
    "not_checked",
    "resolved",
  ];
  const statuses = findingIds
    .map((id) => resolutions.find((item) => item.finding_id === id)?.status)
    .filter((status): status is FindingStatus => Boolean(status));
  if (statuses.length === 0) {
    return null;
  }
  return statuses.sort((a, b) => rank.indexOf(a) - rank.indexOf(b))[0] ?? null;
}

export function RevisionPlanPanel({
  entry,
  resolutions = [],
}: {
  entry: VersionRevisionPlan | undefined;
  /** How the target version's reviewers judged the findings this plan addressed. */
  resolutions?: FindingResolution[];
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
          className="surface-sunken mt-4 flex gap-2 text-sm leading-6 text-ink"
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
        <ol className="mt-4 divide-y divide-line">
          {plan.items.map((item, index) => {
            const priority = PRIORITY_META[item.priority];
            const sources = sourceLabels(item.source_roles);
            const status = itemStatus(item.source_finding_ids, resolutions);
            const targets =
              item.target_sections && item.target_sections.length > 0
                ? item.target_sections
                : [item.target_section];
            return (
              <li
                key={`${item.target_section}-${item.issue}-${index}`}
                className="flex gap-3 py-3"
                data-testid="revision-item"
                data-change-type={item.change_type ?? undefined}
              >
                <span
                  aria-hidden="true"
                  className="mt-1 shrink-0 font-mono text-xs text-ink-faint"
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-sm font-medium leading-6 text-ink">
                    {item.change_type && (
                      <span className="tag" data-testid="revision-item-change">
                        {CHANGE_LABELS[item.change_type]}
                      </span>
                    )}
                    <span className="min-w-0">{item.issue}</span>
                    {status && (
                      <span
                        className={`text-xs font-medium ${STATUS_LABELS[status].className}`}
                        data-testid="revision-item-status"
                      >
                        {STATUS_LABELS[status].label}
                      </span>
                    )}
                  </p>
                  {item.reason && (
                    <p className="mt-1 text-sm leading-6 text-ink-muted">
                      原因：{item.reason}
                    </p>
                  )}
                  {item.required_change.trim() !== "" &&
                    item.required_change !== item.issue && (
                      <p className="mt-1 text-sm leading-6 text-ink">
                        修改要求：{item.required_change}
                      </p>
                    )}
                  {item.expected_result && (
                    <p className="mt-1 text-xs leading-5 text-ink-muted">
                      预期结果：{item.expected_result}
                    </p>
                  )}
                  {item.affected_sections &&
                    item.affected_sections.length > 0 && (
                      <p
                        className="mt-1 text-xs leading-5 text-ink-muted"
                        data-testid="revision-item-affected"
                      >
                        同步修改：{item.affected_sections.join("、")}
                      </p>
                    )}
                  {item.must_preserve && item.must_preserve.length > 0 && (
                    <p className="mt-1 text-xs leading-5 text-ink-muted">
                      必须保留：{item.must_preserve.join("；")}
                    </p>
                  )}
                  {/* One muted meta line instead of three filled badges: with
                      six items sharing the same priority and section, repeated
                      badges read as decoration rather than information. */}
                  <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-faint">
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
                      className="text-ink-muted"
                      data-testid="revision-item-section"
                    >
                      {targets.join(" / ")}
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

      {plan.declined_findings && plan.declined_findings.length > 0 && (
        <div className="mt-4" data-testid="revision-plan-declined">
          <h3 className="meta-label">未采纳的评审意见</h3>
          <ul className="mt-1.5 space-y-1">
            {plan.declined_findings.map((item) => (
              <li
                key={item.finding_id}
                className="text-xs leading-5 text-ink-muted"
              >
                <span className="font-mono text-ink-faint">
                  {item.finding_id}
                </span>
                {" · "}
                {item.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
