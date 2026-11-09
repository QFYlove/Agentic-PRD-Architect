import {
  CheckCircle2,
  ChevronDown,
  Circle,
  CircleDashed,
  Loader2,
  MinusCircle,
  Wrench,
  XCircle,
} from "lucide-react";
import { lazy, Suspense } from "react";

import { localizedErrorMessage } from "../lib/errorMessages";
import { formatSeconds } from "../lib/nodeTimings";
import type { RunViewState } from "../lib/runReducer";
import { buildRunTimeline, type StageState } from "../lib/runTimeline";
import { AgentTrace } from "./AgentTrace";
import { TelemetryPanel } from "./TelemetryPanel";

const WorkflowDiagram = lazy(() =>
  import("./WorkflowDiagram").then((module) => ({
    default: module.WorkflowDiagram,
  })),
);
const RadarScoreChart = lazy(() =>
  import("./RadarScoreChart").then((module) => ({
    default: module.RadarScoreChart,
  })),
);

const STATE_META: Record<
  StageState,
  { label: string; icon: typeof Circle; className: string }
> = {
  done: { label: "已完成", icon: CheckCircle2, className: "text-ok" },
  running: { label: "进行中", icon: Loader2, className: "text-accent" },
  failed: { label: "失败", icon: XCircle, className: "text-danger" },
  pending: { label: "等待中", icon: CircleDashed, className: "text-ink-faint" },
  skipped: { label: "未执行", icon: MinusCircle, className: "text-ink-faint" },
};

function formatElapsed(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return minutes > 0 ? `${minutes} 分 ${remainder} 秒` : `${remainder} 秒`;
}

function StateIcon({ state }: { state: StageState }) {
  const meta = STATE_META[state];
  const Icon = meta.icon;
  return (
    <Icon
      aria-hidden="true"
      size={15}
      className={`mt-0.5 shrink-0 ${meta.className} ${
        state === "running" ? "animate-spin" : ""
      }`}
    />
  );
}

/**
 * The run record as a reader needs it.
 *
 * The default view answers "what ran, what finished, what failed and why, what
 * do I have, what next" from durable state -- so a run reopened a week later
 * reads the same as a live one. Event sequence numbers, token counts, node ids
 * and the trace id are still here, folded into one developer section.
 */
