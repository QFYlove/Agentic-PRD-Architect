import { useState } from "react";
import { InsightNote } from "./Explore";
import { api } from "./api";
import type { ProjectStore } from "./store";
import type { Finding, GroupKey, Item, Revision } from "./types";
import { Icon, STATUS_TEXT, StatusMark, timeText } from "./ui";

type View = "decide" | "all";
const UNDECIDED = ["inferred", "proposed", "assumption"];

export function Requirements({
  store,
  highlight,
  onClose,
}: {
  store: ProjectStore;
  highlight: string[];
  onClose: () => void;
}) {
  const { data } = store;
  const projectId = data.summary!.id;
  const pendingItems = data.items.filter((i) => UNDECIDED.includes(i.status));
  const pendingFindings = data.baseline.filter((f) => f.status === "open");
  const total = pendingItems.length + pendingFindings.length;
  // Until the user picks a tab, show whatever needs them.
  const [chosen, setView] = useState<View | null>(null);
  const view: View = chosen ?? (total > 0 ? "decide" : "all");
  const [hover, setHover] = useState<string[]>([]);
  const lit = [...highlight, ...hover];

  // Items lit from the conversation that are not pending force the full view.
  const effective: View =
    highlight.length > 0 &&
    !highlight.some((code) => pendingItems.some((p) => p.code === code))
      ? "all"
      : view;

  const update = (
    item: Item,
    body: { content?: string; status?: Item["status"] },
  ) => void store.act(() => api.patchItem(item.id, body));
  const decide = (finding: Finding, status: Finding["status"]) =>
    void store.act(() => api.decide(finding.id, status));

  return (
    <aside className="req" aria-label="需求" data-testid="requirements">
      <header className="req__head">
        <div className="seg" role="tablist" aria-label="需求视图">
          <button
            type="button"
            role="tab"
            aria-selected={effective === "decide"}
            onClick={() => setView("decide")}
          >
            待你决定
            {total > 0 && <span className="count">{total}</span>}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={effective === "all"}
            onClick={() => setView("all")}
          >
            全部需求
          </button>
        </div>
        <button
          type="button"
          className="icon-btn"
          onClick={onClose}
          aria-label="收起需求面板"
        >
          <Icon name="close" />
        </button>
      </header>

      <div className="req__scroll">
        {effective === "decide" ? (
          total === 0 ? (
            <div className="calm">
              <p>没有需要你决定的事项。</p>
              <p className="quiet">新的推断和 AI 发现会出现在这里。</p>
            </div>
          ) : (
            <>
              {pendingFindings.length > 0 && (
                <section className="req__block">
                  <h3 className="label">AI 发现</h3>
                  {pendingFindings.map((f) => (
                    <InsightNote
                      key={f.id}
                      finding={f}
                      initiallyOpen={pendingFindings.length <= 2}
                      onHover={setHover}
                      onDecide={decide}
                    />
                  ))}
                </section>
              )}
              {pendingItems.length > 0 && (
                <section className="req__block">
                  <div className="req__blockhead">
                    <h3 className="label">需要确认</h3>
                    {pendingItems.length > 1 && (
                      <button
                        type="button"
                        className="btn btn--text"
                        onClick={() =>
                          void store.act(async () => {
                            for (const item of pendingItems) {
                              await api.patchItem(item.id, {
                                status: "confirmed",
                              });
                            }
                          }, `已确认 ${pendingItems.length} 项。`)
                        }
                      >
                        全部确认
                      </button>
                    )}
                  </div>
                  <ul className="ilist">
                    {pendingItems.map((item) => (
                      <ItemRow
                        key={item.id}
                        item={item}
                        groupLabel={labelOf(store, item.group)}
                        lit={lit.includes(item.code)}
                        onUpdate={update}
                      />
                    ))}
                  </ul>
                </section>
              )}
            </>
          )
        ) : (
          <Baseline
            store={store}
            projectId={projectId}
            lit={lit}
            onUpdate={update}
          />
        )}
      </div>
    </aside>
  );
}

