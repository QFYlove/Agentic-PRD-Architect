import { useState } from "react";
import { ACTIVITY, ENTRY_MODES, PROJECTS } from "../data/projects";
import type { Project } from "../data/projects";
import { STAGES } from "../data/types";
import { Corners, Cover, Id, StageTrack } from "./Marks";

type Filter = "all" | "active" | "delivered";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "active", label: "进行中" },
  { key: "delivered", label: "已交付" },
];

const PLACEHOLDER: Record<string, string> = {
  A: "例如：我想做一个类似迅雷的云盘，支持磁力链接下载、在线播放和分享。",
  B: "粘贴业务需求、会议纪要或初步方案……",
  C: "粘贴已有 PRD 的 Markdown 正文……",
};

function stageLabel(project: Project) {
  return STAGES.find((s) => s.key === project.stage) ?? STAGES[0];
}

export function Workspace({ onOpen }: { onOpen: () => void }) {
  const [mode, setMode] = useState<string>("A");
  const [idea, setIdea] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<string>("p7");

  const shown = PROJECTS.filter((p) =>
    filter === "all"
      ? true
      : filter === "delivered"
        ? p.stage === "deliver"
        : p.stage !== "deliver",
  );
  const findings = PROJECTS.reduce((sum, p) => sum + p.openFindings, 0);
  const questions = PROJECTS.reduce((sum, p) => sum + p.openQuestions, 0);
  const active = PROJECTS.filter((p) => p.stage !== "deliver").length;

  return (
    <div className="ws grid">
      <section className="ws-mast" aria-labelledby="ws-title">
        <div className="ws-mast__index mono">01 / WORKSPACE · 2026.11.08</div>
        <h1 id="ws-title" className="display">
          Think clearly.
          <br />
          Design better.
        </h1>
        <p className="ws-mast__lede">
          从一个想法开始，把问题想清楚，把方案设计完整，把 PRD 做扎实。
        </p>
        <div className="ws-mast__figure" aria-hidden="true">
          <span className="fig-block" />
          <span className="fig-accent" />
          <span className="fig-line fig-line--h" />
          <span className="fig-line fig-line--v" />
          <span className="fig-label mono">PRJ / 0007</span>
        </div>
      </section>

      <dl className="ws-stats" aria-label="工作区概览">
        <div>
          <dt>进行中项目</dt>
          <dd>{String(active).padStart(2, "0")}</dd>
        </div>
        <div>
          <dt>待处理问题</dt>
          <dd>{String(findings).padStart(2, "0")}</dd>
        </div>
        <div>
          <dt>待确认事项</dt>
          <dd className="is-accent">{String(questions).padStart(2, "0")}</dd>
        </div>
      </dl>

      <section className="ws-new" aria-labelledby="ws-new-title">
        <Corners />
        <header className="sec-head">
          <span className="sec-head__num">A</span>
          <h2 id="ws-new-title">新建项目</h2>
          <span className="sec-head__en">New project</span>
        </header>
        <div className="modes" role="radiogroup" aria-label="输入方式">
          {ENTRY_MODES.map((m) => (
            <button
              key={m.code}
              type="button"
              role="radio"
              aria-checked={mode === m.code}
              className={mode === m.code ? "mode is-on" : "mode"}
              onClick={() => setMode(m.code)}
            >
              <span className="mode__code">{m.code}</span>
              <span className="mode__body">
                <span className="mode__title">{m.title}</span>
                <span className="mode__detail">{m.detail}</span>
              </span>
            </button>
          ))}
        </div>
        <label className="field">
          <span className="field__label mono">INPUT</span>
          <textarea
            rows={4}
            value={idea}
            placeholder={PLACEHOLDER[mode]}
            onChange={(e) => setIdea(e.target.value)}
          />
        </label>
        <div className="ws-new__actions">
          <span className="hint">AI 先追问，不会直接生成 PRD。</span>
          <button type="button" className="btn btn--primary" onClick={onOpen}>
            {mode === "C" ? "开始审查" : "开始探索"}
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </section>

      <section className="ws-recent" aria-labelledby="ws-recent-title">
        <header className="sec-head">
          <span className="sec-head__num">B</span>
          <h2 id="ws-recent-title">最近项目</h2>
          <span className="sec-head__en">Recent</span>
          <span className="seg" role="tablist" aria-label="筛选项目">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                role="tab"
                aria-selected={filter === f.key}
                className={filter === f.key ? "is-on" : undefined}
                onClick={() => setFilter(f.key)}
              >
                {f.label}
              </button>
            ))}
          </span>
        </header>

        <div className="plist" role="list">
          <div className="plist__head mono" aria-hidden="true">
            <span>项目</span>
            <span>阶段</span>
            <span>问题</span>
            <span>待确认</span>
            <span>修改</span>
          </div>
          {shown.length === 0 && <EmptyProjects />}
          {shown.map((p) => (
            <ProjectRow
              key={p.id}
              project={p}
              selected={selected === p.id}
              onSelect={() => setSelected(p.id)}
              onOpen={onOpen}
            />
          ))}
        </div>
      </section>

      <section className="ws-log" aria-labelledby="ws-log-title">
        <header className="sec-head">
          <span className="sec-head__num">C</span>
          <h2 id="ws-log-title">最近修改</h2>
          <span className="sec-head__en">Activity</span>
        </header>
        <ol className="log">
          {ACTIVITY.map((a, i) => (
            <li key={i}>
              <span className="log__time mono">{a.time}</span>
              <span
                className={a.actor === "ai" ? "log__actor is-ai" : "log__actor"}
              >
                {a.actor === "ai" ? "AI" : "你"}
              </span>
              <span className="log__text">
                <Id>{a.project}</Id> {a.text}
              </span>
              <span className="log__ref mono">{a.ref}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function ProjectRow({
  project,
  selected,
  onSelect,
  onOpen,
}: {
  project: Project;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
}) {
  const stage = stageLabel(project);
  const openable = project.id === "p7";
  return (
    <div role="listitem" className={selected ? "prow is-selected" : "prow"}>
      <button
        type="button"
        className="prow__main"
        onClick={onSelect}
        aria-expanded={selected}
      >
        <Cover seed={project.seed} size={52} />
        <span className="prow__title">
          <span className="prow__code mono">{project.code}</span>
          <span className="prow__name">{project.name}</span>
          <span className="prow__summary">{project.summary}</span>
        </span>
        <span className="prow__stage">
          <span className="prow__stage-label">
            <b className="mono">{stage?.index}</b> {stage?.label}
          </span>
          <StageTrack stage={project.stage} compact />
        </span>
        <span
          className={
            project.openFindings > 0 ? "prow__num" : "prow__num is-zero"
          }
        >
          <span className="sr">待处理问题</span>
          {project.openFindings}
        </span>
        <span
          className={
            project.openQuestions > 0 ? "prow__num" : "prow__num is-zero"
          }
        >
          <span className="sr">待确认事项</span>
          {project.openQuestions}
        </span>
        <span className="prow__time mono">{project.updatedLabel}</span>
      </button>
      {selected && (
        <div className="prow__detail">
          <span className="prow__detail-meta mono">
            {project.version ? `PRD ${project.version}` : "尚未生成 PRD"} ·
            更新于 {project.updatedAt}
          </span>
          <span className="prow__detail-text">
            {project.openFindings > 0
              ? `${project.openFindings} 个问题和 ${project.openQuestions} 个待确认事项等待处理。`
              : "没有待处理的问题。"}
          </span>
          <button
            type="button"
            className="btn btn--line"
            onClick={openable ? onOpen : undefined}
            disabled={!openable}
            title={openable ? undefined : "原型中只有 P-0007 可以打开"}
          >
            继续{stage?.label} <span aria-hidden="true">→</span>
          </button>
        </div>
      )}
    </div>
  );
}

function EmptyProjects() {
  return (
    <div className="empty">
      <span className="empty__glyph" aria-hidden="true" />
      <p>这里还没有项目。</p>
    </div>
  );
}
