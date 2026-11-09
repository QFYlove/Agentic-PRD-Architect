import { useState } from "react";
import type { EntryMode } from "../data/projects";
import { ENTRY_MODES, PROJECTS } from "../data/projects";
import type { Project } from "../data/projects";
import { STEPS } from "../data/types";
import { go } from "../lib/route";
import { Icon, ProjectMark, Steps } from "./ui";

export function Home({ pending }: { pending: number }) {
  const [mode, setMode] = useState<EntryMode>("idea");
  const [text, setText] = useState("");
  const [showDone, setShowDone] = useState(false);
  const [query, setQuery] = useState("");

  const entry = ENTRY_MODES.find((m) => m.key === mode) ?? ENTRY_MODES[0];
  const projects = PROJECTS.map((p) =>
    p.id === "p7"
      ? {
          ...p,
          pending,
          next:
            pending > 0
              ? `3 个问题等你回答，${pending} 项内容等你决定`
              : "3 个问题等你回答",
        }
      : p,
  );
  const matches = (p: Project) =>
    !query || p.name.includes(query) || p.summary.includes(query);
  const [current, ...rest] = projects.filter((p) => !p.done && matches(p));
  const done = projects.filter((p) => p.done && matches(p));

  return (
    <div className="home">
      <section className="start" aria-labelledby="start-title">
        <h1 id="start-title" className="start__title">
          从一个想法开始
        </h1>
        <p className="start__lede">
          描述你想做的产品。AI 会先问几个关键问题，帮你把需求想清楚，再一起写
          PRD。
        </p>

        <div className="composer">
          <textarea
            className="composer__input"
            rows={3}
            value={text}
            placeholder={entry.hint}
            aria-label="项目输入"
            onChange={(e) => setText(e.target.value)}
          />
          <div className="composer__foot">
            <div className="tabs" role="radiogroup" aria-label="开始方式">
              {ENTRY_MODES.map((m) => (
                <button
                  key={m.key}
                  type="button"
                  role="radio"
                  aria-checked={mode === m.key}
                  className={mode === m.key ? "is-on" : undefined}
                  onClick={() => setMode(m.key)}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="btn btn--primary"
              disabled={!text.trim()}
              onClick={() => go("p7/explore")}
            >
              {mode === "review" ? "开始审查" : "开始"}
              <Icon name="arrow" />
            </button>
          </div>
        </div>
      </section>

      <section className="projects" aria-labelledby="projects-title">
        <div className="projects__head">
          <h2 id="projects-title" className="label">
            项目
          </h2>
          <input
            className="search"
            type="search"
            placeholder="搜索"
            value={query}
            aria-label="搜索项目"
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {current ? (
          <Featured project={current} />
        ) : (
          <p className="quiet empty-line">没有找到匹配的项目。</p>
        )}

        {rest.length > 0 && (
          <ul className="plist">
            {rest.map((p) => (
              <ProjectRow key={p.id} project={p} />
            ))}
          </ul>
        )}

        {done.length > 0 && (
          <>
            <button
              type="button"
              className="more"
              aria-expanded={showDone}
              onClick={() => setShowDone((v) => !v)}
            >
              <Icon name={showDone ? "down" : "chevron"} />
              已交付 {done.length}
            </button>
            {showDone && (
              <ul className="plist plist--done">
                {done.map((p) => (
                  <ProjectRow key={p.id} project={p} />
                ))}
              </ul>
            )}
          </>
        )}
      </section>
    </div>
  );
}

/** The most recently touched project gets a larger row with its next action. */
function Featured({ project }: { project: Project }) {
  const step = STEPS.indexOf(project.step);
  return (
    <a className="featured" href="#/p7/explore">
      <span className="featured__meta">
        <span>继续上次的工作</span>
        <span>{project.updated}</span>
      </span>
      <span className="featured__name">{project.name}</span>
      <span className="featured__summary">{project.summary}</span>
      <span className="featured__foot">
        <span className="featured__step">
          <Steps current={step} />
          {project.step}
        </span>
        <span className="featured__next">
          {project.next}
          <Icon name="arrow" />
        </span>
      </span>
    </a>
  );
}

function ProjectRow({ project }: { project: Project }) {
  const openable = project.id === "p7";
  const content = (
    <>
      <ProjectMark seed={project.seed} />
      <span className="prow__main">
        <span className="prow__name">{project.name}</span>
        <span className="prow__next">{project.next}</span>
      </span>
      <span className="prow__step">{project.step}</span>
      <span className="prow__time">{project.updated}</span>
    </>
  );
  return (
    <li>
      {openable ? (
        <a className="prow" href="#/p7/explore">
          {content}
        </a>
      ) : (
        <span
          className="prow is-static"
          title="原型中只有「云盘离线下载」可以打开"
        >
          {content}
        </span>
      )}
    </li>
  );
}
