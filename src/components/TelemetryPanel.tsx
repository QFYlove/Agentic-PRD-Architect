import { Clock3, Coins, Cpu, Gauge } from "lucide-react";

import {
  formatSeconds,
  nodeTimingRows,
  slowestSeconds,
} from "../lib/nodeTimings";
import type { RunSnapshot } from "../lib/types";

function formatElapsed(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return minutes > 0 ? `${minutes}分 ${remainder}秒` : `${remainder}秒`;
}

export function TelemetryPanel({ snapshot }: { snapshot: RunSnapshot }) {
  const timings = nodeTimingRows(snapshot.node_timings);
  const slowest = slowestSeconds(timings);
  const metrics = [
    {
      label: "迭代进度",
      value: `${snapshot.current_iteration}/${snapshot.max_iterations}`,
      icon: Gauge,
    },
    {
      label: "运行时长",
      value: formatElapsed(snapshot.elapsed_seconds),
      icon: Clock3,
    },
    {
      label: "输入 Token",
      value: snapshot.total_tokens.input_tokens.toLocaleString(),
      icon: Cpu,
    },
    {
      label: "输出 Token",
      value: snapshot.total_tokens.output_tokens.toLocaleString(),
      icon: Cpu,
    },
    {
      label: "Token 总量",
      value: snapshot.total_tokens.total_tokens.toLocaleString(),
      icon: Cpu,
    },
    {
      label: "预估费用",
      value: snapshot.cost_available
        ? `$${(snapshot.estimated_cost_usd ?? 0).toFixed(4)}`
        : "暂不可用",
      icon: Coins,
    },
  ];

  return (
    <section className="panel" aria-labelledby="telemetry-heading">
      <div className="panel-heading">
        <Gauge aria-hidden="true" size={18} />
        <h2 id="telemetry-heading">运行指标</h2>
        {snapshot.is_mock && (
          <span className="tag ml-auto" data-testid="telemetry-mock">
            模拟数据
          </span>
        )}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
        {metrics.map(({ label, value, icon: Icon }) => (
          <div key={label} className="min-w-0 border-l border-line pl-3">
            <dt className="flex items-center gap-1.5 text-[11px] text-ink-faint">
              <Icon aria-hidden="true" size={12} />
              {label}
            </dt>
            <dd className="mt-0.5 text-sm font-medium text-ink">{value}</dd>
          </div>
        ))}
      </dl>

      {/* Which node owned the time. A 500-second run gives no clue on its own,
          and the answer is only ever needed after the fact, so it lives here in
          运行记录 rather than beside the document. */}
      {timings.length > 0 && (
        <div className="mt-5 min-w-0" data-testid="node-timings">
          <h3 className="meta-label">节点耗时</h3>
          <ul className="mt-2 space-y-1.5">
            {timings.map((row, index) => (
              <li
                key={`${row.label}-${index}`}
                className="min-w-0"
                data-testid="node-timing-row"
              >
                <div className="flex min-w-0 items-baseline justify-between gap-3">
                  <span className="min-w-0 truncate text-xs text-ink">
                    {row.label}
                    {row.attempt !== null && (
                      <span className="text-ink-faint">
                        {" "}
                        · 第 {row.attempt} 次
                      </span>
                    )}
                    {!row.succeeded && (
                      <span className="text-danger"> · 失败</span>
                    )}
                  </span>
                  <span className="shrink-0 font-mono text-[11px] text-ink-muted">
                    {formatSeconds(row.seconds)}
                    {row.outputTokens > 0 && (
                      <span className="text-ink-faint">
                        {" "}
                        · {row.inputTokens}/{row.outputTokens} tok
                      </span>
                    )}
                  </span>
                </div>
                <div
                  aria-hidden="true"
                  className="mt-1 h-0.5 w-full bg-line"
                  role="presentation"
                >
                  <div
                    className={`h-full ${row.succeeded ? "bg-accent" : "bg-danger"}`}
                    style={{
                      width: `${Math.max(2, (row.seconds / slowest) * 100)}%`,
                    }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
