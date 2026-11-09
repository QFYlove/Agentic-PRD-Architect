import { localizedErrorMessage } from "./errorMessages";
import { isUsableDraft, type RunViewState } from "./runReducer";
import type { RecoveryAction, RecoveryMode, RunError } from "./types";

/** One thing the reader can do about a failed run, with the words for it. */
export interface FailureAction {
  mode: RecoveryMode;
  label: string;
  hint: string;
  primary: boolean;
}

/**
 * The four questions a failure screen has to answer, as data.
 *
 * What happened (`reason`), where (`stageLabel`), what is still usable (`detail`),
 * and what to do next (`actions`, `guidance`). The old notice answered only the
 * third, and the reason lived in a dismissible banner.
 */
export interface FailureNotice {
  /** `v3 生成失败` — which version was lost, said plainly. */
  headline: string;
  /** What survived, so the reader does not assume the whole run is gone. */
  detail: string | null;
  reason?: string;
  stageLabel?: string | null;
  /** True when the same request may succeed later (transient cause). */
  retryable?: boolean;
  /** Recovery runs the reader can start. Each creates a new run. */
  actions?: FailureAction[];
  /** One sentence for causes no button can fix (keys, quota, content). */
  guidance?: string | null;
  /** Characters the interrupted draft reached, when there is one. */
  draftCharacters?: number | null;
}

const STAGE_LABELS: Record<string, string> = {
  generation: "PRD 生成",
  review: "三方评审",
  aggregation: "评审汇总",
  revision_planning: "修订计划",
};

const NODE_LABELS: Record<string, string> = {
  generator: "生成器",
  tech_reviewer: "技术评审",
  ux_reviewer: "体验评审",
  biz_reviewer: "商业评审",
  aggregator: "汇总器",
  optimizer: "优化器",
};

const NODE_STAGES: Record<string, string> = {
  generator: "generation",
  tech_reviewer: "review",
  ux_reviewer: "review",
  biz_reviewer: "review",
  aggregator: "aggregation",
  optimizer: "revision_planning",
};

const GUIDANCE: Partial<Record<RecoveryAction, string>> = {
  check_configuration:
    "这是配置或账号问题，重试不会成功。请检查 API Key、模型名称或账户余额后再新建任务。",
  edit_input: "模型拒绝了本次内容，请调整需求描述后新建任务。",
};

/**
 * Everything the notice needs, gathered from one place.
 *
 * These facts are read from the live view state rather than from the snapshot
 * alone, because the snapshot a client holds is the one it fetched when it opened
 * the run: a page that watched v1 and v2 arrive as events still has
 * `versions: []` and `current_iteration: 1` on that snapshot. Deriving the
 * failing version from it is what made a run that lost v3 report
 * 「首版 PRD 生成失败」 with two finished documents on screen.
 */
interface FailureFacts {
  completedVersions: number[];
  failedVersion: number;
  reviewedVersions: number[];
  hasRevisionPlan: boolean;
  bestVersion: number | null;
  bestScore: number | null;
}

function factsFromState(state: RunViewState): FailureFacts {
  const snapshot = state.snapshot;
  const drafts = Object.values(state.drafts);
  const completed = new Set<number>(
    snapshot?.versions.map((version) => version.version) ?? [],
  );
  for (const draft of drafts) {
    if (isUsableDraft(draft)) {
      completed.add(draft.version);
    }
  }
  const reviewed = new Set<number>(
    Object.keys(state.reviewsByVersion).map(Number),
  );
  for (const version of snapshot?.versions ?? []) {
    if (version.evaluation) {
      reviewed.add(version.version);
    }
  }
  // The version the run died on is the newest one it was known to be working on:
  // the iteration on the snapshot, the iteration a draft had started streaming,
  // or the one a committed version already reached.
  const known = [
    snapshot?.current_iteration ?? 1,
    ...drafts.map((draft) => draft.version),
    ...completed,
  ];
  return {
    completedVersions: [...completed].sort((a, b) => a - b),
    failedVersion: Math.max(...known),
    reviewedVersions: [...reviewed],
    hasRevisionPlan:
      state.pendingRevisionPlan !== null ||
      Object.keys(state.revisionPlansBySourceVersion).length > 0 ||
      (snapshot?.versions.some((version) => version.revision_plan) ?? false),
    bestVersion: state.bestVersion,
    bestScore: state.bestScore,
  };
}

