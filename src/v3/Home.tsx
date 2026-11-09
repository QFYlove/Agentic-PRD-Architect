import { useEffect, useMemo, useState } from "react";
import { go } from "./App";
import { api, errorText } from "./api";
import type { EntryMode, ProjectSummary, Stage } from "./types";
import { Icon, timeText, useToast } from "./ui";

const ENTRY_MODES: { key: EntryMode; label: string; hint: string }[] = [
  {
    key: "idea",
    label: "从想法开始",
    hint: "例如：我想做一个帮大学生管理课程资料的工具……",
  },
  {
    key: "requirement",
    label: "从已有需求开始",
    hint: "粘贴业务需求、会议纪要或初步方案，AI 会整理并找出缺失信息",
  },
  {
    key: "review",
    label: "审查已有 PRD",
    hint: "粘贴一份 Markdown 格式的 PRD，按章节导入后直接审查",
  },
];

const STAGE_TEXT: Record<Stage, string> = {
  explore: "需求探索",
  brief: "Product Brief",
  prd: "PRD",
  review: "审查",
  deliver: "交付",
};
const STAGES: Stage[] = ["explore", "brief", "prd", "review", "deliver"];

export function nextStep(p: ProjectSummary): string {
  const c = p.counts;
  if (p.active_job) return "AI 正在处理，完成后会停下来等你";
  if (c.questions > 0 || c.decide > 0) {
    const parts = [];
    if (c.questions > 0) parts.push(`${c.questions} 个问题等你回答`);
    if (c.decide > 0) parts.push(`${c.decide} 项内容等你决定`);
    return parts.join("，");
  }
  switch (p.stage) {
    case "explore":
      return "补充信息，或整理成 Brief";
    case "brief":
      return "生成 PRD 大纲";
    case "prd":
      return p.outline_confirmed_at
        ? `继续生成 PRD（${c.written}/${c.sections} 章）`
        : "检查并确认大纲";
    case "review":
      return c.open_findings > 0
        ? `${c.open_findings} 条审查意见待处理`
        : "开始审查";
    case "deliver":
      return "可以导出 Markdown";
  }
}

function spaceFor(p: ProjectSummary): "explore" | "document" {
  return p.stage === "explore" ? "explore" : "document";
}

export function Home() {
  const toast = useToast();
  const [mode, setMode] = useState<EntryMode>("idea");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [showDone, setShowDone] = useState(false);
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);

  const load = () =>
    api
      .projects()
      .then((r) => setProjects(r.items))
      .catch((error: unknown) => {
        setProjects([]);
        toast({ text: errorText(error), error: true });
      });

  useEffect(() => {
    void load();
    // Loaded once on arrival; actions below reload explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const entry = ENTRY_MODES.find((m) => m.key === mode) ?? ENTRY_MODES[0]!;

  const start = async () => {
    setBusy(true);
    try {
      const created = await api.createProject({
        text: text.trim(),
        entry_mode: mode,
        depth: "detailed",
      });
      go(
        `p/${created.project.id}/${mode === "review" ? "document" : "explore"}`,
      );
    } catch (error) {
      toast({ text: errorText(error), error: true });
      setBusy(false);
    }
  };

  const visible = useMemo(() => {
    const all = projects ?? [];
    return all.filter((p) => !query || p.name.includes(query));
  }, [projects, query]);
  const active = visible.filter((p) => p.stage !== "deliver");
  const done = visible.filter((p) => p.stage === "deliver");
  const [current, ...rest] = active;

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
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                (e.metaKey || e.ctrlKey) &&
                text.trim()
              ) {
                void start();
              }
            }}
          />
          <div className="composer__foot">
            <div className="tabs" role="radiogroup" aria-label="开始方式">
              {ENTRY_MODES.map((m) => (
                <button
                  key={m.key}
                  type="button"
                  role="radio"
                  aria-checked={mode === m.key}
                  onClick={() => setMode(m.key)}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="btn btn--primary"
              disabled={!text.trim() || busy}
              onClick={() => void start()}
            >
              {busy ? "正在创建…" : mode === "review" ? "开始审查" : "开始"}
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
          {(projects?.length ?? 0) > 3 && (
            <input
              className="search"
              type="search"
              placeholder="搜索"
              value={query}
              aria-label="搜索项目"
              onChange={(e) => setQuery(e.target.value)}
            />
          )}
        </div>

        {projects === null ? (
          <p className="quiet empty-line">正在载入…</p>
        ) : current ? (
          <Featured project={current} />
        ) : (
          <p className="quiet empty-line">
            {query
              ? "没有找到匹配的项目。"
              : "还没有项目。写下第一个想法就可以开始。"}
          </p>
        )}

        {rest.length > 0 && (
          <ul className="plist">
            {rest.map((p) => (
              <ProjectRow key={p.id} project={p} onChange={load} />
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
                  <ProjectRow key={p.id} project={p} onChange={load} />
                ))}
              </ul>
            )}
          </>
        )}
        {current && (
          <ul className="plist plist--manage" aria-label="当前项目操作">
            <ProjectRow project={current} onChange={load} manageOnly />
          </ul>
        )}

        <a className="history-link" href="/runs">
          历史运行（V2，只读）
        </a>
      </section>
    </div>
  );
}

