import {
  AlertCircle,
  ArrowUpRight,
  Boxes,
  Radio,
  RefreshCw,
} from "lucide-react";
import { lazy, Suspense } from "react";

import { useAgentRun, type UseAgentRunOptions } from "../hooks/useAgentRun";
import type { ConnectionStatus } from "../lib/runReducer";
import { isTerminalRunStatus } from "../lib/types";
import { AgentTrace } from "./AgentTrace";
import { ConversationSidebar } from "./ConversationSidebar";
import { ProductIdeaForm } from "./ProductIdeaForm";
import { RunControls } from "./RunControls";
import { RUN_STATUS_LABELS, StatusBadge } from "./StatusBadge";
import { TelemetryPanel } from "./TelemetryPanel";

const PRDViewer = lazy(() =>
  import("./PRDViewer").then((module) => ({ default: module.PRDViewer })),
);
const RadarScoreChart = lazy(() =>
  import("./RadarScoreChart").then((module) => ({
    default: module.RadarScoreChart,
  })),
);
const WorkflowDiagram = lazy(() =>
  import("./WorkflowDiagram").then((module) => ({
    default: module.WorkflowDiagram,
  })),
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
      <p className="text-sm text-slate-500">正在加载{label}…</p>
    </div>
  );
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

  return (
    <main className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-96 bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.12),_transparent_58%)]" />
      <div className="relative mx-auto max-w-[1800px] px-4 py-7 sm:px-6 lg:px-8">
        <header className="mb-7 flex flex-wrap items-center justify-between gap-5">
          <div className="flex items-center gap-3">
            <span className="rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-2.5 text-cyan-200 shadow-lg shadow-cyan-950/20">
              <Boxes aria-hidden="true" size={23} />
            </span>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-cyan-300">
                多智能体产品实验室
              </p>
              <h1 className="text-xl font-semibold tracking-tight text-white sm:text-2xl">
                Agentic PRD Architect
              </h1>
            </div>
          </div>
          <a
            className="inline-flex items-center gap-2 text-xs font-medium text-slate-400 transition hover:text-white"
            href="#workspace"
          >
            全程可观测
            <ArrowUpRight aria-hidden="true" size={14} />
          </a>
        </header>

        <div className="lg:grid lg:grid-cols-[17rem_minmax(0,1fr)] lg:gap-6">
          <ConversationSidebar
            conversations={controller.conversations}
            selectedRunId={state.runId}
            isLoading={controller.isLoadingConversations}
            onSelect={(runId) => void controller.selectRun(runId)}
            onNewConversation={controller.newRun}
          />

          <div className="min-w-0">
            <div className="sr-only" aria-live="polite" aria-atomic="true">
              {state.isCreating
                ? "正在创建任务"
                : state.status
                  ? `运行状态：${RUN_STATUS_LABELS[state.status]}`
                  : "可以开始新任务"}
            </div>

            {state.error && (
              <div
                className="mb-5 flex flex-wrap items-start gap-3 rounded-2xl border border-rose-400/20 bg-rose-400/8 px-4 py-3 text-sm text-rose-100"
                role="alert"
              >
                <AlertCircle
                  aria-hidden="true"
                  className="mt-0.5 shrink-0"
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
                  className="text-xs font-medium text-rose-200 underline underline-offset-4"
                  type="button"
                  onClick={controller.clearError}
                >
                  关闭
                </button>
              </div>
            )}

            {!state.runId ? (
              <section className="grid items-center gap-10 py-8 lg:grid-cols-[0.8fr_1.2fr] lg:py-20">
                <div>
                  <p className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300">
                    <Radio
                      aria-hidden="true"
                      size={13}
                      className="text-emerald-300"
                    />
                    生成器 · 3 位独立评审 · 优化器
                  </p>
                  <h2 className="mt-6 max-w-xl text-4xl font-semibold leading-[1.05] tracking-[-0.04em] text-white sm:text-6xl">
                    让每一份需求，
                    <span className="text-cyan-300">都经得起推敲。</span>
                  </h2>
                  <p className="mt-6 max-w-lg text-base leading-7 text-slate-400">
                    将一个产品想法逐步转化为可评审的
                    PRD，并通过技术、体验和商业三个 独立视角持续校准质量。
                  </p>
                  <dl className="mt-8 grid max-w-lg grid-cols-3 gap-3">
                    {[
                      ["3", "位独立评审"],
                      ["≤5", "轮可控迭代"],
                      ["实时", "可回放运行轨迹"],
                    ].map(([value, label]) => (
                      <div
                        key={label}
                        className="border-l border-white/10 pl-3"
                      >
                        <dt className="text-xl font-semibold text-white">
                          {value}
                        </dt>
                        <dd className="mt-1 text-[11px] leading-4 text-slate-500">
                          {label}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
                <ProductIdeaForm
                  isSubmitting={state.isCreating}
                  onSubmit={controller.createRun}
                />
              </section>
            ) : !snapshot || !state.status ? (
              <section
                className="flex min-h-[65vh] flex-col items-center justify-center text-center"
                aria-busy="true"
              >
                <span className="h-10 w-10 animate-spin rounded-full border-2 border-cyan-300 border-t-transparent" />
                <h2 className="mt-5 text-lg font-medium text-white">
                  正在恢复工作流
                </h2>
                <p className="mt-2 text-sm text-slate-500">
                  正在加载最新快照，并从断点继续接收实时事件。
                </p>
              </section>
            ) : (
              <div id="workspace">
                <section className="mb-5 rounded-2xl border border-white/10 bg-slate-950/55 p-4 backdrop-blur sm:p-5">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <div className="flex flex-wrap items-center gap-3">
                        <StatusBadge status={state.status} />
                        <span
                          className="inline-flex items-center gap-1.5 text-xs text-slate-500"
                          data-testid="connection-status"
                        >
                          <span
                            aria-hidden="true"
                            className={`h-1.5 w-1.5 rounded-full ${
                              state.connection === "open"
                                ? "bg-emerald-400"
                                : "bg-amber-400"
                            }`}
                          />
                          连接：{CONNECTION_LABELS[state.connection]}
                        </span>
                      </div>
                      <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
                        {snapshot.user_idea}
                      </p>
                      <p className="mt-1 font-mono text-[10px] text-slate-600">
                        任务 {snapshot.run_id}
                      </p>
                    </div>
                    {isTerminalRunStatus(state.status) && (
                      <p className="max-w-xs text-right text-xs leading-5 text-slate-400">
                        本次任务已结束。你可以查看任意版本，或开启新的架构任务。
                      </p>
                    )}
                  </div>
                </section>

                <RunControls
                  status={state.status}
                  pendingControl={state.pendingControl}
                  onPause={controller.pause}
                  onResume={controller.resume}
                  onCancel={controller.cancel}
                  onNewRun={controller.newRun}
                />

                <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(22rem,0.72fr)_minmax(0,1.28fr)]">
                  <div className="grid content-start gap-5 md:grid-cols-2 xl:grid-cols-1">
                    <Suspense fallback={<ModuleFallback label="工作流" />}>
                      <WorkflowDiagram
                        statuses={snapshot.node_statuses}
                        runStatus={state.status}
                      />
                    </Suspense>
                    <AgentTrace events={state.events} />
                    <Suspense fallback={<ModuleFallback label="评分" />}>
                      <RadarScoreChart scores={state.scoresByVersion} />
                    </Suspense>
                    <TelemetryPanel snapshot={snapshot} />
                  </div>
                  <Suspense fallback={<ModuleFallback label="PRD 工作区" />}>
                    <PRDViewer
                      runId={snapshot.run_id}
                      drafts={state.drafts}
                      scores={state.scoresByVersion}
                      selectedVersion={state.selectedVersion}
                      onSelectVersion={controller.selectVersion}
                    />
                  </Suspense>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
