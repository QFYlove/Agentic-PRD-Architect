import { useEffect, useMemo, useRef, useState } from "react";
import type { ReviewFinding, Section } from "../data/prd";
import {
  FINDING_STATUS_LABEL,
  REVIEW_FINDINGS,
  SECTIONS,
  SEVERITY_LABEL,
  TRACE,
  VERSIONS,
} from "../data/prd";
import type { FindingStatus } from "../data/prd";
import { parseBlocks, parseInline, toMarkdown } from "../lib/blocks";
import type { Block } from "../lib/blocks";
import { Id } from "./Marks";

type Mode = "read" | "diff";
type PanelTab = "findings" | "trace";

const ORIGIN_LABEL: Record<Section["origin"], string> = {
  ai: "AI 生成",
  optimized: "AI 定向优化",
  human: "人工编辑",
};

const DOC_TITLE = "云盘离线下载 · 产品需求文档";

export function Editor() {
  const [sections, setSections] = useState<Section[]>(SECTIONS);
  const [findings, setFindings] = useState<ReviewFinding[]>(REVIEW_FINDINGS);
  const [active, setActive] = useState<string>("s1");
  const [focusFinding, setFocusFinding] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [dirty, setDirty] = useState<Set<string>>(new Set());
  const [version, setVersion] = useState("v3");
  const [mode, setMode] = useState<Mode>("read");
  // On narrow screens the panel overlays the document, so start closed.
  const [panelOpen, setPanelOpen] = useState(() => window.innerWidth >= 1024);
  const [tocOpen, setTocOpen] = useState(false);
  const [tab, setTab] = useState<PanelTab>("findings");
  const [toast, setToast] = useState<string | null>(null);
  const docRef = useRef<HTMLDivElement>(null);

  const readOnly = version !== "v3";
  const activeSection = sections.find((s) => s.id === active);
  const openCount = findings.filter((f) => f.status === "open").length;

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
        if (id && !editing) setActive(id);
      },
      { rootMargin: "-140px 0px -45% 0px" },
    );
    doc
      .querySelectorAll("[data-section]")
      .forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [sections, mode, editing]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 2600);
    return () => window.clearTimeout(t);
  }, [toast]);

  const jump = (id: string) => {
    setActive(id);
    setTocOpen(false);
    document
      .getElementById(`sec-${id}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const showFinding = (id: string) => {
    const f = findings.find((x) => x.id === id);
    if (!f) return;
    setFocusFinding(id);
    setPanelOpen(true);
    setTab("findings");
    jump(f.section);
  };

  const saveSection = (id: string, body: string) => {
    setSections((prev) =>
      prev.map((s) =>
        s.id === id && s.body !== body ? { ...s, body, origin: "human" } : s,
      ),
    );
    const section = sections.find((s) => s.id === id);
    if (section && section.body !== body) {
      setDirty((prev) => new Set(prev).add(id));
      setFindings((prev) =>
        prev.map((f) =>
          f.section === id && f.status === "open"
            ? { ...f, status: "stale" }
            : f,
        ),
      );
      const impacted = section.impacts
        .map((sid) => sections.find((s) => s.id === sid))
        .filter((s): s is Section => Boolean(s))
        .map((s) => `§${s.num} ${s.title}`)
        .join("、");
      setToast(
        impacted
          ? `已保存。修改可能影响 ${impacted}，已加入待检查。`
          : "已保存。",
      );
    }
    setEditing(null);
  };

  const setFindingStatus = (id: string, status: FindingStatus) =>
    setFindings((prev) =>
      prev.map((f) => (f.id === id ? { ...f, status } : f)),
    );

  const exportMd = () => {
    const blob = new Blob([toMarkdown(sections, DOC_TITLE)], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `P-0007-prd-${version}.md`;
    a.click();
    URL.revokeObjectURL(url);
    setToast(`已导出 P-0007-prd-${version}.md`);
  };

  const shownSections =
    mode === "diff" ? sections.filter((s) => s.diff) : sections;

  return (
    <div className={panelOpen ? "ed" : "ed is-panel-closed"}>
      <EditorBar
        version={version}
        mode={mode}
        dirty={dirty.size}
        openCount={openCount}
        panelOpen={panelOpen}
        onVersion={(v) => {
          setVersion(v);
          setEditing(null);
          if (v === "v1") setMode("read");
        }}
        onMode={setMode}
        onExport={exportMd}
        onPanel={() => setPanelOpen((v) => !v)}
        onToc={() => setTocOpen((v) => !v)}
        tocOpen={tocOpen}
      />

      <Toc
        sections={sections}
        findings={findings}
        active={active}
        dirty={dirty}
        open={tocOpen}
        onJump={jump}
      />

      <article className="doc" ref={docRef} aria-label="PRD 正文">
        <header className="doc__head">
          <span className="doc__kicker mono">
            P-0007 · PRD · {version.toUpperCase()}
          </span>
          <h1 className="doc__title">{DOC_TITLE}</h1>
          <dl className="doc__meta">
            <div>
              <dt>基于</dt>
              <dd>Product Brief 确认版 · 11-08 12:56</dd>
            </div>
            <div>
              <dt>版本</dt>
              <dd>{VERSIONS.find((v) => v.id === version)?.source}</dd>
            </div>
            <div>
              <dt>未解决</dt>
              <dd>{openCount} 个问题</dd>
            </div>
          </dl>
          {readOnly && (
            <p className="doc__banner">
              正在查看历史版本 {version}，只读。
              <button
                type="button"
                className="link"
                onClick={() => setVersion("v3")}
              >
                返回当前草稿
              </button>
            </p>
          )}
          {mode === "diff" && (
            <p className="doc__banner doc__banner--diff">
              对比 v2 → v3 · 只显示有改动的章节。
              <span className="diff-key">
                <span className="diff-key__add">+ 新增</span>
                <span className="diff-key__del">− 删除</span>
              </span>
            </p>
          )}
        </header>

        {shownSections.map((section) => (
          <SectionView
            key={section.id}
            section={section}
            mode={mode}
            active={active === section.id}
            editing={editing === section.id}
            readOnly={readOnly}
            dirty={dirty.has(section.id)}
            findings={findings.filter((f) => f.section === section.id)}
            focusFinding={focusFinding}
            onEdit={() => setEditing(section.id)}
            onCancel={() => setEditing(null)}
            onSave={(body) => saveSection(section.id, body)}
            onFinding={showFinding}
            onSelect={() => setActive(section.id)}
          />
        ))}
        <footer className="doc__end mono">
          END OF DOCUMENT · {sections.length} SECTIONS
        </footer>
      </article>

      {panelOpen && (
        <Panel
          tab={tab}
          onTab={setTab}
          section={activeSection}
          sections={sections}
          findings={findings}
          focus={focusFinding}
          onFocus={showFinding}
          onStatus={setFindingStatus}
          onClose={() => setPanelOpen(false)}
        />
      )}

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}

function EditorBar({
  version,
  mode,
  dirty,
  openCount,
  panelOpen,
  tocOpen,
  onVersion,
  onMode,
  onExport,
  onPanel,
  onToc,
}: {
  version: string;
  mode: Mode;
  dirty: number;
  openCount: number;
  panelOpen: boolean;
  tocOpen: boolean;
  onVersion: (v: string) => void;
  onMode: (m: Mode) => void;
  onExport: () => void;
  onPanel: () => void;
  onToc: () => void;
}) {
  return (
    <div className="edbar">
      <button
        type="button"
        className="edbar__toc act"
        aria-expanded={tocOpen}
        onClick={onToc}
      >
        目录
      </button>
      <span className="edbar__num mono" aria-hidden="true">
        04
      </span>
      <span className="edbar__title">PRD 编辑器</span>
      <div className="versions" role="radiogroup" aria-label="版本">
        {VERSIONS.map((v) => (
          <button
            key={v.id}
            type="button"
            role="radio"
            aria-checked={version === v.id}
            className={version === v.id ? "ver is-on" : "ver"}
            onClick={() => onVersion(v.id)}
            title={`${v.source} · ${v.time} · ${v.note}`}
          >
            <span className="mono">{v.label}</span>
            <span className="ver__src">{v.source}</span>
          </button>
        ))}
      </div>
      <div className="seg" role="tablist" aria-label="视图">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "read"}
          className={mode === "read" ? "is-on" : undefined}
          onClick={() => onMode("read")}
        >
          正文
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "diff"}
          className={mode === "diff" ? "is-on" : undefined}
          onClick={() => onMode("diff")}
          disabled={version === "v1"}
        >
          对比 v2
        </button>
      </div>
      <span className="edbar__state">
        {dirty > 0 ? (
          <>
            <i className="dot dot--accent" aria-hidden="true" />
            {dirty} 个章节已人工修改 · 待影响检查
          </>
        ) : (
          <>
            <i className="dot" aria-hidden="true" />
            无未检查的修改
          </>
        )}
      </span>
      <span className="edbar__actions">
        <button
          type="button"
          className="btn btn--line"
          disabled={dirty === 0}
          title="原型中不执行检查"
        >
          检查影响
        </button>
        <button type="button" className="btn btn--line" onClick={onExport}>
          导出 .md
        </button>
        <button
          type="button"
          className="act edbar__panel"
          aria-expanded={panelOpen}
          onClick={onPanel}
        >
          问题 <span className="mono">{openCount}</span>
        </button>
      </span>
    </div>
  );
}

function Toc({
  sections,
  findings,
  active,
  dirty,
  open,
  onJump,
}: {
  sections: Section[];
  findings: ReviewFinding[];
  active: string;
  dirty: Set<string>;
  open: boolean;
  onJump: (id: string) => void;
}) {
  return (
    <nav className={open ? "toc is-open" : "toc"} aria-label="章节目录">
      <span className="toc__label mono">CONTENTS</span>
      <ol>
        {sections.map((s) => {
          const open = findings.filter(
            (f) =>
              f.section === s.id &&
              (f.status === "open" || f.status === "stale"),
          ).length;
          const classes = ["toc__item", `toc__item--l${s.level}`];
          if (active === s.id) classes.push("is-active");
          return (
            <li key={s.id}>
              <button
                type="button"
                className={classes.join(" ")}
                onClick={() => onJump(s.id)}
                aria-current={active === s.id ? "true" : undefined}
              >
                <span className="toc__num mono">{s.num}</span>
                <span className="toc__title">{s.title}</span>
                {dirty.has(s.id) && (
                  <span className="toc__flag toc__flag--edit" title="人工修改">
                    ✎
                  </span>
                )}
                {open > 0 && (
                  <span
                    className="toc__flag mono"
                    title={`${open} 个待处理问题`}
                  >
                    {open}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ol>
      <dl className="toc__stats">
        <div>
          <dt>章节</dt>
          <dd className="mono">{sections.length}</dd>
        </div>
        <div>
          <dt>人工修改</dt>
          <dd className="mono">
            {sections.filter((s) => s.origin === "human").length}
          </dd>
        </div>
      </dl>
    </nav>
  );
}

function SectionView({
  section,
  mode,
  active,
  editing,
  readOnly,
  dirty,
  findings,
  focusFinding,
  onEdit,
  onCancel,
  onSave,
  onFinding,
  onSelect,
}: {
  section: Section;
  mode: Mode;
  active: boolean;
  editing: boolean;
  readOnly: boolean;
  dirty: boolean;
  findings: ReviewFinding[];
  focusFinding: string | null;
  onEdit: () => void;
  onCancel: () => void;
  onSave: (body: string) => void;
  onFinding: (id: string) => void;
  onSelect: () => void;
}) {
  const [draft, setDraft] = useState(section.body);
  useEffect(() => {
    if (editing) setDraft(section.body);
  }, [editing, section.body]);

  const Heading = section.level === 1 ? "h2" : "h3";
  const classes = ["sec", `sec--l${section.level}`];
  if (active) classes.push("is-active");
  if (editing) classes.push("is-editing");
  const open = findings.filter(
    (f) => f.status === "open" || f.status === "stale",
  );

  return (
    <section
      id={`sec-${section.id}`}
      data-section={section.id}
      className={classes.join(" ")}
      onClick={onSelect}
    >
      <div className="sec__gutter" aria-hidden="true">
        <span className="sec__num mono">{section.num}</span>
      </div>
      <div className="sec__main">
        <header className="sec__head">
          <Heading className="sec__title">{section.title}</Heading>
          <span className={`origin origin--${section.origin}`}>
            <i aria-hidden="true" />
            {ORIGIN_LABEL[section.origin]}
            {dirty && " · 未检查"}
          </span>
          {open.length > 0 && (
            <button
              type="button"
              className="sec__flag mono"
              onClick={() => onFinding(open[0]?.id ?? "")}
            >
              {open.length} 问题
            </button>
          )}
          {!readOnly && mode === "read" && !editing && (
            <button
              type="button"
              className="act sec__edit"
              onClick={(e) => {
                e.stopPropagation();
                onEdit();
              }}
            >
              编辑
            </button>
          )}
        </header>

        {mode === "diff" && section.diff ? (
          <DiffView lines={section.diff} />
        ) : editing ? (
          <div className="sec__editor">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={Math.max(4, draft.split("\n").length + 1)}
              aria-label={`编辑 ${section.num} ${section.title}`}
              autoFocus
            />
            <div className="sec__editor-foot">
              <span className="hint mono">
                MARKDOWN · 保存后标记为人工编辑，AI 不会覆盖
              </span>
              <button type="button" className="link" onClick={onCancel}>
                取消
              </button>
              <button
                type="button"
                className="btn btn--small"
                onClick={() => onSave(draft)}
              >
                保存章节
              </button>
            </div>
          </div>
        ) : (
          <div className="sec__body">
            {parseBlocks(section.body).map((block, i) => (
              <BlockView
                key={i}
                block={block}
                focus={focusFinding}
                findings={findings}
                onFinding={onFinding}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function InlineText({
  text,
  focus,
  findings,
  onFinding,
}: {
  text: string;
  focus: string | null;
  findings: ReviewFinding[];
  onFinding: (id: string) => void;
}) {
  return (
    <>
      {parseInline(text).map((part, i) => {
        if (part.kind === "text") return <span key={i}>{part.text}</span>;
        if (part.kind === "fact")
          return (
            <span
              key={i}
              className={`fact fact--${part.label === "用户输入" ? "user" : part.label === "假设" ? "asm" : "open"}`}
            >
              {part.label}
            </span>
          );
        const f = findings.find((x) => x.id === part.id);
        const resolved =
          f && (f.status === "resolved" || f.status === "rejected");
        if (!f || resolved) return <span key={i}>{part.text}</span>;
        return (
          <button
            key={i}
            type="button"
            className={focus === part.id ? "anchor is-focus" : "anchor"}
            data-sev={f.severity}
            onClick={(e) => {
              e.stopPropagation();
              onFinding(part.id);
            }}
          >
            {part.text}
            <sup className="mono">{part.id}</sup>
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
  focus: string | null;
  findings: ReviewFinding[];
  onFinding: (id: string) => void;
}) {
  if (block.kind === "p")
    return (
      <p>
        <InlineText text={block.text} {...rest} />
      </p>
    );
  if (block.kind === "quote")
    return (
      <blockquote>
        <InlineText text={block.text} {...rest} />
      </blockquote>
    );
  if (block.kind === "ol")
    return (
      <ol>
        {block.items.map((item, i) => (
          <li key={i}>
            <InlineText text={item} {...rest} />
          </li>
        ))}
      </ol>
    );
  if (block.kind === "ul")
    return (
      <ul>
        {block.items.map((item, i) => (
          <li key={i}>
            <InlineText text={item} {...rest} />
          </li>
        ))}
      </ul>
    );
  return (
    <div className="table-wrap">
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
                  <InlineText text={cell} {...rest} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DiffView({ lines }: { lines: NonNullable<Section["diff"]> }) {
  return (
    <ol className="diff">
      {lines.map((line, i) => (
        <li key={i} className={`diff__line diff__line--${line.kind}`}>
          <span
            className="diff__sign mono"
            aria-label={
              line.kind === "add"
                ? "新增"
                : line.kind === "del"
                  ? "删除"
                  : "未修改"
            }
          >
            {line.kind === "add" ? "+" : line.kind === "del" ? "−" : " "}
          </span>
          <span className="diff__text">{line.text.replace(/^- /, "")}</span>
          {line.reason && (
            <span className="diff__reason mono">{line.reason}</span>
          )}
        </li>
      ))}
    </ol>
  );
}

const REVIEWERS = ["ALL", "TECH", "UX", "BIZ"] as const;

function Panel({
  tab,
  onTab,
  section,
  sections,
  findings,
  focus,
  onFocus,
  onStatus,
  onClose,
}: {
  tab: PanelTab;
  onTab: (t: PanelTab) => void;
  section: Section | undefined;
  sections: Section[];
  findings: ReviewFinding[];
  focus: string | null;
  onFocus: (id: string) => void;
  onStatus: (id: string, s: FindingStatus) => void;
  onClose: () => void;
}) {
  const [reviewer, setReviewer] = useState<(typeof REVIEWERS)[number]>("ALL");
  const [scope, setScope] = useState<"section" | "all">("all");

  const list = useMemo(() => {
    const order: Record<string, number> = {
      must_fix: 0,
      should_fix: 1,
      optional: 2,
    };
    return findings
      .filter((f) => reviewer === "ALL" || f.reviewer === reviewer)
      .filter((f) => scope === "all" || f.section === section?.id)
      .sort((a, b) => {
        const done = (f: ReviewFinding) =>
          f.status === "resolved" || f.status === "rejected" ? 1 : 0;
        return (
          done(a) - done(b) ||
          (order[a.severity] ?? 0) - (order[b.severity] ?? 0)
        );
      });
  }, [findings, reviewer, scope, section]);

  const sectionNum = (id: string) =>
    sections.find((s) => s.id === id)?.num ?? "";
  const trace = section ? TRACE[section.id] : undefined;
  const impacts = section?.impacts
    .map((id) => sections.find((s) => s.id === id))
    .filter(Boolean) as Section[] | undefined;

  return (
    <aside className="panel" aria-label="问题与关联需求">
      <div className="panel__tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "findings"}
          className={tab === "findings" ? "is-on" : undefined}
          onClick={() => onTab("findings")}
        >
          审查问题
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "trace"}
          className={tab === "trace" ? "is-on" : undefined}
          onClick={() => onTab("trace")}
        >
          需求追溯
        </button>
        <button
          type="button"
          className="panel__close act"
          onClick={onClose}
          aria-label="收起面板"
        >
          收起
        </button>
      </div>

      {tab === "findings" ? (
        <>
          <div className="panel__filters">
            <span className="seg" aria-label="按评审筛选">
              {REVIEWERS.map((r) => (
                <button
                  key={r}
                  type="button"
                  className={reviewer === r ? "is-on" : undefined}
                  onClick={() => setReviewer(r)}
                >
                  {r === "ALL" ? "全部" : r}
                </button>
              ))}
            </span>
            <label className="check">
              <input
                type="checkbox"
                checked={scope === "section"}
                onChange={(e) => setScope(e.target.checked ? "section" : "all")}
              />
              仅当前章节 {section?.num}
            </label>
          </div>
          {list.length === 0 ? (
            <div className="empty empty--small">
              <span className="empty__glyph" aria-hidden="true" />
              <p>这个范围内没有问题。评审允许零问题。</p>
            </div>
          ) : (
            <ol className="flist">
              {list.map((f) => (
                <FindingRecord
                  key={f.id}
                  finding={f}
                  num={sectionNum(f.section)}
                  focus={focus === f.id}
                  onFocus={() => onFocus(f.id)}
                  onStatus={onStatus}
                />
              ))}
            </ol>
          )}
        </>
      ) : (
        <div className="trace">
          <p className="trace__lead">
            <span className="mono">§{section?.num}</span> {section?.title}
          </p>
          <h3 className="trace__h mono">SOURCE · 需求来源</h3>
          {section && section.requirements.length > 0 ? (
            <ul className="trace__reqs">
              {section.requirements.map((r) => (
                <li key={r}>
                  <Id>{r}</Id>
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">此章节没有直接关联的基线条目。</p>
          )}
          {trace && (
            <>
              <h3 className="trace__h mono">CHAIN · 追溯链</h3>
              <ol className="chain">
                {trace.map((n) => (
                  <li key={n.id}>
                    <span className="chain__kind">{n.kind}</span>
                    <Id>{n.id}</Id>
                    <span className="chain__text">{n.text}</span>
                  </li>
                ))}
              </ol>
            </>
          )}
          <h3 className="trace__h mono">IMPACT · 修改后需检查</h3>
          {impacts && impacts.length > 0 ? (
            <ul className="trace__impacts">
              {impacts.map((s) => (
                <li key={s.id}>
                  <span className="mono">{s.num}</span> {s.title}
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">没有记录下游章节。</p>
          )}
        </div>
      )}
    </aside>
  );
}

const STATUS_ACTIONS: { status: FindingStatus; label: string }[] = [
  { status: "accepted", label: "采纳" },
  { status: "modified", label: "修改后采纳" },
  { status: "deferred", label: "暂缓" },
  { status: "rejected", label: "拒绝" },
];

function FindingRecord({
  finding,
  num,
  focus,
  onFocus,
  onStatus,
}: {
  finding: ReviewFinding;
  num: string;
  focus: boolean;
  onFocus: () => void;
  onStatus: (id: string, s: FindingStatus) => void;
}) {
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (focus)
      ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [focus]);
  const done = finding.status === "resolved" || finding.status === "rejected";
  const classes = ["frec", `frec--${finding.severity}`, `is-${finding.status}`];
  if (focus) classes.push("is-focus");
  return (
    <li ref={ref} className={classes.join(" ")}>
      <button type="button" className="frec__head" onClick={onFocus}>
        <span
          className="frec__sev"
          aria-label={SEVERITY_LABEL[finding.severity]}
        />
        <span className="frec__id mono">{finding.id}</span>
        <span className="frec__who mono">{finding.reviewer}</span>
        <span className="frec__sec mono">§{num}</span>
        <span className="frec__status">
          {FINDING_STATUS_LABEL[finding.status]}
        </span>
      </button>
      <p className="frec__title">{finding.title}</p>
      {focus && (
        <div className="frec__body">
          <blockquote className="frec__evidence">{finding.evidence}</blockquote>
          <p>{finding.problem}</p>
          <p className="frec__rec">
            <span className="mono">FIX</span> {finding.recommendation}
          </p>
          {!done && (
            <div className="frec__actions">
              {STATUS_ACTIONS.map((a) => (
                <button
                  key={a.status}
                  type="button"
                  className={
                    finding.status === a.status
                      ? "act is-on"
                      : a.status === "accepted"
                        ? "act act--yes"
                        : "act"
                  }
                  onClick={() => onStatus(finding.id, a.status)}
                >
                  {a.label}
                </button>
              ))}
            </div>
          )}
          {(finding.status === "accepted" || finding.status === "modified") && (
            <p className="hint">
              已加入下一轮定向优化。只有采纳的问题会被修改。
            </p>
          )}
          {finding.status === "stale" && (
            <p className="hint">章节已被人工修改，需要重新验证。</p>
          )}
        </div>
      )}
    </li>
  );
}
