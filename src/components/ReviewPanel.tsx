import {
  BookOpen,
  ChevronDown,
  ClipboardList,
  Cpu,
  Crosshair,
  Minus,
  TrendingDown,
  TrendingUp,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import { RUBRIC, dimensionLabel } from "../lib/rubric";
import type { SeverityCounts, VersionFindings } from "../lib/runReducer";
import { normalizeFeedback } from "../lib/contracts";
import { FEEDBACK_SEVERITIES } from "../lib/types";
import type {
  FeedbackItem,
  FeedbackSeverity,
  FindingStatus,
  GateStatus,
  ReviewRole,
  RoleReview,
} from "../lib/types";

interface RoleMeta {
  label: string;
  short: string;
  caption: string;
  icon: LucideIcon;
}

export const ROLE_META: Record<ReviewRole, RoleMeta> = {
  tech: {
    label: "技术评审",
    short: "技术",
    caption: "架构 · 可行性",
    icon: Cpu,
  },
  ux: {
    label: "体验评审",
    short: "体验",
    caption: "用户旅程 · 状态",
    icon: Users,
  },
  biz: {
    label: "商业评审",
    short: "商业",
    caption: "价值 · 范围",
    icon: TrendingUp,
  },
};
const ROLE_ORDER: ReviewRole[] = ["tech", "ux", "biz"];

/**
 * Severity is the only place colour still carries meaning in this panel.
 *
 * Each label is also written out in text, so a reader who cannot separate the
 * hues still gets the tier from the word -- and `must_fix` is the only one that
 * reads as an alarm, because it is the only one that blocks a run.
 */
export const SEVERITY_META: Record<
  FeedbackSeverity,
  { label: string; className: string }
> = {
  must_fix: { label: "必须修复", className: "border-danger/50 text-danger" },
  should_fix: { label: "重要改进", className: "border-warn/50 text-warn" },
  optional: { label: "可选优化", className: "text-ink-faint" },
};

const GATE_META: Record<GateStatus, { label: string; className: string }> = {
  PASSED: { label: "通过", className: "text-ok" },
  NEEDS_REVISION: { label: "需要修订", className: "text-warn" },
  BLOCKED: { label: "受阻：违反硬约束", className: "text-danger" },
  UNSCORED: { label: "未评分", className: "text-ink-faint" },
};

const RESOLUTION_META: Record<
  FindingStatus,
  { label: string; className: string }
> = {
  resolved: { label: "已解决", className: "text-ok" },
  partially_resolved: { label: "部分解决", className: "text-warn" },
  unresolved: { label: "未解决", className: "text-danger" },
  declined: { label: "未采纳", className: "text-ink-muted" },
  not_checked: { label: "未复查", className: "text-ink-faint" },
};

/**
 * The change in one reviewer's score against the version before it.
 *
 * Reviewers score each version independently, so a later version can legitimately
 * score lower. The delta is stated with the previous number beside it, so a drop
 * reads as information about the revision instead of a bug in the tool.
 */
function ScoreDelta({
  role,
  score,
  previous,
  previousVersion,
}: {
  role: ReviewRole;
  score: number;
  previous: number;
  previousVersion: number;
}) {
  const delta = Math.round((score - previous) * 10) / 10;
  const meta =
    delta > 0
      ? { icon: TrendingUp, className: "text-ok" }
      : delta < 0
        ? { icon: TrendingDown, className: "text-danger" }
        : { icon: Minus, className: "text-ink-faint" };
  const Icon = meta.icon;
  return (
    <p
      className={`mt-1 flex items-center justify-end gap-1 text-xs ${meta.className}`}
      data-testid={`reviewer-delta-${role}`}
      data-delta={delta}
    >
      <Icon aria-hidden="true" size={11} className="shrink-0" />
      <span>
        {delta === 0 ? "持平" : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}`}
      </span>
      <span className="text-ink-faint">
        · v{previousVersion} {previous}
      </span>
    </p>
  );
}

function DimensionBars({ review }: { review: RoleReview }) {
  const dimensions = review.dimension_scores ?? [];
  if (dimensions.length === 0) {
    return (
      <p
        className="mt-3 text-xs leading-5 text-ink-faint"
        data-testid={`reviewer-legacy-${review.role}`}
      >
        历史评分：该版本按旧评分方式由模型直接给分，没有维度数据。
      </p>
    );
  }
  return (
    <ul
      className="mt-3 space-y-2"
      data-testid={`reviewer-dimensions-${review.role}`}
    >
      {dimensions.map((item) => (
        <li key={item.dimension} title={item.rationale}>
          <div className="flex items-baseline justify-between gap-2 text-xs">
            <span className="min-w-0 truncate text-ink-muted">
              {dimensionLabel(review.role, item.dimension)}
              {typeof item.weight === "number" && (
                <span className="text-ink-faint">
                  {" "}
                  · {Math.round(item.weight * 100)}%
                </span>
              )}
            </span>
            <span className="shrink-0 font-medium text-ink">
              {item.score}/5
            </span>
          </div>
          <div aria-hidden="true" className="mt-1 h-1 rounded-full bg-line">
            <div
              className="h-full rounded-full bg-accent"
              style={{ width: `${(item.score / 5) * 100}%` }}
            />
          </div>
          <p className="mt-0.5 text-xs leading-5 text-ink-faint">
            {item.rationale}
          </p>
        </li>
      ))}
    </ul>
  );
}

function ReviewerCard({
  role,
  review,
  previous,
  previousVersion,
}: {
  role: ReviewRole;
  review: RoleReview | undefined;
  previous: RoleReview | undefined;
  previousVersion: number | null;
}) {
  const meta = ROLE_META[role];
  const RoleIcon = meta.icon;
  const summary = review?.summary.trim() ?? "";
  const strengths = (review?.strengths ?? []).filter(
    (item) => item.trim() !== "",
  );

  return (
    <article
      className="surface-sunken"
      data-testid={`reviewer-card-${role}`}
      data-role={role}
      aria-labelledby={`reviewer-${role}-heading`}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <RoleIcon aria-hidden="true" size={15} className="text-ink-muted" />
          <div className="min-w-0">
            <h4
              id={`reviewer-${role}-heading`}
              className="text-sm font-semibold text-ink"
            >
              {meta.label}
            </h4>
            <p className="meta-label mt-0.5">{meta.caption}</p>
          </div>
        </div>
        {review ? (
          <div className="shrink-0 text-right">
            <span
              className="text-lg font-semibold text-ink"
              data-testid={`reviewer-score-${role}`}
            >
              {review.score}
              <span className="ml-0.5 text-xs font-medium text-ink-faint">
                /100
              </span>
            </span>
            {previous && previousVersion !== null && (
              <ScoreDelta
                role={role}
                score={review.score}
                previous={previous.score}
                previousVersion={previousVersion}
              />
            )}
          </div>
        ) : (
          <span
            className="shrink-0 text-xs font-medium text-ink-faint"
            data-testid={`reviewer-pending-${role}`}
          >
            评审进行中
          </span>
        )}
      </header>

      {review && (
        <>
          {summary !== "" && (
            <p className="mt-3 text-sm leading-6 text-ink">{summary}</p>
          )}
          <DimensionBars review={review} />
          {strengths.length > 0 && (
            <div className="mt-3">
              <h5 className="meta-label">做得好</h5>
              <ul
                className="mt-1.5 space-y-1"
                data-testid={`reviewer-strengths-${role}`}
              >
                {strengths.map((item) => (
                  <li key={item} className="text-xs leading-5 text-ink-muted">
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {(review.filtered_findings ?? 0) > 0 && (
            <p className="mt-2 text-xs text-ink-faint">
              另有 {review.filtered_findings}{" "}
              条意见因缺少证据或超出数量上限未列入。
            </p>
          )}
        </>
      )}
    </article>
  );
}

function rolesOf(item: FeedbackItem): ReviewRole[] {
  if (item.source_roles && item.source_roles.length > 0) {
    return item.source_roles;
  }
  return item.source_role ? [item.source_role] : [];
}

/** Findings for this version: the aggregator's merged list, else every reviewer's. */
function collectFindings(
  reviews: Partial<Record<ReviewRole, RoleReview>>,
  findings: VersionFindings | undefined,
): FeedbackItem[] {
  // The aggregator's list is authoritative when present -- empty included: a
  // version whose reviewers found nothing must not fall back to anything else.
  if (findings) {
    return findings.combined;
  }
  return ROLE_ORDER.flatMap((role) =>
    normalizeFeedback(reviews[role]?.feedback ?? []).map((item) => ({
      ...item,
      source_roles: rolesOf(item).length > 0 ? rolesOf(item) : [role],
    })),
  );
}

function FindingRow({
  item,
  onLocate,
}: {
  item: FeedbackItem;
  onLocate?: ((section: string) => void) | undefined;
}) {
  const meta = SEVERITY_META[item.severity];
  const roles = rolesOf(item);
  const title = item.title?.trim() || item.issue.trim();
  const problem = item.issue.trim();
  const recommendation = item.recommendation.trim();
  const observations = (item.observations ?? []).filter(
    (observation) => observation.role !== item.source_role,
  );
  return (
    <li
      className={`finding-row ${item.severity === "must_fix" ? "finding-row-blocking" : ""}`}
      data-testid="feedback-item"
      data-severity={item.severity}
      data-roles={roles.join(",")}
    >
      <details className="group">
        <summary className="flex cursor-pointer list-none items-start gap-3">
          <span
            className={`tag mt-0.5 shrink-0 ${meta.className}`}
            data-testid="feedback-severity"
          >
            {meta.label}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium leading-6 text-ink">
              {title}
            </span>
            <span className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-ink-faint">
              {roles.map((role) => ROLE_META[role].short).join(" · ") || "评审"}
              {roles.length > 1 && <span>· {roles.length} 位评审都提到</span>}
              {item.section && <span>· {item.section}</span>}
              {item.severity_adjusted_from && (
                <span title="评审标为必须修复，但该类问题按规则不阻塞">
                  · 已由「{SEVERITY_META[item.severity_adjusted_from].label}
                  」调整
                </span>
              )}
            </span>
          </span>
          <ChevronDown
            aria-hidden="true"
            size={14}
            className="mt-1.5 shrink-0 text-ink-faint transition group-open:rotate-180"
          />
        </summary>
        <dl className="mt-3 grid gap-x-4 gap-y-2 pl-1 text-sm sm:grid-cols-[5rem_1fr]">
          {problem !== "" && problem !== title && (
            <>
              <dt className="text-xs text-ink-faint">问题</dt>
              <dd className="leading-6 text-ink-muted">{problem}</dd>
            </>
          )}
          {item.evidence && (
            <>
              <dt className="text-xs text-ink-faint">依据</dt>
              <dd className="border-l-2 border-line-strong pl-2 leading-6 text-ink-muted">
                {item.evidence}
              </dd>
            </>
          )}
          {item.user_impact && (
            <>
              <dt className="text-xs text-ink-faint">影响</dt>
              <dd className="leading-6 text-ink-muted">{item.user_impact}</dd>
            </>
          )}
          {recommendation !== "" && recommendation !== problem && (
            <>
              <dt className="text-xs text-ink-faint">建议</dt>
              <dd className="leading-6 text-ink">
                {recommendation.replace(/^建议[:：]\s*/, "")}
              </dd>
            </>
          )}
          {observations.length > 0 && (
            <>
              <dt className="text-xs text-ink-faint">其他评审</dt>
              <dd>
                <ul className="space-y-1">
                  {observations.map((observation) => (
                    <li
                      key={observation.finding_id}
                      className="text-xs leading-5 text-ink-muted"
                    >
                      <span className="text-ink">
                        {ROLE_META[observation.role].short}：
                      </span>
                      {observation.problem}
                    </li>
                  ))}
                </ul>
              </dd>
            </>
          )}
        </dl>
        {item.section && onLocate && (
          <button
            type="button"
            className="button-ghost mt-2 text-xs"
            data-testid="feedback-locate"
            onClick={() => onLocate(item.section!)}
          >
            <Crosshair aria-hidden="true" size={13} />
            定位到 PRD 章节
          </button>
        )}
      </details>
    </li>
  );
}

function RubricRules() {
  return (
    <details className="surface-sunken mt-4" data-testid="rubric-rules">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-xs font-medium text-ink-muted hover:text-ink">
        <BookOpen aria-hidden="true" size={13} />
        评分规则（{RUBRIC.rubric_version}）
      </summary>
      <div className="mt-3 grid gap-4 text-xs leading-5 text-ink-muted lg:grid-cols-2">
        <div>
          <p className="font-medium text-ink">分数由谁计算</p>
          <ul className="mt-1 list-disc space-y-1 pl-4">
            <li>评审模型为每个维度打 1–5 分并写出依据，不输出总分。</li>
            <li>
              后端计算角色分：<code>Σ(维度分 / 5 × 权重) × 100</code>
            </li>
            <li>综合分 = (技术 + 体验 + 商业) / 3，保留一位小数。</li>
            <li>
              通过门槛需要同时满足：综合分 ≥
              目标分，且没有未解决的「必须修复」。哪些问题属于「必须修复」由评审判断，后端只执行规则。
            </li>
          </ul>
          <p className="mt-3 font-medium text-ink">1–5 分含义</p>
          <ul className="mt-1 space-y-0.5">
            {Object.entries(RUBRIC.scale.anchors).map(([score, text]) => (
              <li key={score}>
                <span className="text-ink">{score}</span> · {text.zh}
              </li>
            ))}
          </ul>
        </div>
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
          {ROLE_ORDER.map((role) => (
            <div key={role}>
              <p className="font-medium text-ink">{ROLE_META[role].label}</p>
              <ul className="mt-1 space-y-0.5">
                {RUBRIC.roles[role].map((dimension) => (
                  <li key={dimension.id}>
                    {dimension.label_zh} · {Math.round(dimension.weight * 100)}%
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}

type SeverityFilter = FeedbackSeverity | "all";
type RoleFilter = ReviewRole | "all";

export function ReviewPanel({
  version,
  reviews,
  previousReviews,
  previousVersion = null,
  severity,
  findings,
  overall,
  qualityThreshold,
  onLocate,
}: {
  version: number | null;
  reviews: Partial<Record<ReviewRole, RoleReview>> | undefined;
  /** The version before this one, for the per-reviewer score delta. */
  previousReviews?: Partial<Record<ReviewRole, RoleReview>> | undefined;
  previousVersion?: number | null;
  /** Open findings for this version, summarized above the list. */
  severity?: SeverityCounts | undefined;
  findings?: VersionFindings | undefined;
  overall?: number | undefined;
  qualityThreshold?: number | undefined;
  onLocate?: ((section: string) => void) | undefined;
}) {
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");
  const present = ROLE_ORDER.filter((role) => reviews?.[role]);
  // No reviewer has finished for this version yet: showing an empty scaffold
  // would imply reviews exist, so the panel stays out of the page entirely.
  if (version === null || present.length === 0 || !reviews) {
    return null;
  }
  const totals = severity ?? null;
  const all = collectFindings(reviews, findings);
  const ordered = FEEDBACK_SEVERITIES.flatMap((tier) =>
    all.filter((item) => item.severity === tier),
  );
  const visible = ordered.filter(
    (item) =>
      (severityFilter === "all" || item.severity === severityFilter) &&
      (roleFilter === "all" || rolesOf(item).includes(roleFilter)),
  );
  const gate = findings?.gateStatus ?? null;
  const resolutions = findings?.resolutions ?? [];
  const scores = present.map((role) => reviews[role]!.score);

  return (
    <section
      className="panel"
      aria-labelledby="review-panel-heading"
      data-testid="review-panel"
      data-version={version}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="panel-heading">
            <ClipboardList aria-hidden="true" size={18} />
            <h2 id="review-panel-heading">评审结果</h2>
          </div>
          <p className="mt-1.5 text-xs text-ink-muted">
            三位评审独立审阅 v{version}，评分由后端按评分规则计算。
          </p>
        </div>
        {overall !== undefined && (
          <div className="text-right" data-testid="review-overall">
            <p className="text-2xl font-semibold text-ink">{overall}</p>
            <p className="text-xs text-ink-faint">
              综合分 = ({scores.join(" + ")}) / 3
            </p>
            {qualityThreshold !== undefined && (
              <p className="mt-0.5 text-xs">
                <span className="text-ink-faint">
                  目标 {qualityThreshold} · 门槛：
                </span>
                <span
                  className={
                    gate ? GATE_META[gate].className : "text-ink-muted"
                  }
                  data-testid="review-gate"
                >
                  {gate
                    ? GATE_META[gate].label
                    : overall >= qualityThreshold &&
                        (totals?.mustFix ?? 0) === 0
                      ? "通过"
                      : "需要修订"}
                </span>
              </p>
            )}
          </div>
        )}
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {ROLE_ORDER.map((role) => (
          <ReviewerCard
            key={role}
            role={role}
            review={reviews[role]}
            previous={previousReviews?.[role]}
            previousVersion={previousVersion}
          />
        ))}
      </div>

      <RubricRules />

      {resolutions.length > 0 && (
        <div className="mt-6" data-testid="finding-resolutions">
          <h3 className="text-sm font-semibold text-ink">
            v{previousVersion ?? version - 1} 问题的处理情况
          </h3>
          <ul className="mt-2 space-y-1.5">
            {resolutions.map((item) => (
              <li
                key={item.finding_id}
                className="flex gap-3 text-sm"
                data-testid="finding-resolution"
                data-status={item.status}
              >
                <span
                  className={`w-16 shrink-0 text-xs font-medium leading-6 ${RESOLUTION_META[item.status]?.className ?? "text-ink-faint"}`}
                >
                  {RESOLUTION_META[item.status]?.label ?? item.status}
                </span>
                <span className="min-w-0 leading-6 text-ink-muted">
                  {item.title ?? item.finding_id}
                  {item.note ? (
                    <span className="text-ink-faint"> · {item.note}</span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-ink">
            剩余问题
            {findings?.beforeDedup != null &&
              findings.beforeDedup > all.length && (
                <span className="ml-2 text-xs font-normal text-ink-faint">
                  {findings.beforeDedup} 条评审意见合并为 {all.length} 条
                </span>
              )}
          </h3>
          {totals && (
            <dl
              className="flex flex-wrap gap-x-4 gap-y-1"
              data-testid="review-severity-totals"
            >
              {(
                [
                  ["must_fix", totals.mustFix],
                  ["should_fix", totals.shouldFix],
                  ["optional", totals.optional],
                ] as const
              ).map(([tier, count]) => (
                <div key={tier} className="flex items-baseline gap-1.5">
                  <dt className="meta-label">{SEVERITY_META[tier].label}</dt>
                  <dd
                    className={`text-xs font-semibold ${
                      tier === "must_fix" && count > 0
                        ? "text-danger"
                        : "text-ink"
                    }`}
                    data-testid={`review-total-${tier}`}
                  >
                    {count}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>

        {ordered.length > 0 && (
          <div
            className="mt-3 flex flex-wrap gap-1.5"
            role="group"
            aria-label="筛选问题"
          >
            {(["all", ...FEEDBACK_SEVERITIES] as SeverityFilter[]).map(
              (tier) => (
                <button
                  key={tier}
                  type="button"
                  className={`chip ${severityFilter === tier ? "chip-active" : ""}`}
                  aria-pressed={severityFilter === tier}
                  data-testid={`filter-severity-${tier}`}
                  onClick={() => setSeverityFilter(tier)}
                >
                  {tier === "all" ? "全部" : SEVERITY_META[tier].label}
                </button>
              ),
            )}
            <span
              aria-hidden="true"
              className="mx-1 w-px self-stretch bg-line"
            />
            {(["all", ...ROLE_ORDER] as RoleFilter[]).map((role) => (
              <button
                key={role}
                type="button"
                className={`chip ${roleFilter === role ? "chip-active" : ""}`}
                aria-pressed={roleFilter === role}
                data-testid={`filter-role-${role}`}
                onClick={() => setRoleFilter(role)}
              >
                {role === "all" ? "全部评审" : ROLE_META[role].short}
              </button>
            ))}
          </div>
        )}

        {ordered.length === 0 ? (
          <p className="empty-copy" data-testid="findings-empty">
            评审没有提出需要处理的问题。
          </p>
        ) : visible.length === 0 ? (
          <p className="empty-copy">当前筛选条件下没有问题。</p>
        ) : (
          <ul className="mt-3 divide-y divide-line" data-testid="findings-list">
            {visible.map((item, index) => (
              <FindingRow
                key={
                  item.finding_id ?? `${item.severity}-${index}-${item.issue}`
                }
                item={item}
                onLocate={onLocate}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/** The must-fix and should-fix findings, compact, for the PRD side column. */
export function FindingsSidebar({
  reviews,
  findings,
  onLocate,
}: {
  reviews: Partial<Record<ReviewRole, RoleReview>> | undefined;
  findings: VersionFindings | undefined;
  onLocate?: ((section: string) => void) | undefined;
}) {
  if (!reviews) {
    return null;
  }
  const important = collectFindings(reviews, findings).filter(
    (item) => item.severity !== "optional",
  );
  return (
    <div className="sticky top-6 space-y-2" data-testid="prd-findings-sidebar">
      <p className="meta-label">待处理问题 · {important.length}</p>
      {important.length === 0 ? (
        <p className="text-xs text-ink-muted">没有必须修复或重要改进的问题。</p>
      ) : (
        <ul className="space-y-2">
          {important.slice(0, 8).map((item, index) => (
            <li key={item.finding_id ?? index} className="surface-sunken py-2">
              <span className={`tag ${SEVERITY_META[item.severity].className}`}>
                {SEVERITY_META[item.severity].label}
              </span>
              <p className="mt-1 text-xs leading-5 text-ink">
                {item.title?.trim() || item.issue}
              </p>
              {item.section && onLocate && (
                <button
                  type="button"
                  className="mt-1 text-xs text-accent underline-offset-4 hover:underline"
                  onClick={() => onLocate(item.section!)}
                >
                  {item.section}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
