import { AlertCircle, Boxes, RefreshCw } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";

import { useAgentRun, type UseAgentRunOptions } from "../hooks/useAgentRun";
import { useProviderCatalog } from "../hooks/useProviderCatalog";
import { failureNotice } from "../lib/failureNotice";
import { outcomeSummary } from "../lib/outcomeSummary";
import { locateSection, parseOutline } from "../lib/prdOutline";
import {
  isUsableDraft,
  type ConnectionStatus,
  type VersionScore,
} from "../lib/runReducer";
import { isTerminalRunStatus } from "../lib/types";
import { ConversationSidebar } from "./ConversationSidebar";
import { FailurePanel } from "./FailurePanel";
import { OutcomePanel } from "./OutcomePanel";
import { ProductIdeaForm } from "./ProductIdeaForm";
import { scrollToHeading } from "./PRDViewer";
import { RevisionPlanPanel } from "./RevisionPlanPanel";
import { FindingsSidebar, ReviewPanel } from "./ReviewPanel";
import { RunControls } from "./RunControls";
import { RunRequest } from "./RunRequest";
import { RunTimeline } from "./RunTimeline";
import { RUN_STATUS_LABELS, StatusBadge } from "./StatusBadge";
import { VersionRail } from "./VersionRail";
import { WorkspaceTabs, type WorkspaceTab } from "./WorkspaceTabs";

const PRDViewer = lazy(() =>
  import("./PRDViewer").then((module) => ({ default: module.PRDViewer })),
);
const VersionDiff = lazy(() =>
  import("./VersionDiff").then((module) => ({ default: module.VersionDiff })),
);

const CONNECTION_LABELS: Record<ConnectionStatus, string> = {
  idle: "未连接",
  connecting: "连接中",
  open: "已连接",
  recovering: "恢复中",
  closed: "已关闭",
};

function ModuleFallback({ label }: { label: string }) {
  return (
    <div className="panel min-h-40 animate-pulse" role="status">
      <p className="text-sm text-ink-muted">正在加载{label}…</p>
    </div>
  );
}
/**
 * The version immediately before `version` among the versions that exist.
 *
 * The comparison tab reads the selected version against its predecessor, and
 * "predecessor" has to mean the previous *existing* version rather than
 * `version - 1`: a run whose first generation was retried can be missing one.
 */
function previousVersionOf(
  versions: number[],
  version: number | null,
): number | null {
  if (version === null) {
    return null;
  }
  const earlier = versions.filter((candidate) => candidate < version);
  return earlier.at(-1) ?? null;
}

/**
 * Only finished versions can be compared; a streaming or interrupted draft has
 * no final text.
 */
function comparableContent(
  draft: Parameters<typeof isUsableDraft>[0],
): string | null {
  return draft && isUsableDraft(draft) ? draft.content : null;
}

