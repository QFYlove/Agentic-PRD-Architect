import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  GROUPS,
  INSIGHTS,
  ITEMS,
  MESSAGES,
  NEXT,
  QUESTIONS,
} from "../data/explore";
import type {
  AnswerState,
  Insight,
  InsightState,
  Item,
  ItemStatus,
  Message,
  Question,
} from "../data/types";
import { INSIGHT_TEXT } from "../data/types";
import { Requirements } from "./Requirements";
import { Icon } from "./ui";

export const NEEDS_DECISION: ItemStatus[] = [
  "inferred",
  "proposed",
  "assumption",
];

/** Lifted into App so the demo keeps its changes when switching spaces. */
export function useExploreState() {
  const [items, setItems] = useState<Item[]>(ITEMS);
  const [insights, setInsights] = useState<Insight[]>(INSIGHTS);
  const [messages, setMessages] = useState<Message[]>(MESSAGES);
  const [questions, setQuestions] = useState<Question[]>(QUESTIONS);
  const [round, setRound] = useState(3);
  const [answers, setAnswers] = useState<Record<string, AnswerState>>(() =>
    Object.fromEntries(
      QUESTIONS.filter((q) => q.draft).map((q) => [
        q.id,
        { kind: "answer", text: q.draft ?? "" } as AnswerState,
      ]),
    ),
  );

  const pendingItems = items.filter((i) => NEEDS_DECISION.includes(i.status));
  const pendingInsights = insights.filter((i) => i.state === "open");
  const pending = pendingItems.length + pendingInsights.length;

  return {
    items,
    setItems,
    insights,
    setInsights,
    messages,
    setMessages,
    questions,
    setQuestions,
    round,
    setRound,
    answers,
    setAnswers,
    pending,
    pendingItems,
    pendingInsights,
  };
}

export type ExploreState = ReturnType<typeof useExploreState>;

