import { Clock3, LoaderCircle, MessageSquareText, Plus } from "lucide-react";

import type { RunSummary } from "../lib/types";
import { RUN_STATUS_LABELS } from "./StatusBadge";

export interface ConversationSidebarProps {
  conversations: RunSummary[];
  selectedRunId: string | null;
  isLoading: boolean;
  onSelect(runId: string): void;
  onNewConversation(): void;
}

function updatedLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function ConversationSidebar({
  conversations,
  selectedRunId,
  isLoading,
  onSelect,
  onNewConversation,
}: ConversationSidebarProps) {
  return (
    <aside
      aria-label="对话记录"
      className="min-w-0 lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)]"
    >
      <div className="flex h-full min-h-0 flex-col rounded-panel border border-line bg-surface p-3">
        <div className="flex min-w-0 items-center gap-2 px-1">
          <MessageSquareText
            aria-hidden="true"
            size={15}
            className="shrink-0 text-ink-muted"
          />
          <h2 className="text-sm font-semibold text-ink">对话记录</h2>
        </div>

        <button
          className="button-secondary mt-3 w-full"
          type="button"
          onClick={onNewConversation}
        >
          <Plus aria-hidden="true" size={15} />
          新建对话
        </button>

        <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1 lg:max-h-none">
          {isLoading ? (
            <div
              className="flex items-center justify-center gap-2 py-8 text-xs text-ink-faint"
              role="status"
            >
              <LoaderCircle className="animate-spin" size={14} />
              正在加载记录
            </div>
          ) : conversations.length === 0 ? (
            <p className="rounded-control border border-dashed border-line px-3 py-6 text-center text-xs leading-5 text-ink-faint">
              暂无历史对话
              <br />
              创建任务后会自动保存在这里
            </p>
          ) : (
            <ul className="space-y-1">
              {conversations.map((conversation) => {
                const selected = conversation.run_id === selectedRunId;
                // The list shows the best score, not the latest one: a later
                // version may legitimately score lower, and the row must not
                // imply the last attempt is the result to keep.
                const best =
                  conversation.best_version != null &&
                  conversation.best_score != null
                    ? {
                        version: conversation.best_version,
                        score: conversation.best_score,
                      }
                    : null;
                return (
                  <li key={conversation.run_id}>
                    <button
                      aria-current={selected ? "page" : undefined}
                      className={`w-full border-l-2 py-2 pl-2.5 pr-1 text-left transition ${
                        selected
                          ? "border-accent bg-accent-soft"
                          : "border-transparent hover:border-line-strong hover:bg-raised"
                      }`}
                      type="button"
                      onClick={() => onSelect(conversation.run_id)}
                    >
                      <span
                        className={`block truncate text-xs font-medium ${
                          selected ? "text-ink" : "text-ink-muted"
                        }`}
                        title={conversation.user_idea}
                      >
                        {conversation.user_idea}
                      </span>
                      <span className="mt-1.5 flex items-center justify-between gap-2 text-[10px] text-ink-faint">
                        <span className="truncate">
                          {RUN_STATUS_LABELS[conversation.status]} · 第
                          {conversation.current_iteration}轮
                        </span>
                        {best ? (
                          <span
                            className="font-mono"
                            title={`最佳版本 v${best.version} · ${best.score.toFixed(1)}`}
                          >
                            v{best.version} · {best.score.toFixed(1)}
                          </span>
                        ) : (
                          conversation.latest_score != null && (
                            <span className="font-mono">
                              {conversation.latest_score.toFixed(1)}
                            </span>
                          )
                        )}
                      </span>
                      <span className="mt-1 flex items-center gap-1 text-[9px] text-ink-faint">
                        <Clock3 aria-hidden="true" size={10} />
                        {updatedLabel(conversation.updated_at)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </aside>
  );
}
