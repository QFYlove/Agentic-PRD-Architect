import { useEffect, useState } from "react";
import { api } from "./api";
import { DocumentSpace } from "./Document";
import { ExploreSpace } from "./Explore";
import { Home } from "./Home";
import { useProjectStore } from "./store";
import type { Meta } from "./types";
import { ToastProvider } from "./ui";

type Route =
  | { page: "home" }
  | { page: "project"; id: string; space: "explore" | "document" };

function parse(hash: string): Route {
  const match = /^#\/p\/([a-f0-9]+)\/(explore|document)/.exec(hash);
  if (match?.[1] && match[2]) {
    return {
      page: "project",
      id: match[1],
      space: match[2] as "explore" | "document",
    };
  }
  return { page: "home" };
}

export function go(path: string) {
  window.location.hash = `/${path}`;
}

export function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}

function Shell() {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
  const [meta, setMeta] = useState<Meta | null>(null);

  useEffect(() => {
    const onHash = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    void api
      .meta()
      .then(setMeta)
      .catch(() => setMeta(null));
  }, []);

  if (route.page === "home") {
    return (
      <>
        <Bar meta={meta} />
        <main className="main">
          <Home />
        </main>
      </>
    );
  }
  return (
    <ProjectShell
      key={route.id}
      id={route.id}
      space={route.space}
      meta={meta}
    />
  );
}

function ProjectShell({
  id,
  space,
  meta,
}: {
  id: string;
  space: "explore" | "document";
  meta: Meta | null;
}) {
  const store = useProjectStore(id, meta);
  const summary = store.data.summary;

  useEffect(() => {
    if (space === "document") window.scrollTo(0, 0);
  }, [space]);

  if (store.missing) {
    return (
      <>
        <Bar meta={meta} />
        <main className="main">
          <div className="calm calm--page">
            <p>这个项目不存在，或已经删除。</p>
            <a className="btn btn--ghost" href="#/">
              返回项目列表
            </a>
          </div>
        </main>
      </>
    );
  }

  const counts = summary?.counts;
  const exploreCount = counts ? counts.questions + counts.decide : 0;
  const documentCount = counts?.open_findings ?? 0;

  return (
    <>
      <Bar meta={meta}>
        <nav className="bar__crumb" aria-label="位置">
          <a href="#/">项目</a>
          <span aria-hidden="true">/</span>
          <b>{summary?.name ?? "…"}</b>
        </nav>
        <nav className="spaces" aria-label="项目空间">
          <a
            href={`#/p/${id}/explore`}
            className={space === "explore" ? "is-on" : undefined}
            aria-current={space === "explore" ? "page" : undefined}
          >
            需求
            {space !== "explore" && exploreCount > 0 && (
              <span className="count">{exploreCount}</span>
            )}
          </a>
          <a
            href={`#/p/${id}/document`}
            className={space === "document" ? "is-on" : undefined}
            aria-current={space === "document" ? "page" : undefined}
          >
            文档
            {space !== "document" && documentCount > 0 && (
              <span className="count">{documentCount}</span>
            )}
          </a>
        </nav>
      </Bar>
      <main className="main">
        {!store.loaded ? (
          <p className="loading">正在载入项目…</p>
        ) : space === "explore" ? (
          <ExploreSpace store={store} />
        ) : (
          <DocumentSpace store={store} />
        )}
      </main>
    </>
  );
}

function Bar({
  meta,
  children,
}: {
  meta: Meta | null;
  children?: React.ReactNode;
}) {
  return (
    <header className="bar">
      <a className="bar__brand" href="#/">
        Agentic PRD Architect
      </a>
      {children}
      <div className="bar__end">
        {meta?.mock && (
          <span
            className="bar__mode"
            title="当前使用模拟模型：AI 的回复是固定规则生成的，用于演示和测试"
          >
            模拟模型
          </span>
        )}
      </div>
    </header>
  );
}
