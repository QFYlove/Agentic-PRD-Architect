import { useState } from "react";
import { InsightNote } from "./Explore";
import { api } from "./api";
import { running, type ProjectStore } from "./store";
import type { Brief, Finding, FindingStatus } from "./types";
import { Icon, Markdown, timeText } from "./ui";

/** Product Brief: assembled from the baseline, edited, then confirmed once. */
export function BriefView({ store }: { store: ProjectStore }) {
  const { data } = store;
  const projectId = data.summary!.id;
  const [shown, setShown] = useState<number | null>(null);
  const latest = data.briefs[0];
  const brief = data.briefs.find((b) => b.version === shown) ?? latest;
  const confirmed = data.briefs.find((b) => b.confirmed_at !== null);
  const hasSections = (data.sections?.items.length ?? 0) > 0;

  if (!brief) {
    return (
      <div className="stage">
        <h1 className="page-title">Product Brief</h1>
        <p className="stage__lede">
          Brief 是写 PRD 之前的需求基线快照：从需求面板整理出来，由你确认。PRD
          只读取你确认过的 Brief。
        </p>
        <button
          type="button"
          className="btn btn--primary"
          disabled={data.items.length === 0}
          onClick={() => void store.act(() => api.draftBrief(projectId))}
        >
          从当前需求整理 Brief
          <Icon name="arrow" />
        </button>
        {data.items.length === 0 && (
          <p className="quiet stage__note">
            需求还是空的，先到「需求」里回答几个问题。
          </p>
        )}
      </div>
    );
  }

  const isDraft = brief.confirmed_at === null;
  return (
    <div className="stage stage--brief">
      <header className="stage__head">
        <div>
          <h1 className="page-title">Product Brief</h1>
          <p className="talk__status">
            v{brief.version} ·{" "}
            {isDraft
              ? "草稿，确认后才会用于生成 PRD"
              : `已确认 · ${timeText(brief.confirmed_at!)}`}
          </p>
        </div>
        <div className="talk__actions">
          {data.briefs.length > 1 && (
            <select
              className="select"
              aria-label="Brief 版本"
              value={brief.version}
              onChange={(e) => setShown(Number(e.target.value))}
            >
              {data.briefs.map((b) => (
                <option key={b.id} value={b.version}>
                  v{b.version}
                  {b.confirmed_at ? "（已确认）" : "（草稿）"}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            className="btn btn--text"
            disabled={running(store)}
            title="Product Analyst 检查这份 Brief 的定位、用户、问题、场景、目标、方案、缺失信息和冲突。会调用一次模型。"
            onClick={() =>
              void store.startJob(
                () => api.analyze(projectId, brief.id),
                "检查 Brief",
              )
            }
          >
            {running(store, "analyze") ? "正在检查…" : "检查 Brief"}
          </button>
          {!isDraft && (
            <button
              type="button"
              className="btn btn--text"
              onClick={() => {
                setShown(null);
                void store.act(
                  () => api.draftBrief(projectId),
                  "已按最新需求整理新版本。",
                );
              }}
            >
              按最新需求重新整理
            </button>
          )}
          {isDraft && (
            <button
              type="button"
              className="btn btn--primary"
              onClick={() =>
                void store.act(
                  () => api.confirmBrief(brief.id),
                  "Brief 已确认。",
                )
              }
            >
              确认 Brief
            </button>
          )}
        </div>
      </header>

      {isDraft && brief.unconfirmed_count > 0 && (
        <p className="banner">
          其中 {brief.unconfirmed_count}{" "}
          项还没有确认。可以先回到「需求」确认，也可以直接确认
          Brief：它们会以「假设」或「待确认」的身份带进 PRD。
        </p>
      )}

      <BriefCheck store={store} version={brief.version} />

      <div className="brief">
        {brief.sections.map((section) => (
          <BriefBlock
            key={section.key}
            brief={brief}
            sectionKey={section.key}
            store={store}
          />
        ))}
      </div>

      {!isDraft && !hasSections && confirmed && (
        <div className="next">
          <p>
            下一步：AI 根据这份 Brief 设计 PRD
            的章节结构。生成后你可以增删、改名和调整顺序。
          </p>
          <button
            type="button"
            className="btn btn--primary"
            disabled={running(store)}
            onClick={() =>
              void store.startJob(() => api.outline(projectId), "生成大纲")
            }
          >
            {running(store, "outline") ? "正在生成大纲…" : "生成 PRD 大纲"}
            <Icon name="arrow" />
          </button>
        </div>
      )}
    </div>
  );
}

function BriefBlock({
  brief,
  sectionKey,
  store,
}: {
  brief: Brief;
  sectionKey: string;
  store: ProjectStore;
}) {
  const section = brief.sections.find((s) => s.key === sectionKey)!;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(section.text);
  const editable = brief.confirmed_at === null;
  const empty = section.text === "（暂无）";

  const save = async () => {
    await store.act(() => api.editBrief(brief.id, sectionKey, draft));
    setEditing(false);
  };

  return (
    <section className={empty ? "bsec is-empty" : "bsec"}>
      <header className="bsec__head">
        <h2 className="bsec__title">{section.title}</h2>
        {section.edited && <span className="sec__by">你修改</span>}
        {editable && !editing && (
          <button
            type="button"
            className="btn btn--text bsec__edit"
            onClick={() => {
              setDraft(section.text);
              setEditing(true);
            }}
          >
            <Icon name="edit" />
            编辑
          </button>
        )}
      </header>
      {editing ? (
        <div className="sec__editor">
          <textarea
            className="field field--source"
            rows={Math.max(3, draft.split("\n").length + 1)}
            value={draft}
            autoFocus
            aria-label={`编辑${section.title}`}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="sec__editor-foot">
            <span className="quiet">
              这里只改 Brief 的文字，需求面板里的原始条目不变
            </span>
            <button
              type="button"
              className="btn btn--text"
              onClick={() => setEditing(false)}
            >
              取消
            </button>
            <button
              type="button"
              className="btn btn--small"
              onClick={() => void save()}
            >
              保存
            </button>
          </div>
        </div>
      ) : empty ? (
        <p className="quiet">暂无</p>
      ) : (
        <Markdown body={section.text} />
      )}
    </section>
  );
}

/** Product Analyst results for this Brief version, shown above the text. */
function BriefCheck({
  store,
  version,
}: {
  store: ProjectStore;
  version: number;
}) {
  const checked = store.data.baseline.filter(
    (f) => f.brief_version === version,
  );
  const [open, setOpen] = useState(true);
  if (running(store, "analyze")) {
    return (
      <p className="banner" aria-live="polite">
        正在检查 Brief…
      </p>
    );
  }
  if (store.job?.kind === "analyze" && store.job.status === "failed") {
    return (
      <p className="banner banner--warn" role="alert">
        检查没有完成：{store.job.error?.message ?? "AI 任务失败"}
        。可以再试一次。
      </p>
    );
  }
  const ran = (store.data.conversation?.messages ?? []).some(
    (m) =>
      m.kind === "analysis" &&
      m.content.startsWith(`检查了 Product Brief v${version}：`),
  );
  if (checked.length === 0) {
    return ran ? (
      <p className="banner" data-testid="brief-check">
        检查了这份 Brief，没有发现需要处理的问题。
      </p>
    ) : null;
  }
  const pending = checked.filter((f) => f.status === "open");
  const decide = (finding: Finding, status: FindingStatus) =>
    void store.act(() => api.decide(finding.id, status));
  return (
    <section
      className="brief-check"
      data-testid="brief-check"
      aria-label="Brief 检查结果"
    >
      <button
        type="button"
        className="more more--flush"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name={open ? "down" : "chevron"} />
        检查发现 {checked.length} 个问题
        {pending.length > 0 && `，${pending.length} 个待你决定`}
      </button>
      {open &&
        checked.map((f) => (
          <InsightNote
            key={f.id}
            finding={f}
            initiallyOpen={f.status === "open" && pending.length <= 2}
            onHover={() => undefined}
            onDecide={decide}
          />
        ))}
    </section>
  );
}
