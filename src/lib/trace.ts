import type { RunEvent } from "./types";

export interface TraceItem {
  sequence: number;
  label: string;
  detail: string;
  tone: "neutral" | "active" | "success" | "warning" | "error";
}

const NODE_LABELS: Record<string, string> = {
  generator: "生成器",
  tech_reviewer: "技术评审",
  ux_reviewer: "体验评审",
  biz_reviewer: "商业评审",
  aggregator: "汇总器",
  optimizer: "优化器",
};

const REVIEW_ROLE_LABELS: Record<string, string> = {
  tech: "技术",
  ux: "体验",
  biz: "商业",
};

function text(value: unknown, fallback: string): string {
  return typeof value === "string" ? value.slice(0, 500) : fallback;
}

export function toTraceItem(event: RunEvent): TraceItem | null {
  const payload = event.payload;
  switch (event.event) {
    case "run_started":
      return {
        sequence: event.sequence,
        label: "任务已启动",
        detail: `第 ${event.iteration} 轮迭代已进入工作流。`,
        tone: "active",
      };
    case "node_started": {
      const node = text(payload.node, "workflow_node");
      return {
        sequence: event.sequence,
        label: NODE_LABELS[node] ?? "工作流节点",
        detail: "已开始处理。",
        tone: "active",
      };
    }
    case "prd_generated":
      return {
        sequence: event.sequence,
        label: `PRD v${event.iteration}`,
        detail: "本轮生成已完成。",
        tone: "success",
      };
    case "review_completed": {
      const role = text(payload.role, "reviewer").toLowerCase();
      const roleLabel = REVIEW_ROLE_LABELS[role] ?? "独立";
      // Only the count is projected, never the finding text: the trace is a
      // running log, and reviewer prose belongs to the review panel. The tally
      // separates blockers from advice, because "3 条反馈" alone is what made a
      // finished run look unfinished.
      const feedback = Array.isArray(payload.feedback) ? payload.feedback : [];
      const blocking = feedback.filter(
        (item) =>
          typeof item === "object" &&
          item !== null &&
          (item as { severity?: unknown }).severity === "must_fix",
      ).length;
      const detail =
        blocking > 0
          ? `第 ${event.iteration} 轮评审完成 · ${feedback.length} 条反馈（${blocking} 项必须修复）。`
          : `第 ${event.iteration} 轮评审完成 · ${feedback.length} 条反馈。`;
      return {
        sequence: event.sequence,
        label: `${roleLabel}评审`,
        detail,
        tone: "success",
      };
    }
    case "scores_updated":
      return {
        sequence: event.sequence,
        label: "评分已汇总",
        detail: `综合评分：${typeof payload.overall === "number" ? payload.overall : "—"}。`,
        tone: "success",
      };
    case "revision_planned":
      return {
        sequence: event.sequence,
        label: "优化方案已生成",
        detail: "结构化改进项已准备好，可进入下一轮迭代。",
        tone: "neutral",
      };
    case "pause_requested":
      return {
        sequence: event.sequence,
        label: "已请求暂停",
        detail: "当前安全步骤完成后将暂停工作流。",
        tone: "warning",
      };
    case "run_paused":
      return {
        sequence: event.sequence,
        label: "任务已暂停",
        detail: "可以补充新的优化要求后继续。",
        tone: "warning",
      };
    case "run_resumed":
      return {
        sequence: event.sequence,
        label: "任务已继续",
        detail: "工作流正从安全断点继续执行。",
        tone: "active",
      };
    case "run_cancelled":
      return {
        sequence: event.sequence,
        label: "任务已取消",
        detail: "系统不会再接收后续工作流结果。",
        tone: "warning",
      };
    case "run_completed":
      return {
        sequence: event.sequence,
        label: "质量门禁已通过",
        detail: "评分达到目标，且没有必须修复的问题。",
        tone: "success",
      };
    case "max_iterations_reached": {
      const blocking =
        typeof payload.must_fix_count === "number" ? payload.must_fix_count : 0;
      return {
        sequence: event.sequence,
        label: "已达迭代上限",
        detail:
          blocking > 0
            ? `迭代预算已用尽，仍有 ${blocking} 项必须修复问题未解决。`
            : "当前质量最高的 PRD 已准备好。",
        tone: "warning",
      };
    }
    case "run_failed":
      return {
        sequence: event.sequence,
        label: "任务运行失败",
        detail: "工作流未能完成，请查看页面错误提示。",
        tone: "error",
      };
    default:
      return null;
  }
}
