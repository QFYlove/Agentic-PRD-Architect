import { BarChart3 } from "lucide-react";
import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import type { VersionScore } from "../lib/runReducer";

const COLORS = ["#22d3ee", "#a78bfa", "#34d399"];

export function RadarScoreChart({
  scores,
}: {
  scores: Record<number, VersionScore>;
}) {
  const versions = Object.values(scores)
    .sort((left, right) => left.version - right.version)
    .slice(-3);
  const data = [
    {
      dimension: "技术",
      ...Object.fromEntries(
        versions.map((score) => [`v${score.version}`, score.tech]),
      ),
    },
    {
      dimension: "体验",
      ...Object.fromEntries(
        versions.map((score) => [`v${score.version}`, score.ux]),
      ),
    },
    {
      dimension: "商业",
      ...Object.fromEntries(
        versions.map((score) => [`v${score.version}`, score.biz]),
      ),
    },
  ];

  return (
    <section className="panel" aria-labelledby="scores-heading">
      <div className="panel-heading">
        <BarChart3 aria-hidden="true" size={18} />
        <h2 id="scores-heading">质量评分</h2>
      </div>
      {versions.length === 0 ? (
        <p className="empty-copy">三位评审全部完成后，这里会显示质量评分。</p>
      ) : (
        <>
          <div
            className="mt-3 h-64 min-w-0"
            aria-label="对比不同 PRD 版本评分的雷达图"
          >
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={data} outerRadius="68%">
                <PolarGrid stroke="#334155" />
                <PolarAngleAxis
                  dataKey="dimension"
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, 100]}
                  tick={{ fill: "#64748b", fontSize: 9 }}
                  tickCount={5}
                />
                {versions.map((score, index) => (
                  <Radar
                    key={score.version}
                    name={`v${score.version}`}
                    dataKey={`v${score.version}`}
                    stroke={COLORS[index]}
                    fill={COLORS[index]}
                    fillOpacity={0.08}
                    strokeWidth={2}
                  />
                ))}
                <Tooltip
                  contentStyle={{
                    background: "#0f172a",
                    border: "1px solid #334155",
                    borderRadius: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <caption className="sr-only">PRD 质量评分的文本表格</caption>
              <thead className="text-slate-500">
                <tr>
                  <th className="py-2 font-medium">版本</th>
                  <th className="py-2 font-medium">技术</th>
                  <th className="py-2 font-medium">体验</th>
                  <th className="py-2 font-medium">商业</th>
                  <th className="py-2 font-medium">综合</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((score) => (
                  <tr
                    key={score.version}
                    data-testid={`score-v${score.version}`}
                    className="border-t border-white/8 text-slate-300"
                  >
                    <th className="py-2 font-semibold text-white">
                      v{score.version}
                    </th>
                    <td>{score.tech}</td>
                    <td>{score.ux}</td>
                    <td>{score.biz}</td>
                    <td>{score.overall}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
