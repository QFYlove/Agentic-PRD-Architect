import {
  ClipboardList,
  Cpu,
  Minus,
  ThumbsUp,
  TrendingDown,
  TrendingUp,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import type { SeverityCounts } from "../lib/runReducer";
import { FEEDBACK_SEVERITIES } from "../lib/types";
import type {
  FeedbackItem,
  FeedbackSeverity,
  ReviewRole,
  RoleReview,
} from "../lib/types";

interface RoleMeta {
  label: string;
  caption: string;
  icon: LucideIcon;
}

const ROLE_META: Record<ReviewRole, RoleMeta> = {
  tech: { label: "技术评审", caption: "架构 · 可行性", icon: Cpu },
  ux: { label: "体验评审", caption: "用户旅程 · 无障碍", icon: Users },
  biz: { label: "商业评审", caption: "价值 · 风险", icon: TrendingUp },
};
const ROLE_ORDER: ReviewRole[] = ["tech", "ux", "biz"];

/**
 * Severity is the only place colour still carries meaning in this panel.
 *
 * Each label is also written out in text, so a reader who cannot separate the
 * three hues still gets the tier from the word -- and `must_fix` is the only one
 * that reads as an alarm, because it is the only one that blocks a run.
 */
export const SEVERITY_META: Record<
  FeedbackSeverity,
  { label: string; className: string }
> = {
  must_fix: { label: "必须修复", className: "border-danger/50 text-danger" },
  should_fix: { label: "重要改进", className: "border-warn/50 text-warn" },
  optional: { label: "可选优化", className: "text-ink-faint" },
};

/**
 * The change in one reviewer's score against the version before it.
 *
 * Reviewers score each version independently, so a later version can legitimately
 * score lower -- and it does, whenever a revision that closed a blocker also
 * opened a new gap. Rather than hide that or ask the model for a "this version is
 * better" narrative, the delta is stated with the previous number beside it, so a
 * drop reads as information about the revision instead of a bug in the tool.
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
      className={`mt-1 flex items-center justify-end gap-1 text-[11px] ${meta.className}`}
      data-testid={`reviewer-delta-${role}`}
      data-delta={delta}
    >
      <Icon aria-hidden="true" size={11} className="shrink-0" />
      <span>
        {delta === 0 ? "持平" : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}`}
      </span>
      <span className="text-ink-faint">
        · 上一版本 v{previousVersion} {previous}
      </span>
    </p>
  );
}

function StrengthList({ items, testId }: { items: string[]; testId: string }) {
  const entries = items.filter((item) => item.trim() !== "");
  if (entries.length === 0) {
    return null;
  }
  return (
    <div className="mt-3">
      <h5 className="meta-label flex items-center gap-1.5">
        <ThumbsUp aria-hidden="true" size={12} />
        做得好
      </h5>
      <ul className="mt-2 space-y-1.5" data-testid={testId}>
        {entries.map((item) => (
          <li
            key={item}
            className="flex gap-2 text-xs leading-5 text-ink-muted"
          >
            <span
              aria-hidden="true"
              className="mt-2 h-1 w-1 shrink-0 rounded-full bg-line-strong"
            />
            <span className="min-w-0">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The open findings for one reviewer, grouped highest-severity first.
 *
 * The heading is 「剩余问题」 rather than the old 「需要修改」: on a run that
 * passed the gate these items are advice that outlives the document, and calling
 * them "needs changes" is what made a finished PRD read as unfinished. The tier
 * on each row is what tells the reader whether anything here actually blocks.
 */
function FeedbackList({
  items,
  testId,
}: {
  items: FeedbackItem[];
  testId: string;
}) {
  const entries = items.filter(
    (item) => item.issue.trim() !== "" || item.recommendation.trim() !== "",
  );
  if (entries.length === 0) {
    return null;
  }
  return (
    <div className="mt-3">
      <h5 className="meta-label flex items-center gap-1.5">
        <Wrench aria-hidden="true" size={12} />
        剩余问题
      </h5>
      <ul className="mt-2 space-y-2" data-testid={testId}>
        {FEEDBACK_SEVERITIES.flatMap((severity) =>
          entries
            .filter((item) => item.severity === severity)
            .map((item, index) => {
              const meta = SEVERITY_META[severity];
              const issue = item.issue.trim();
              const recommendation = item.recommendation.trim();
              return (
                <li
                  key={`${severity}-${index}-${issue}`}
                  className="min-w-0"
                  data-severity={severity}
                  data-testid="feedback-item"
                >
                  <span
                    className={`tag ${meta.className}`}
                    data-testid="feedback-severity"
                  >
                    {meta.label}
                  </span>
                  <p className="mt-1.5 text-xs leading-5 text-ink-muted">
                    {issue === "" ? recommendation : issue}
                  </p>
                  {recommendation !== "" && recommendation !== issue && (
                    <p className="mt-1 text-xs leading-5 text-ink-faint">
                      建议：{recommendation}
                    </p>
                  )}
                </li>
              );
            }),
        )}
      </ul>
    </div>
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

  return (
    <article
      className="block-inset py-3.5"
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
              className="text-sm font-semibold text-ink"
              data-testid={`reviewer-score-${role}`}
            >
              {review.score}
              <span className="ml-0.5 text-[10px] font-medium text-ink-faint">
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
            className="shrink-0 text-[11px] font-medium text-ink-faint"
            data-testid={`reviewer-pending-${role}`}
          >
            评审进行中
          </span>
        )}
      </header>

      {review && (
        <>
          {summary !== "" && (
            <p className="mt-3 text-xs leading-5 text-ink">{summary}</p>
          )}
          <StrengthList
            items={review.strengths}
            testId={`reviewer-strengths-${role}`}
          />
          <FeedbackList
            items={review.feedback}
            testId={`reviewer-feedback-${role}`}
          />
        </>
      )}
    </article>
  );
}

export function ReviewPanel({
  version,
  reviews,
  previousReviews,
  previousVersion = null,
  severity,
}: {
  version: number | null;
  reviews: Partial<Record<ReviewRole, RoleReview>> | undefined;
  /** The version before this one, for the per-reviewer score delta. */
  previousReviews?: Partial<Record<ReviewRole, RoleReview>> | undefined;
  previousVersion?: number | null;
  /** Open findings for this version, summarized above the three cards. */
  severity?: SeverityCounts | undefined;
}) {
  const present = ROLE_ORDER.filter((role) => reviews?.[role]);
  // No reviewer has finished for this version yet: showing an empty scaffold
  // would imply reviews exist, so the panel stays out of the page entirely.
  if (version === null || present.length === 0) {
    return null;
  }
  const totals = severity ?? null;

  return (
    <section
      className="panel"
      aria-labelledby="review-panel-heading"
      data-testid="review-panel"
      data-version={version}
    >
      <div className="panel-heading">
        <ClipboardList aria-hidden="true" size={18} />
        <h2 id="review-panel-heading">评审详情</h2>
      </div>
      <p className="mt-1.5 text-xs text-ink-muted">
        三位评审独立审阅 v{version}，下面是各自的评分依据。
      </p>
      {totals && (
        <dl
          className="mt-3 flex flex-wrap gap-x-4 gap-y-1"
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
                  tier === "must_fix" && count > 0 ? "text-danger" : "text-ink"
                }`}
                data-testid={`review-total-${tier}`}
              >
                {count}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {ROLE_ORDER.map((role) => (
          <ReviewerCard
            key={role}
            role={role}
            review={reviews?.[role]}
            previous={previousReviews?.[role]}
            previousVersion={previousVersion}
          />
        ))}
      </div>
    </section>
  );
}