export function Explore({ state }: { state: ExploreState }) {
  const {
    items,
    setItems,
    insights,
    setInsights,
    messages,
    setMessages,
    questions,
    setQuestions,
    round,
    setRound,
    answers,
    setAnswers,
  } = state;
  const [busy, setBusy] = useState(false);
  const [highlight, setHighlight] = useState<string[]>([]);
  const [flash, setFlash] = useState<string[]>([]);
  const [panel, setPanel] = useState(() => window.innerWidth >= 1024);
  const endRef = useRef<HTMLDivElement>(null);

  const core = GROUPS.filter((g) => g.core);
  const coreDone = core.filter((g) =>
    items.some((i) => i.group === g.key && i.status === "confirmed"),
  ).length;

  const setInsight = useCallback(
    (id: string, next: InsightState) =>
      setInsights((prev) =>
        prev.map((i) => (i.id === id ? { ...i, state: next } : i)),
      ),
    [setInsights],
  );

  const reveal = (ids: string[]) => {
    setHighlight(ids);
    if (window.innerWidth < 1024) setPanel(true);
    window.setTimeout(() => {
      document
        .querySelector(`[data-item="${ids[0]}"]`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 60);
  };

  const answersRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = answersRef.current;
    if (!el) return;
    const top = el.getBoundingClientRect().top + window.scrollY - 120;
    window.scrollTo({ top: Math.max(0, top), behavior: "instant" });
    // Only on arrival; later rounds scroll with endRef.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (flash.length === 0) return;
    const t = window.setTimeout(() => setFlash([]), 2600);
    return () => window.clearTimeout(t);
  }, [flash]);

  const handled = questions.filter((q) => {
    const a = answers[q.id];
    return a && (a.kind !== "answer" || a.text.trim());
  });

  const submit = () => {
    if (handled.length === 0 || busy) return;
    const added: Item[] = [];
    const nextId = (prefix: string) => {
      const used = [...items, ...added].filter((i) =>
        i.id.startsWith(prefix),
      ).length;
      return `${prefix}-${String(used + 1).padStart(2, "0")}`;
    };
    const parts: string[] = [];
    const skipped: string[] = [];
    for (const q of questions) {
      const a = answers[q.id];
      if (!a) continue;
      if (a.kind === "answer" && a.text.trim()) {
        parts.push(a.text.trim());
        added.push({
          id: nextId("DEC"),
          group: "decision",
          text: a.text.trim(),
          status: "proposed",
          source: "ai",
          round,
          reason: `根据你对「${q.text}」的回答整理。`,
        });
        if (q.id === "Q-06")
          added.push({
            id: nextId("OPEN"),
            group: "open",
            text: "免费用户每日流量上限的具体额度。",
            status: "open",
            source: "ai",
            round,
          });
        if (q.insight) setInsight(q.insight, "accepted");
      } else {
        skipped.push(q.id);
        added.push({
          id: nextId("OPEN"),
          group: "open",
          text: q.text,
          status: "open",
          source: "you",
          round,
        });
      }
    }

    setBusy(true);
    setItems((prev) => [...prev, ...added]);
    setMessages((prev) => [
      ...prev,
      {
        id: `m${prev.length}`,
        from: "you",
        round,
        text: parts.join(" ") || "这一轮先跳过。",
        changes: added.map((a) => ({ item: a.id, kind: "added" as const })),
        ...(skipped.length ? { skipped } : {}),
      },
    ]);
    setQuestions([]);
    setFlash(added.map((a) => a.id));
    window.setTimeout(
      () =>
        endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }),
      50,
    );

    window.setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: `m${prev.length}`,
          from: "ai",
          round: round + 1,
          text: NEXT.text,
        },
      ]);
      setQuestions(NEXT.questions);
      setAnswers({});
      setRound(round + 1);
      setBusy(false);
      window.setTimeout(
        () =>
          endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }),
        50,
      );
    }, 1100);
  };

  return (
    <div className={panel ? "explore has-panel" : "explore"}>
      <section className="talk" aria-label="需求讨论">
        <header className="talk__head">
          <div>
            <h1 className="page-title">需求探索</h1>
            <p className="talk__status">
              第 {round} 轮 · 核心信息已明确 {coreDone}/{core.length}
            </p>
          </div>
          <div className="talk__actions">
            <button
              type="button"
              className="btn btn--ghost"
              title="原型中不执行"
            >
              整理成 Brief
            </button>
            <button
              type="button"
              className={panel ? "btn btn--toggle is-on" : "btn btn--toggle"}
              aria-expanded={panel}
              onClick={() => setPanel((v) => !v)}
            >
              需求
              {!panel && state.pending > 0 && (
                <span className="count">{state.pending}</span>
              )}
            </button>
          </div>
        </header>

        <ol className="thread">
          {messages.map((m) => (
            <MessageView
              key={m.id}
              message={m}
              insights={insights}
              onReveal={reveal}
              onHover={setHighlight}
              onInsight={setInsight}
            />
          ))}
          {busy && (
            <li className="msg msg--ai">
              <span className="msg__who">AI</span>
              <p className="typing" aria-live="polite">
                正在整理你的回答<span aria-hidden="true">…</span>
              </p>
            </li>
          )}
        </ol>

        <div ref={answersRef} />
        {questions.length > 0 && !busy && (
          <Answers
            questions={questions}
            answers={answers}
            insights={insights}
            onChange={(id, a) =>
              setAnswers((prev) => {
                const next = { ...prev };
                if (a) next[id] = a;
                else delete next[id];
                return next;
              })
            }
            onSubmit={submit}
            handled={handled.length}
          />
        )}
        <div ref={endRef} />
      </section>

      {panel && (
        <Requirements
          state={state}
          highlight={highlight}
          flash={flash}
          onInsight={setInsight}
          onClose={() => setPanel(false)}
        />
      )}
    </div>
  );
}

