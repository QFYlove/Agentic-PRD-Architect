import { useState } from "react";
import { GROUPS } from "../data/explore";
import type {
  BaselineItem,
  ExploreFinding,
  ExploreFindingStatus,
  GroupKey,
  ItemStatus,
} from "../data/types";
import { FINDING_KIND, STATUS_LABEL } from "../data/types";
import { Id, PriorityTag, StatusMark } from "./Marks";

type LinkFn = (id: string | null, el?: HTMLElement | null) => void;
type Filter = "all" | "review" | "confirmed" | "open";

const FILTERS: {
  key: Filter;
  label: string;
  match: (s: ItemStatus) => boolean;
}[] = [
  { key: "all", label: "全部", match: (s) => s !== "rejected" },
  {
    key: "review",
    label: "待你确认",
    match: (s) => s === "inferred" || s === "proposed" || s === "assumption",
  },
  { key: "confirmed", label: "已确认", match: (s) => s === "confirmed" },
  { key: "open", label: "待确认事项", match: (s) => s === "open" },
];

const FINDING_STATUS: Record<ExploreFindingStatus, string> = {
  open: "待处理",
  accepted: "已采纳",
  deferred: "暂缓",
  rejected: "已拒绝",
  resolved: "已解决",
};

export function Baseline({
  items,
  findings,
  linked,
  fresh,
  onLink,
  onStatus,
  onEdit,
  onFinding,
}: {
  items: BaselineItem[];
  findings: ExploreFinding[];
  linked: string | null;
  fresh: string[];
  onLink: LinkFn;
  onStatus: (id: string, status: ItemStatus) => void;
  onEdit: (id: string, content: string) => void;
  onFinding: (id: string, status: ExploreFindingStatus) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [collapsed, setCollapsed] = useState<Set<GroupKey>>(new Set());
  const [showFindings, setShowFindings] = useState(true);
  const [showRejected, setShowRejected] = useState(false);

  const match = FILTERS.find((f) => f.key === filter)?.match ?? (() => true);
  const visible = items.filter(
    (i) => match(i.status) || (showRejected && i.status === "rejected"),
  );
  const rejected = items.filter((i) => i.status === "rejected").length;
  const reviewCount = items.filter((i) => FILTERS[1]?.match(i.status)).length;
  const openFindings = findings.filter((f) => f.status === "open");

  const findingsFor = (id: string) =>
    findings.filter((f) => f.related.includes(id) && f.status === "open");

  const toggleGroup = (key: GroupKey) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <section className="baseline" aria-labelledby="baseline-title">
      <header className="baseline__head">
        <div className="baseline__title">
          <h2 id="baseline-title">需求基线</h2>
          <span className="sec-head__en">Requirement baseline</span>
        </div>
        <Legend />
        <div className="seg" role="tablist" aria-label="按状态筛选">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              role="tab"
              aria-selected={filter === f.key}
              className={filter === f.key ? "is-on" : undefined}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
              {f.key === "review" && reviewCount > 0 && (
                <span className="seg__n">{reviewCount}</span>
              )}
            </button>
          ))}
        </div>
      </header>

      <div className="notes">
        <button
          type="button"
          className="notes__toggle"
          aria-expanded={showFindings}
          onClick={() => setShowFindings((v) => !v)}
        >
          <span className="notes__flag" aria-hidden="true" />
          <span>AI 发现</span>
          <span className="mono">{openFindings.length} 待处理</span>
          <span className="chev" aria-hidden="true">
            {showFindings ? "−" : "+"}
          </span>
        </button>
        {showFindings && (
          <ol className="notes__list">
            {findings.map((f) => (
              <FindingNote
                key={f.id}
                finding={f}
                linked={linked}
                onLink={onLink}
                onStatus={onFinding}
              />
            ))}
          </ol>
        )}
      </div>

      <div className="groups">
        {GROUPS.map((g) => {
          const list = visible.filter((i) => i.group === g.key);
          const all = items.filter(
            (i) => i.group === g.key && i.status !== "rejected",
          );
          const isCollapsed = collapsed.has(g.key);
          if (filter !== "all" && list.length === 0) return null;
          return (
            <section
              key={g.key}
              className={list.length === 0 ? "group is-empty" : "group"}
            >
              <button
                type="button"
                className="group__head"
                aria-expanded={!isCollapsed}
                onClick={() => toggleGroup(g.key)}
              >
                <span className="group__num mono">{g.index}</span>
                <span className="group__title">{g.title}</span>
                <span className="group__en">{g.en}</span>
                <PriorityTag priority={g.priority} />
                <span className="group__count mono">
                  {all.filter((i) => i.status === "confirmed").length}/
                  {all.length}
                </span>
                <span className="chev" aria-hidden="true">
                  {isCollapsed ? "+" : "−"}
                </span>
              </button>
              {!isCollapsed &&
                (list.length === 0 ? (
                  <p className="group__empty">
                    {g.priority === "P0"
                      ? "尚未明确 · AI 会优先追问"
                      : "尚未涉及"}
                  </p>
                ) : (
                  <ul className="items">
                    {list.map((item) => (
                      <ItemRow
                        key={item.id}
                        item={item}
                        notes={findingsFor(item.id)}
                        linked={linked}
                        fresh={fresh.includes(item.id)}
                        onLink={onLink}
                        onStatus={onStatus}
                        onEdit={onEdit}
                      />
                    ))}
                  </ul>
                ))}
            </section>
          );
        })}
      </div>

      {rejected > 0 && (
        <button
          type="button"
          className="link baseline__rejected"
          onClick={() => setShowRejected((v) => !v)}
        >
          {showRejected ? "隐藏" : "显示"} {rejected} 条已拒绝的推断
        </button>
      )}
    </section>
  );
}