function scoreBadge(score: VersionScore | undefined): string | undefined {
  return score ? String(score.overall) : undefined;
}
export function AgentDashboard({
  api,
  eventSourceFactory,
}: UseAgentRunOptions) {
  const controller = useAgentRun({
    ...(api ? { api } : {}),
    ...(eventSourceFactory ? { eventSourceFactory } : {}),
  });
  const { state } = controller;
  const snapshot = state.snapshot;
  const catalog = useProviderCatalog(api ?? undefined);
  const [requestedTab, setRequestedTab] = useState("prd");
  /** A heading to scroll to once the PRD tab has rendered. */
  const [pendingHeading, setPendingHeading] = useState<string | null>(null);
  useEffect(() => {
    if (pendingHeading !== null && requestedTab === "prd") {
      scrollToHeading(pendingHeading);
      setPendingHeading(null);
    }
  }, [pendingHeading, requestedTab]);

  const versions = Object.keys(state.drafts)
    .map(Number)
    .sort((a, b) => a - b);
  const selected = state.selectedVersion;
  const draft = selected === null ? null : (state.drafts[selected] ?? null);
  const score = selected === null ? undefined : state.scoresByVersion[selected];
  const reviews =
    selected === null ? undefined : state.reviewsByVersion[selected];
  const plan =
    selected === null
      ? undefined
      : state.revisionPlansBySourceVersion[selected];
  const finished = versions.filter((version) =>
    isUsableDraft(state.drafts[version]),
  );
  const previous = previousVersionOf(finished, selected);
  const findings =
    selected === null ? undefined : state.findingsByVersion[selected];
  const quality =
    selected === null ? undefined : state.qualityByVersion[selected];
  const nextVersion = plan === undefined ? undefined : plan.targetVersion;
  const nextResolutions =
    nextVersion === undefined
      ? []
      : (state.findingsByVersion[nextVersion]?.resolutions ?? []);
  function locate(section: string): void {
    if (!draft || !isUsableDraft(draft)) {
      return;
    }
    const heading = locateSection(parseOutline(draft.content), section);
    setRequestedTab("prd");
    setPendingHeading(heading?.id ?? null);
  }
  const previousReviews =
    previous === null ? undefined : state.reviewsByVersion[previous];
  const sourceContent =
    previous === null ? null : comparableContent(state.drafts[previous]);
  const targetContent = comparableContent(draft ?? undefined);
  const comparable =
    previous !== null &&
    selected !== null &&
    sourceContent !== null &&
    targetContent !== null;
  const reviewCount = score
    ? score.severity.mustFix +
      score.severity.shouldFix +
      score.severity.optional
    : 0;
  // A failed run still holds every version it committed. Naming the version that
  // died, and what survived it, is the difference between "v3 生成失败" and the
  // reader concluding the whole task was lost.
  const failure = failureNotice(state);

  /*
   * The document is the first tab and the only one that is never disabled.
   *
   * Everything the run produces is still here, but the workflow diagram, the
   * event trace and the telemetry grid now share one 运行记录 tab instead of
   * standing beside the PRD -- they are how the run was produced, not what it
   * produced.
   */
  const tabs: WorkspaceTab[] = snapshot
    ? [
        {
          id: "prd",
          label: "PRD",
          badge: scoreBadge(score),
          panel: (
            <Suspense fallback={<ModuleFallback label="PRD 文档" />}>
              <PRDViewer
                runId={snapshot.run_id}
                draft={draft}
                score={score}
                quality={quality}
                aside={
                  reviews ? (
                    <FindingsSidebar
                      reviews={reviews}
                      findings={findings}
                      onLocate={locate}
                    />
                  ) : undefined
                }
              />
            </Suspense>
          ),
        },
        {
          id: "review",
          label: "评审",
          badge: reviewCount > 0 ? String(reviewCount) : undefined,
          disabled: reviews === undefined,
          panel: (
            <ReviewPanel
              version={selected}
              reviews={reviews}
              previousReviews={previousReviews}
              previousVersion={previous}
              severity={score?.severity}
              findings={findings}
              overall={score?.overall}
              qualityThreshold={snapshot.quality_threshold}
              onLocate={locate}
            />
          ),
        },
        {
          id: "plan",
          label: "修订计划",
          badge: plan ? String(plan.plan.items.length) : undefined,
          disabled: plan === undefined,
          panel: (
            <RevisionPlanPanel entry={plan} resolutions={nextResolutions} />
          ),
        },
        {
          id: "diff",
          label: "对比",
          disabled: !comparable,
          panel: (
            <section className="panel">
              {comparable ? (
                <Suspense fallback={<ModuleFallback label="版本对比" />}>
                  <VersionDiff
                    sourceVersion={previous}
                    targetVersion={selected}
                    sourceContent={sourceContent}
                    targetContent={targetContent}
                  />
                </Suspense>
              ) : (
                <p className="empty-copy">
                  需要两个已完成的版本才能对比，当前只有一个版本。
                </p>
              )}
            </section>
          ),
        },
        {
          id: "trace",
          label: "运行记录",
          // No count: the old badge counted every event, including the
          // thousands of deltas the panel never shows.
          panel: <RunTimeline state={state} />,
        },
      ]
    : [];
  // A tab the reader picked can become unavailable when they switch versions --
  // v1 has a revision plan and v2 does not. Falling back to the document is
  // better than rendering an empty frame under a still-selected tab.
  const requested = tabs.find((tab) => tab.id === requestedTab);
  const activeTab =
    requested && !(requested.disabled ?? false) ? requestedTab : "prd";
  return (
    <main className="min-h-screen">
      <div className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8">
        <header className="mb-6 flex items-center gap-2.5">
          <Boxes aria-hidden="true" size={20} className="text-ink-muted" />
          <h1 className="text-base font-semibold tracking-tight text-ink">
            Agentic PRD Architect
          </h1>
          <span className="meta-label ml-1 hidden sm:inline">
            生成 · 三方评审 · 优化
          </span>
        </header>

        {/* The sidebar is a fixed rail and the workspace takes the rest, so a
            wide screen does not leave the document floating in a narrow column
            with hundreds of empty pixels on either side.
            The column is a flex box below `lg` rather than a plain block,
            because `order` needs a flex or grid parent to mean anything: as a
            block, the phone layout followed DOM order and opened on 对话记录
            instead of on the run. */}
        <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-6">
          <div className="order-2 min-w-0 lg:order-1">
            <ConversationSidebar
              conversations={controller.conversations}
              selectedRunId={state.runId}
              isLoading={controller.isLoadingConversations}
              onSelect={(runId) => void controller.selectRun(runId)}
              onNewConversation={controller.newRun}
            />
          </div>

          <div className="order-1 min-w-0 lg:order-2">
            <div className="sr-only" aria-live="polite" aria-atomic="true">
              {state.isCreating
                ? "正在创建任务"
                : state.status
                  ? `运行状态：${RUN_STATUS_LABELS[state.status]}${
                      state.outcome ? ` · ${outcomeSummary(state.outcome)}` : ""
                    }`
                  : "可以开始新任务"}
            </div>

            {/* A run failure's cause is in the failure panel; the banner is for
                everything else (a recovery request that failed, a lost connection). */}
            {state.error && state.error !== failure?.reason && (
              <div
                className="mb-4 flex flex-wrap items-start gap-3 rounded-panel border border-line bg-surface px-4 py-3 text-sm text-ink"
                role="alert"
              >
                <AlertCircle
                  aria-hidden="true"
                  className="mt-0.5 shrink-0 text-danger"
                  size={17}
                />
                <p className="min-w-0 flex-1">{state.error}</p>
                {state.runId && !state.status && (
                  <button
                    className="button-ghost"
                    type="button"
                    onClick={() => void controller.retryConnection()}
                  >
                    <RefreshCw aria-hidden="true" size={14} />
                    重试
                  </button>
                )}
                <button
                  className="text-xs font-medium text-ink-muted underline underline-offset-4 hover:text-ink"
                  type="button"
                  onClick={controller.clearError}
                >
                  关闭
                </button>
              </div>
            )}
            {!state.runId ? (
              <section className="grid items-start gap-8 py-4 lg:grid-cols-[0.85fr_1.15fr] lg:py-10">
                <div>
                  <h2 className="max-w-xl text-2xl font-semibold leading-snug tracking-tight text-ink sm:text-3xl">
                    让每一份需求，都经得起推敲。
                  </h2>
                  <p className="mt-4 max-w-lg text-sm leading-7 text-ink-muted">
                    将一个产品想法逐步转化为可评审的 PRD，并通过技术、体验和商业
                    三个独立视角持续校准质量。
                  </p>
                  <dl className="mt-7 grid max-w-lg grid-cols-3 gap-3">
                    {[
                      ["3", "位独立评审"],
                      ["≤5", "轮可控迭代"],
                      ["实时", "可回放运行轨迹"],
                    ].map(([value, label]) => (
                      <div key={label} className="border-l border-line pl-3">
                        <dt className="text-lg font-semibold text-ink">
                          {value}
                        </dt>
                        <dd className="mt-1 text-[11px] leading-4 text-ink-faint">
                          {label}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
                <ProductIdeaForm
                  isSubmitting={state.isCreating}
                  onSubmit={controller.createRun}
                  providers={catalog.providers}
                  catalogState={catalog.state}
                  catalogError={catalog.error}
                  onRetryCatalog={catalog.retry}
                />
              </section>
            ) : !snapshot || !state.status ? (
              <section
                className="flex min-h-[60vh] flex-col items-center justify-center text-center"
                aria-busy="true"
              >
                <span className="h-9 w-9 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                <h2 className="mt-5 text-sm font-medium text-ink">
                  正在恢复工作流
                </h2>
                <p className="mt-2 text-xs text-ink-muted">
                  正在加载最新快照，并从断点继续接收实时事件。
                </p>
              </section>
            ) : (
              <div id="workspace" className="min-w-0">
                {/* Run header: what was asked, how it ended, which version is
                    being read. Mobile order is outcome -> version -> document,
                    so the opening screen answers "is this done and which
                    version am I looking at" before anything else. */}
                <section className="min-w-0 space-y-4">
                  <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
                    <RunRequest snapshot={snapshot} />
                    <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2">
                      <StatusBadge status={state.status} />
                      {!isTerminalRunStatus(state.status) && (
                        <span
                          className="inline-flex items-center gap-1.5 text-xs text-ink-faint"
                          data-testid="connection-status"
                        >
                          <span
                            aria-hidden="true"
                            className={`h-1.5 w-1.5 rounded-full ${
                              state.connection === "open" ? "bg-ok" : "bg-warn"
                            }`}
                          />
                          {CONNECTION_LABELS[state.connection]}
                        </span>
                      )}
                      {isTerminalRunStatus(state.status) && (
                        <span
                          className="sr-only"
                          data-testid="connection-status"
                        >
                          连接：{CONNECTION_LABELS[state.connection]}
                        </span>
                      )}
                      {state.connection !== "open" &&
                        !isTerminalRunStatus(state.status) && (
                          <button
                            className="inline-flex items-center gap-1 text-xs font-medium text-accent underline underline-offset-4"
                            type="button"
                            data-testid="reconnect"
                            onClick={() => void controller.retryConnection()}
                          >
                            <RefreshCw aria-hidden="true" size={12} />
                            重新连接
                          </button>
                        )}
                    </div>
                  </div>
                  {state.outcome && <OutcomePanel outcome={state.outcome} />}
                  {failure && (
                    <FailurePanel
                      notice={failure}
                      busy={state.isCreating}
                      onRecover={(mode) => void controller.recover(mode)}
                    />
                  )}
                  {versions.length > 0 && (
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                      <VersionRail
                        versions={versions}
                        scores={state.scoresByVersion}
                        selectedVersion={selected}
                        bestVersion={state.bestVersion}
                        interrupted={versions.filter(
                          (version) => state.drafts[version]?.interrupted,
                        )}
                        onSelectVersion={controller.selectVersion}
                      />
                      <span className="meta-label">
                        目标 {snapshot.quality_threshold}
                      </span>
                    </div>
                  )}
                </section>

                <div className="mt-5 min-w-0">
                  <WorkspaceTabs
                    tabs={tabs}
                    activeId={activeTab}
                    onSelect={setRequestedTab}
                  />
                </div>

                <div className="mt-5 min-w-0">
                  <RunControls
                    status={state.status}
                    pendingControl={state.pendingControl}
                    onPause={controller.pause}
                    onResume={controller.resume}
                    onCancel={controller.cancel}
                    onNewRun={controller.newRun}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
