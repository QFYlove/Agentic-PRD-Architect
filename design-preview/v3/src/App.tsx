import { useEffect, useState } from "react";
import { Editor } from "./components/Editor";
import { Exploration } from "./components/Exploration";
import { LogoMark } from "./components/Marks";
import { Workspace } from "./components/Workspace";
import type { PageKey, StageKey } from "./data/types";
import { STAGES } from "./data/types";

const PAGES: { key: PageKey; index: string; en: string }[] = [
  { key: "workspace", index: "01", en: "Project Workspace" },
  { key: "explore", index: "02", en: "Requirement Exploration" },
  { key: "editor", index: "03", en: "PRD Editor" },
];

const STAGE_PAGE: Partial<Record<StageKey, PageKey>> = {
  explore: "explore",
  prd: "editor",
};

function readHash(): PageKey {
  const hash = window.location.hash.replace(/^#\/?/, "");
  return hash === "explore" || hash === "editor" ? hash : "workspace";
}

export function App() {
  const [page, setPage] = useState<PageKey>(readHash);

  useEffect(() => {
    const onHash = () => setPage(readHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [page]);

  const go = (next: PageKey) => {
    window.location.hash = `/${next}`;
  };

  return (
    <div className="app" data-page={page}>
      <div className="strip">
        <span className="strip__label">V3 DESIGN PREVIEW · MOCK DATA</span>
        <nav className="strip__nav" aria-label="原型页面">
          {PAGES.map((p) => (
            <a
              key={p.key}
              href={`#/${p.key}`}
              className={p.key === page ? "is-active" : undefined}
              aria-current={p.key === page ? "page" : undefined}
            >
              <b>{p.index}</b> {p.en}
            </a>
          ))}
        </nav>
      </div>

      <header className="header">
        <a className="brand" href="#/workspace" aria-label="返回项目工作台">
          <LogoMark />
          <span className="brand__name">
            PRD
            <br />
            Architect
          </span>
        </a>

        {page === "workspace" ? (
          <span className="header__context">
            <span className="mono">WORKSPACE</span>
            <span className="header__sep" />
            <span>5 个项目</span>
          </span>
        ) : (
          <>
            <span className="header__context">
              <span className="mono">P-0007</span>
              <span className="header__sep" />
              <span className="header__project">云盘离线下载</span>
            </span>
            <nav className="stages" aria-label="项目阶段">
              {STAGES.map((stage) => {
                const target = STAGE_PAGE[stage.key];
                const active = target === page;
                if (!target)
                  return (
                    <span
                      key={stage.key}
                      className="stages__item is-off"
                      title="原型未包含此页面"
                    >
                      <b>{stage.index}</b>
                      {stage.label}
                    </span>
                  );
                return (
                  <a
                    key={stage.key}
                    href={`#/${target}`}
                    className={
                      active ? "stages__item is-active" : "stages__item"
                    }
                    aria-current={active ? "page" : undefined}
                  >
                    <b>{stage.index}</b>
                    {stage.label}
                  </a>
                );
              })}
            </nav>
          </>
        )}

        <span className="header__meta">
          <span className="saved">
            <i aria-hidden="true" />
            已保存 14:32
          </span>
          <span className="avatar" aria-label="当前用户">
            PM
          </span>
        </span>
      </header>

      <main className="page" key={page}>
        {page === "workspace" && <Workspace onOpen={() => go("explore")} />}
        {page === "explore" && (
          <Exploration onOpenEditor={() => go("editor")} />
        )}
        {page === "editor" && <Editor />}
      </main>
    </div>
  );
}