function Legend() {
  const shown: ItemStatus[] = [
    "confirmed",
    "inferred",
    "proposed",
    "assumption",
    "open",
  ];
  return (
    <ul className="legend" aria-label="状态图例">
      {shown.map((s) => (
        <li key={s}>
          <StatusMark status={s} />
          {STATUS_LABEL[s]}
        </li>
      ))}
    </ul>
  );
}

function ItemRow({
  item,
  notes,
  linked,
  fresh,
  onLink,
  onStatus,
  onEdit,
}: {
  item: BaselineItem;
  notes: ExploreFinding[];
  linked: string | null;
  fresh: boolean;
  onLink: LinkFn;
  onStatus: (id: string, status: ItemStatus) => void;
  onEdit: (id: string, content: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.content);
  const [showHistory, setShowHistory] = useState(false);
  const needsReview =
    item.status === "inferred" ||
    item.status === "proposed" ||
    item.status === "assumption";
  const isLinked = linked === item.id || notes.some((n) => n.id === linked);

  const classes = ["item", `item--${item.status}`];
  if (isLinked) classes.push("is-linked");
  if (fresh) classes.push("is-fresh");

  const save = () => {
    const next = draft.trim();
    if (next) onEdit(item.id, next);
    setEditing(false);
  };

  return (
    <li
      className={classes.join(" ")}
      data-item={item.id}
      onMouseEnter={(e) => onLink(item.id, e.currentTarget)}
      onMouseLeave={() => onLink(null)}
    >
      <StatusMark status={item.status} />
      <div className="item__main">
        {editing ? (
          <div className="item__edit">
            <textarea
              rows={2}
              value={draft}
              aria-label={`编辑 ${item.id}`}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save();
                if (e.key === "Escape") setEditing(false);
              }}
              autoFocus
            />
            <div className="item__edit-actions">
              <span className="hint mono">⌘↵ 保存 · Esc 取消</span>
              <button
                type="button"
                className="link"
                onClick={() => setEditing(false)}
              >
                取消
              </button>
              <button type="button" className="btn btn--small" onClick={save}>
                保存
              </button>
            </div>
          </div>
        ) : (
          <p className="item__text">{item.content}</p>
        )}
        <div className="item__meta">
          <Id>{item.id}</Id>
          <span
            className={
              item.status === "confirmed"
                ? "item__status"
                : "item__status is-pending"
            }
          >
            {STATUS_LABEL[item.status]}
          </span>
          <span className="item__src mono">
            {item.source.kind === "user" ? "用户" : "AI"} · R{item.source.round}
          </span>
          {item.history && item.history.length > 0 && (
            <button
              type="button"
              className="link"
              onClick={() => setShowHistory((v) => !v)}
              aria-expanded={showHistory}
            >
              修改 {item.history.length} 次
            </button>
          )}
          {notes.map((n) => (
            <span key={n.id} className="item__note mono" title={n.title}>
              {FINDING_KIND[n.kind].code} · {n.id}
            </span>
          ))}
        </div>
        {showHistory && item.history && (
          <ol className="item__history">
            {item.history.map((h, i) => (
              <li key={i}>
                <s>{h}</s>
              </li>
            ))}
          </ol>
        )}
      </div>
      {!editing && (
        <div className="item__actions">
          {needsReview && (
            <>
              <button
                type="button"
                className="act act--yes"
                onClick={() => onStatus(item.id, "confirmed")}
              >
                确认
              </button>
              <button
                type="button"
                className="act"
                onClick={() => onStatus(item.id, "rejected")}
              >
                拒绝
              </button>
            </>
          )}
          {item.status === "rejected" && (
            <button
              type="button"
              className="act"
              onClick={() => onStatus(item.id, "inferred")}
            >
              恢复
            </button>
          )}
          <button
            type="button"
            className="act"
            onClick={() => {
              setDraft(item.content);
              setEditing(true);
            }}
          >
            编辑
          </button>
        </div>
      )}
    </li>
  );
}

