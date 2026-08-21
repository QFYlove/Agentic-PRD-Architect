import type { RunViewState } from "./runReducer";

export interface FailureNotice {
  /** `v3 生成失败` — which version was lost, said plainly. */
  headline: string;
  /** What survived, so the reader does not assume the whole run is gone. */
  detail: string | null;
}

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
    if (draft.complete) {
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

/**
 * What a failed run still has.
 *
 * A generation that dies on iteration 3 leaves v1 and v2, their reviews and their
 * revision plans intact -- but the only thing the reader saw was a red banner,
 * which reads as "the task is gone". This states three facts separately: which
 * version was lost, which ones survived it, and which of those is the best
 * document the run actually produced.
 *
 * 「首版 PRD 生成失败」 is reserved for the case it describes: nothing committed at
 * all. Returns `null` when there is nothing version-specific to say.
 */
export function failureNotice(state: RunViewState): FailureNotice | null {
  if (state.status !== "FAILED") {
    return null;
  }
  if (state.snapshot === null) {
    return null;
  }
  const facts = factsFromState(state);
  // The failure belongs to a version that never landed. If the version the run
  // was on did commit, the run died somewhere after generation and naming it
  // would point at a document that exists.
  if (facts.completedVersions.includes(facts.failedVersion)) {
    return null;
  }
  const kept = facts.completedVersions.filter(
    (version) => version < facts.failedVersion,
  );
  if (kept.length === 0) {
    return { headline: "首版 PRD 生成失败", detail: null };
  }
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
  return {
    headline: `v${facts.failedVersion} 生成失败`,
    detail: best === null ? surviving : `${surviving}${best}`,
  };
}
