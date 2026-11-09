import { useState } from "react";
import { api } from "./api";
import { running, type ProjectStore } from "./store";
import type { Section } from "./types";
import { Icon } from "./ui";

/** Outline editor: shown after the outline job, until the user confirms it. */
export function OutlineView({ store }: { store: ProjectStore }) {
  const { data } = store;
  const projectId = data.summary!.id;
  const sections = data.sections?.items ?? [];
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");

  const order = (list: Section[]) =>
    list.map((s) => ({ code: s.code, level: s.level }));
  const move = (index: number, delta: number) => {
    const next = [...sections];
    const [moved] = next.splice(index, 1);
    if (!moved) return;
    next.splice(index + delta, 0, moved);
    void store.act(() => api.reorder(projectId, order(next)));
  };
  const indent = (index: number) => {
    const next = sections.map((s, i) =>
      i === index ? { ...s, level: s.level === 1 ? 2 : 1 } : s,
    );
    void store.act(() => api.reorder(projectId, order(next)));
  };
  const add = async () => {
    if (!title.trim()) return;
    await store.act(() =>
      api.addSection(projectId, title.trim(), sections.at(-1)?.code ?? null, 1),
    );
    setTitle("");
    setAdding(false);
  };

  return (
    <div className="stage stage--outline">
      <header className="stage__head">
        <div>
          <h1 className="page-title">PRD 大纲</h1>
          <p className="talk__status">
            {sections.length} 个章节 · 确认后按顺序逐章生成，每章可以单独重试
          </p>
        </div>
        <div className="talk__actions">
          <button
            type="button"
            className="btn btn--primary"
            disabled={sections.length === 0 || running(store)}
            onClick={() =>
              void (async () => {
                const ok = await store.act(() => api.confirmOutline(projectId));
                if (ok)
                  await store.startJob(
                    () => api.generate(projectId),
                    "生成 PRD",
                  );
              })()
            }
          >
            确认大纲并生成
            <Icon name="arrow" />
          </button>
        </div>
      </header>

      <ol className="olist" data-testid="outline-editor">
        {sections.map((s, index) => (
          <OutlineRow
            key={s.id}
            section={s}
            first={index === 0}
            last={index === sections.length - 1}
            onUp={() => move(index, -1)}
            onDown={() => move(index, 1)}
            onIndent={() => indent(index)}
            store={store}
          />
        ))}
      </ol>
      {adding ? (
        <div className="olist__add">
          <input
            className="field field--small"
            value={title}
            autoFocus
            placeholder="新章节标题"
            aria-label="新章节标题"
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void add();
              if (e.key === "Escape") setAdding(false);
            }}
          />
          <button
            type="button"
            className="btn btn--text"
            onClick={() => setAdding(false)}
          >
            取消
          </button>
          <button
            type="button"
            className="btn btn--small"
            disabled={!title.trim()}
            onClick={() => void add()}
          >
            添加
          </button>
        </div>
      ) : (
        <button type="button" className="more" onClick={() => setAdding(true)}>
          <Icon name="plus" />
          添加章节
        </button>
      )}
    </div>
  );
}

function OutlineRow({
  section,
  first,
  last,
  onUp,
  onDown,
  onIndent,
  store,
}: {
  section: Section;
  first: boolean;
  last: boolean;
  onUp: () => void;
  onDown: () => void;
  onIndent: () => void;
  store: ProjectStore;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(section.title);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const rename = async () => {
    setEditing(false);
    if (title.trim() && title.trim() !== section.title) {
      await store.act(() =>
        api.saveSection(section.id, {
          row_version: section.row_version,
          title: title.trim(),
        }),
      );
    }
  };

  return (
    <li className={`orow orow--l${section.level}`}>
      <span className="orow__num">{section.num}</span>
      <div className="orow__main">
        {editing ? (
          <input
            className="field field--small"
            value={title}
            autoFocus
            aria-label="章节标题"
            onChange={(e) => setTitle(e.target.value)}
            onBlur={() => void rename()}
            onKeyDown={(e) => {
              if (e.key === "Enter") void rename();
              if (e.key === "Escape") setEditing(false);
            }}
          />
        ) : (
          <button
            type="button"
            className="orow__title"
            title="点击修改标题"
            onClick={() => setEditing(true)}
          >
            {section.title}
          </button>
        )}
        {section.goal && <p className="orow__goal">{section.goal}</p>}
        {(section.item_codes.length > 0 || section.open_points.length > 0) && (
          <p className="orow__meta">
            {section.item_codes.length > 0 && (
              <span
                title={section.item_codes
                  .map(
                    (c) =>
                      store.data.items.find((i) => i.code === c)?.content ?? c,
                  )
                  .join("\n")}
              >
                依据 {section.item_codes.length} 条需求
              </span>
            )}
            {section.depends.length > 0 && (
              <> · 依赖第 {section.depends.join("、")} 节</>
            )}
            {section.open_points.length > 0 && (
              <> · 待确认：{section.open_points.join("；")}</>
            )}
          </p>
        )}
      </div>
      {confirmDelete ? (
        <span className="orow__tools is-shown">
          <button
            type="button"
            className="btn btn--text"
            onClick={() => setConfirmDelete(false)}
          >
            取消
          </button>
          <button
            type="button"
            className="btn btn--danger btn--small"
            onClick={() =>
              void store.act(() =>
                api.deleteSection(section.id, section.row_version),
              )
            }
          >
            删除
          </button>
        </span>
      ) : (
        <span className="orow__tools">
          <button
            type="button"
            className="icon-btn icon-btn--small"
            aria-label="上移"
            disabled={first}
            onClick={onUp}
          >
            <Icon name="up" />
          </button>
          <button
            type="button"
            className="icon-btn icon-btn--small"
            aria-label="下移"
            disabled={last}
            onClick={onDown}
          >
            <Icon name="down" />
          </button>
          <button type="button" className="btn btn--text" onClick={onIndent}>
            {section.level === 1 ? "降为小节" : "升为章"}
          </button>
          <button
            type="button"
            className="btn btn--text"
            onClick={() => setConfirmDelete(true)}
          >
            删除
          </button>
        </span>
      )}
    </li>
  );
}