function FindingNote({
  finding,
  linked,
  onLink,
  onStatus,
}: {
  finding: ExploreFinding;
  linked: string | null;
  onLink: LinkFn;
  onStatus: (id: string, status: ExploreFindingStatus) => void;
}) {
  const [open, setOpen] = useState(false);
  const kind = FINDING_KIND[finding.kind];
  const handled = finding.status !== "open";
  const classes = ["note", `note--${finding.kind}`];
  if (linked === finding.id || finding.related.includes(linked ?? ""))
    classes.push("is-linked");
  if (handled) classes.push("is-handled");
  return (
    <li
      className={classes.join(" ")}
      data-item={finding.id}
      onMouseEnter={(e) => onLink(finding.id, e.currentTarget)}
      onMouseLeave={() => onLink(null)}
    >
      <button
        type="button"
        className="note__head"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="note__code mono" title={kind.label}>
          {kind.code}
        </span>
        <span className="note__title">{finding.title}</span>
        <span className="note__state mono">
          {FINDING_STATUS[finding.status]}
        </span>
      </button>
      {open && (
        <div className="note__body">
          <dl>
            <dt>依据</dt>
            <dd>{finding.evidence}</dd>
            <dt>影响</dt>
            <dd>{finding.impact}</dd>
            <dt>建议</dt>
            <dd>{finding.recommendation}</dd>
          </dl>
          <div className="note__foot">
            <span className="note__rel">
              {kind.label} · 关联{" "}
              {finding.related.map((r) => (
                <Id key={r}>{r}</Id>
              ))}
            </span>
            {handled ? (
              <button
                type="button"
                className="link"
                onClick={() => onStatus(finding.id, "open")}
              >
                撤销
              </button>
            ) : (
              <span className="note__actions">
                <button
                  type="button"
                  className="act act--yes"
                  onClick={() => onStatus(finding.id, "accepted")}
                >
                  采纳
                </button>
                <button
                  type="button"
                  className="act"
                  onClick={() => onStatus(finding.id, "deferred")}
                >
                  暂缓
                </button>
                <button
                  type="button"
                  className="act"
                  onClick={() => onStatus(finding.id, "rejected")}
                >
                  拒绝
                </button>
              </span>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
