import { Clock3, Coins, Cpu, Gauge } from "lucide-react";

import type { RunSnapshot } from "../lib/types";

function formatElapsed(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return minutes > 0 ? `${minutes}分 ${remainder}秒` : `${remainder}秒`;
}

export function TelemetryPanel({ snapshot }: { snapshot: RunSnapshot }) {
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
          <span className="ml-auto rounded-full bg-violet-400/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-violet-200">
            模拟
          </span>
        )}
      </div>
      <dl className="mt-5 grid grid-cols-2 gap-3">
        {metrics.map(({ label, value, icon: Icon }) => (
          <div
            key={label}
            className="rounded-xl border border-white/8 bg-white/[0.025] p-3"
          >
            <dt className="flex items-center gap-2 text-[11px] text-slate-500">
              <Icon aria-hidden="true" size={13} />
              {label}
            </dt>
            <dd className="mt-1 text-sm font-semibold text-slate-100">
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
