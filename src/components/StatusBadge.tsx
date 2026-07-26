import type { RunStatus } from "../lib/types";

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  QUEUED: "等待中",
  GENERATING: "生成中",
  REVIEWING: "评审中",
  AGGREGATING: "汇总中",
  OPTIMIZING: "优化中",
  PAUSE_REQUESTED: "安全暂停中",
  PAUSED: "已暂停",
  CANCEL_REQUESTED: "取消中",
  COMPLETED: "已完成",
  MAX_ITERATIONS_REACHED: "已达迭代上限",
  CANCELLED: "已取消",
  FAILED: "运行失败",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  const terminal = ["COMPLETED", "MAX_ITERATIONS_REACHED"].includes(status);
  const danger = ["FAILED", "CANCELLED"].includes(status);
  const waiting = ["PAUSE_REQUESTED", "PAUSED", "CANCEL_REQUESTED"].includes(
    status,
  );
  return (
    <span
      data-testid="run-status"
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${
        terminal
          ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200"
          : danger
            ? "border-rose-400/25 bg-rose-400/10 text-rose-200"
            : waiting
              ? "border-amber-400/25 bg-amber-400/10 text-amber-200"
              : "border-cyan-400/25 bg-cyan-400/10 text-cyan-200"
      }`}
    >
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 rounded-full bg-current"
      />
      {RUN_STATUS_LABELS[status]}
    </span>
  );
}
