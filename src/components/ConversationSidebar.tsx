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
      className="mb-5 min-w-0 lg:sticky lg:top-6 lg:mb-0 lg:h-[calc(100vh-3rem)]"
    >
      <div className="flex h-full min-h-0 flex-col rounded-2xl border border-white/10 bg-slate-950/65 p-3 shadow-2xl shadow-black/10 backdrop-blur">
        <div className="flex items-center justify-between gap-3 px-1 py-1">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="rounded-lg border border-cyan-300/15 bg-cyan-300/8 p-2 text-cyan-300">
              <MessageSquareText aria-hidden="true" size={16} />
            </span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-white">对话记录</h2>
              <p className="mt-0.5 text-[10px] text-slate-500">
                本地 SQLite 持久化
              </p>
            </div>
          </div>
        </div>

        <button
          className="button-primary mt-3 w-full"
          type="button"
          onClick={onNewConversation}
        >
          <Plus aria-hidden="true" size={15} />
          新建对话
        </button>

        <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1 lg:max-h-none">
          {isLoading ? (
            <div
              className="flex items-center justify-center gap-2 py-8 text-xs text-slate-500"
              role="status"
            >
              <LoaderCircle className="animate-spin" size={14} />
              正在加载记录
            </div>
          ) : conversations.length === 0 ? (
            <p className="rounded-xl border border-dashed border-white/10 px-3 py-6 text-center text-xs leading-5 text-slate-500">
              暂无历史对话
              <br />
              创建任务后会自动保存在这里
            </p>
          ) : (
            <ul className="space-y-1.5">
              {conversations.map((conversation) => {
                const selected = conversation.run_id === selectedRunId;
                return (
                  <li key={conversation.run_id}>
                    <button
                      aria-current={selected ? "page" : undefined}
                      className={`group w-full rounded-xl border px-3 py-2.5 text-left transition ${
                        selected
                          ? "border-cyan-300/25 bg-cyan-300/10 shadow-inner shadow-cyan-950/20"
                          : "border-transparent hover:border-white/8 hover:bg-white/[0.04]"
                      }`}
                      type="button"
                      onClick={() => onSelect(conversation.run_id)}
                    >
                      <span
                        className={`block truncate text-xs font-medium ${
                          selected ? "text-cyan-50" : "text-slate-300"
                        }`}
                        title={conversation.user_idea}
                      >
                        {conversation.user_idea}
                      </span>
                      <span className="mt-2 flex items-center justify-between gap-2 text-[10px] text-slate-500">
                        <span className="truncate">
                          {RUN_STATUS_LABELS[conversation.status]} · 第
                          {conversation.current_iteration}轮
                        </span>
                        {conversation.latest_score != null && (
                          <span className="font-mono text-slate-400">
                            {conversation.latest_score.toFixed(1)}
                          </span>
                        )}
                      </span>
                      <span className="mt-1.5 flex items-center gap-1 text-[9px] text-slate-600">
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
