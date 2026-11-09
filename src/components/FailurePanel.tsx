import { AlertCircle, RotateCcw } from "lucide-react";

import type { FailureNotice } from "../lib/failureNotice";
import type { RecoveryMode } from "../lib/types";

/**
 * A failed run's four answers in one place: what happened, where, what is still
 * usable, and what to do next. Every action starts a *new* run; the failed one
 * and everything it produced stay exactly as they are.
 */
export function FailurePanel({
  notice,
  busy,
  onRecover,
}: {
  notice: FailureNotice;
  busy: boolean;
  onRecover(mode: RecoveryMode): void;
}) {
  const actions = notice.actions ?? [];
  return (
    <div className="callout-danger" role="alert" data-testid="failure-notice">
      <p className="flex items-center gap-1.5 text-sm font-semibold text-danger">
        <AlertCircle aria-hidden="true" size={15} className="shrink-0" />
        <span className="min-w-0">{notice.headline}</span>
      </p>
      <dl className="mt-2 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[6rem_1fr]">
        {notice.reason && (
          <>
            <dt className="text-ink-faint">发生了什么</dt>
            <dd className="text-ink" data-testid="failure-notice-reason">
              {notice.reason}
            </dd>
          </>
        )}
        {notice.stageLabel && (
          <>
            <dt className="text-ink-faint">失败步骤</dt>
            <dd className="text-ink" data-testid="failure-notice-stage">
              {notice.stageLabel}
            </dd>
          </>
        )}
        <dt className="text-ink-faint">仍可使用</dt>
        <dd
          className="text-ink"
          {...(notice.detail !== null
            ? { "data-testid": "failure-notice-detail" }
            : {})}
        >
          {notice.detail ?? "没有已完成的版本。"}
          {notice.draftCharacters ? (
            <span className="text-ink-muted">
              {" "}
              中断的草稿（{notice.draftCharacters.toLocaleString()}{" "}
              字）可在版本栏查看，但不会作为正式版本下载或评分。
            </span>
          ) : null}
        </dd>
        <dt className="text-ink-faint">下一步</dt>
        <dd className="text-ink-muted">
          {notice.guidance ??
            (actions.length > 0
              ? "以下操作会新建一个任务，当前任务和已有结果保持不变。"
              : "可以新建任务重新开始。")}
        </dd>
      </dl>
      {actions.length > 0 && (
        <div
          className="mt-3 flex flex-wrap gap-2"
          data-testid="failure-actions"
        >
          {actions.map((action) => (
            <button
              key={action.mode}
              type="button"
              className={action.primary ? "button-primary" : "button-secondary"}
              title={action.hint}
              disabled={busy}
              data-testid={`recover-${action.mode}`}
              onClick={() => onRecover(action.mode)}
            >
              <RotateCcw aria-hidden="true" size={14} />
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