export function RunTimeline({ state }: { state: RunViewState }) {
  const model = buildRunTimeline(state);
  const snapshot = state.snapshot;
  if (model === null || snapshot === null) {
    return null;
  }
  const error = state.runError ?? snapshot.error ?? null;
  return (
    <div className="grid min-w-0 gap-4" data-testid="run-timeline">
      <section className="panel" aria-labelledby="run-summary-heading">
        <h2 id="run-summary-heading" className="panel-heading">
          执行摘要
        </h2>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
          <div>
            <dt className="meta-label">总耗时</dt>
            <dd className="mt-0.5 text-ink" data-testid="timeline-elapsed">
              {formatElapsed(model.elapsedSeconds)}
            </dd>
          </div>
          <div>
            <dt className="meta-label">已完成版本</dt>
            <dd className="mt-0.5 text-ink" data-testid="timeline-usable">
              {model.usableVersions.length > 0
                ? model.usableVersions
                    .map((version) => `v${version}`)
                    .join("、")
                : "无"}
            </dd>
          </div>
          <div>
            <dt className="meta-label">最佳版本</dt>
            <dd className="mt-0.5 text-ink">
              {model.bestVersion !== null ? `v${model.bestVersion}` : "—"}
            </dd>
          </div>
          <div>
            <dt className="meta-label">迭代</dt>
            <dd className="mt-0.5 text-ink">
              {/* The snapshot a live page holds is the one it opened with, so
                  the iteration is the newest version the page has seen. */}
              {Math.max(
                snapshot.current_iteration,
                ...model.versions.map((version) => version.version),
              )}{" "}
              / {snapshot.max_iterations}
            </dd>
          </div>
        </dl>

        <ol className="mt-5 space-y-5">
          {model.versions.map((version) => (
            <li
              key={version.version}
              data-testid={`timeline-v${version.version}`}
            >
              <h3 className="text-sm font-semibold text-ink">
                v{version.version}
              </h3>
              <ol className="mt-2 space-y-2 border-l border-line pl-4">
                {version.stages.map((stage) => (
                  <li
                    key={stage.key}
                    className="flex gap-2.5"
                    data-testid="timeline-stage"
                    data-stage={stage.key}
                    data-state={stage.state}
                  >
                    <StateIcon state={stage.state} />
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-baseline gap-x-2 text-sm">
                        <span className="font-medium text-ink">
                          {stage.label}
                        </span>
                        <span
                          className={`text-xs ${STATE_META[stage.state].className}`}
                        >
                          {STATE_META[stage.state].label}
                        </span>
                        {stage.seconds !== null && (
                          <span className="text-xs text-ink-faint">
                            {formatSeconds(stage.seconds)}
                          </span>
                        )}
                      </p>
                      {stage.result && (
                        <p className="text-xs leading-5 text-ink-muted">
                          {stage.result}
                        </p>
                      )}
                      {stage.state === "failed" && error && (
                        <p
                          className="text-xs leading-5 text-danger"
                          data-testid="timeline-failure"
                        >
                          {localizedErrorMessage(error.code)}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </li>
          ))}
          <li className="flex gap-2.5" data-testid="timeline-final">
            <StateIcon state={model.finalState} />
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink">最终质量检查</p>
              {model.finalResult && (
                <p className="text-xs leading-5 text-ink-muted">
                  {model.finalResult}
                </p>
              )}
            </div>
          </li>
        </ol>
      </section>

      {Object.keys(state.scoresByVersion).length > 0 && (
        <Suspense fallback={null}>
          <RadarScoreChart scores={state.scoresByVersion} />
        </Suspense>
      )}

      <details className="panel group" data-testid="run-debug">
        <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-ink">
          <Wrench aria-hidden="true" size={15} className="text-ink-muted" />
          开发者调试信息
          <span className="text-xs font-normal text-ink-faint">
            Provider、Token、节点耗时、Trace ID、原始事件
          </span>
          <ChevronDown
            aria-hidden="true"
            size={14}
            className="ml-auto text-ink-muted transition group-open:rotate-180"
          />
        </summary>
        <dl className="mt-4 grid gap-x-6 gap-y-1.5 font-mono text-xs text-ink-muted sm:grid-cols-[8rem_1fr]">
          <dt className="text-ink-faint">Run ID</dt>
          <dd className="break-all">{snapshot.run_id}</dd>
          <dt className="text-ink-faint">Trace ID</dt>
          <dd className="break-all" data-testid="debug-trace-id">
            {snapshot.trace_id ?? "—（历史任务）"}
          </dd>
          {error && (
            <>
              <dt className="text-ink-faint">Error</dt>
              <dd data-testid="debug-error">
                {error.code}
                {error.node ? ` @ ${error.node}` : ""}
                {error.attempt ? ` · attempt ${error.attempt}` : ""}
                {` · retryable=${String(error.retryable)}`}
              </dd>
            </>
          )}
          {snapshot.source_run_id && (
            <>
              <dt className="text-ink-faint">Source run</dt>
              <dd className="break-all">{snapshot.source_run_id}</dd>
            </>
          )}
        </dl>
        <div className="mt-4 grid min-w-0 gap-4 xl:grid-cols-2">
          <Suspense fallback={null}>
            <WorkflowDiagram
              statuses={snapshot.node_statuses}
              runStatus={state.status ?? snapshot.status}
            />
          </Suspense>
          <TelemetryPanel snapshot={snapshot} />
          <div className="xl:col-span-2">
            <AgentTrace events={state.events} />
          </div>
        </div>
      </details>
    </div>
  );
}