function survivorsText(facts: FailureFacts, kept: number[]): string {
  const survivors = kept.map((version) => `v${version}`).join("、");
  const hasReviews = kept.some((version) =>
    facts.reviewedVersions.includes(version),
  );
  const surviving =
    hasReviews && facts.hasRevisionPlan
      ? `${survivors} 及已有评审和修订计划已保留。`
      : hasReviews
        ? `${survivors} 及已有评审已保留。`
        : facts.hasRevisionPlan
          ? `${survivors} 及已有修订计划已保留。`
          : `${survivors} 已保留。`;
  // Which of the survivors to actually read. A failed run's newest version is
  // frequently not its best one, and after losing a generation that is the single
  // most useful thing left to say.
  const best =
    facts.bestVersion !== null &&
    facts.bestScore !== null &&
    kept.includes(facts.bestVersion)
      ? `最佳可用版本：v${facts.bestVersion} · ${facts.bestScore.toFixed(1)}`
      : null;
  return best === null ? surviving : `${surviving}${best}`;
}

/**
 * The recovery buttons for a cause.
 *
 * A truncation offers the compact regeneration first -- run 9fa59292 showed the
 * same request cannot succeed twice. Configuration and content problems offer
 * nothing a button could fix; they get a sentence instead.
 */
function actionsFor(
  error: RunError | null,
  hasVersion: boolean,
): FailureAction[] {
  const action = error?.recovery_action ?? null;
  if (action === "check_configuration" || action === "edit_input") {
    return [];
  }
  const actions: FailureAction[] = [];
  if (hasVersion) {
    actions.push({
      mode: "continue_from_best",
      label: "从最佳版本继续（精简模式）",
      hint: "新建一个任务，以最佳版本为底稿继续修订，原任务保留不变。",
      primary: action === "continue_from_best" || action === null,
    });
  }
  const truncated =
    error?.code === "PROVIDER_OUTPUT_TRUNCATED" ||
    error?.category === "output_limit";
  actions.push({
    mode: "regenerate_compact",
    label: "使用精简模式重新生成",
    hint: "新建一个任务，用较短的篇幅预算从头生成，原任务保留不变。",
    primary: !hasVersion && (truncated || action === "regenerate_compact"),
  });
  if (error?.retryable !== false && !truncated) {
    actions.push({
      mode: "restart",
      label: "以相同设置重新运行",
      hint: "新建一个任务，使用原始需求和设置从头运行。",
      primary: !hasVersion && !truncated,
    });
  }
  if (!actions.some((item) => item.primary) && actions[0]) {
    actions[0] = { ...actions[0], primary: true };
  }
  return actions;
}

/**
 * What a failed run still has, why it failed, and what to do next.
 *
 * 「首版 PRD 生成失败」 is reserved for the case it describes: nothing committed at
 * all. Returns `null` for a run that has not failed.
 */
export function failureNotice(state: RunViewState): FailureNotice | null {
  if (state.status !== "FAILED") {
    return null;
  }
  if (state.snapshot === null) {
    return null;
  }
  const facts = factsFromState(state);
  const error = state.runError ?? state.snapshot.error ?? null;
  const node = error?.node ?? null;
  const stage =
    error?.stage ?? (node !== null ? (NODE_STAGES[node] ?? null) : null);
  const stageLabel =
    stage !== null
      ? `${STAGE_LABELS[stage] ?? stage}${
          node !== null && NODE_LABELS[node] && stage === "review"
            ? ` · ${NODE_LABELS[node]}`
            : ""
        }`
      : null;
  const failedVersion = error?.version ?? facts.failedVersion;
  const generationFailed =
    stage === "generation" ||
    (stage === null && !facts.completedVersions.includes(failedVersion));
  const kept = facts.completedVersions.filter((version) =>
    generationFailed ? version < failedVersion : version <= failedVersion,
  );
  const draft = Object.values(state.drafts).find(
    (item) => item.interrupted && item.version === failedVersion,
  );
  const common = {
    reason: localizedErrorMessage(error?.code),
    stageLabel,
    retryable: error?.retryable ?? false,
    actions: actionsFor(error, kept.length > 0),
    guidance: error?.recovery_action
      ? (GUIDANCE[error.recovery_action] ?? null)
      : null,
    draftCharacters: draft ? draft.content.length : null,
  };
  if (generationFailed) {
    if (kept.length === 0) {
      return { headline: "首版 PRD 生成失败", detail: null, ...common };
    }
    return {
      headline: `v${failedVersion} 生成失败`,
      detail: survivorsText(facts, kept),
      ...common,
    };
  }
  const stageName =
    stage !== null ? (STAGE_LABELS[stage] ?? "后续步骤") : "后续步骤";
  return {
    headline: `v${failedVersion} 的${stageName}失败`,
    detail: kept.length > 0 ? survivorsText(facts, kept) : null,
    ...common,
  };
}
