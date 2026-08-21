import { AlertTriangle, CheckCircle2, CircleSlash } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { summarizeOutcome, type OutcomeTone } from "../lib/outcomeSummary";
import type { RunOutcome } from "../lib/runReducer";

const TONE_META: Record<
  OutcomeTone,
  { icon: LucideIcon; accent: string; rule: string }
> = {
  passed: { icon: CheckCircle2, accent: "text-ok", rule: "border-l-ok" },
  blocked: {
    icon: AlertTriangle,
    accent: "text-warn",
    rule: "border-l-warn",
  },
  unmet: {
    icon: CircleSlash,
    accent: "text-ink-muted",
    rule: "border-l-line-strong",
  },
};

/**
 * How the run ended, stated once, at the top.
 *
 * The three tones are three genuinely different endings and the copy has to keep
 * them apart. In particular a run that cleared its score target while a blocking
 * finding stayed open is neither a success nor a failure, and the previous
 * summary presented it as the former -- which is what made a reader ask why the
 * system stopped while three reviewers still listed work.
 */
export function OutcomePanel({ outcome }: { outcome: RunOutcome }) {
  const summary = summarizeOutcome(outcome);
  const meta = TONE_META[summary.tone];
  const Icon = meta.icon;

  return (
    <div
      className={`border-l-2 pl-3 ${meta.rule}`}
      data-testid="run-outcome"
      data-tone={summary.tone}
    >
      <p
        className={`flex items-center gap-1.5 text-sm font-semibold ${meta.accent}`}
      >
        <Icon aria-hidden="true" size={15} className="shrink-0" />
        <span className="min-w-0">{summary.headline}</span>
      </p>
      {summary.note !== null && (
        <p
          className="mt-1 text-xs leading-5 text-ink-muted"
          data-testid="run-outcome-note"
        >
          {summary.note}
        </p>
      )}
      <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {summary.facts.map((fact) => (
          <div key={fact.label} className="flex items-baseline gap-1.5">
            <dt className="meta-label">{fact.label}</dt>
            <dd
              className="text-xs font-medium text-ink"
              data-testid={`outcome-fact-${fact.label}`}
            >
              {fact.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
