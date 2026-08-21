import {
  CheckCircle2,
  CircleDashed,
  LoaderCircle,
  MinusCircle,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import type { NodeStatus, RunStatus } from "../lib/types";
import { isTerminalRunStatus } from "../lib/types";

/**
 * The graph, as a list of stages.
 *
 * The previous version drew this with an absolutely positioned SVG canvas, a
 * gradient overlay, a grid glow and a pulsing hub -- roughly 250 lines of CSS
 * for a pipeline that never branches except at the three parallel reviewers.
 * `group` marks the stages that run at the same time, which is the only
 * structural fact the picture was carrying.
 */
const STAGES = [
  { id: "generator", label: "生成器", caption: "草稿", group: 1 },
  { id: "tech_reviewer", label: "技术", caption: "评审", group: 2 },
  { id: "ux_reviewer", label: "体验", caption: "评审", group: 2 },
  { id: "biz_reviewer", label: "商业", caption: "评审", group: 2 },
  { id: "aggregator", label: "汇总器", caption: "综合分析", group: 3 },
  { id: "optimizer", label: "优化器", caption: "修订", group: 4 },
] as const;

const STATUS_META: Record<
  NodeStatus,
  { icon: LucideIcon; label: string; tone: string }
> = {
  PENDING: { icon: CircleDashed, label: "等待中", tone: "text-ink-faint" },
  RUNNING: { icon: LoaderCircle, label: "运行中", tone: "text-accent" },
  SUCCEEDED: { icon: CheckCircle2, label: "已完成", tone: "text-ok" },
  FAILED: { icon: XCircle, label: "失败", tone: "text-danger" },
  SKIPPED: { icon: MinusCircle, label: "已跳过", tone: "text-ink-faint" },
};

const RUN_LABELS: Record<RunStatus, string> = {
  QUEUED: "等待中",
  GENERATING: "进行中",
  REVIEWING: "进行中",
  AGGREGATING: "进行中",
  OPTIMIZING: "进行中",
  PAUSE_REQUESTED: "暂停中",
  PAUSED: "已暂停",
  CANCEL_REQUESTED: "取消中",
  COMPLETED: "已完成",
  MAX_ITERATIONS_REACHED: "已达上限",
  FAILED: "失败",
  CANCELLED: "已取消",
};

function statusFor(
  statuses: Record<string, NodeStatus>,
  id: string,
): NodeStatus {
  return statuses[id] ?? "PENDING";
}

function WorkflowNode({
  id,
  label,
  caption,
  status,
  groupLabel,
}: {
  id: string;
  label: string;
  caption: string;
  status: NodeStatus;
  /** Set on the first stage of a parallel group; renders above the row. */
  groupLabel: string | null;
}) {
  const meta = STATUS_META[status];
  const StatusIcon = meta.icon;

  return (
    <li
      className="list-none"
      data-node={id}
      data-status={status.toLowerCase()}
      aria-label={`${label}：${meta.label}`}
    >
      {groupLabel === null ? null : (
        <p className="meta-label pb-1 pt-1.5">{groupLabel}</p>
      )}
      <span className="flex min-w-0 items-center gap-2.5 rounded-control border border-line bg-canvas px-3 py-2">
        <StatusIcon
          aria-hidden="true"
          size={15}
          className={`shrink-0 ${meta.tone} ${
            status === "RUNNING" ? "animate-spin" : ""
          }`}
        />
        <span className="min-w-0">
          <strong className="block truncate text-sm font-medium text-ink">
            {label}
          </strong>
          <small className="block truncate text-[11px] text-ink-faint">
            {caption}
          </small>
        </span>
      </span>
    </li>
  );
}

export function WorkflowDiagram({
  statuses,
  runStatus,
}: {
  statuses: Record<string, NodeStatus>;
  runStatus: RunStatus;
}) {
  const completeStatus: NodeStatus = isTerminalRunStatus(runStatus)
    ? runStatus === "FAILED" || runStatus === "CANCELLED"
      ? "FAILED"
      : "SUCCEEDED"
    : "PENDING";

  return (
    <section className="panel" aria-labelledby="workflow-heading">
      <header className="flex items-center justify-between gap-3">
        <h2 id="workflow-heading" className="panel-heading">
          工作流
        </h2>
        <span className="tag">{RUN_LABELS[runStatus]}</span>
      </header>

      <ol className="mt-4 space-y-1.5" aria-label="智能体工作流步骤">
        {STAGES.map((stage, index) => (
          <WorkflowNode
            key={stage.id}
            id={stage.id}
            label={stage.label}
            caption={stage.caption}
            status={statusFor(statuses, stage.id)}
            groupLabel={
              stage.group === 2 && STAGES[index - 1]?.group !== stage.group
                ? "并行评审"
                : null
            }
          />
        ))}
        <WorkflowNode
          id="complete"
          label="完成"
          caption="最终 PRD"
          status={completeStatus}
          groupLabel={null}
        />
      </ol>
    </section>
  );
}
