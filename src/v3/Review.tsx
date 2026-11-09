import { useEffect, useMemo, useRef, useState } from "react";
import { DiffLines } from "./Document";
import { api } from "./api";
import { running, type ProjectStore } from "./store";
import type {
  Finding,
  FindingEvent,
  FindingStatus,
  Proposal,
  ProposalChange,
  Reviewer,
  ReviewResult,
} from "./types";
import {
  FINDING_STATUS_TEXT,
  Icon,
  REVIEWER_TEXT,
  SEVERITY_TEXT,
  timeText,
} from "./ui";

const OPEN: FindingStatus[] = ["open", "stale"];
const RANK = { must_fix: 0, should_fix: 1, optional: 2 } as const;
const REVIEWERS: Reviewer[] = ["product", "ux", "tech", "biz"];

/** Review side panel: run the four reviewers, handle findings, apply fixes. */
export function ReviewPanel({
  store,
  focus,
  sectionFilter,
  onClearSection,
  onFocus,
  onClose,
}: {
  store: ProjectStore;
  focus: string | null;
  sectionFilter: string | null;
  onClearSection: () => void;
  onFocus: (code: string) => void;
  onClose: () => void;
}) {
  const { data } = store;
  const projectId = data.summary!.id;
  const [reviewer, setReviewer] = useState<Reviewer | "all">("all");
  const [severity, setSeverity] = useState<string>("all");
  const [showDone, setShowDone] = useState(false);
  const [showSummaries, setShowSummaries] = useState(false);
  const sections = data.sections?.items ?? [];
  const numOf = (code: string | undefined) =>
    sections.find((s) => s.code === code)?.num ?? "";

  const matches = (f: Finding) =>
    (reviewer === "all" || f.reviewers.includes(reviewer)) &&
    (severity === "all" || f.severity === severity) &&
    (!sectionFilter || f.related_sections.includes(sectionFilter));
  const open = useMemo(
    () =>
      data.findings
        .filter((f) => OPEN.includes(f.status) && matches(f))
        .sort((a, b) => RANK[a.severity] - RANK[b.severity]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data.findings, reviewer, severity, sectionFilter],
  );
  const done = data.findings.filter(
    (f) => !OPEN.includes(f.status) && matches(f),
  );
  const accepted = data.findings.filter(
    (f) => f.status === "accepted" || f.status === "modified",
  );
  const pending = data.proposals.find(
    (p) => p.status === "pending" || p.status === "partial",
  );
  const reviewing = running(store, "review");
  const unfinished = sections.filter((s) => s.status !== "done").length;
  const blocked = running(store) || unfinished > 0;
  const optimizing = running(store, "optimize");
  const hasReview = data.reviews.length > 0;
  const lastReview = data.reviews.reduce<string | null>(
    (latest, r) =>
      latest === null || r.created_at > latest ? r.created_at : latest,
    null,
  );

  const decide = (finding: Finding, status: FindingStatus, note?: string) =>
    void store.act(() => api.decide(finding.id, status, note));

  return (
    <div className="notes">
      <header className="side__head">
        <h2 className="side__title">审查</h2>
        <button
          type="button"
          className="icon-btn"
          onClick={onClose}
          aria-label="关闭审查"
        >
          <Icon name="close" />
        </button>
      </header>

      {!hasReview ? (
        <div className="review-start">
          <p>
            产品、体验、技术、商业四个审查角色各自独立阅读全文，只提出有原文依据的问题，没有问题时可以不提。
          </p>
          <button
            type="button"
            className="btn btn--primary"
            disabled={blocked}
            onClick={() =>
              void store.startJob(() => api.review(projectId), "审查")
            }
          >
            {reviewing ? "正在审查…" : "开始审查"}
          </button>
          <p className="quiet">
            {unfinished > 0
              ? `还有 ${unfinished} 个章节没有完成，全部完成后才能审查全文。`
              : "会调用 4 次模型，并行执行。"}
          </p>
        </div>
      ) : (
        <>
          <p className="side__sub">
            四个角色独立审查{lastReview ? ` · ${timeText(lastReview)}` : ""}
            <button
              type="button"
              className="btn btn--text"
              disabled={blocked}
              onClick={() =>
                void store.startJob(() => api.review(projectId), "审查")
              }
            >
              {reviewing ? "正在审查…" : "重新审查全文"}
            </button>
          </p>

          <button
            type="button"
            className="more more--flush"
            aria-expanded={showSummaries}
            onClick={() => setShowSummaries((v) => !v)}
          >
            <Icon name={showSummaries ? "down" : "chevron"} />
            各角色结论
          </button>
          {showSummaries && <Summaries results={data.reviews} />}

          <div className="filters">
            <div
              className="seg seg--small"
              role="tablist"
              aria-label="按角色筛选"
            >
              {(["all", ...REVIEWERS] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  role="tab"
                  aria-selected={reviewer === r}
                  onClick={() => setReviewer(r)}
                >
                  {r === "all" ? "全部" : REVIEWER_TEXT[r]}
                </button>
              ))}
            </div>
            <select
              className="select select--small"
              aria-label="按严重程度筛选"
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
            >
              <option value="all">全部程度</option>
              <option value="must_fix">必须修改</option>
              <option value="should_fix">建议修改</option>
              <option value="optional">可选</option>
            </select>
          </div>
          {sectionFilter && (
            <p className="filter-chip">
              只看第 {numOf(sectionFilter)} 节
              <button
                type="button"
                className="btn btn--text"
                onClick={onClearSection}
              >
                显示全部
              </button>
            </p>
          )}

          {open.length === 0 ? (
            <div className="calm">
              <p>没有待处理的意见。</p>
              <p className="quiet">
                {data.findings.length === 0
                  ? "四个角色都没有发现需要处理的问题。"
                  : "处理过的意见在下面。"}
              </p>
            </div>
          ) : (
            <ol className="nlist" data-testid="findings">
              {open.map((f) => (
                <NoteItem
                  key={f.id}
                  finding={f}
                  num={numOf(f.related_sections[0])}
                  open={focus === f.code}
                  onOpen={() => onFocus(f.code)}
                  onDecide={decide}
                />
              ))}
            </ol>
          )}
        </>
      )}

      {pending ? (
        <ProposalView store={store} proposal={pending} />
      ) : (
        accepted.length > 0 && (
          <div className="apply">
            <p>
              已采纳 {accepted.length} 条。AI
              只按这些意见提出修改，你逐条确认后才会改动正文。
            </p>
            <button
              type="button"
              className="btn btn--ghost btn--small"
              disabled={running(store)}
              onClick={() =>
                void store.startJob(
                  () => api.optimize(projectId),
                  "生成修改提案",
                )
              }
            >
              {optimizing ? "正在生成修改…" : "按采纳的意见修改"}
            </button>
          </div>
        )
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
              {done.map((f) => (
                <li key={f.id} className="ndone">
                  <span className="ndone__title">{f.title}</span>
                  <span className="ndone__state">
                    {FINDING_STATUS_TEXT[f.status]}
                    {f.status !== "resolved" && (
                      <button
                        type="button"
                        className="btn btn--text"
                        onClick={() => decide(f, "open")}
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

function Summaries({ results }: { results: ReviewResult[] }) {
  return (
    <ul className="summaries" data-testid="review-summaries">
      {REVIEWERS.map((r) => {
        const result = results.find((x) => x.reviewer === r);
        return (
          <li key={r} className="summary">
            <p className="summary__head">
              <b>{REVIEWER_TEXT[r]}</b>
              {result ? (
                <span className="quiet">
                  {result.score !== null ? `${result.score} 分` : "未评分"} ·{" "}
                  {result.finding_codes.length} 条意见
                  {result.blocking && " · 有阻塞问题"}
                </span>
              ) : (
                <span className="quiet">没有完成</span>
              )}
            </p>
            {result && (
              <>
                <p>{result.summary}</p>
                {result.risks.length > 0 && (
                  <p className="quiet">核心风险：{result.risks.join("；")}</p>
                )}
                <details className="summary__dims">
                  <summary>评分维度</summary>
                  <ul>
                    {result.dimension_scores.map((d) => (
                      <li key={d.dimension}>
                        {d.score}/5 · {d.rationale}
                      </li>
                    ))}
                  </ul>
                </details>
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function NoteItem({
  finding,
  num,
  open,
  onOpen,
  onDecide,
}: {
  finding: Finding;
  num: string;
  open: boolean;
  onOpen: () => void;
  onDecide: (finding: Finding, status: FindingStatus, note?: string) => void;
}) {
  const ref = useRef<HTMLLIElement>(null);
  const [modifying, setModifying] = useState(false);
  const [text, setText] = useState(finding.user_note ?? "");
  const [history, setHistory] = useState<FindingEvent[] | null>(null);
  useEffect(() => {
    if (open)
      ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    else setModifying(false);
  }, [open]);

  const sev =
    finding.severity === "must_fix"
      ? "high"
      : finding.severity === "optional"
        ? "low"
        : "medium";
  return (
    <li
      ref={ref}
      className={`note note--${sev}${open ? " is-open" : ""}`}
      data-finding={finding.code}
    >
      <button
        type="button"
        className="note__head"
        aria-expanded={open}
        onClick={onOpen}
      >
        <span className="note__meta">
          <span className="note__sev">{SEVERITY_TEXT[finding.severity]}</span>
          <span>
            {finding.reviewers.map((r) => REVIEWER_TEXT[r]).join(" / ")}
            {num && ` · 第 ${num} 节`}
          </span>
          {finding.status === "stale" && (
            <span className="note__recheck">需重新确认</span>
          )}
        </span>
        <span className="note__title">{finding.title}</span>
      </button>
      {open && (
        <div className="note__body">
          <blockquote className="note__quote">
            {finding.evidence}
            {!finding.evidence_verified && (
              <span className="note__warn">
                正文中没有找到这段引用，请自己核对
              </span>
            )}
          </blockquote>
          <p>{finding.problem}</p>
          {finding.cause && <p className="quiet">原因：{finding.cause}</p>}
          {finding.impact && <p className="quiet">影响：{finding.impact}</p>}
          <p className="note__suggest">
            <span>建议</span>
            {finding.recommendation}
          </p>
          {finding.status === "stale" && (
            <p className="quiet">
              这一节在意见提出后被修改过，意见可能已经不适用。
            </p>
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
                  onClick={() => onDecide(finding, "modified", text.trim())}
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
                onClick={() => onDecide(finding, "accepted")}
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
            </span>
          )}
          <button
            type="button"
            className="more more--flush"
            onClick={() =>
              void api
                .findingHistory(finding.id)
                .then((r) => setHistory(r.items))
                .catch(() => setHistory([]))
            }
          >
            处理记录
          </button>
          {history && (
            <ol className="revisions">
              {history.map((e) => (
                <li key={e.id}>
                  {e.actor === "user"
                    ? "你"
                    : e.actor === "system"
                      ? "系统"
                      : (REVIEWER_TEXT[e.actor as Reviewer] ?? e.actor)}
                  ：{FINDING_STATUS_TEXT[e.to_status] ?? e.to_status}
                  {e.note && `（${e.note}）`}
                  <span className="quiet"> · {timeText(e.created_at)}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </li>
  );
}

const CHANGE_TEXT: Record<ProposalChange["change_type"], string> = {
  ADD: "新增",
  UPDATE: "修改",
  REMOVE: "删除",
  CONSOLIDATE: "合并",
  RETAIN: "保持不变",
};

function ProposalView({
  store,
  proposal,
}: {
  store: ProjectStore;
  proposal: Proposal;
}) {
  const sections = store.data.sections?.items ?? [];
  const pending = proposal.changes.filter((c) => c.state === "pending");
  const [chosen, setChosen] = useState<string[]>(
    pending.filter((c) => !c.human_section).map((c) => c.id),
  );
  const toggle = (id: string) =>
    setChosen((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );

  return (
    <section className="proposal" data-testid="proposal" aria-label="修改提案">
      <h3 className="proposal__title">修改提案 {proposal.code}</h3>
      <p className="quiet">
        {proposal.objective} 勾选要应用的修改，没勾选的不会改动。
      </p>
      {pending.length === 0 && <p className="quiet">没有可以应用的修改。</p>}
      <ol className="plist-changes">
        {pending.map((change) => {
          const section = sections.find((s) => s.code === change.section_code);
          return (
            <li key={change.id} className="pchange">
              <label className="pchange__head">
                <input
                  type="checkbox"
                  checked={chosen.includes(change.id)}
                  onChange={() => toggle(change.id)}
                />
                <span>
                  {CHANGE_TEXT[change.change_type]} 第 {section?.num} 节「
                  {section?.title}」
                  {change.new_title && ` → 新章节「${change.new_title}」`}
                </span>
              </label>
              <p className="pchange__why">
                {change.reason}
                <span className="quiet">
                  {" "}
                  · 处理 {change.finding_codes.join("、")}
                </span>
              </p>
              {change.human_section && (
                <p className="pchange__warn">
                  这一节是你写的。默认不勾选，确认改动后再应用。
                </p>
              )}
              {change.warnings.length > 0 && (
                <p className="pchange__warn">
                  修改后缺少应保留的内容：{change.warnings.join("；")}
                </p>
              )}
              <DiffLines lines={lineDiff(change.before, change.after)} />
            </li>
          );
        })}
      </ol>
      {proposal.declined.length > 0 && (
        <p className="quiet">
          没有处理：
          {proposal.declined
            .map((d) => `${d.finding_code}（${d.reason}）`)
            .join("；")}
        </p>
      )}
      <div className="proposal__foot">
        <button
          type="button"
          className="btn btn--text"
          onClick={() =>
            void store.act(() => api.discard(proposal.id), "已放弃这个提案。")
          }
        >
          放弃
        </button>
        <button
          type="button"
          className="btn btn--small"
          disabled={chosen.length === 0}
          onClick={() =>
            void store
              .act(async () => {
                const result = await api.apply(proposal.id, chosen);
                return result;
              })
              .then((result) => {
                if (!result) return;
                if (result.conflicts.length > 0) {
                  // The section changed after the proposal was made.
                  window.alert(
                    `${result.conflicts.length} 处修改没有应用：对应章节在提案生成后被改过。`,
                  );
                }
              })
          }
        >
          应用 {chosen.length} 处修改
        </button>
      </div>
    </section>
  );
}

/** Minimal line diff for proposal previews. */
function lineDiff(before: string, after: string) {
  const a = before.split("\n");
  const b = after.split("\n");
  const inB = new Set(b);
  const inA = new Set(a);
  const out: { kind: "same" | "add" | "del"; text: string }[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    const left = a[i];
    const right = b[j];
    if (left !== undefined && left === right) {
      out.push({ kind: "same", text: left });
      i++;
      j++;
    } else if (left !== undefined && !inB.has(left)) {
      out.push({ kind: "del", text: left });
      i++;
    } else if (right !== undefined && !inA.has(right)) {
      out.push({ kind: "add", text: right });
      j++;
    } else {
      if (left !== undefined) out.push({ kind: "del", text: left });
      if (right !== undefined) out.push({ kind: "add", text: right });
      i++;
      j++;
    }
  }
  return out.filter((line) => line.kind !== "same" || line.text.trim());
}