function Steps({ stage }: { stage: Stage }) {
  const current = STAGES.indexOf(stage);
  return (
    <span className="steps" aria-hidden="true">
      {STAGES.map((s, i) => (
        <i
          key={s}
          className={
            i < current ? "is-done" : i === current ? "is-now" : undefined
          }
        />
      ))}
    </span>
  );
}

function Featured({ project }: { project: ProjectSummary }) {
  return (
    <a
      className="featured"
      href={`#/p/${project.id}/${spaceFor(project)}`}
      data-testid="featured-project"
    >
      <span className="featured__meta">
        <span>继续上次的工作</span>
        <span>{timeText(project.updated_at)}</span>
      </span>
      <span className="featured__name">{project.name}</span>
      <span className="featured__foot">
        <span className="featured__step">
          <Steps stage={project.stage} />
          {STAGE_TEXT[project.stage]}
        </span>
        <span className="featured__next">
          {nextStep(project)}
          <Icon name="arrow" />
        </span>
      </span>
    </a>
  );
}

function ProjectRow({
  project,
  onChange,
  manageOnly = false,
}: {
  project: ProjectSummary;
  onChange: () => void;
  manageOnly?: boolean;
}) {
  const toast = useToast();
  const [mode, setMode] = useState<"idle" | "rename" | "delete">("idle");
  const [name, setName] = useState(project.name);

  const rename = async () => {
    try {
      await api.rename(project.id, name.trim());
      setMode("idle");
      onChange();
    } catch (error) {
      toast({ text: errorText(error), error: true });
    }
  };
  const remove = async () => {
    try {
      await api.remove(project.id);
      toast({ text: `已删除「${project.name}」。` });
      onChange();
    } catch (error) {
      toast({ text: errorText(error), error: true });
    }
  };

  if (mode === "rename") {
    return (
      <li className="prow prow--edit">
        <input
          className="field field--small"
          value={name}
          autoFocus
          aria-label="项目名称"
          maxLength={60}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && name.trim()) void rename();
            if (e.key === "Escape") setMode("idle");
          }}
        />
        <button
          type="button"
          className="btn btn--text"
          onClick={() => setMode("idle")}
        >
          取消
        </button>
        <button
          type="button"
          className="btn btn--small"
          disabled={!name.trim()}
          onClick={() => void rename()}
        >
          保存
        </button>
      </li>
    );
  }
  if (mode === "delete") {
    return (
      <li className="prow prow--edit" role="alert">
        <span className="prow__main">
          删除「{project.name}」？删除后无法通过列表或链接打开。
        </span>
        <button
          type="button"
          className="btn btn--text"
          onClick={() => setMode("idle")}
        >
          取消
        </button>
        <button
          type="button"
          className="btn btn--danger"
          onClick={() => void remove()}
        >
          删除
        </button>
      </li>
    );
  }
  const tools = (
    <span className="prow__tools">
      <button
        type="button"
        className="btn btn--text"
        onClick={() => setMode("rename")}
      >
        重命名
      </button>
      <button
        type="button"
        className="btn btn--text"
        onClick={() => setMode("delete")}
      >
        删除
      </button>
    </span>
  );
  if (manageOnly) {
    return <li className="prow prow--manage">{tools}</li>;
  }
  return (
    <li className="prow">
      <a className="prow__link" href={`#/p/${project.id}/${spaceFor(project)}`}>
        <span className="prow__main">
          <span className="prow__name">{project.name}</span>
          <span className="prow__next">{nextStep(project)}</span>
        </span>
        <span className="prow__step">{STAGE_TEXT[project.stage]}</span>
        <span className="prow__time">{timeText(project.updated_at)}</span>
      </a>
      {tools}
    </li>
  );
}
