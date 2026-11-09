import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import type React from "react";
import {
  CURRENT_ROUND,
  DRAFT_ANSWERS,
  FINDINGS,
  GROUPS,
  INITIAL_ITEMS,
  NEXT_ROUND,
  TURNS,
} from "../data/explore";
import type {
  BaselineItem,
  ExploreFinding,
  ExploreFindingStatus,
  Extraction,
  ItemStatus,
  Question,
  QuestionState,
  Turn,
} from "../data/types";
import { FINDING_KIND } from "../data/types";
import { Baseline } from "./Baseline";
import { Id, PriorityTag } from "./Marks";

type MobileView = "talk" | "baseline";

interface Round {
  round: number;
  summary: string;
  questions: Question[];
  findings: string[];
}

export function Exploration({ onOpenEditor }: { onOpenEditor: () => void }) {
  const [items, setItems] = useState<BaselineItem[]>(INITIAL_ITEMS);
  const [findings, setFindings] = useState<ExploreFinding[]>(FINDINGS);
  const [turns, setTurns] = useState<Turn[]>(TURNS);
  const [round, setRound] = useState<Round>(CURRENT_ROUND);
  const [answers, setAnswers] = useState<Record<string, string>>(DRAFT_ANSWERS);
  const [qstate, setQstate] = useState<Record<string, QuestionState>>({});
  const [linked, setLinked] = useState<string | null>(null);
  const [fresh, setFresh] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [mobile, setMobile] = useState<MobileView>("talk");

  const rootRef = useRef<HTMLDivElement>(null);
  const talkEndRef = useRef<HTMLDivElement>(null);
  const sourceRef = useRef<HTMLElement | null>(null);

  const link = useCallback((id: string | null, el?: HTMLElement | null) => {
    sourceRef.current = el ?? null;
    setLinked(id);
  }, []);

  const itemById = useMemo(() => new Map(items.map((i) => [i.id, i])), [items]);

  const setItemStatus = useCallback((id: string, status: ItemStatus) => {
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, status } : i)));
  }, []);

  const editItem = useCallback(
    (id: string, content: string) => {
      setItems((prev) =>
        prev.map((i) =>
          i.id === id && i.content !== content
            ? {
                ...i,
                content,
                status: "confirmed",
                source: { kind: "user", round: round.round },
                history: [...(i.history ?? []), i.content],
              }
            : i,
        ),
      );
    },
    [round.round],
  );

  const setFindingStatus = useCallback(
    (id: string, status: ExploreFindingStatus) => {
      setFindings((prev) =>
        prev.map((f) => (f.id === id ? { ...f, status } : f)),
      );
    },
    [],
  );

  const submit = () => {
    const answered = round.questions.filter(
      (q) =>
        (answers[q.id] ?? "").trim() &&
        qstate[q.id] !== "skipped" &&
        qstate[q.id] !== "unknown",
    );
    const skipped = round.questions
      .filter((q) => !answered.includes(q))
      .map((q) => q.id);
    if (answered.length === 0 && skipped.length === 0) return;

    const text = answered.map((q) => (answers[q.id] ?? "").trim()).join(" ");
    const extracted: Extraction[] = [];
    const created: BaselineItem[] = [];
    let n = items.filter((i) => i.group === "decision").length;
    for (const q of answered) {
      n += 1;
      const id = `DEC-${String(n).padStart(2, "0")}`;
      created.push({
        id,
        group: q.target === "feature" ? "decision" : q.target,
        content: (answers[q.id] ?? "").trim(),
        status: "proposed",
        source: { kind: "user", round: round.round },
      });
      extracted.push({ id, action: "created" });
    }
    const openId = `OPEN-${String(items.filter((i) => i.group === "open").length + 1).padStart(2, "0")}`;
    if (answered.some((q) => q.id === "Q-06")) {
      created.push({
        id: openId,
        group: "open",
        content: "免费用户每日流量上限的具体额度。",
        status: "open",
        source: { kind: "ai", round: round.round },
      });
      extracted.push({ id: openId, action: "created" });
    }

    setBusy(true);
    setTurns((prev) => [
      ...prev,
      {
        kind: "ai",
        round: round.round,
        summary: round.summary,
        questions: round.questions,
        findings: round.findings,
      },
      {
        kind: "user",
        round: round.round,
        text: text || "（本轮跳过）",
        extracted,
        ...(skipped.length ? { skipped } : {}),
      },
    ]);
    setItems((prev) => [...prev, ...created]);
    setFresh(created.map((c) => c.id));
    if (answered.some((q) => q.finding === "F-02"))
      setFindingStatus("F-02", "accepted");
    if (answered.some((q) => q.finding === "F-01"))
      setFindingStatus("F-01", "accepted");

    window.setTimeout(() => {
      setRound({
        round: round.round + 1,
        summary: NEXT_ROUND.summary,
        questions: NEXT_ROUND.questions,
        findings: ["F-03"],
      });
      setAnswers({});
      setQstate({});
      setBusy(false);
      talkEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }, 900);
    window.setTimeout(() => setFresh([]), 3200);
  };

  const progress = useMemo(() => {
    return GROUPS.map((g) => {
      const list = items.filter(
        (i) => i.group === g.key && i.status !== "rejected",
      );
      const confirmed = list.filter((i) => i.status === "confirmed").length;
      return { ...g, total: list.length, confirmed };
    });
  }, [items]);

  const answeredCount = round.questions.filter(
    (q) => (answers[q.id] ?? "").trim() && !qstate[q.id],
  ).length;
  const handledCount = round.questions.filter(
    (q) => qstate[q.id] === "skipped" || qstate[q.id] === "unknown",
  ).length;

  return (
    <div className="ex" ref={rootRef} data-mobile={mobile}>
      <ProgressRail
        progress={progress}
        round={round.round}
        onOpenEditor={onOpenEditor}
        findings={findings}
      />

      <div className="ex-switch" role="tablist" aria-label="切换视图">
        <button
          type="button"
          role="tab"
          aria-selected={mobile === "talk"}
          onClick={() => setMobile("talk")}
        >
          对话 <span className="mono">R{round.round}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mobile === "baseline"}
          onClick={() => setMobile("baseline")}
        >
          需求基线{" "}
          <span className="mono">
            {items.filter((i) => i.status !== "rejected").length}
          </span>
        </button>
      </div>

      <section className="talk" aria-label="需求探索对话">
        <header className="talk__head">
          <span className="sec-head__num">02</span>
          <div>
            <h1 className="talk__title">需求探索</h1>
            <p className="talk__sub">
              AI 每轮提出 1～3
              个问题，并说明为什么问。回答会同步到右侧的需求基线。
            </p>
          </div>
        </header>

        <ol className="turns">
          {turns.map((turn, i) => (
            <TurnView
              key={i}
              turn={turn}
              itemById={itemById}
              findings={findings}
              linked={linked}
              onLink={link}
            />
          ))}
        </ol>

        <CurrentRound
          round={round}
          answers={answers}
          qstate={qstate}
          busy={busy}
          findings={findings}
          linked={linked}
          onLink={link}
          onAnswer={(id, v) => setAnswers((prev) => ({ ...prev, [id]: v }))}
          onState={(id, s) =>
            setQstate((prev) => {
              const next = { ...prev };
              if (s === "pending") delete next[id];
              else next[id] = s;
              return next;
            })
          }
          onSubmit={submit}
          answeredCount={answeredCount}
          handledCount={handledCount}
        />
        <div ref={talkEndRef} />
      </section>

      <Baseline
        items={items}
        findings={findings}
        linked={linked}
        fresh={fresh}
        onLink={link}
        onStatus={setItemStatus}
        onEdit={editItem}
        onFinding={setFindingStatus}
      />

      <Connector root={rootRef} source={sourceRef} linked={linked} />
    </div>
  );
}

