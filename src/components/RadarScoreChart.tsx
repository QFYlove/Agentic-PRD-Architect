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

/**
 * Three versions, three lines, one hue family.
 *
 * The previous palette was cyan / violet / green -- three unrelated accents that
 * made the chart the loudest thing on the page. These are the accent plus two
 * neutrals, so the newest version reads as the subject and the older ones as
 * context.
 */
const COLORS = ["#66717f", "#929caa", "#2cb7c9"];
const GRID = "#28313c";
const AXIS_TEXT = "#929caa";
const AXIS_TICK = "#66717f";

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
                <PolarGrid stroke={GRID} />
                <PolarAngleAxis
                  dataKey="dimension"
                  tick={{ fill: AXIS_TEXT, fontSize: 11 }}
                />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, 100]}
                  tick={{ fill: AXIS_TICK, fontSize: 9 }}
                  tickCount={5}
                />
                {versions.map((score, index) => {
                  // Counted from the end, so the newest version always takes
                  // the accent whether the run has one version or three.
                  const colour =
                    COLORS[COLORS.length - versions.length + index];
                  return (
                    <Radar
                      key={score.version}
                      name={`v${score.version}`}
                      dataKey={`v${score.version}`}
                      stroke={colour}
                      fill={colour}
                      fillOpacity={0.08}
                      strokeWidth={2}
                    />
                  );
                })}
                <Tooltip
                  contentStyle={{
                    background: "#11161d",
                    border: `1px solid ${GRID}`,
                    borderRadius: 6,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <caption className="sr-only">PRD 质量评分的文本表格</caption>
              <thead className="text-ink-faint">
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
                    className="border-t border-line text-ink-muted"
                  >
                    <th className="py-2 font-semibold text-ink">
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
