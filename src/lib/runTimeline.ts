import type { RunViewState } from "./runReducer";
import { isUsableDraft } from "./runReducer";
import type { NodeTiming, ReviewRole } from "./types";
import { isTerminalRunStatus } from "./types";

export type StageState = "done" | "running" | "failed" | "pending" | "skipped";

export interface TimelineStage {
  key: "generation" | "review" | "aggregation" | "revision_planning";
  label: string;
  state: StageState;
  /** One line on what the stage produced, in the reader's terms. */
  result: string | null;
  seconds: number | null;
}

export interface TimelineVersion {
  version: number;
  stages: TimelineStage[];
}

export interface RunTimelineModel {
  versions: TimelineVersion[];
  elapsedSeconds: number;
  usableVersions: number[];
  bestVersion: number | null;
  /** The final check: whether the run ended passed, held, capped, or failed. */
  finalState: StageState;
  finalResult: string | null;
}

const ROLE_LABELS: Record<ReviewRole, string> = {
  tech: "技术",
  ux: "体验",
  biz: "商业",
};

const STAGE_FOR_NODE: Record<string, TimelineStage["key"]> = {
  generator: "generation",
  tech_reviewer: "review",
  ux_reviewer: "review",
  biz_reviewer: "review",
  aggregator: "aggregation",
  optimizer: "revision_planning",
};

const GATE_LABELS: Record<string, string> = {
  PASSED: "质量门槛通过",
  NEEDS_REVISION: "需要修订",
  BLOCKED: "存在硬约束问题",
  UNSCORED: "未评分",
};

function timings(value: unknown): NodeTiming[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is NodeTiming =>
          typeof item === "object" &&
          item !== null &&
          typeof (item as NodeTiming).node === "string" &&
          typeof (item as NodeTiming).version === "number" &&
          typeof (item as NodeTiming).seconds === "number",
      )
    : [];
}

function sumSeconds(rows: NodeTiming[]): number | null {
  return rows.length > 0
    ? Math.round(rows.reduce((total, row) => total + row.seconds, 0) * 10) / 10
    : null;
}

function maxSeconds(rows: NodeTiming[]): number | null {
  return rows.length > 0 ? Math.max(...rows.map((row) => row.seconds)) : null;
}

/**
 * What the run did, version by version, built only from durable state.
 *
 * The run record used to be the raw event stream, which is empty for any run
 * opened after it finished and lists "已开始处理" thirty times for one that is
 * live. Every fact here comes from the snapshot and the reducer's per-version
 * maps, so a reopened run reads the same as a live one, and no stage is shown
 * that the workflow did not actually reach.
 */
