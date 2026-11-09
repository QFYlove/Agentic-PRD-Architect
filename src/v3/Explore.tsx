import { useEffect, useMemo, useRef, useState } from "react";
import { go } from "./App";
import { api } from "./api";
import { Requirements } from "./Requirements";
import { running, type ProjectStore } from "./store";
import type { Finding, FindingStatus, Message, Question } from "./types";
import { Icon, KIND_TEXT } from "./ui";

type Answer =
  | { kind: "answer"; text: string }
  | { kind: "skip" }
  | { kind: "unknown" };

export function ExploreSpace({ store }: { store: ProjectStore }) {
  const { data } = store;
  const project = data.summary!;
  const conversation = data.conversation;
  const [panel, setPanel] = useState(() => window.innerWidth >= 1024);
  const [highlight, setHighlight] = useState<string[]>([]);
  const [revealed, setRevealed] = useState<string[]>([]);
  const answersRef = useRef<HTMLDivElement>(null);
  const busy = running(store);
  const exploring = running(store, "explore");

  const groups = store.meta?.groups ?? [];
  const core = groups.filter((g) => g.core);
  const coreDone = core.filter((g) =>
    data.items.some((i) => i.group === g.key && i.status === "confirmed"),
  ).length;

  const pending = useMemo(
    () =>
      (conversation?.questions ?? []).filter(
        (q) => q.state === "pending" && q.round === conversation?.round,
      ),
    [conversation],
  );

  useEffect(() => {
    if (pending.length > 0) {
      answersRef.current?.scrollIntoView({ block: "nearest" });
    }
    // Scroll once a new round of questions arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending.map((q) => q.id).join()]);

  const decideCount =
    data.items.filter((i) =>
      ["inferred", "proposed", "assumption"].includes(i.status),
    ).length + data.baseline.filter((f) => f.status === "open").length;

  const reveal = (codes: string[]) => {
    setPanel(true);
    setRevealed(codes);
    window.setTimeout(() => setRevealed([]), 2400);
  };

  const toBrief = async () => {
    const draft = data.briefs.find((b) => b.confirmed_at === null);
    if (!draft) {
      await store.act(() => api.draftBrief(project.id));
    }
    go(`p/${project.id}/document`);
  };

  return (
    <div className={panel ? "explore has-panel" : "explore"}>
      <section className="talk" aria-label="需求讨论">
        <header className="talk__head">
          <div>
            <h1 className="page-title">需求探索</h1>
            <p className="talk__status">
              第 {conversation?.round ?? 1} 轮 · 核心信息已确认 {coreDone}/
              {core.length}
            </p>
          </div>
          <div className="talk__actions">
            <button
              type="button"
              className="btn btn--text"
              disabled={busy || data.items.length === 0}
              title="AI 检查需求的完整性、冲突、遗漏场景、风险和机会。会调用一次模型。"
              onClick={() =>
                void store.startJob(() => api.analyze(project.id), "产品分析")
              }
            >
              {running(store, "analyze") ? "正在检查…" : "检查需求"}
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={busy || data.items.length === 0}
              onClick={() => void toBrief()}
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
              {!panel && decideCount > 0 && (
                <span className="count">{decideCount}</span>
              )}
            </button>
          </div>
        </header>

        <ol className="thread" data-testid="thread">
          {(conversation?.messages ?? []).map((m) => (
            <MessageView
              key={m.id}
              message={m}
              findings={data.baseline}
              onHover={setHighlight}
              onReveal={reveal}
              onDecide={(f, status) =>
                void store.act(() => api.decide(f.id, status))
              }
            />
          ))}
          {exploring && (
            <li className="msg msg--ai">
              <span className="msg__who">AI</span>
              <p className="typing" aria-live="polite">
                正在整理你的回答<span aria-hidden="true">…</span>
              </p>
            </li>
          )}
          {running(store, "analyze") && (
            <li className="msg msg--ai">
              <span className="msg__who">AI</span>
              <p className="typing" aria-live="polite">
                正在检查需求<span aria-hidden="true">…</span>
              </p>
            </li>
          )}
          {store.job?.status === "failed" &&
            ["explore", "analyze"].includes(store.job.kind) && (
              <li className="msg msg--ai">
                <span className="msg__who">AI</span>
                <p className="msg__error" role="alert">
                  这一步没有完成：{store.job.error?.message}
                  。你的回答已经保存，可以重新发送或补充后再试。
                </p>
              </li>
            )}
        </ol>

        <div ref={answersRef} className="answers-anchor" />
        {!busy && (
          <Answers
            key={pending.map((q) => q.id).join() || "none"}
            questions={pending}
            depth={project.depth}
            onSubmit={(answers, supplement, depth) =>
              store.startJob(
                () =>
                  api.submitTurn(project.id, {
                    answers: Object.entries(answers).map(([question, a]) => ({
                      question,
                      kind: a.kind,
                      text: a.kind === "answer" ? a.text : "",
                    })),
                    supplement,
                    ...(depth !== project.depth ? { depth } : {}),
                  }),
                "发送回答",
              )
            }
          />
        )}
      </section>

      {panel && (
        <Requirements
          store={store}
          highlight={[...highlight, ...revealed]}
          onClose={() => setPanel(false)}
        />
      )}
    </div>
  );
}

function MessageView({
  message,
  findings,
  onHover,
  onReveal,
  onDecide,
}: {
  message: Message;
  findings: Finding[];
  onHover: (codes: string[]) => void;
  onReveal: (codes: string[]) => void;
  onDecide: (finding: Finding, status: FindingStatus) => void;
}) {
  if (message.role === "user") {
    const answered = message.answers.filter((a) => a.kind === "answer");
    const skipped = message.answers.filter((a) => a.kind !== "answer");
    return (
      <li className="msg msg--you">
        <span className="msg__who">你</span>
        <div className="msg__body">
          {message.kind === "initial" ||
          message.kind === "supplement" ||
          message.kind === "edit" ? (
            <p className="msg__text">
              {message.kind === "edit" && (
                <span className="msg__tag">直接添加</span>
              )}
              {message.content}
            </p>
          ) : (
            <>
              {answered.map((a) => (
                <div key={a.question} className="qa">
                  <p className="qa__q">{a.text}</p>
                  <p className="msg__text">{a.answer}</p>
                </div>
              ))}
              {message.content &&
                answered.length === 0 &&
                skipped.length === 0 && (
                  <p className="msg__text">{message.content}</p>
                )}
              {skipped.length > 0 && (
                <p className="quiet">
                  {skipped.length} 个问题
                  {skipped.every((s) => s.kind === "skip")
                    ? "跳过了"
                    : "暂时不确定"}
                  ，已记为待确认事项
                </p>
              )}
            </>
          )}
        </div>
      </li>
    );
  }
  const codes = message.changes.map((c) => c.item);
  const added = message.changes.filter((c) => c.kind === "added").length;
  const updated = message.changes.length - added;
  const raised = message.finding_codes
    .map((code) => findings.find((f) => f.code === code))
    .filter((f): f is Finding => Boolean(f));
  return (
    <li className="msg msg--ai">
      <span className="msg__who">AI</span>
      <div className="msg__body">
        <p className="msg__text">{message.content}</p>
        {message.changes.length > 0 && (
          <button
            type="button"
            className="trace"
            onMouseEnter={() => onHover(codes)}
            onMouseLeave={() => onHover([])}
            onFocus={() => onHover(codes)}
            onBlur={() => onHover([])}
            onClick={() => onReveal(codes)}
          >
            <span className="trace__line" aria-hidden="true" />
            {added > 0 && `记录了 ${added} 项`}
            {added > 0 && updated > 0 && "，"}
            {updated > 0 && `更新了 ${updated} 项`}
            ，确认后生效
          </button>
        )}
        {message.kind === "analysis" && raised.length === 0 && (
          <p className="quiet">没有发现需要处理的问题。</p>
        )}
        {raised.map((finding) => (
          <InsightNote
            key={finding.id}
            finding={finding}
            initiallyOpen={false}
            onHover={onHover}
            onDecide={onDecide}
          />
        ))}
      </div>
    </li>
  );
}

const DECIDED: Partial<Record<FindingStatus, string>> = {
  accepted: "已采纳，会在下一轮追问",
  modified: "已采纳",
  deferred: "暂缓",
  rejected: "已拒绝",
  resolved: "已解决",
};

/** One Product Analyst finding. Collapsed unless it still needs a decision. */
export function InsightNote({
  finding,
  initiallyOpen,
  onHover,
  onDecide,
}: {
  finding: Finding;
  initiallyOpen: boolean;
  onHover: (codes: string[]) => void;
  onDecide: (finding: Finding, status: FindingStatus) => void;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const decided = finding.status !== "open";
  const isOpen = open && !decided;
  const op = finding.opportunity;
  return (
    <div
      className={`insight insight--${finding.kind}${decided ? " is-done" : ""}`}
      data-finding={finding.code}
      onMouseEnter={() => onHover(finding.related_items)}
      onMouseLeave={() => onHover([])}
    >
      <button
        type="button"
        className="insight__head"
        aria-expanded={isOpen}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="insight__kind">
          {KIND_TEXT[finding.kind] ?? finding.kind}
        </span>
        <span className="insight__title">{finding.title}</span>
        {decided && (
          <span className="insight__state">{DECIDED[finding.status]}</span>
        )}
      </button>
      {isOpen && (
        <div className="insight__body">
          <p>{finding.problem}</p>
          <p className="insight__basis">
            依据：{finding.evidence}
            <span className="insight__codes">
              {finding.related_items.join("、")}
            </span>
          </p>
          {op && (
            <dl className="opportunity">
              <dt>用户问题</dt>
              <dd>{op.user_problem}</dd>
              <dt>现在怎么做</dt>
              <dd>{op.current_solution}</dd>
              <dt>不足</dt>
              <dd>{op.shortfall}</dd>
              <dt>价值</dt>
              <dd>{op.value}</dd>
              <dt>代价</dt>
              <dd>{op.cost}</dd>
              <dt>待验证</dt>
              <dd>{op.assumptions.join("；")}</dd>
            </dl>
          )}
          <p className="insight__suggest">
            <span>建议</span>
            {finding.recommendation}
          </p>
          <div className="insight__actions">
            <button
              type="button"
              className="btn btn--small"
              onClick={() => onDecide(finding, "accepted")}
            >
              采纳
            </button>
            <button
              type="button"
              className="btn btn--text"
              onClick={() => onDecide(finding, "deferred")}
            >
              暂缓
            </button>
            <button
              type="button"
              className="btn btn--text"
              onClick={() => onDecide(finding, "rejected")}
            >
              拒绝
            </button>
          </div>
        </div>
      )}
      {decided && finding.status !== "resolved" && (
        <button
          type="button"
          className="insight__undo"
          onClick={() => onDecide(finding, "open")}
        >
          撤销
        </button>
      )}
    </div>
  );
}

/** The current round's questions plus free-form input. One question open at a time. */
function Answers({
  questions,
  depth,
  onSubmit,
}: {
  questions: Question[];
  /** Sent with the next turn; changes how many questions follow. */
  depth: "brief" | "detailed";
  onSubmit: (
    answers: Record<string, Answer>,
    supplement: string,
    depth: "brief" | "detailed",
  ) => Promise<void>;
}) {
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [active, setActive] = useState<string | null>(
    questions[0]?.code ?? null,
  );
  const [supplement, setSupplement] = useState("");
  const [showSupplement, setShowSupplement] = useState(questions.length === 0);
  const [chosenDepth, setChosenDepth] = useState(depth);
  const [sending, setSending] = useState(false);

  const set = (code: string, a: Answer | null) =>
    setAnswers((prev) => {
      const next = { ...prev };
      if (a && (a.kind !== "answer" || a.text)) next[code] = a;
      else delete next[code];
      return next;
    });

  const advance = (code: string) => {
    const i = questions.findIndex((q) => q.code === code);
    const next =
      questions.slice(i + 1).find((q) => !answers[q.code]) ?? questions[i + 1];
    setActive(next?.code ?? null);
  };

  const handled = Object.keys(answers).length;
  const canSend = handled > 0 || supplement.trim().length > 0;

  const send = async () => {
    setSending(true);
    await onSubmit(answers, supplement.trim(), chosenDepth);
    setSending(false);
  };

  return (
    <section className="answers" aria-label="本轮问题" data-testid="answers">
      {questions.length > 0 ? (
        <p className="answers__label">
          需要你回答 <span>{questions.length} 个问题，可以跳过</span>
        </p>
      ) : (
        <p className="answers__label">
          补充信息 <span>没有新的问题。你可以直接补充，或者整理成 Brief。</span>
        </p>
      )}
      <ol>
        {questions.map((q, index) => {
          const a = answers[q.code];
          const isActive = active === q.code;
          const status =
            a?.kind === "skip"
              ? "已跳过"
              : a?.kind === "unknown"
                ? "暂时不确定"
                : a?.kind === "answer"
                  ? "已回答"
                  : "";
          return (
            <li
              key={q.code}
              className={
                isActive ? "q is-active" : status ? "q is-handled" : "q"
              }
            >
              <button
                type="button"
                className="q__head"
                aria-expanded={isActive}
                onClick={() => setActive(isActive ? null : q.code)}
              >
                <span className="q__num">{index + 1}</span>
                <span className="q__text">{q.text}</span>
                {!isActive && status && (
                  <span className="q__status">{status}</span>
                )}
              </button>
              {isActive && (
                <div className="q__body">
                  <p className="q__why">
                    {q.purpose}
                    {q.finding_code && (
                      <span className="q__ref">
                        来自你采纳的发现 {q.finding_code}
                      </span>
                    )}
                  </p>
                  {a && a.kind !== "answer" ? (
                    <p className="q__skipped">
                      {a.kind === "skip" ? "已跳过" : "暂时不确定"}
                      ，会记为待确认事项。
                      <button
                        type="button"
                        className="btn btn--text"
                        onClick={() => set(q.code, null)}
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
                        autoFocus={index > 0}
                        onChange={(e) =>
                          set(q.code, { kind: "answer", text: e.target.value })
                        }
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && (e.metaKey || e.ctrlKey))
                            advance(q.code);
                        }}
                      />
                      <div className="q__actions">
                        <button
                          type="button"
                          className="btn btn--text"
                          onClick={() => {
                            set(q.code, { kind: "unknown" });
                            advance(q.code);
                          }}
                        >
                          暂时不确定
                        </button>
                        <button
                          type="button"
                          className="btn btn--text"
                          onClick={() => {
                            set(q.code, { kind: "skip" });
                            advance(q.code);
                          }}
                        >
                          跳过
                        </button>
                        <button
                          type="button"
                          className="btn btn--ghost btn--small"
                          onClick={() => advance(q.code)}
                        >
                          {index < questions.length - 1 ? "下一题" : "完成"}
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
      {showSupplement ? (
        <textarea
          className="field answers__extra"
          rows={2}
          value={supplement}
          placeholder="还有其他想补充的？例如约束、已经决定的事、想法的变化"
          aria-label="补充信息"
          onChange={(e) => setSupplement(e.target.value)}
        />
      ) : (
        <button
          type="button"
          className="more"
          onClick={() => setShowSupplement(true)}
        >
          <Icon name="plus" />
          补充其他信息
        </button>
      )}
      <div className="answers__foot">
        <span className="answers__meta">
          <span
            className="seg seg--small"
            role="radiogroup"
            aria-label="提问深度"
          >
            {(["brief", "detailed"] as const).map((d) => (
              <button
                key={d}
                type="button"
                role="radio"
                aria-checked={chosenDepth === d}
                aria-selected={chosenDepth === d}
                onClick={() => setChosenDepth(d)}
              >
                {d === "brief" ? "简要" : "详细"}
              </button>
            ))}
          </span>
          <span className="answers__hint">
            回答会整理成需求，由你确认后生效
          </span>
        </span>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!canSend || sending}
          onClick={() => void send()}
        >
          发送
          <Icon name="arrow" />
        </button>
      </div>
    </section>
  );
}