type LinkFn = (id: string | null, el?: HTMLElement | null) => void;

function RefChip({
  id,
  action,
  label,
  linked,
  onLink,
}: {
  id: string;
  action?: Extraction["action"] | undefined;
  label?: string | undefined;
  linked: string | null;
  onLink: LinkFn;
}) {
  const focus = (el: HTMLElement) => {
    onLink(id, el);
    document
      .querySelector(`.baseline [data-item="${id}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  return (
    <button
      type="button"
      className={linked === id ? "ref is-linked" : "ref"}
      data-ref={id}
      onMouseEnter={(e) => onLink(id, e.currentTarget)}
      onMouseLeave={() => onLink(null)}
      onFocus={(e) => onLink(id, e.currentTarget)}
      onBlur={() => onLink(null)}
      onClick={(e) => focus(e.currentTarget)}
    >
      {action && (
        <span className="ref__op">{action === "created" ? "+" : "~"}</span>
      )}
      <span className="mono">{id}</span>
      {label && <span className="ref__label">{label}</span>}
    </button>
  );
}

function TurnView({
  turn,
  itemById,
  findings,
  linked,
  onLink,
}: {
  turn: Turn;
  itemById: Map<string, BaselineItem>;
  findings: ExploreFinding[];
  linked: string | null;
  onLink: LinkFn;
}) {
  if (turn.kind === "user") {
    return (
      <li className="turn turn--user">
        <span className="turn__who mono">你 · R{turn.round}</span>
        <div className="turn__body">
          <p className="turn__text">{turn.text}</p>
          {turn.skipped && (
            <p className="turn__skipped mono">
              跳过 {turn.skipped.join("、")} · 已记为待确认
            </p>
          )}
          {turn.extracted.length > 0 && (
            <div className="extract" aria-label="写入需求基线">
              <span className="extract__label mono">→ BASELINE</span>
              {turn.extracted.map((e) => (
                <RefChip
                  key={e.id}
                  id={e.id}
                  action={e.action}
                  label={itemById.get(e.id) ? undefined : "已移除"}
                  linked={linked}
                  onLink={onLink}
                />
              ))}
            </div>
          )}
        </div>
      </li>
    );
  }
  return (
    <li className="turn turn--ai">
      <span className="turn__who mono">AI · R{turn.round}</span>
      <div className="turn__body">
        <p className="turn__text">{turn.summary}</p>
        <ol className="asked">
          {turn.questions.map((q) => (
            <li key={q.id}>
              <span className="mono">{q.id}</span>
              <PriorityTag priority={q.priority} />
              <span>{q.text}</span>
            </li>
          ))}
        </ol>
        {turn.findings.length > 0 && (
          <div className="extract">
            <span className="extract__label mono">FINDING</span>
            {turn.findings.map((id) => {
              const f = findings.find((x) => x.id === id);
              return (
                <RefChip
                  key={id}
                  id={id}
                  label={f ? FINDING_KIND[f.kind].code : undefined}
                  linked={linked}
                  onLink={onLink}
                />
              );
            })}
          </div>
        )}
      </div>
    </li>
  );
}

function CurrentRound({
  round,
  answers,
  qstate,
  busy,
  findings,
  linked,
  onLink,
  onAnswer,
  onState,
  onSubmit,
  answeredCount,
  handledCount,
}: {
  round: Round;
  answers: Record<string, string>;
  qstate: Record<string, QuestionState>;
  busy: boolean;
  findings: ExploreFinding[];
  linked: string | null;
  onLink: LinkFn;
  onAnswer: (id: string, value: string) => void;
  onState: (id: string, state: QuestionState) => void;
  onSubmit: () => void;
  answeredCount: number;
  handledCount: number;
}) {
  const total = round.questions.length;
  return (
    <section
      className={busy ? "now is-busy" : "now"}
      aria-labelledby="now-title"
    >
      <header className="now__head">
        <span className="now__round mono">
          ROUND {String(round.round).padStart(2, "0")}
        </span>
        <h2 id="now-title" className="now__title">
          本轮问题
        </h2>
        <span className="now__count mono">
          {answeredCount + handledCount}/{total}
        </span>
      </header>
      <p className="now__summary">{round.summary}</p>

      <ol className="qs">
        {round.questions.map((q, i) => {
          const state = qstate[q.id];
          const finding = q.finding
            ? findings.find((f) => f.id === q.finding)
            : undefined;
          return (
            <li key={q.id} className={state ? `q is-${state}` : "q"}>
              <div className="q__index" aria-hidden="true">
                {String(i + 1).padStart(2, "0")}
              </div>
              <div className="q__main">
                <div className="q__meta">
                  <Id>{q.id}</Id>
                  <PriorityTag priority={q.priority} />
                  {finding && (
                    <RefChip
                      id={finding.id}
                      label={FINDING_KIND[finding.kind].label}
                      linked={linked}
                      onLink={onLink}
                    />
                  )}
                </div>
                <p className="q__text">{q.text}</p>
                <p className="q__purpose">
                  <span className="mono">WHY</span> {q.purpose}
                </p>
                {state ? (
                  <div className="q__handled">
                    <span>
                      {state === "skipped"
                        ? "已跳过，记为待确认事项"
                        : "暂时不知道，记为待确认事项"}
                    </span>
                    <button
                      type="button"
                      className="link"
                      onClick={() => onState(q.id, "pending")}
                    >
                      撤销
                    </button>
                  </div>
                ) : (
                  <>
                    <textarea
                      className="q__input"
                      rows={2}
                      value={answers[q.id] ?? ""}
                      placeholder="用自己的话回答，不需要完整……"
                      aria-label={`回答 ${q.id}`}
                      onChange={(e) => onAnswer(q.id, e.target.value)}
                      disabled={busy}
                    />
                    <div className="q__actions">
                      <button
                        type="button"
                        className="link"
                        onClick={() => onState(q.id, "unknown")}
                        disabled={busy}
                      >
                        暂时不知道
                      </button>
                      <button
                        type="button"
                        className="link"
                        onClick={() => onState(q.id, "skipped")}
                        disabled={busy}
                      >
                        跳过
                      </button>
                    </div>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      <footer className="now__foot">
        <span className="hint">
          {busy
            ? "正在整理回答，更新需求基线……"
            : "回答会写入基线，状态为「AI 建议」，由你确认后生效。"}
        </span>
        <button
          type="button"
          className="btn btn--primary"
          onClick={onSubmit}
          disabled={busy || answeredCount + handledCount === 0}
        >
          {busy ? "处理中" : "提交本轮"}
          <span aria-hidden="true">→</span>
        </button>
      </footer>
      {busy && <span className="now__scan" aria-hidden="true" />}
    </section>
  );
}

function ProgressRail({
  progress,
  round,
  findings,
  onOpenEditor,
}: {
  progress: {
    key: string;
    index: string;
    title: string;
    priority: string;
    total: number;
    confirmed: number;
  }[];
  round: number;
  findings: ExploreFinding[];
  onOpenEditor: () => void;
}) {
  const p0 = progress.filter((p) => p.priority === "P0");
  const p0Ready = p0.filter((p) => p.confirmed > 0).length;
  const openFindings = findings.filter((f) => f.status === "open").length;
  return (
    <aside className="rail" aria-label="探索进度">
      <div className="rail__block">
        <span className="rail__label mono">ROUND</span>
        <span className="rail__big">{String(round).padStart(2, "0")}</span>
      </div>
      <ol className="rail__groups">
        {progress.map((p) => (
          <li
            key={p.key}
            className={
              p.confirmed > 0 ? "is-done" : p.total > 0 ? "is-part" : undefined
            }
            title={`${p.title}：${p.confirmed}/${p.total} 已确认`}
          >
            <span className="mono">{p.index}</span>
            <span className="rail__name">{p.title}</span>
            <span className="rail__bar" aria-hidden="true" />
          </li>
        ))}
      </ol>
      <dl className="rail__summary">
        <div>
          <dt>P0 信息</dt>
          <dd className="mono">
            {p0Ready}/{p0.length}
          </dd>
        </div>
        <div>
          <dt>待处理发现</dt>
          <dd className="mono">{openFindings}</dd>
        </div>
      </dl>
      <button
        type="button"
        className="btn btn--line rail__next"
        onClick={onOpenEditor}
      >
        生成 Brief
        <span aria-hidden="true">→</span>
      </button>
      <p className="rail__note">原型中此按钮直接打开 PRD 编辑器。</p>
    </aside>
  );
}

interface Path {
  d: string;
  a: [number, number];
  b: [number, number];
}

/**
 * Draws an orthogonal leader line from the hovered reference to its
 * counterpart on the other side (conversation ↔ baseline). Wide layouts only.
 */
function Connector({
  root,
  source,
  linked,
}: {
  root: React.RefObject<HTMLDivElement>;
  source: React.MutableRefObject<HTMLElement | null>;
  linked: string | null;
}) {
  const [path, setPath] = useState<Path | null>(null);

  useLayoutEffect(() => {
    if (!linked) {
      setPath(null);
      return;
    }
    const measure = () => {
      const el = source.current;
      const host = root.current;
      if (!el || !host || window.innerWidth < 1024) return setPath(null);
      const inBaseline = Boolean(el.closest(".baseline"));
      const selector = inBaseline
        ? `.talk [data-ref="${linked}"]`
        : `.baseline [data-item="${linked}"]`;
      const candidates = Array.from(
        host.querySelectorAll<HTMLElement>(selector),
      );
      const target = inBaseline
        ? candidates[candidates.length - 1]
        : candidates[0];
      if (!target) return setPath(null);
      const s = el.getBoundingClientRect();
      const t = target.getBoundingClientRect();
      const visible = (r: DOMRect) =>
        r.bottom > 0 && r.top < window.innerHeight && r.height > 0;
      if (!visible(s) || !visible(t)) return setPath(null);
      const left = inBaseline ? t : s;
      const right = inBaseline ? s : t;
      // Start past the end of the source's text column so the line never
      // crosses neighbouring chips.
      const column = (inBaseline ? target : el)
        .closest(".turn__body, .now")
        ?.getBoundingClientRect();
      const ax = Math.max(left.right, column?.right ?? 0) + 8;
      const ay = left.top + left.height / 2;
      const bx = right.left - 4;
      const by = Math.min(Math.max(right.top + 14, 0), window.innerHeight);
      if (bx <= ax) return setPath(null);
      const mid = bx - 18;
      setPath({
        d: `M${ax} ${ay} H${mid} V${by} H${bx}`,
        a: [ax, ay],
        b: [bx, by],
      });
    };
    measure();
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [linked, root, source]);

  if (!path) return null;
  return (
    <svg className="connector" aria-hidden="true">
      <path d={path.d} />
      <rect x={path.a[0] - 3} y={path.a[1] - 3} width="6" height="6" />
      <rect
        x={path.b[0] - 3}
        y={path.b[1] - 3}
        width="6"
        height="6"
        className="end"
      />
    </svg>
  );
}
