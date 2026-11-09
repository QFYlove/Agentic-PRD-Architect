import { useState } from "react";
import { GROUPS } from "../data/explore";
import type { Insight, InsightState, Item } from "../data/types";
import { STATUS_TEXT } from "../data/types";
import type { ExploreState } from "./Explore";
import { InsightNote, NEEDS_DECISION } from "./Explore";
import { Icon, StatusMark } from "./ui";

type View = "decide" | "all";

export function Requirements({
  state,
  highlight,
  flash,
  onInsight,
  onClose,
}: {
  state: ExploreState;
  highlight: string[];
  flash: string[];
  onInsight: (id: string, s: InsightState) => void;
  onClose: () => void;
}) {
  const { items, setItems, insights, pendingItems, pendingInsights, round } =
    state;
  const [view, setView] = useState<View>(
    pendingItems.length + pendingInsights.length > 0 ? "decide" : "all",
  );
  const [hover, setHover] = useState<string[]>([]);
  const lit = [...highlight, ...hover];

  // Highlighted items from the conversation force the full view so they are visible.
  const effective: View =
    highlight.length > 0 &&
    !highlight.some((id) => pendingItems.some((p) => p.id === id))
      ? "all"
      : view;

  const confirm = (id: string) =>
    setItems((prev) =>
      prev.map((i) => (i.id === id ? { ...i, status: "confirmed" } : i)),
    );
  const reject = (id: string) =>
    setItems((prev) => prev.filter((i) => i.id !== id));
  const edit = (id: string, text: string) =>
    setItems((prev) =>
      prev.map((i) =>
        i.id === id && i.text !== text
          ? {
              ...i,
              text,
              status: "confirmed",
              source: "you",
              round,
              previous: [...(i.previous ?? []), i.text],
            }
          : i,
      ),
    );

  const total = pendingItems.length + pendingInsights.length;

  return (
    <aside className="req" aria-label="需求">
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
              <span className="calm__mark" aria-hidden="true" />
              <p>没有需要你决定的事项。</p>
              <p className="quiet">新的推断和发现会出现在这里。</p>
            </div>
          ) : (
            <>
              {pendingInsights.length > 0 && (
                <section className="req__block">
                  <h3 className="label">AI 发现</h3>
                  {pendingInsights.map((i) => (
                    <InsightNote
                      key={i.id}
                      insight={i}
                      initiallyOpen={false}
                      onHover={setHover}
                      onState={onInsight}
                    />
                  ))}
                </section>
              )}
              {pendingItems.length > 0 && (
                <section className="req__block">
                  <h3 className="label">需要确认</h3>
                  <ul className="ilist">
                    {pendingItems.map((item) => (
                      <ItemRow
                        key={item.id}
                        item={item}
                        showGroup
                        lit={lit.includes(item.id)}
                        fresh={flash.includes(item.id)}
                        onConfirm={confirm}
                        onReject={reject}
                        onEdit={edit}
                      />
                    ))}
                  </ul>
                </section>
              )}
            </>
          )
        ) : (
          <Baseline
            items={items}
            insights={insights}
            lit={lit}
            flash={flash}
            onConfirm={confirm}
            onReject={reject}
            onEdit={edit}
          />
        )}
      </div>
    </aside>
  );
}

function Baseline({
  items,
  insights,
  lit,
  flash,
  onConfirm,
  onReject,
  onEdit,
}: {
  items: Item[];
  insights: Insight[];
  lit: string[];
  flash: string[];
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
  onEdit: (id: string, text: string) => void;
}) {
  const handled = insights.filter((i) => i.state !== "open").length;
  return (
    <div className="baseline">
      {GROUPS.map((g) => {
        const list = items.filter((i) => i.group === g.key);
        return (
          <section key={g.key} className="bgroup">
            <h3 className="bgroup__title">
              {g.label}
              {g.core && list.every((i) => i.status !== "confirmed") && (
                <span className="bgroup__missing">待补充</span>
              )}
            </h3>
            {list.length === 0 ? (
              <p className="bgroup__empty">
                {g.core ? "还没有明确，AI 会优先询问。" : "暂无"}
              </p>
            ) : (
              <ul className="ilist">
                {list.map((item) => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    lit={lit.includes(item.id)}
                    fresh={flash.includes(item.id)}
                    onConfirm={onConfirm}
                    onReject={onReject}
                    onEdit={onEdit}
                  />
                ))}
              </ul>
            )}
          </section>
        );
      })}
      {handled > 0 && (
        <p className="quiet baseline__foot">已处理 {handled} 条 AI 发现</p>
      )}
    </div>
  );
}

function ItemRow({
  item,
  showGroup = false,
  lit,
  fresh,
  onConfirm,
  onReject,
  onEdit,
}: {
  item: Item;
  showGroup?: boolean;
  lit: boolean;
  fresh: boolean;
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
  onEdit: (id: string, text: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.text);
  const [details, setDetails] = useState(false);
  const pending = NEEDS_DECISION.includes(item.status);
  const group = GROUPS.find((g) => g.key === item.group);

  const classes = ["irow", `irow--${item.status}`];
  if (lit) classes.push("is-lit");
  if (fresh) classes.push("is-fresh");

  const save = () => {
    const next = draft.trim();
    if (next) onEdit(item.id, next);
    setEditing(false);
  };

  return (
    <li className={classes.join(" ")} data-item={item.id}>
      <StatusMark status={item.status} />
      <div className="irow__main">
        {showGroup && <span className="irow__group">{group?.label}</span>}
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
          <p className="irow__text">{item.text}</p>
        )}

        {pending && !editing && (
          <>
            <p className="irow__why">
              <span className="irow__status">{STATUS_TEXT[item.status]}</span>
              {item.reason}
            </p>
            <span className="irow__actions">
              <button
                type="button"
                className="btn btn--small"
                onClick={() => onConfirm(item.id)}
              >
                确认
              </button>
              <button
                type="button"
                className="btn btn--text"
                onClick={() => {
                  setDraft(item.text);
                  setEditing(true);
                }}
              >
                修改
              </button>
              <button
                type="button"
                className="btn btn--text"
                onClick={() => onReject(item.id)}
              >
                不对
              </button>
            </span>
          </>
        )}

        {!pending && !editing && item.status === "open" && (
          <p className="irow__why">待确认 · 可以在之后的对话中补充</p>
        )}

        {details && !editing && (
          <p className="irow__details">
            {item.source === "you" ? "来自你的回答" : "AI 整理"} · 第{" "}
            {item.round} 轮
            {item.previous && item.previous.length > 0 && (
              <> · 原为「{item.previous[item.previous.length - 1]}」</>
            )}
          </p>
        )}
      </div>
      {!pending && !editing && (
        <span className="irow__more">
          <button
            type="button"
            className="icon-btn icon-btn--small"
            aria-label="来源"
            aria-expanded={details}
            onClick={() => setDetails((v) => !v)}
          >
            <span className="dots" aria-hidden="true">
              ···
            </span>
          </button>
          <button
            type="button"
            className="icon-btn icon-btn--small"
            aria-label="编辑"
            onClick={() => {
              setDraft(item.text);
              setEditing(true);
            }}
          >
            <Icon name="edit" />
          </button>
        </span>
      )}
    </li>
  );
}
