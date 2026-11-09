import { useEffect, useMemo, useRef, useState } from "react";
import {
  DIFFS,
  DOC_TITLE,
  NOTES,
  SECTIONS,
  SOURCE_TEXT,
  VERSIONS,
} from "../data/prd";
import type { NoteState, ReviewNote, Section } from "../data/types";
import { NOTE_STATE_TEXT, REVIEWER_TEXT, SEVERITY_TEXT } from "../data/types";
import { parseBlocks, parseInline, toMarkdown } from "../lib/blocks";
import type { Block } from "../lib/blocks";
import { Icon } from "./ui";

type Side = "notes" | "sources";

const OPEN_STATES: NoteState[] = ["open", "recheck"];

export function useDocState() {
  const [sections, setSections] = useState<Section[]>(SECTIONS);
  const [notes, setNotes] = useState<ReviewNote[]>(NOTES);
  const [edited, setEdited] = useState<string[]>([]);
  const openNotes = notes.filter((n) => OPEN_STATES.includes(n.state)).length;
  return {
    sections,
    setSections,
    notes,
    setNotes,
    edited,
    setEdited,
    openNotes,
  };
}

export type DocState = ReturnType<typeof useDocState>;

export function Document({ state }: { state: DocState }) {
  const { sections, setSections, notes, setNotes, edited, setEdited } = state;
  const wide = window.innerWidth >= 1200;
  const [outline, setOutline] = useState(wide);
  const [side, setSide] = useState<Side | null>(wide ? "notes" : null);
  const [active, setActive] = useState("s1");
  const [focus, setFocus] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [version, setVersion] = useState("v3");
  const [compare, setCompare] = useState(false);
  const [versionMenu, setVersionMenu] = useState(false);
  const [toast, setToast] = useState<{ text: string; action?: string } | null>(
    null,
  );
  const docRef = useRef<HTMLElement>(null);

  const readOnly = version !== "v3";
  const current = VERSIONS.find((v) => v.id === version) ?? VERSIONS[0]!;
  const shown = compare ? sections.filter((s) => DIFFS[s.id]) : sections;
  const openCount = notes.filter((n) => OPEN_STATES.includes(n.state)).length;

  // Track the section at the top of the viewport.
  useEffect(() => {
    const doc = docRef.current;
    if (!doc) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const top = entries
          .filter((e) => e.isIntersecting)
          .sort(
            (a, b) => a.boundingClientRect.top - b.boundingClientRect.top,
          )[0];
        const id = top?.target.getAttribute("data-section");
        if (id) setActive(id);
      },
      { rootMargin: "-96px 0px -55% 0px" },
    );
    doc
      .querySelectorAll("[data-section]")
      .forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [shown]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(t);
  }, [toast]);

  const jump = (id: string) => {
    setActive(id);
    if (window.innerWidth < 1200) setOutline(false);
    document
      .getElementById(`sec-${id}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const openNote = (id: string) => {
    const note = notes.find((n) => n.id === id);
    setFocus(id);
    setSide("notes");
    if (note) {
      setActive(note.section);
      window.setTimeout(() => {
        document
          .querySelector(`[data-anchor="${id}"]`)
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 40);
    }
  };

  const save = (id: string, body: string) => {
    const section = sections.find((s) => s.id === id);
    setEditing(null);
    if (!section || section.body === body) return;
    setSections((prev) =>
      prev.map((s) => (s.id === id ? { ...s, body, by: "you" } : s)),
    );
    setEdited((prev) => (prev.includes(id) ? prev : [...prev, id]));
    setNotes((prev) =>
      prev.map((n) =>
        n.section === id && n.state === "open" ? { ...n, state: "recheck" } : n,
      ),
    );
    const affected = section.impacts
      .map((sid) => sections.find((s) => s.id === sid))
      .filter((s): s is Section => Boolean(s))
      .map((s) => `第 ${s.num} 节「${s.title}」`);
    setToast(
      affected.length
        ? {
            text: `已保存。这次修改可能影响 ${affected.join("、")}。`,
            action: "检查这些章节",
          }
        : { text: "已保存。" },
    );
  };

  const setNote = (id: string, next: NoteState, userNote?: string) =>
    setNotes((prev) =>
      prev.map((n) =>
        n.id === id
          ? {
              ...n,
              state: next,
              ...(userNote !== undefined ? { userNote } : {}),
            }
          : n,
      ),
    );

  const exportMd = () => {
    const blob = new Blob([toMarkdown(sections, DOC_TITLE)], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `云盘离线下载-PRD-${version}.md`;
    a.click();
    URL.revokeObjectURL(url);
    setToast({ text: `已导出 云盘离线下载-PRD-${version}.md` });
  };

  const classes = ["docview"];
  if (outline) classes.push("has-outline");
  if (side) classes.push("has-side");

  return (
    <div className={classes.join(" ")}>
      <div className="dtool">
        <button
          type="button"
          className={outline ? "icon-btn is-on" : "icon-btn"}
          aria-label="目录"
          aria-expanded={outline}
          onClick={() => setOutline((v) => !v)}
        >
          <Icon name="outline" />
        </button>

        <div className="dtool__version">
          <button
            type="button"
            className="vbtn"
            aria-expanded={versionMenu}
            onClick={() => setVersionMenu((v) => !v)}
          >
            <b>{current.label}</b>
            <span>
              {current.by} · {current.time}
            </span>
            <Icon name="down" />
          </button>
          {versionMenu && (
            <VersionMenu
              version={version}
              compare={compare}
              onPick={(v) => {
                setVersion(v);
                setCompare(false);
                setEditing(null);
                setVersionMenu(false);
              }}
              onCompare={() => {
                setVersion("v3");
                setCompare(true);
                setVersionMenu(false);
              }}
              onClose={() => setVersionMenu(false)}
            />
          )}
        </div>

        {edited.length > 0 && !readOnly && !compare && (
          <span className="dtool__state">
            <i aria-hidden="true" />
            你修改了 {edited.length} 个章节
          </span>
        )}

        <span className="dtool__end">
          <button type="button" className="btn btn--text" onClick={exportMd}>
            <Icon name="download" />
            导出
          </button>
          <button
            type="button"
            className={
              side === "notes" ? "btn btn--toggle is-on" : "btn btn--toggle"
            }
            aria-expanded={side === "notes"}
            onClick={() => setSide(side === "notes" ? null : "notes")}
          >
            审查意见
            {openCount > 0 && <span className="count">{openCount}</span>}
          </button>
        </span>
      </div>

      {outline && (
        <Outline
          sections={sections}
          notes={notes}
          active={active}
          edited={edited}
          onJump={jump}
        />
      )}

      <article className="paper" ref={docRef} aria-label="PRD 正文">
        {readOnly && (
          <p className="banner">
            正在查看 {current.label}（{current.note}），只读。
            <button
              type="button"
              className="btn btn--text"
              onClick={() => setVersion("v3")}
            >
              回到当前版本
            </button>
          </p>
        )}
        {compare && (
          <p className="banner">
            v2 → v3 的改动，只显示有变化的章节。
            <button
              type="button"
              className="btn btn--text"
              onClick={() => setCompare(false)}
            >
              退出对比
            </button>
          </p>
        )}

        <header className="paper__head">
          <h1 className="paper__title">{DOC_TITLE}</h1>
          <p className="paper__meta">
            基于 11月8日确认的 Product Brief · {sections.length} 个章节
          </p>
        </header>

        {shown.map((section) => (
          <SectionView
            key={section.id}
            section={section}
            notes={notes.filter((n) => n.section === section.id)}
            focus={focus}
            editing={editing === section.id}
            canEdit={!readOnly && !compare}
            compare={compare}
            onEdit={() => setEditing(section.id)}
            onCancel={() => setEditing(null)}
            onSave={(body) => save(section.id, body)}
            onNote={openNote}
            onSources={() => {
              setActive(section.id);
              setSide("sources");
            }}
          />
        ))}
      </article>

      {side && (
        <aside
          className="side"
          aria-label={side === "notes" ? "审查意见" : "本章来源"}
        >
          {side === "notes" ? (
            <Notes
              notes={notes}
              sections={sections}
              focus={focus}
              onFocus={openNote}
              onState={setNote}
              onClose={() => setSide(null)}
            />
          ) : (
            <Sources
              section={sections.find((s) => s.id === active)}
              sections={sections}
              onClose={() => setSide(null)}
              onJump={jump}
            />
          )}
        </aside>
      )}

      {toast && (
        <div className="toast" role="status">
          <span>{toast.text}</span>
          {toast.action && (
            <button
              type="button"
              className="toast__action"
              onClick={() => setToast({ text: "原型中不执行检查。" })}
            >
              {toast.action}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function VersionMenu({
  version,
  compare,
  onPick,
  onCompare,
  onClose,
}: {
  version: string;
  compare: boolean;
  onPick: (v: string) => void;
  onCompare: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);
  return (
    <div className="menu" ref={ref} role="menu">
      <p className="menu__label">版本历史</p>
      {VERSIONS.map((v) => (
        <button
          key={v.id}
          type="button"
          role="menuitemradio"
          aria-checked={version === v.id && !compare}
          className={
            version === v.id && !compare ? "menu__item is-on" : "menu__item"
          }
          onClick={() => onPick(v.id)}
        >
          <b>{v.label}</b>
          <span className="menu__main">
            {v.note}
            <span className="quiet">
              {v.by} · {v.time}
            </span>
          </span>
          {v.id === "v3" && <span className="menu__tag">当前</span>}
        </button>
      ))}
      <div className="menu__sep" />
      <button
        type="button"
        role="menuitem"
        className="menu__item"
        onClick={onCompare}
      >
        <Icon name="compare" />
        <span className="menu__main">与 v2 对比</span>
      </button>
    </div>
  );
}

function Outline({
  sections,
  notes,
  active,
  edited,
  onJump,
}: {
  sections: Section[];
  notes: ReviewNote[];
  active: string;
  edited: string[];
  onJump: (id: string) => void;
}) {
  return (
    <nav className="outline" aria-label="目录">
      <ol>
        {sections.map((s) => {
          const open = notes.some(
            (n) => n.section === s.id && OPEN_STATES.includes(n.state),
          );
          const classes = ["outline__item", `is-l${s.level}`];
          if (active === s.id) classes.push("is-on");
          return (
            <li key={s.id}>
              <button
                type="button"
                className={classes.join(" ")}
                aria-current={active === s.id ? "true" : undefined}
                onClick={() => onJump(s.id)}
              >
                <span className="outline__num">{s.num}</span>
                <span className="outline__title">{s.title}</span>
                {edited.includes(s.id) && (
                  <span className="outline__edited" title="你修改过" />
                )}
                {open && (
                  <span className="outline__note" title="有待处理的审查意见" />
                )}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function SectionView({
  section,
  notes,
  focus,
  editing,
  canEdit,
  compare,
  onEdit,
  onCancel,
  onSave,
  onNote,
  onSources,
}: {
  section: Section;
  notes: ReviewNote[];
  focus: string | null;
  editing: boolean;
  canEdit: boolean;
  compare: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: (body: string) => void;
  onNote: (id: string) => void;
  onSources: () => void;
}) {
  const [draft, setDraft] = useState(section.body);
  useEffect(() => {
    if (editing) setDraft(section.body);
  }, [editing, section.body]);

  const Heading = section.level === 1 ? "h2" : "h3";
  const diff = compare ? DIFFS[section.id] : undefined;
  const classes = ["sec", `sec--l${section.level}`];
  if (editing) classes.push("is-editing");

  return (
    <section
      id={`sec-${section.id}`}
      data-section={section.id}
      className={classes.join(" ")}
    >
      <header className="sec__head">
        <Heading className="sec__title">
          <span className="sec__num">{section.num}</span>
          {section.title}
        </Heading>
        {section.by === "you" && <span className="sec__by">你修改</span>}
        {canEdit && !editing && (
          <span className="sec__tools">
            {section.sources.length > 0 && (
              <button
                type="button"
                className="btn btn--text"
                onClick={onSources}
              >
                来源
              </button>
            )}
            <button type="button" className="btn btn--text" onClick={onEdit}>
              <Icon name="edit" />
              编辑
            </button>
          </span>
        )}
      </header>

      {diff ? (
        <ol className="diff">
          {diff.map((line, i) => (
            <li key={i} className={`diff__line diff__line--${line.kind}`}>
              <span
                className="diff__sign"
                aria-label={
                  line.kind === "add"
                    ? "新增"
                    : line.kind === "del"
                      ? "删除"
                      : "未改"
                }
              >
                {line.kind === "add" ? "+" : line.kind === "del" ? "−" : ""}
              </span>
              <span className="diff__text">
                {line.text.replace(/\s*\[[^\]]+\]/g, "")}
              </span>
              {line.why && <span className="diff__why">{line.why}</span>}
            </li>
          ))}
        </ol>
      ) : editing ? (
        <div className="sec__editor">
          <textarea
            className="field field--source"
            value={draft}
            rows={Math.max(4, draft.split("\n").length + 1)}
            aria-label={`编辑 ${section.num} ${section.title}`}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onSave(draft);
              if (e.key === "Escape") onCancel();
            }}
          />
          <div className="sec__editor-foot">
            <span className="quiet">
              Markdown · 你修改的章节，AI 不会自动覆盖
            </span>
            <button type="button" className="btn btn--text" onClick={onCancel}>
              取消
            </button>
            <button
              type="button"
              className="btn btn--small"
              onClick={() => onSave(draft)}
            >
              保存
            </button>
          </div>
        </div>
      ) : (
        <div className="sec__body">
          {parseBlocks(section.body).map((block, i) => (
            <BlockView
              key={i}
              block={block}
              notes={notes}
              focus={focus}
              onNote={onNote}
            />
          ))}
        </div>
      )}
    </section>
  );
}

const FACT_CLASS: Record<string, string> = {
  用户输入: "fact fact--user",
  假设: "fact fact--assume",
  待确认: "fact fact--open",
};

function Inline({
  text,
  notes,
  focus,
  onNote,
}: {
  text: string;
  notes: ReviewNote[];
  focus: string | null;
  onNote: (id: string) => void;
}) {
  return (
    <>
      {parseInline(text).map((part, i) => {
        if (part.kind === "text") return <span key={i}>{part.text}</span>;
        if (part.kind === "fact")
          return (
            <span key={i} className={FACT_CLASS[part.label] ?? "fact"}>
              {part.label}
            </span>
          );
        const note = notes.find((n) => n.id === part.id);
        if (!note || !OPEN_STATES.includes(note.state))
          return <span key={i}>{part.text}</span>;
        return (
          <button
            key={i}
            type="button"
            data-anchor={part.id}
            data-sev={note.severity}
            className={focus === part.id ? "anchor is-focus" : "anchor"}
            onClick={() => onNote(part.id)}
            title={note.title}
          >
            {part.text}
          </button>
        );
      })}
    </>
  );
}

function BlockView({
  block,
  ...rest
}: {
  block: Block;
  notes: ReviewNote[];
  focus: string | null;
  onNote: (id: string) => void;
}) {
  if (block.kind === "p")
    return (
      <p>
        <Inline text={block.text} {...rest} />
      </p>
    );
  if (block.kind === "quote")
    return (
      <blockquote>
        <Inline text={block.text} {...rest} />
      </blockquote>
    );
  if (block.kind === "ol" || block.kind === "ul") {
    const List = block.kind;
    return (
      <List>
        {block.items.map((item, i) => (
          <li key={i}>
            <Inline text={item} {...rest} />
          </li>
        ))}
      </List>
    );
  }
  return (
    <div className="table">
      <table>
        <thead>
          <tr>
            {block.head.map((h, i) => (
              <th key={i}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, c) => (
                <td key={c}>
                  <Inline text={cell} {...rest} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SEVERITY_ORDER = { high: 0, medium: 1, low: 2 } as const;

function Notes({
  notes,
  sections,
  focus,
  onFocus,
  onState,
  onClose,
}: {
  notes: ReviewNote[];
  sections: Section[];
  focus: string | null;
  onFocus: (id: string) => void;
  onState: (id: string, s: NoteState, userNote?: string) => void;
  onClose: () => void;
}) {
  const [showDone, setShowDone] = useState(false);
  const open = useMemo(
    () =>
      notes
        .filter((n) => OPEN_STATES.includes(n.state))
        .sort(
          (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
        ),
    [notes],
  );
  const done = notes.filter((n) => !OPEN_STATES.includes(n.state));
  const accepted = notes.filter(
    (n) => n.state === "accepted" || n.state === "modified",
  ).length;
  const num = (id: string) => sections.find((s) => s.id === id)?.num ?? "";

  return (
    <div className="notes">
      <header className="side__head">
        <h2 className="side__title">审查意见</h2>
        <button
          type="button"
          className="icon-btn"
          onClick={onClose}
          aria-label="关闭审查意见"
        >
          <Icon name="close" />
        </button>
      </header>
      <p className="side__sub">技术、体验、商业三方审查 · 今天 13:58</p>

      {open.length === 0 ? (
        <div className="calm">
          <span className="calm__mark" aria-hidden="true" />
          <p>没有待处理的意见。</p>
        </div>
      ) : (
        <ol className="nlist">
          {open.map((n) => (
            <NoteItem
              key={n.id}
              note={n}
              num={num(n.section)}
              open={focus === n.id}
              onOpen={() => onFocus(n.id)}
              onState={onState}
            />
          ))}
        </ol>
      )}

      {accepted > 0 && (
        <div className="apply">
          <p>
            已采纳 {accepted} 条。AI 只会按这些意见修改，修改前先给你看改动。
          </p>
          <button
            type="button"
            className="btn btn--ghost btn--small"
            title="原型中不执行"
          >
            按采纳的意见修改
          </button>
        </div>
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
            已处理 {done.length}
          </button>
          {showDone && (
            <ol className="nlist nlist--done">
              {done.map((n) => (
                <li key={n.id} className="ndone">
                  <span className="ndone__title">{n.title}</span>
                  <span className="ndone__state">
                    {NOTE_STATE_TEXT[n.state]}
                    {n.state !== "resolved" && (
                      <button
                        type="button"
                        className="btn btn--text"
                        onClick={() => onState(n.id, "open")}
                      >
                        撤销
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </div>
  );
}

function NoteItem({
  note,
  num,
  open,
  onOpen,
  onState,
}: {
  note: ReviewNote;
  num: string;
  open: boolean;
  onOpen: () => void;
  onState: (id: string, s: NoteState, userNote?: string) => void;
}) {
  const ref = useRef<HTMLLIElement>(null);
  const [modifying, setModifying] = useState(false);
  const [text, setText] = useState(note.userNote ?? "");
  useEffect(() => {
    if (open)
      ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    else setModifying(false);
  }, [open]);

  return (
    <li
      ref={ref}
      className={`note note--${note.severity}${open ? " is-open" : ""}`}
    >
      <button
        type="button"
        className="note__head"
        aria-expanded={open}
        onClick={onOpen}
      >
        <span className="note__meta">
          <span className="note__sev">{SEVERITY_TEXT[note.severity]}</span>
          <span>
            {REVIEWER_TEXT[note.reviewer]} · 第 {num} 节
          </span>
          {note.state === "recheck" && (
            <span className="note__recheck">{NOTE_STATE_TEXT.recheck}</span>
          )}
        </span>
        <span className="note__title">{note.title}</span>
      </button>
      {open && (
        <div className="note__body">
          <blockquote className="note__quote">{note.quote}</blockquote>
          <p>{note.problem}</p>
          <p className="note__suggest">
            <span>建议</span>
            {note.suggestion}
          </p>
          {note.state === "recheck" && (
            <p className="quiet">你修改过这一节，意见可能已经不适用。</p>
          )}
          {modifying ? (
            <div className="note__modify">
              <textarea
                className="field field--small"
                rows={2}
                value={text}
                autoFocus
                placeholder="说明你希望怎么改"
                aria-label="修改意见"
                onChange={(e) => setText(e.target.value)}
              />
              <span className="note__actions">
                <button
                  type="button"
                  className="btn btn--text"
                  onClick={() => setModifying(false)}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="btn btn--small"
                  disabled={!text.trim()}
                  onClick={() => onState(note.id, "modified", text.trim())}
                >
                  按我的意见采纳
                </button>
              </span>
            </div>
          ) : (
            <span className="note__actions">
              <button
                type="button"
                className="btn btn--small"
                onClick={() => onState(note.id, "accepted")}
              >
                采纳
              </button>
              <button
                type="button"
                className="btn btn--text"
                onClick={() => setModifying(true)}
              >
                修改后采纳
              </button>
              <button
                type="button"
                className="btn btn--text"
                onClick={() => onState(note.id, "later")}
              >
                稍后
              </button>
              <button
                type="button"
                className="btn btn--text"
                onClick={() => onState(note.id, "dismissed")}
              >
                忽略
              </button>
            </span>
          )}
        </div>
      )}
    </li>
  );
}

function Sources({
  section,
  sections,
  onClose,
  onJump,
}: {
  section: Section | undefined;
  sections: Section[];
  onClose: () => void;
  onJump: (id: string) => void;
}) {
  const impacts = (section?.impacts ?? [])
    .map((id) => sections.find((s) => s.id === id))
    .filter((s): s is Section => Boolean(s));
  return (
    <div className="sources">
      <header className="side__head">
        <h2 className="side__title">
          {section?.num} {section?.title}
        </h2>
        <button
          type="button"
          className="icon-btn"
          onClick={onClose}
          aria-label="关闭来源"
        >
          <Icon name="close" />
        </button>
      </header>
      <p className="side__sub">这一节写了什么，依据是什么，改了会影响哪里。</p>
      <h3 className="label">依据的需求</h3>
      {section && section.sources.length > 0 ? (
        <ul className="srclist">
          {section.sources.map((id) => (
            <li key={id}>
              <span className="srclist__id">{id}</span>
              {SOURCE_TEXT[id] ?? id}
            </li>
          ))}
        </ul>
      ) : (
        <p className="quiet">这一节没有直接关联的需求。</p>
      )}
      <h3 className="label">修改后需要检查</h3>
      {impacts.length > 0 ? (
        <ul className="srclist">
          {impacts.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className="btn btn--text"
                onClick={() => onJump(s.id)}
              >
                {s.num} {s.title}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="quiet">没有记录下游章节。</p>
      )}
    </div>
  );
}
