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

/**
 * The run's state as one short word.
 *
 * This is one of the three places the pill shape survives: it reads as a state,
 * not as a container. The tone is carried by the text colour on a neutral
 * surface rather than by a filled coloured chip -- four filled pills of four
 * different hues was most of what made the header look like a status dashboard.
 */
export function StatusBadge({ status }: { status: RunStatus }) {
  const terminal = ["COMPLETED", "MAX_ITERATIONS_REACHED"].includes(status);
  const danger = ["FAILED", "CANCELLED"].includes(status);
  const waiting = ["PAUSE_REQUESTED", "PAUSED", "CANCEL_REQUESTED"].includes(
    status,
  );
  return (
    <span
      data-testid="run-status"
      className={`tag ${
        terminal
          ? "text-ok"
          : danger
            ? "text-danger"
            : waiting
              ? "text-warn"
              : "text-accent"
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
