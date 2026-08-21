import type { RunOutcome } from "./runReducer";

/**
 * Thresholds are user-entered, so 85 must not render as "85.0" while 71.5 keeps
 * its decimal.
 */
function formatThreshold(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/**
 * Which of the three real endings a run reached.
 *
 * `blocked` is the one the product used to hide: the score target was reached,
 * so the run looks successful, but a reviewer still flagged something that stops
 * the document from being buildable. Presenting that as "quality goal complete"
 * is the specific dishonesty this type exists to prevent.
 */
export type OutcomeTone = "passed" | "blocked" | "unmet";

export interface OutcomeFact {
  label: string;
  value: string;
}

export interface OutcomeSummary {
  tone: OutcomeTone;
  headline: string;
  facts: OutcomeFact[];
  /** Why the run stopped here, when that is not implied by the headline. */
  note: string | null;
}

function tone(outcome: RunOutcome): OutcomeTone {
  if (outcome.qualityGatePassed) {
    return "passed";
  }
  return outcome.thresholdMet ? "blocked" : "unmet";
}

const HEADLINES: Record<OutcomeTone, string> = {
  passed: "已达到目标质量",
  blocked: "已达到评分目标，但质量门禁未通过",
  unmet: "未达到目标评分",
};

/**
 * The structured close of a scored run.
 *
 * Two independent facts drive it: whether the score cleared the target, and
 * whether any blocking finding is still open. They are reported separately
 * because either one alone misleads -- a passing score can hide a blocker, and
 * an open blocker does not erase the score that was reached.
 */
export function summarizeOutcome(outcome: RunOutcome): OutcomeSummary {
  const kind = tone(outcome);
  const facts: OutcomeFact[] = [
    { label: "目标评分", value: formatThreshold(outcome.qualityThreshold) },
  ];
  if (outcome.bestVersion !== null && outcome.bestScore !== null) {
    facts.push({
      label: "最佳版本",
      value: `v${outcome.bestVersion} · ${outcome.bestScore.toFixed(1)}`,
    });
  }
  facts.push({
    label: "已完成迭代",
    value: `${outcome.completedIterations}/${outcome.maxIterations} 轮`,
  });
  facts.push(
    { label: "必须修复", value: String(outcome.severity.mustFix) },
    { label: "重要改进", value: String(outcome.severity.shouldFix) },
    { label: "可选优化", value: String(outcome.severity.optional) },
  );

  let note: string | null = null;
  if (kind === "blocked") {
    // The blocker count is the reason the gate held, and the exhausted budget is
    // the reason the run stopped anyway. Both have to be said, or the reader is
    // left asking why the system did not simply keep going.
    note =
      outcome.severity.mustFix > 0
        ? `剩余 ${outcome.severity.mustFix} 项必须修复问题 · 已达到最大迭代次数`
        : "已达到最大迭代次数";
  } else if (kind === "unmet") {
    note = "迭代预算已用尽";
  } else if (outcome.severity.shouldFix + outcome.severity.optional > 0) {
    note = "剩余条目为改进建议，不阻塞交付";
  }

  return {
    tone: kind,
    headline: HEADLINES[kind],
    facts,
    note,
  };
}

/**
 * The same summary as one line, for the live region and any single-line slot.
 */
export function outcomeSummary(outcome: RunOutcome): string {
  const summary = summarizeOutcome(outcome);
  return [
    summary.headline,
    ...summary.facts.map((fact) => `${fact.label} ${fact.value}`),
  ].join(" · ");
}
