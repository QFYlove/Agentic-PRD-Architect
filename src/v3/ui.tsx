import {
  Children,
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ItemStatus, Reviewer, Severity } from "./types";

// --- Functional icons only -------------------------------------------------

const PATHS = {
  arrow: "M3 8h10M9 4l4 4-4 4",
  back: "M13 8H3M7 4L3 8l4 4",
  chevron: "M6 4l4 4-4 4",
  down: "M4 6l4 4 4-4",
  close: "M4 4l8 8M12 4l-8 8",
  outline: "M3 4h10M3 8h7M3 12h10",
  edit: "M10.5 3.5l2 2L6 12H4v-2z",
  download: "M8 3v7M5 7l3 3 3-3M3 13h10",
  up: "M4 10l4-4 4 4",
  plus: "M8 3v10M3 8h10",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name }: { name: IconName }) {
  return (
    <svg className="icon" viewBox="0 0 16 16" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}

// --- Labels ------------------------------------------------------------------

export const STATUS_TEXT: Record<ItemStatus, string> = {
  confirmed: "已确认",
  inferred: "AI 推断",
  proposed: "AI 建议",
  assumption: "假设",
  open: "待确认",
  rejected: "已否定",
};

export const REVIEWER_TEXT: Record<Reviewer, string> = {
  analyst: "产品分析",
  product: "产品",
  ux: "体验",
  tech: "技术",
  biz: "商业",
};

export const SEVERITY_TEXT: Record<Severity, string> = {
  must_fix: "必须修改",
  should_fix: "建议修改",
  optional: "可选",
};

export const KIND_TEXT: Record<string, string> = {
  gap: "信息缺口",
  conflict: "逻辑冲突",
  scenario: "场景遗漏",
  risk: "产品风险",
  opportunity: "产品机会",
};

export const FINDING_STATUS_TEXT: Record<string, string> = {
  open: "待处理",
  accepted: "已采纳",
  modified: "修改后采纳",
  rejected: "已拒绝",
  deferred: "暂缓",
  resolved: "已解决",
  stale: "需重新确认",
};

/** Only undecided states carry a mark; confirmed text is plain. */
export function StatusMark({ status }: { status: ItemStatus }) {
  if (status === "confirmed" || status === "rejected") return null;
  return (
    <span
      className={`smark smark--${status}`}
      role="img"
      aria-label={STATUS_TEXT[status]}
      title={STATUS_TEXT[status]}
    />
  );
}

export function timeText(iso: string): string {
  const date = new Date(iso);
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
}

// --- Toast -------------------------------------------------------------------

interface ToastState {
  text: string;
  action?: { label: string; run: () => void };
  error?: boolean;
}

const ToastContext = createContext<(toast: ToastState) => void>(
  () => undefined,
);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const show = useCallback((next: ToastState) => {
    setToast(next);
    window.setTimeout(
      () => setToast((current) => (current === next ? null : current)),
      next.action ? 9000 : 4500,
    );
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && (
        <div
          className={`toast${toast.error ? " toast--error" : ""}`}
          role={toast.error ? "alert" : "status"}
          data-testid="toast"
        >
          <span>{toast.text}</span>
          {toast.action && (
            <button
              type="button"
              className="toast__action"
              onClick={() => {
                toast.action?.run();
                setToast(null);
              }}
            >
              {toast.action.label}
            </button>
          )}
          <button
            type="button"
            className="toast__close"
            aria-label="关闭提示"
            onClick={() => setToast(null)}
          >
            <Icon name="close" />
          </button>
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}

// --- Markdown ----------------------------------------------------------------

export interface Mark {
  quote: string;
  code: string;
  severity: Severity;
}

const FACT_CLASS: Record<string, string> = {
  用户输入: "fact fact--user",
  假设: "fact fact--assume",
  "AI 推断": "fact fact--assume",
  建议: "fact fact--assume",
  待确认: "fact fact--open",
};

const SEV_CLASS: Record<Severity, string> = {
  must_fix: "high",
  should_fix: "medium",
  optional: "low",
};

const FACT = /\[(用户输入|已验证事实|已确认|假设|建议|待确认|AI 推断)\]/g;

function decorateText(
  text: string,
  marks: Mark[],
  onMark: ((code: string) => void) | undefined,
  keyBase: string,
): ReactNode[] {
  const out: ReactNode[] = [];
  let rest = text;
  let index = 0;
  while (rest) {
    let best: { at: number; mark: Mark } | null = null;
    for (const mark of marks) {
      const at = rest.indexOf(mark.quote);
      if (at >= 0 && (best === null || at < best.at)) best = { at, mark };
    }
    const segment = best ? rest.slice(0, best.at) : rest;
    let cursor = 0;
    for (const match of segment.matchAll(FACT)) {
      const at = match.index ?? 0;
      if (at > cursor) out.push(segment.slice(cursor, at));
      out.push(
        <span
          key={`${keyBase}-f${index++}`}
          className={FACT_CLASS[match[1] ?? ""] ?? "fact"}
        >
          {match[1]}
        </span>,
      );
      cursor = at + match[0].length;
    }
    if (cursor < segment.length) out.push(segment.slice(cursor));
    if (!best) break;
    const { mark } = best;
    out.push(
      <button
        key={`${keyBase}-m${index++}`}
        type="button"
        className="anchor"
        data-sev={SEV_CLASS[mark.severity]}
        data-finding={mark.code}
        onClick={() => onMark?.(mark.code)}
        title="查看审查意见"
      >
        {mark.quote}
      </button>,
    );
    rest = rest.slice(best.at + mark.quote.length);
  }
  return out;
}

function decorate(
  children: ReactNode,
  marks: Mark[],
  onMark?: (code: string) => void,
): ReactNode {
  let n = 0;
  return Children.map(children, (child) => {
    n += 1;
    if (typeof child === "string")
      return decorateText(child, marks, onMark, `t${n}`);
    return child;
  });
}

export function Markdown({
  body,
  marks = [],
  onMark,
}: {
  body: string;
  marks?: Mark[];
  onMark?: (code: string) => void;
}) {
  const wrap =
    (Tag: "p" | "li" | "td" | "th" | "strong" | "em") =>
    ({ children }: { children?: ReactNode }) => (
      <Tag>{decorate(children, marks, onMark)}</Tag>
    );
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: wrap("p"),
          li: wrap("li"),
          td: wrap("td"),
          th: wrap("th"),
          strong: wrap("strong"),
          em: wrap("em"),
          table: ({ children }) => (
            <div className="md__table">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {body}
      </ReactMarkdown>
    </div>
  );
}

/** The quoted span of a finding's evidence, if it has one. */
export function quoteOf(evidence: string): string {
  const match = /[「“"『](.+?)[」”"』]/.exec(evidence);
  return (match?.[1] ?? "").trim();
}
