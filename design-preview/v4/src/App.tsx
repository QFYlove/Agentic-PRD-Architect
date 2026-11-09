import { useEffect, useState } from "react";
import { Document, useDocState } from "./components/Document";
import { Explore, useExploreState } from "./components/Explore";
import { Home } from "./components/Home";
import { Logo } from "./components/ui";
import type { Route, Space } from "./data/types";

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (hash === "p7/explore") return { page: "project", space: "explore" };
  if (hash === "p7/document") return { page: "project", space: "document" };
  return { page: "home" };
}

const SPACES: { key: Space; label: string }[] = [
  { key: "explore", label: "需求" },
  { key: "document", label: "文档" },
];

export function App() {
  const [route, setRoute] = useState<Route>(readRoute);
  // Project state lives here so switching spaces keeps the demo's changes.
  const explore = useExploreState();
  const doc = useDocState();

  useEffect(() => {
    const onHash = () => setRoute(readRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (route.page === "home" || route.space === "document")
      window.scrollTo(0, 0);
  }, [route]);

  const space = route.page === "project" ? route.space : null;

  return (
    <div className="app" data-space={space ?? "home"}>
      <header className="bar">
        <a className="bar__brand" href="#/" aria-label="返回项目列表">
          <Logo />
          <span>PRD Architect</span>
        </a>

        {space && (
          <>
            <span className="bar__crumb">
              <a href="#/">项目</a>
              <span aria-hidden="true">/</span>
              <b>云盘离线下载</b>
            </span>
            <nav className="spaces" aria-label="工作区">
              {SPACES.map((s) => (
                <a
                  key={s.key}
                  href={`#/p7/${s.key}`}
                  className={s.key === space ? "is-on" : undefined}
                  aria-current={s.key === space ? "page" : undefined}
                >
                  {s.label}
                  {s.key === "explore" &&
                    s.key !== space &&
                    explore.pending > 0 && (
                      <span className="count">{explore.pending}</span>
                    )}
                  {s.key === "document" &&
                    s.key !== space &&
                    doc.openNotes > 0 && (
                      <span className="count count--quiet">
                        {doc.openNotes}
                      </span>
                    )}
                </a>
              ))}
            </nav>
          </>
        )}

        <span className="bar__end">
          {space && <span className="bar__saved">已保存</span>}
          <span
            className="bar__proto"
            title="本原型只使用前端 Mock 数据，刷新会重置"
          >
            原型
          </span>
          <span className="avatar" aria-label="当前用户">
            林
          </span>
        </span>
      </header>

      <main
        className="main"
        key={route.page === "project" ? route.space : "home"}
      >
        {route.page === "home" && <Home pending={explore.pending} />}
        {space === "explore" && <Explore state={explore} />}
        {space === "document" && <Document state={doc} />}
      </main>
    </div>
  );
}