function labelOf(store: ProjectStore, key: GroupKey): string {
  return store.meta?.groups.find((g) => g.key === key)?.label ?? key;
}

function Baseline({
  store,
  projectId,
  lit,
  onUpdate,
}: {
  store: ProjectStore;
  projectId: string;
  lit: string[];
  onUpdate: (
    item: Item,
    body: { content?: string; status?: Item["status"] },
  ) => void;
}) {
  const [adding, setAdding] = useState<GroupKey | null>(null);
  const [draft, setDraft] = useState("");
  const [showRejected, setShowRejected] = useState(false);
  const items = store.data.items;
  const rejected = items.filter((i) => i.status === "rejected");
  const decided = store.data.baseline.filter((f) => f.status !== "open");

  const add = async (group: GroupKey) => {
    const content = draft.trim();
    if (!content) return;
    await store.act(() => api.addItem(projectId, group, content));
    setDraft("");
    setAdding(null);
  };

  return (
    <div className="baseline">
      {(store.meta?.groups ?? []).map((g) => {
        const list = items.filter(
          (i) => i.group === g.key && i.status !== "rejected",
        );
        return (
          <section key={g.key} className="bgroup" data-group={g.key}>
            <h3 className="bgroup__title">
              {g.label}
              {g.core && list.every((i) => i.status !== "confirmed") && (
                <span className="bgroup__missing">待补充</span>
              )}
              <button
                type="button"
                className="icon-btn icon-btn--small bgroup__add"
                aria-label={`在「${g.label}」中添加`}
                onClick={() => {
                  setAdding(adding === g.key ? null : g.key);
                  setDraft("");
                }}
              >
                <Icon name="plus" />
              </button>
            </h3>
            {list.length === 0 && adding !== g.key && (
              <p className="bgroup__empty">
                {g.core ? "还没有明确，AI 会优先询问。" : "暂无"}
              </p>
            )}
            {list.length > 0 && (
              <ul className="ilist">
                {list.map((item) => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    lit={lit.includes(item.code)}
                    onUpdate={onUpdate}
                  />
                ))}
              </ul>
            )}
            {adding === g.key && (
              <div className="irow__edit">
                <textarea
                  className="field field--small"
                  rows={2}
                  value={draft}
                  autoFocus
                  aria-label={`添加${g.label}`}
                  placeholder="你直接写下的内容会记为已确认"
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey))
                      void add(g.key);
                    if (e.key === "Escape") setAdding(null);
                  }}
                />
                <span className="irow__edit-actions">
                  <button
                    type="button"
                    className="btn btn--text"
                    onClick={() => setAdding(null)}
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    className="btn btn--small"
                    disabled={!draft.trim()}
                    onClick={() => void add(g.key)}
                  >
                    添加
                  </button>
                </span>
              </div>
            )}
          </section>
        );
      })}
      {decided.length > 0 && (
        <p className="quiet baseline__foot">
          已处理 {decided.length} 条 AI 发现
        </p>
      )}
      {rejected.length > 0 && (
        <>
          <button
            type="button"
            className="more"
            aria-expanded={showRejected}
            onClick={() => setShowRejected((v) => !v)}
          >
            <Icon name={showRejected ? "down" : "chevron"} />
            已否定 {rejected.length}
          </button>
          {showRejected && (
            <ul className="ilist ilist--rejected">
              {rejected.map((item) => (
                <li key={item.id} className="irow irow--rejected">
                  <div className="irow__main">
                    <p className="irow__text">{item.content}</p>
                  </div>
                  <button
                    type="button"
                    className="btn btn--text"
                    onClick={() => onUpdate(item, { status: "inferred" })}
                  >
                    恢复
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function ItemRow({
  item,
  groupLabel,
  lit,
  onUpdate,
}: {
  item: Item;
  groupLabel?: string;
  lit: boolean;
  onUpdate: (
    item: Item,
    body: { content?: string; status?: Item["status"] },
  ) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.content);
  const [details, setDetails] = useState(false);
  const [history, setHistory] = useState<Revision[] | null>(null);
  const pending = UNDECIDED.includes(item.status);

  const classes = ["irow", `irow--${item.status}`];
  if (lit) classes.push("is-lit");

  const save = () => {
    const next = draft.trim();
    if (next && next !== item.content) onUpdate(item, { content: next });
    setEditing(false);
  };

  const toggleDetails = () => {
    const next = !details;
    setDetails(next);
    if (next && history === null) {
      void api
        .revisions(item.id)
        .then((r) => setHistory(r.items))
        .catch(() => setHistory([]));
    }
  };

  return (
    <li className={classes.join(" ")} data-item={item.code}>
      <StatusMark status={item.status} />
      <div className="irow__main">
        {groupLabel && <span className="irow__group">{groupLabel}</span>}
        {editing ? (
          <div className="irow__edit">
            <textarea
              className="field field--small"
              rows={2}
              value={draft}
              autoFocus
              aria-label="编辑需求"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save();
                if (e.key === "Escape") setEditing(false);
              }}
            />
            <span className="irow__edit-actions">
              <button
                type="button"
                className="btn btn--text"
                onClick={() => setEditing(false)}
              >
                取消
              </button>
              <button type="button" className="btn btn--small" onClick={save}>
                保存
              </button>
            </span>
          </div>
        ) : (
          <p className="irow__text">{item.content}</p>
        )}

        {pending && !editing && (
          <>
            <p className="irow__why">
              <span className="irow__status">{STATUS_TEXT[item.status]}</span>
              {item.source_kind === "user" ? "来自你的描述" : item.reason}
            </p>
            <span className="irow__actions">
              <button
                type="button"
                className="btn btn--small"
                onClick={() => onUpdate(item, { status: "confirmed" })}
              >
                确认
              </button>
              <button
                type="button"
                className="btn btn--text"
                onClick={() => {
                  setDraft(item.content);
                  setEditing(true);
                }}
              >
                修改
              </button>
              <button
                type="button"
                className="btn btn--text"
                onClick={() => onUpdate(item, { status: "rejected" })}
              >
                不对
              </button>
            </span>
          </>
        )}

        {item.status === "open" && !editing && (
          <p className="irow__why">
            <span className="irow__status">待确认</span>
            {item.reason ?? "可以在之后的对话中补充"}
          </p>
        )}

        {details && !editing && (
          <div className="irow__details">
            <p>
              {item.code} ·{" "}
              {item.source_kind === "user" ? "来自你的输入" : "AI 整理"} · 第{" "}
              {item.source_round} 轮
              {item.source_quote && item.source_kind === "user" && (
                <> · 原话「{item.source_quote}」</>
              )}
            </p>
            {history && history.length > 1 && (
              <ol className="revisions">
                {history.map((r) => (
                  <li key={r.id}>
                    {r.actor === "user" ? "你" : "AI"}
                    {r.before_status !== r.after_status
                      ? ` 标为${STATUS_TEXT[r.after_status]}`
                      : " 修改"}
                    {r.before_content &&
                      r.before_content !== r.after_content && (
                        <>：原为「{r.before_content}」</>
                      )}
                    <span className="quiet"> · {timeText(r.created_at)}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
      </div>
      {!editing && (
        <span className="irow__more">
          <button
            type="button"
            className="icon-btn icon-btn--small"
            aria-label="来源与修改记录"
            aria-expanded={details}
            onClick={toggleDetails}
          >
            <span className="dots" aria-hidden="true">
              ···
            </span>
          </button>
          {!pending && (
            <button
              type="button"
              className="icon-btn icon-btn--small"
              aria-label="编辑"
              onClick={() => {
                setDraft(item.content);
                setEditing(true);
              }}
            >
              <Icon name="edit" />
            </button>
          )}
        </span>
      )}
    </li>
  );
}