export function buildRunTimeline(state: RunViewState): RunTimelineModel | null {
  const snapshot = state.snapshot;
  if (snapshot === null || state.status === null) {
    return null;
  }
  const status = state.status;
  const terminal = isTerminalRunStatus(status);
  const error = state.runError ?? snapshot.error ?? null;
  const failedStage =
    status === "FAILED"
      ? (error?.stage ??
        (error?.node ? (STAGE_FOR_NODE[error.node] ?? null) : null) ??
        "generation")
      : null;
  const failedVersion =
    status === "FAILED" ? (error?.version ?? snapshot.current_iteration) : null;
  const rows = timings(snapshot.node_timings);
  const versionNumbers = new Set<number>([
    ...Object.keys(state.drafts).map(Number),
    snapshot.current_iteration,
  ]);
  if (!terminal || status === "FAILED") {
    versionNumbers.add(snapshot.current_iteration);
  }
  const ordered = [...versionNumbers].sort((a, b) => a - b);
  const lastVersion = ordered.at(-1) ?? 1;

  const versions: TimelineVersion[] = ordered.map((version) => {
    const draft = state.drafts[version];
    const usable = isUsableDraft(draft);
    const reviews = state.reviewsByVersion[version] ?? {};
    const score = state.scoresByVersion[version];
    const findings = state.findingsByVersion[version];
    const plan = state.revisionPlansBySourceVersion[version];
    const isCurrent = version === lastVersion;
    const failedHere = (key: TimelineStage["key"]) =>
      failedVersion === version && failedStage === key;
    const running = (key: TimelineStage["key"]) => {
      if (!isCurrent || terminal) {
        return false;
      }
      return (
        (key === "generation" && status === "GENERATING") ||
        (key === "review" && status === "REVIEWING") ||
        (key === "aggregation" && status === "AGGREGATING") ||
        (key === "revision_planning" && status === "OPTIMIZING")
      );
    };
    const stateOf = (key: TimelineStage["key"], done: boolean): StageState =>
      done
        ? "done"
        : failedHere(key)
          ? "failed"
          : running(key)
            ? "running"
            : terminal
              ? "skipped"
              : "pending";

    const generatorRows = rows.filter(
      (row) => row.node === "generator" && row.version === version,
    );
    const failedAttempts = generatorRows.filter((row) => !row.succeeded).length;
    const generation: TimelineStage = {
      key: "generation",
      label:
        version === 1 && !snapshot.source_version
          ? "PRD 生成"
          : `生成 v${version}`,
      state: stateOf("generation", usable),
      result: usable
        ? `v${version} 已完成${
            state.qualityByVersion[version]
              ? ` · ${state.qualityByVersion[version]!.characters.toLocaleString()} 字`
              : ""
          }${failedAttempts > 0 ? ` · 重试 ${failedAttempts} 次` : ""}`
        : draft?.interrupted
          ? `生成中断，已输出 ${draft.content.length.toLocaleString()} 字，未成为正式版本`
          : null,
      seconds: sumSeconds(generatorRows),
    };

    const roles = (["tech", "ux", "biz"] as const).filter(
      (role) => reviews[role],
    );
    const review: TimelineStage = {
      key: "review",
      label: "技术 / 体验 / 商业评审",
      state: stateOf("review", roles.length === 3 || Boolean(score)),
      result:
        roles.length > 0
          ? roles
              .map((role) => `${ROLE_LABELS[role]} ${reviews[role]!.score}`)
              .join(" · ")
          : null,
      seconds: maxSeconds(
        rows.filter(
          (row) => row.version === version && row.node.endsWith("_reviewer"),
        ),
      ),
    };

    const aggregation: TimelineStage = {
      key: "aggregation",
      label: "评审意见聚合与评分",
      state: stateOf("aggregation", Boolean(score)),
      result: score
        ? [
            `综合 ${score.overall}`,
            findings && findings.beforeDedup !== null
              ? `${findings.beforeDedup} 条意见合并为 ${findings.combined.length} 条`
              : null,
            score.severity.mustFix > 0
              ? `必须修复 ${score.severity.mustFix}`
              : null,
            findings?.gateStatus ? GATE_LABELS[findings.gateStatus] : null,
          ]
            .filter(Boolean)
            .join(" · ")
        : null,
      seconds: null,
    };

    const planned = Boolean(plan);
    const planStage: TimelineStage = {
      key: "revision_planning",
      label: "修订计划",
      state: planned
        ? "done"
        : failedHere("revision_planning")
          ? "failed"
          : running("revision_planning")
            ? "running"
            : score && terminal && status !== "FAILED"
              ? "skipped"
              : terminal
                ? "skipped"
                : "pending",
      result: planned
        ? `${plan!.plan.items.length} 项修改，用于生成 v${plan!.targetVersion}`
        : score && terminal && status !== "FAILED"
          ? "已结束，无需继续修订"
          : null,
      seconds: sumSeconds(
        rows.filter(
          (row) => row.node === "optimizer" && row.version === version,
        ),
      ),
    };

    return { version, stages: [generation, review, aggregation, planStage] };
  });

  const usableVersions = Object.values(state.drafts)
    .filter((draft) => isUsableDraft(draft))
    .map((draft) => draft.version)
    .sort((a, b) => a - b);
  let finalState: StageState = "pending";
  let finalResult: string | null = null;
  if (status === "COMPLETED") {
    finalState = "done";
    finalResult = "质量门槛通过：评分达到目标，且没有必须修复的问题。";
  } else if (status === "MAX_ITERATIONS_REACHED") {
    finalState = "done";
    finalResult =
      state.outcome && state.outcome.severity.mustFix > 0
        ? `迭代次数用完，仍有 ${state.outcome.severity.mustFix} 项必须修复问题。`
        : "迭代次数用完，未达到目标评分。";
  } else if (status === "FAILED") {
    finalState = "failed";
    finalResult = "任务失败，未完成最终质量检查。";
  } else if (status === "CANCELLED") {
    finalState = "skipped";
    finalResult = "任务已取消。";
  }
  return {
    versions,
    elapsedSeconds: snapshot.elapsed_seconds,
    usableVersions,
    bestVersion: state.bestVersion,
    finalState,
    finalResult,
  };
}