function MessageView({
  message,
  insights,
  onReveal,
  onHover,
  onInsight,
}: {
  message: Message;
  insights: Insight[];
  onReveal: (ids: string[]) => void;
  onHover: (ids: string[]) => void;
  onInsight: (id: string, state: InsightState) => void;
}) {
  if (message.from === "you") {
    const ids = message.changes.map((c) => c.item);
    const added = message.changes.filter((c) => c.kind === "added").length;
    const updated = message.changes.length - added;
    return (
      <li className="msg msg--you">
        <span className="msg__who">你</span>
        <div className="msg__body">
          <p className="msg__text">{message.text}</p>
          {message.changes.length > 0 && (
            <button
              type="button"
              className="trace"
              onMouseEnter={() => onHover(ids)}
              onMouseLeave={() => onHover([])}
              onFocus={() => onHover(ids)}
              onBlur={() => onHover([])}
              onClick={() => onReveal(ids)}
            >
              <span className="trace__line" aria-hidden="true" />
              {added > 0 && `记录了 ${added} 项`}
              {added > 0 && updated > 0 && "，"}
              {updated > 0 && `更新了 ${updated} 项`}
              {message.skipped &&
                `，${message.skipped.length} 个问题记为待确认`}
            </button>
          )}
        </div>
      </li>
    );
  }
  const raised = (message.insights ?? [])
    .map((id) => insights.find((i) => i.id === id))
    .filter((i): i is Insight => Boolean(i));
  return (
    <li className="msg msg--ai">
      <span className="msg__who">AI</span>
      <div className="msg__body">
        <p className="msg__text">{message.text}</p>
        {raised.map((insight) => (
          <InsightNote
            key={insight.id}
            insight={insight}
            initiallyOpen={false}
            onHover={onHover}
            onState={onInsight}
          />
        ))}
      </div>
    </li>
  );
}

const INSIGHT_DONE: Record<InsightState, string> = {
  open: "",
  accepted: "已采纳",
  later: "稍后处理",
  dismissed: "已忽略",
};

/** An AI finding, shown where it came up in the conversation. */
export function InsightNote({
  insight,
  initiallyOpen,
  onHover,
  onState,
}: {
  insight: Insight;
  initiallyOpen: boolean;
  onHover: (ids: string[]) => void;
  onState: (id: string, state: InsightState) => void;
}) {
  const [open, setOpen] = useState(initiallyOpen && insight.state === "open");
  const isOpen = open && insight.state === "open";
  return (
    <div
      className={`insight insight--${insight.kind}${insight.state !== "open" ? " is-done" : ""}`}
      onMouseEnter={() => onHover(insight.related)}
      onMouseLeave={() => onHover([])}
    >
      <button
        type="button"
        className="insight__head"
        aria-expanded={isOpen}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="insight__kind">{INSIGHT_TEXT[insight.kind]}</span>
        <span className="insight__title">{insight.title}</span>
        {insight.state !== "open" && (
          <span className="insight__state">{INSIGHT_DONE[insight.state]}</span>
        )}
      </button>
      {isOpen && (
        <div className="insight__body">
          <p>{insight.basis}</p>
          <p className="insight__suggest">
            <span>建议</span>
            {insight.suggestion}
          </p>
          <div className="insight__actions">
            <button
              type="button"
              className="btn btn--small"
              onClick={() => onState(insight.id, "accepted")}
            >
              采纳
            </button>
            <button
              type="button"
              className="btn btn--text"
              onClick={() => onState(insight.id, "later")}
            >
              稍后
            </button>
            <button
              type="button"
              className="btn btn--text"
              onClick={() => onState(insight.id, "dismissed")}
            >
              忽略
            </button>
          </div>
        </div>
      )}
      {insight.state !== "open" && (
        <button
          type="button"
          className="insight__undo"
          onClick={() => onState(insight.id, "open")}
        >
          撤销
        </button>
      )}
    </div>
  );
}

