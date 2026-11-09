import { useEffect, useMemo, useRef, useState } from "react";
import { BriefView } from "./Brief";
import { OutlineView } from "./Outline";
import { ReviewPanel } from "./Review";
import { api, errorText, V3Error } from "./api";
import { running, type ProjectStore } from "./store";
import type {
  DiffSection,
  Finding,
  Quality,
  Section,
  Sources,
  VersionDetail,
} from "./types";
import { Icon, Markdown, quoteOf, timeText, useToast, type Mark } from "./ui";

type Side = "notes" | "sources" | "quality";
const MARKED = ["open", "stale", "accepted", "modified"];

export function DocumentSpace({ store }: { store: ProjectStore }) {
  const { data } = store;
  const sections = data.sections?.items ?? [];
  const hasBrief = data.briefs.some((b) => b.confirmed_at !== null);
  const isReview = data.summary?.entry_mode === "review";
  const outlineConfirmed = data.sections?.outline_confirmed ?? false;
  const [view, setView] = useState<"brief" | "doc" | null>(null);

  const natural: "brief" | "outline" | "doc" =
    sections.length === 0 ? "brief" : !outlineConfirmed ? "outline" : "doc";
  const shown = view === "brief" ? "brief" : natural;

  const tabs =
    !isReview && (hasBrief || data.briefs.length > 0) && sections.length > 0;

  const switcher = tabs ? (
    <div className="doc-switch" role="tablist" aria-label="文档">
      <button
        type="button"
        role="tab"
        aria-selected={shown === "brief"}
        onClick={() => setView("brief")}
      >
        Product Brief
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={shown !== "brief"}
        onClick={() => setView("doc")}
      >
        PRD
      </button>
    </div>
  ) : null;

  if (shown === "doc") return <Editor store={store} switcher={switcher} />;
  return (
    <>
      {switcher}
      {shown === "brief" ? (
        <BriefView store={store} />
      ) : (
        <OutlineView store={store} />
      )}
    </>
  );
}

