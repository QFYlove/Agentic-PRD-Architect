import {
  CheckCircle2,
  CircleDashed,
  GitFork,
  LoaderCircle,
  MinusCircle,
  Workflow,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import type { NodeStatus, RunStatus } from "../lib/types";
import { isTerminalRunStatus } from "../lib/types";

const STEPS = [
  ["generator", "生成器", "草稿"],
  ["tech_reviewer", "技术", "评审"],
  ["ux_reviewer", "体验", "评审"],
  ["biz_reviewer", "商业", "评审"],
  ["aggregator", "汇总器", "综合分析"],
  ["optimizer", "优化器", "修订"],
] as const;

const STATUS_META: Record<NodeStatus, { icon: LucideIcon; label: string }> = {
  PENDING: { icon: CircleDashed, label: "等待中" },
  RUNNING: { icon: LoaderCircle, label: "运行中" },
  SUCCEEDED: { icon: CheckCircle2, label: "已完成" },
  FAILED: { icon: XCircle, label: "失败" },
  SKIPPED: { icon: MinusCircle, label: "已跳过" },
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

function edgeIsActive(
  statuses: Record<string, NodeStatus>,
  ...nodeIds: string[]
): boolean {
  return nodeIds.some((id) => statusFor(statuses, id) !== "PENDING");
}

function WorkflowNode({
  id,
  label,
  caption,
  status,
  className,
}: {
  id: string;
  label: string;
  caption: string;
  status: NodeStatus;
  className: string;
}) {
  const meta = STATUS_META[status];
  const StatusIcon = meta.icon;

  return (
    <li
      className={`workflow-node ${className}`}
      data-node={id}
      data-status={status.toLowerCase()}
      aria-label={`${label}：${meta.label}`}
    >
      <span className="workflow-node-icon" aria-hidden="true">
        <StatusIcon
          size={15}
          className={status === "RUNNING" ? "animate-spin" : undefined}
        />
      </span>
      <span className="min-w-0">
        <strong>{label}</strong>
        <small>{caption}</small>
      </span>
      <span className="workflow-status-dot" aria-hidden="true" />
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

  const pathStates = {
    generated: edgeIsActive(
      statuses,
      "generator",
      "tech_reviewer",
      "ux_reviewer",
      "biz_reviewer",
    ),
    reviewing: edgeIsActive(
      statuses,
      "tech_reviewer",
      "ux_reviewer",
      "biz_reviewer",
    ),
    aggregated: edgeIsActive(statuses, "aggregator", "optimizer"),
    optimizing: edgeIsActive(statuses, "optimizer"),
    completed: completeStatus !== "PENDING",
  };

  return (
    <section
      className="panel workflow-panel"
      aria-labelledby="workflow-heading"
    >
      <header className="workflow-header">
        <div className="flex min-w-0 items-center gap-3">
          <span className="workflow-header-icon">
            <Workflow aria-hidden="true" size={17} />
          </span>
          <div>
            <p className="workflow-eyebrow">智能体图谱</p>
            <h2 id="workflow-heading">工作流</h2>
          </div>
        </div>
        <span className="workflow-run-state" data-run-status={runStatus}>
          <span aria-hidden="true" />
          {RUN_LABELS[runStatus]}
        </span>
      </header>

      <div className="workflow-canvas" role="group" aria-label="智能体工作流图">
        <div className="workflow-grid-glow" aria-hidden="true" />
        <svg
          className="workflow-connectors"
          viewBox="0 0 600 510"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <linearGradient
              id="workflow-line-active"
              x1="0"
              y1="0"
              x2="1"
              y2="1"
            >
              <stop offset="0" stopColor="#22d3ee" />
              <stop offset="1" stopColor="#34d399" />
            </linearGradient>
            <marker
              id="workflow-arrow"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="4"
              orient="auto"
            >
              <path d="M0,0 L8,4 L0,8 Z" fill="currentColor" />
            </marker>
          </defs>

          <path
            className="workflow-path"
            data-active={pathStates.generated}
            d="M300 86 L300 118"
          />
          <path
            className="workflow-path"
            data-active={pathStates.reviewing}
            d="M300 160 C300 174 98 166 98 180"
          />
          <path
            className="workflow-path"
            data-active={pathStates.reviewing}
            d="M300 160 L300 180"
          />
          <path
            className="workflow-path"
            data-active={pathStates.reviewing}
            d="M300 160 C300 174 502 166 502 180"
          />
          <path
            className="workflow-path"
            data-active={pathStates.aggregated}
            d="M98 242 C98 270 300 256 300 285"
          />
          <path
            className="workflow-path"
            data-active={pathStates.aggregated}
            d="M300 242 L300 285"
          />
          <path
            className="workflow-path"
            data-active={pathStates.aggregated}
            d="M502 242 C502 270 300 256 300 285"
          />
          <path
            className="workflow-path"
            data-active={pathStates.optimizing}
            d="M300 347 C300 378 150 370 150 400"
          />
          <path
            className="workflow-path"
            data-active={pathStates.completed}
            d="M300 347 C300 378 450 370 450 400"
          />
          <path
            className="workflow-path workflow-path-loop"
            data-active={pathStates.optimizing}
            d="M150 462 C42 462 42 56 210 56"
            markerEnd="url(#workflow-arrow)"
          />
        </svg>

        <div className="workflow-hub" aria-label="并行评审分支">
          <GitFork aria-hidden="true" size={15} />
          <span>并行评审</span>
          <i aria-hidden="true" />
        </div>

        <span className="workflow-branch-label workflow-branch-label-left">
          未达门槛
        </span>
        <span className="workflow-branch-label workflow-branch-label-right">
          达到门槛
        </span>

        <ol className="workflow-node-layer" aria-label="智能体工作流步骤">
          {STEPS.map(([id, label, caption]) => (
            <WorkflowNode
              key={id}
              id={id}
              label={label}
              caption={caption}
              status={statusFor(statuses, id)}
              className={`workflow-node-${id.replaceAll("_", "-")}`}
            />
          ))}
          <WorkflowNode
            id="complete"
            label="完成"
            caption="最终 PRD"
            status={completeStatus}
            className="workflow-node-complete"
          />
        </ol>
      </div>
    </section>
  );
}