/** Current round's questions. One question is open at a time. */
function Answers({
  questions,
  answers,
  insights,
  onChange,
  onSubmit,
  handled,
}: {
  questions: Question[];
  answers: Record<string, AnswerState>;
  insights: Insight[];
  onChange: (id: string, a: AnswerState | null) => void;
  onSubmit: () => void;
  handled: number;
}) {
  const firstOpen =
    questions.find((q) => !answers[q.id])?.id ?? questions[0]?.id ?? null;
  const [active, setActive] = useState<string | null>(firstOpen);
  const ordered = useMemo(() => questions, [questions]);

  const advance = (id: string) => {
    const i = ordered.findIndex((q) => q.id === id);
    const next =
      ordered.slice(i + 1).find((q) => !answers[q.id]) ?? ordered[i + 1];
    setActive(next?.id ?? null);
  };

  return (
    <section className="answers" aria-label="本轮问题">
      <p className="answers__label">
        需要你回答 <span>{questions.length} 个问题，可以跳过</span>
      </p>
      <ol>
        {ordered.map((q, index) => {
          const a = answers[q.id];
          const isActive = active === q.id;
          const insight = q.insight
            ? insights.find((i) => i.id === q.insight)
            : undefined;
          const status =
            a?.kind === "skip"
              ? "已跳过"
              : a?.kind === "unsure"
                ? "暂时不确定"
                : a?.text.trim()
                  ? "已回答"
                  : "";
          return (
            <li
              key={q.id}
              className={
                isActive ? "q is-active" : status ? "q is-handled" : "q"
              }
            >
              <button
                type="button"
                className="q__head"
                aria-expanded={isActive}
                onClick={() => setActive(isActive ? null : q.id)}
              >
                <span className="q__num">{index + 1}</span>
                <span className="q__text">{q.text}</span>
                {!isActive && status && (
                  <span className="q__status">
                    {status === "已回答" && <Icon name="check" />}
                    {status}
                  </span>
                )}
              </button>
              {isActive && (
                <div className="q__body">
                  <p className="q__why">
                    {q.why}
                    {insight && (
                      <span className="q__ref">
                        来自「{INSIGHT_TEXT[insight.kind]}」
                      </span>
                    )}
                  </p>
                  {a && a.kind !== "answer" ? (
                    <p className="q__skipped">
                      {a.kind === "skip"
                        ? "已跳过，会记为待确认事项。"
                        : "暂时不确定，会记为待确认事项。"}
                      <button
                        type="button"
                        className="btn btn--text"
                        onClick={() => onChange(q.id, null)}
                      >
                        改为回答
                      </button>
                    </p>
                  ) : (
                    <>
                      <textarea
                        className="field"
                        rows={3}
                        value={a?.kind === "answer" ? a.text : ""}
                        placeholder="用你自己的话回答，不需要很完整"
                        aria-label={q.text}
                        autoFocus
                        onChange={(e) =>
                          onChange(
                            q.id,
                            e.target.value
                              ? { kind: "answer", text: e.target.value }
                              : null,
                          )
                        }
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && (e.metaKey || e.ctrlKey))
                            advance(q.id);
                        }}
                      />
                      <div className="q__actions">
                        <button
                          type="button"
                          className="btn btn--text"
                          onClick={() => onChange(q.id, { kind: "unsure" })}
                        >
                          暂时不确定
                        </button>
                        <button
                          type="button"
                          className="btn btn--text"
                          onClick={() => onChange(q.id, { kind: "skip" })}
                        >
                          跳过
                        </button>
                        <button
                          type="button"
                          className="btn btn--ghost btn--small"
                          onClick={() => advance(q.id)}
                        >
                          {index < ordered.length - 1 ? "下一题" : "完成"}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <div className="answers__foot">
        <span className="quiet">
          已处理 {handled} / {questions.length}
          <span className="answers__hint">
            回答会整理成需求，由你确认后生效
          </span>
        </span>
        <button
          type="button"
          className="btn btn--primary"
          disabled={handled === 0}
          onClick={onSubmit}
        >
          发送回答
          <Icon name="arrow" />
        </button>
      </div>
    </section>
  );
}