function Editor({
  store,
  switcher,
}: {
  store: ProjectStore;
  switcher: React.ReactNode;
}) {
  const toast = useToast();
  const { data } = store;
  const projectId = data.summary!.id;
  const sections = useMemo(() => data.sections?.items ?? [], [data.sections]);
  const wide = window.innerWidth >= 1200;
  const [outline, setOutline] = useState(wide);
  const [side, setSide] = useState<Side | null>(
    wide && data.findings.length > 0 ? "notes" : null,
  );
  const [active, setActive] = useState<string | null>(
    sections[0]?.code ?? null,
  );
  const [focus, setFocus] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [historic, setHistoric] = useState<VersionDetail | null>(null);
  const [compare, setCompare] = useState<{
    a: number;
    b: number;
    rows: DiffSection[];
  } | null>(null);
  const [menu, setMenu] = useState(false);
  const [sectionFilter, setSectionFilter] = useState<string | null>(null);

  const generating = running(store, "generate");
  const reviewing = running(store, "review");
  const latest = data.versions[0];
  const readOnly = historic !== null || compare !== null;
  const openFindings = data.findings.filter(
    (f) => f.status === "open" || f.status === "stale",
  );
  const failed = sections.filter((s) => s.status === "failed");
  const planned = sections.filter((s) => s.status === "planned");
  const written = sections.filter((s) => s.body.trim()).length;
  const human = sections.filter((s) => s.origin === "human").length;
  const recheck = sections.filter((s) => s.needs_recheck);

  const marksFor = (section: Section): Mark[] =>
    data.findings
      .filter(
        (f) =>
          f.related_sections.includes(section.code) &&
          MARKED.includes(f.status),
      )
      .map((f) => ({
        quote: quoteOf(f.evidence),
        code: f.code,
        severity: f.severity,
      }))
      .filter((m) => m.quote.length >= 2 && section.body.includes(m.quote));

  const openFinding = (code: string) => {
    setFocus(code);
    setSectionFilter(null);
    setSide("notes");
  };

  const jump = (code: string) => {
    setActive(code);
    document
      .getElementById(`sec-${code}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const recheckSections = (codes: string[]) =>
    void store.startJob(() => api.review(projectId, codes), "复查");

  const save = async (section: Section, body: string): Promise<boolean> => {
    try {
      const result = await api.saveSection(section.id, {
        row_version: section.row_version,
        body,
      });
      setEditing(null);
      await store.reload();
      const { impact } = result;
      if (impact.change === "format") {
        toast({ text: "已保存。只改了格式，不需要复查。" });
      } else {
        const names = impact.sections
          .map((code) => sections.find((s) => s.code === code))
          .filter((s): s is Section => Boolean(s))
          .map((s) => `第 ${s.num} 节「${s.title}」`);
        const stale = impact.stale.length
          ? `，${impact.stale.length} 条审查意见需要重新确认`
          : "";
        toast({
          text: names.length
            ? `已保存${stale}。这次修改可能影响 ${names.join("、")}。`
            : `已保存${stale}。`,
          action: {
            label: "复查这些章节",
            run: () => recheckSections([section.code, ...impact.sections]),
          },
        });
      }
      return true;
    } catch (error) {
      if (error instanceof V3Error && error.code === "SECTION_CHANGED") {
        await store.reload();
      }
      toast({ text: errorText(error), error: true });
      return false;
    }
  };

  const exportMd = async () => {
    try {
      const text = await api.exportMarkdown(projectId, historic?.number);
      const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const label = historic
        ? `v${historic.number}`
        : latest
          ? `v${latest.number}`
          : "draft";
      link.href = url;
      link.download = `${(data.sections?.title ?? "PRD").replace(/[\\/:*?"<>|]/g, "")}-${label}.md`;
      link.click();
      URL.revokeObjectURL(url);
      toast({ text: `已导出 ${link.download}` });
    } catch (error) {
      toast({ text: errorText(error), error: true });
    }
  };

  const shown: Section[] = historic
    ? historic.sections.map((s, i) => ({
        ...(sections.find((c) => c.code === s.code) ?? sections[0]!),
        ...s,
        id: `h-${s.code}`,
        position: i,
      }))
    : sections;

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
        {switcher}

        <div className="dtool__version">
          <button
            type="button"
            className="vbtn"
            aria-expanded={menu}
            onClick={() => setMenu((v) => !v)}
            disabled={data.versions.length === 0}
          >
            <b>
              {historic
                ? `v${historic.number}`
                : latest
                  ? `v${latest.number}`
                  : "草稿"}
            </b>
            <span>
              {historic
                ? `${historic.actor} · ${timeText(historic.created_at)}`
                : latest
                  ? `${latest.actor} · ${timeText(latest.created_at)}`
                  : "还没有保存版本"}
            </span>
            {data.versions.length > 0 && <Icon name="down" />}
          </button>
          {menu && (
            <VersionMenu
              store={store}
              current={historic?.number ?? null}
              onPick={async (n) => {
                setMenu(false);
                setCompare(null);
                setEditing(null);
                if (latest && n === latest.number) {
                  setHistoric(null);
                  return;
                }
                setHistoric(await api.version(projectId, n));
              }}
              onCompare={async (a, b) => {
                setMenu(false);
                setHistoric(null);
                setEditing(null);
                const diff = await api.diff(projectId, a, b);
                setCompare({ a, b, rows: diff.sections });
              }}
              onClose={() => setMenu(false)}
            />
          )}
        </div>

        {!readOnly && human > 0 && (
          <span className="dtool__state">
            <i aria-hidden="true" />
            你写过 {human} 个章节
          </span>
        )}
        {generating && (
          <span className="dtool__state dtool__state--busy" aria-live="polite">
            正在生成 {written}/{sections.length}
          </span>
        )}

        <span className="dtool__end">
          {!readOnly && written > 0 && (
            <button
              type="button"
              className="btn btn--text"
              onClick={() => {
                const note =
                  window.prompt("这个版本改了什么？（可选）", "") ?? null;
                if (note === null) return;
                void store.act(
                  () => api.saveVersion(projectId, note),
                  "已保存为新版本。",
                );
              }}
            >
              保存版本
            </button>
          )}
          <button
            type="button"
            className="btn btn--text"
            disabled={written === 0}
            onClick={() => void exportMd()}
          >
            <Icon name="download" />
            导出
          </button>
          <button
            type="button"
            className={
              side === "quality" ? "btn btn--toggle is-on" : "btn btn--toggle"
            }
            aria-expanded={side === "quality"}
            onClick={() => setSide(side === "quality" ? null : "quality")}
          >
            质量
          </button>
          <button
            type="button"
            className={
              side === "notes" ? "btn btn--toggle is-on" : "btn btn--toggle"
            }
            aria-expanded={side === "notes"}
            onClick={() => {
              setSectionFilter(null);
              setSide(side === "notes" ? null : "notes");
            }}
          >
            {reviewing ? "审查中…" : "审查"}
            {openFindings.length > 0 && (
              <span className="count">{openFindings.length}</span>
            )}
          </button>
        </span>
      </div>

      {outline && (
        <nav className="outline" aria-label="目录">
          <ol>
            {shown.map((s) => {
              const open = data.findings.some(
                (f) =>
                  f.related_sections.includes(s.code) &&
                  (f.status === "open" || f.status === "stale"),
              );
              const cls = ["outline__item", `is-l${s.level}`];
              if (active === s.code) cls.push("is-on");
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    className={cls.join(" ")}
                    aria-current={active === s.code ? "true" : undefined}
                    onClick={() => jump(s.code)}
                  >
                    <span className="outline__num">{s.num}</span>
                    <span className="outline__title">{s.title}</span>
                    {s.origin === "human" && (
                      <span className="outline__edited" title="你写过" />
                    )}
                    {(open || s.status === "failed") && (
                      <span className="outline__note" title="需要处理" />
                    )}
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
      )}

      <article className="paper" aria-label="PRD 正文" data-testid="paper">
        {historic && (
          <p className="banner">
            正在查看 v{historic.number}（{historic.note}），只读。
            <button
              type="button"
              className="btn btn--text"
              onClick={() => setHistoric(null)}
            >
              回到当前版本
            </button>
          </p>
        )}
        {compare && (
          <p className="banner">
            v{compare.a} → v{compare.b} 的改动，只显示有变化的章节。
            <button
              type="button"
              className="btn btn--text"
              onClick={() => setCompare(null)}
            >
              退出对比
            </button>
          </p>
        )}
        {!readOnly && failed.length > 0 && !generating && (
          <p className="banner banner--warn" role="alert">
            {failed.length} 个章节没有生成成功，其他章节不受影响。
            <button
              type="button"
              className="btn btn--text"
              onClick={() =>
                void store.startJob(
                  () =>
                    api.generate(
                      projectId,
                      failed.map((s) => s.code),
                    ),
                  "重试",
                )
              }
            >
              重试这些章节
            </button>
          </p>
        )}
        {!readOnly &&
          planned.length > 0 &&
          !generating &&
          failed.length === 0 && (
            <p className="banner">
              还有 {planned.length} 个章节没有内容。
              <button
                type="button"
                className="btn btn--text"
                disabled={running(store)}
                onClick={() =>
                  void store.startJob(() => api.generate(projectId), "生成")
                }
              >
                生成这些章节
              </button>
            </p>
          )}
        {!readOnly && recheck.length > 0 && !reviewing && (
          <p className="banner">
            {recheck.length} 个章节修改后还没有复查。
            <button
              type="button"
              className="btn btn--text"
              disabled={running(store)}
              onClick={() => recheckSections(recheck.map((s) => s.code))}
            >
              只复查这些章节
            </button>
          </p>
        )}

        <header className="paper__head">
          <h1 className="paper__title">{data.sections?.title}</h1>
          <p className="paper__meta">
            {data.summary?.brief_version
              ? `基于 Product Brief v${data.summary.brief_version}`
              : "导入的 PRD"}{" "}
            · {sections.length} 个章节
          </p>
        </header>

        {compare ? (
          compare.rows.length === 0 ? (
            <p className="quiet">两个版本没有差别。</p>
          ) : (
            compare.rows.map((row) => (
              <section key={row.code} className="sec">
                <header className="sec__head">
                  <h2 className="sec__title">
                    <span className="sec__num">{row.num}</span>
                    {row.title}
                  </h2>
                  <span className="sec__by">
                    {row.kind === "added"
                      ? "新增"
                      : row.kind === "removed"
                        ? "删除"
                        : "修改"}
                  </span>
                </header>
                <DiffLines lines={row.lines} />
              </section>
            ))
          )
        ) : (
          shown.map((section) => (
            <SectionView
              key={section.id}
              section={section}
              stream={store.streams[section.code]}
              marks={readOnly ? [] : marksFor(section)}
              editing={editing === section.code}
              canEdit={!readOnly && !generating}
              noteCount={
                data.findings.filter(
                  (f) =>
                    f.related_sections.includes(section.code) &&
                    (f.status === "open" || f.status === "stale"),
                ).length
              }
              onEdit={() => setEditing(section.code)}
              onCancel={() => setEditing(null)}
              onSave={(body) => save(section, body)}
              onMark={openFinding}
              onSources={() => {
                setActive(section.code);
                setSide("sources");
              }}
              onNotes={() => {
                setSectionFilter(section.code);
                setFocus(null);
                setSide("notes");
              }}
              onRetry={() =>
                void store.startJob(
                  () => api.generate(projectId, [section.code]),
                  "重试",
                )
              }
            />
          ))
        )}
      </article>

      {side && (
        <aside className="side" aria-label="侧栏" data-testid={`side-${side}`}>
          {side === "notes" ? (
            <ReviewPanel
              store={store}
              focus={focus}
              sectionFilter={sectionFilter}
              onClearSection={() => setSectionFilter(null)}
              onFocus={(code) => {
                setFocus(code);
                const finding = data.findings.find((f) => f.code === code);
                const target = finding?.related_sections[0];
                if (target) jump(target);
              }}
              onClose={() => setSide(null)}
            />
          ) : side === "sources" ? (
            <SourcesPanel
              section={sections.find((s) => s.code === active) ?? null}
              sections={sections}
              findings={data.findings}
              onJump={jump}
              onClose={() => setSide(null)}
            />
          ) : (
            <QualityPanel
              projectId={projectId}
              version={data.summary?.updated_at ?? ""}
              onClose={() => setSide(null)}
            />
          )}
        </aside>
      )}
    </div>
  );
}

function VersionMenu({
  store,
  current,
  onPick,
  onCompare,
  onClose,
}: {
  store: ProjectStore;
  current: number | null;
  onPick: (n: number) => void;
  onCompare: (a: number, b: number) => void;
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
  const versions = store.data.versions;
  const latest = versions[0];
  return (
    <div className="menu" ref={ref} role="menu">
      <p className="menu__label">版本历史</p>
      {versions.map((v) => {
        const on = (current ?? latest?.number) === v.number;
        return (
          <button
            key={v.id}
            type="button"
            role="menuitemradio"
            aria-checked={on}
            className={on ? "menu__item is-on" : "menu__item"}
            onClick={() => onPick(v.number)}
          >
            <b>v{v.number}</b>
            <span className="menu__main">
              {v.note}
              <span className="quiet">
                {v.actor} · {timeText(v.created_at)}
                {v.finding_codes.length > 0 &&
                  ` · 处理 ${v.finding_codes.join("、")}`}
              </span>
            </span>
            {v === latest && <span className="menu__tag">最新</span>}
          </button>
        );
      })}
      {versions.length > 1 && latest && versions[1] && (
        <>
          <div className="menu__sep" />
          <button
            type="button"
            role="menuitem"
            className="menu__item"
            onClick={() => onCompare(versions[1]!.number, latest.number)}
          >
            <span className="menu__main">与 v{versions[1].number} 对比</span>
          </button>
        </>
      )}
    </div>
  );
}

export function DiffLines({ lines }: { lines: DiffSection["lines"] }) {
  return (
    <ol className="diff">
      {lines.map((line, i) => (
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
          <span className="diff__text">{line.text}</span>
        </li>
      ))}
    </ol>
  );
}

function SectionView({
  section,
  stream,
  marks,
  editing,
  canEdit,
  noteCount,
  onEdit,
  onCancel,
  onSave,
  onMark,
  onSources,
  onNotes,
  onRetry,
}: {
  section: Section;
  stream: string | undefined;
  marks: Mark[];
  editing: boolean;
  canEdit: boolean;
  noteCount: number;
  onEdit: () => void;
  onCancel: () => void;
  onSave: (body: string) => Promise<boolean>;
  onMark: (code: string) => void;
  onSources: () => void;
  onNotes: () => void;
  onRetry: () => void;
}) {
  const [draft, setDraft] = useState(section.body);
  useEffect(() => {
    if (editing) setDraft(section.body);
  }, [editing, section.body]);

  const Heading = section.level === 1 ? "h2" : "h3";
  const classes = ["sec", `sec--l${section.level}`];
  if (editing) classes.push("is-editing");
  const live = stream !== undefined;

  return (
    <section
      id={`sec-${section.code}`}
      data-section={section.code}
      className={classes.join(" ")}
    >
      <header className="sec__head">
        <Heading className="sec__title">
          <span className="sec__num">{section.num}</span>
          {section.title}
        </Heading>
        {section.origin === "human" && <span className="sec__by">你写的</span>}
        {section.origin === "optimized" && (
          <span className="sec__by">按意见修改</span>
        )}
        {section.needs_recheck && <span className="sec__flag">待复查</span>}
        {canEdit && !editing && (
          <span className="sec__tools">
            {noteCount > 0 && (
              <button type="button" className="btn btn--text" onClick={onNotes}>
                意见 {noteCount}
              </button>
            )}
            {section.item_codes.length > 0 && (
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

      {editing ? (
        <div className="sec__editor">
          <textarea
            className="field field--source"
            value={draft}
            rows={Math.max(5, draft.split("\n").length + 1)}
            aria-label={`编辑 ${section.num} ${section.title}`}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey))
                void onSave(draft);
              if (e.key === "Escape") onCancel();
            }}
          />
          <div className="sec__editor-foot">
            <span className="quiet">
              Markdown · 你改过的章节，AI 只能提修改建议，不会直接覆盖
            </span>
            <button type="button" className="btn btn--text" onClick={onCancel}>
              取消
            </button>
            <button
              type="button"
              className="btn btn--small"
              onClick={() => void onSave(draft)}
            >
              保存
            </button>
          </div>
        </div>
      ) : live ? (
        <div className="sec__body sec__body--live" aria-live="polite">
          {stream ? (
            <Markdown body={stream} />
          ) : (
            <p className="typing">正在写这一节…</p>
          )}
        </div>
      ) : section.status === "failed" ? (
        <div className="sec__failed" role="alert">
          <p>这一节没有生成成功：{section.error ?? "AI 没有返回完整内容"}。</p>
          {canEdit && (
            <span>
              <button
                type="button"
                className="btn btn--ghost btn--small"
                onClick={onRetry}
              >
                重试这一节
              </button>
              <button type="button" className="btn btn--text" onClick={onEdit}>
                自己写
              </button>
            </span>
          )}
        </div>
      ) : section.body.trim() ? (
        <div className="sec__body">
          <Markdown body={section.body} marks={marks} onMark={onMark} />
        </div>
      ) : (
        <p className="sec__empty">
          {section.goal || "还没有内容。"}
          {section.status === "generating" && "（等待生成）"}
        </p>
      )}
    </section>
  );
}

function SourcesPanel({
  section,
  sections,
  findings,
  onJump,
  onClose,
}: {
  section: Section | null;
  sections: Section[];
  findings: Finding[];
  onJump: (code: string) => void;
  onClose: () => void;
}) {
  const [sources, setSources] = useState<Sources | null>(null);
  useEffect(() => {
    if (!section) return;
    setSources(null);
    void api
      .sources(section.id)
      .then(setSources)
      .catch(() => setSources(null));
  }, [section]);
  const dependents = section
    ? sections.filter((s) => s.depends.includes(section.num))
    : [];
  const related = findings.filter(
    (f) => section && f.related_sections.includes(section.code),
  );
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
      <p className="side__sub">这一节依据哪些需求，改了会影响哪里。</p>
      <h3 className="label">依据的需求</h3>
      {sources && sources.items.length > 0 ? (
        <ul className="srclist">
          {sources.items.map((item) => (
            <li key={item.code}>
              <span className="srclist__id">{item.code}</span>
              {item.group}：{item.content}
              {item.status !== "confirmed" && (
                <span className="quiet">
                  （{item.status === "open" ? "待确认" : "未确认"}）
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="quiet">
          {sources ? "这一节没有直接关联的需求。" : "正在载入…"}
        </p>
      )}
      <h3 className="label">修改后需要检查</h3>
      {dependents.length > 0 ? (
        <ul className="srclist">
          {dependents.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className="btn btn--text"
                onClick={() => onJump(s.code)}
              >
                {s.num} {s.title}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="quiet">没有章节依赖这一节。</p>
      )}
      {related.length > 0 && (
        <>
          <h3 className="label">相关审查意见</h3>
          <ul className="srclist">
            {related.map((f) => (
              <li key={f.id}>
                <span className="srclist__id">{f.code}</span>
                {f.title}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

const QUALITY_LABELS: [keyof Omit<Quality, "risks">, string, string][] = [
  ["document_quality", "文档质量", "章节完成度和结构检查"],
  ["requirement_maturity", "需求成熟度", "需求中由你确认的比例"],
  ["implementation_readiness", "实施就绪度", "P0 功能覆盖、阻塞问题和待确认项"],
];

function QualityPanel({
  projectId,
  version,
  onClose,
}: {
  projectId: string;
  version: string;
  onClose: () => void;
}) {
  const [quality, setQuality] = useState<Quality | null>(null);
  useEffect(() => {
    void api
      .quality(projectId)
      .then(setQuality)
      .catch(() => setQuality(null));
  }, [projectId, version]);
  return (
    <div className="quality" data-testid="quality">
      <header className="side__head">
        <h2 className="side__title">质量</h2>
        <button
          type="button"
          className="icon-btn"
          onClick={onClose}
          aria-label="关闭质量"
        >
          <Icon name="close" />
        </button>
      </header>
      <p className="side__sub">
        四个视角分别看，不合成一个总分。全部由规则计算，没有数据时不显示数字。
      </p>
      {!quality ? (
        <p className="quiet">正在计算…</p>
      ) : (
        <>
          {QUALITY_LABELS.map(([key, label, hint]) => {
            const view = quality[key];
            return (
              <section key={key} className="qrow">
                <header className="qrow__head">
                  <h3>{label}</h3>
                  <b>{view.value === null ? "—" : view.value}</b>
                </header>
                <p className="quiet">
                  {view.value === null ? view.reason : hint}
                </p>
                <ul>
                  {view.details.map((d) => (
                    <li key={d}>{d}</li>
                  ))}
                </ul>
                {view.formula && (
                  <p className="qrow__formula">{view.formula}</p>
                )}
              </section>
            );
          })}
          <section className="qrow">
            <header className="qrow__head">
              <h3>未解决风险与阻塞</h3>
              <b
                className={quality.risks.blocking > 0 ? "is-alert" : undefined}
              >
                {quality.risks.blocking}
              </b>
            </header>
            <p className="quiet">必须修改且未解决的问题数</p>
            <ul>
              <li>{quality.risks.open_findings} 条待处理的审查意见</li>
              <li>{quality.risks.stale_findings} 条修改后需要重新确认</li>
              <li>{quality.risks.deferred_findings} 条暂缓</li>
              <li>
                需求里 {quality.risks.open_items} 项待确认、
                {quality.risks.assumptions} 项假设
              </li>
              {quality.risks.unverified_evidence > 0 && (
                <li>
                  {quality.risks.unverified_evidence} 条意见的引用在正文中找不到
                </li>
              )}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
