import { Pause, Play, RotateCcw, Square } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import type { RunStatus } from "../lib/types";
import { isTerminalRunStatus } from "../lib/types";

interface RunControlsProps {
  status: RunStatus;
  pendingControl: "pause" | "resume" | "cancel" | null;
  onPause(): Promise<void>;
  onResume(userOverride?: string): Promise<void>;
  onCancel(): Promise<void>;
  onNewRun(): void;
}

const PAUSABLE = new Set<RunStatus>([
  "GENERATING",
  "REVIEWING",
  "AGGREGATING",
  "OPTIMIZING",
]);

export function RunControls({
  status,
  pendingControl,
  onPause,
  onResume,
  onCancel,
  onNewRun,
}: RunControlsProps) {
  const [override, setOverride] = useState("");
  const [showResumeForm, setShowResumeForm] = useState(true);
  const busy = pendingControl !== null;
  const canCancel =
    !isTerminalRunStatus(status) && status !== "CANCEL_REQUESTED";

  async function submitResume(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || override.length > 2000) {
      return;
    }
    await onResume(override);
  }

  return (
    <section className="panel" aria-labelledby="run-controls-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2
          id="run-controls-heading"
          className="text-sm font-semibold text-ink"
        >
          运行控制
        </h2>
        <div className="flex flex-wrap gap-2">
          {PAUSABLE.has(status) && (
            <button
              className="button-secondary"
              type="button"
              disabled={busy}
              onClick={() => void onPause()}
            >
              <Pause aria-hidden="true" size={16} />
              {pendingControl === "pause" ? "正在请求…" : "暂停"}
            </button>
          )}
          {canCancel && (
            <button
              className="button-danger"
              type="button"
              disabled={busy}
              onClick={() => void onCancel()}
            >
              <Square aria-hidden="true" size={14} />
              {pendingControl === "cancel" ? "正在取消…" : "取消"}
            </button>
          )}
          <button
            className="button-secondary"
            type="button"
            disabled={busy}
            onClick={onNewRun}
          >
            <RotateCcw aria-hidden="true" size={16} />
            新建任务
          </button>
        </div>
      </div>

      {status === "PAUSE_REQUESTED" && (
        <p className="mt-3 text-sm text-warn" role="status">
          当前安全步骤完成后，工作流将自动暂停。
        </p>
      )}

      {status === "PAUSED" && showResumeForm && (
        <form
          className="mt-4 border-t border-line pt-4"
          onSubmit={submitResume}
        >
          <label className="block text-sm font-medium text-ink">
            补充优化要求（选填）
            <textarea
              className="field mt-2 min-h-24 resize-y"
              value={override}
              onChange={(event) => setOverride(event.target.value)}
              maxLength={2001}
              placeholder="例如：补充退款流程和反欺诈要求。"
              aria-describedby="override-help"
            />
          </label>
          <div className="mt-2 flex items-center justify-between gap-4">
            <span
              id="override-help"
              className={`text-xs ${
                override.length > 2000 ? "text-danger" : "text-ink-faint"
              }`}
            >
              {override.length}/2000 · 此内容用于补充 PRD
              要求，不会修改系统提示词。
            </span>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              className="button-primary"
              type="submit"
              disabled={busy || override.length > 2000}
            >
              <Play aria-hidden="true" size={16} />
              {pendingControl === "resume" ? "正在继续…" : "继续运行"}
            </button>
            <button
              className="button-ghost"
              type="button"
              disabled={busy}
              onClick={() => {
                setOverride("");
                setShowResumeForm(false);
              }}
            >
              收起
            </button>
          </div>
        </form>
      )}
      {status === "PAUSED" && !showResumeForm && (
        <button
          className="button-ghost mt-3"
          type="button"
          onClick={() => setShowResumeForm(true)}
        >
          补充要求并继续
        </button>
      )}
    </section>
  );
}
