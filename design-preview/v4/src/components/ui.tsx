import type { ItemStatus } from "../data/types";
import { STATUS_TEXT } from "../data/types";

/** 16px line icons. One stroke weight, no fills, so they stay quiet. */
const PATHS = {
  arrow: "M3 8h10M9 4l4 4-4 4",
  back: "M13 8H3M7 4L3 8l4 4",
  chevron: "M6 4l4 4-4 4",
  down: "M4 6l4 4 4-4",
  close: "M4 4l8 8M12 4l-8 8",
  check: "M3 8.5l3 3 7-7",
  outline: "M3 4h10M3 8h7M3 12h9",
  notes: "M3 3h10v8H8l-3 2.5V11H3z",
  edit: "M10.5 3.5l2 2L6 12H4v-2z",
  download: "M8 3v7M5 7l3 3 3-3M3 13h10",
  compare: "M5 3v10M11 3v10M3 6h4M9 10h4",
  plus: "M8 3v10M3 8h10",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, label }: { name: IconName; label?: string }) {
  return (
    <svg
      className="icon"
      viewBox="0 0 16 16"
      width="16"
      height="16"
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

/**
 * Status glyph. Confirmed items carry no mark at all: the baseline reads as
 * plain text, and only things that still need a decision stand out.
 */
export function StatusMark({ status }: { status: ItemStatus }) {
  if (status === "confirmed") return null;
  return (
    <span className={`smark smark--${status}`} title={STATUS_TEXT[status]}>
      <span className="sr">{STATUS_TEXT[status]}</span>
    </span>
  );
}

/** Small deterministic flat-graphic mark for a project. Decoration only. */
export function ProjectMark({
  seed,
  size = 32,
}: {
  seed: number;
  size?: number;
}) {
  const v = seed % 4;
  return (
    <svg
      className="pmark"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      aria-hidden="true"
    >
      <rect x="0.5" y="0.5" width="31" height="31" className="pmark__bg" />
      {v === 0 && <path d="M0 32 L32 0 L32 32 Z" className="pmark__ink" />}
      {v === 1 && (
        <rect x="0" y="16" width="32" height="16" className="pmark__ink" />
      )}
      {v === 2 && <circle cx="16" cy="16" r="9" className="pmark__ink" />}
      {v === 3 && <path d="M0 0 H16 V32 H0 Z" className="pmark__ink" />}
      {seed % 3 === 0 && (
        <rect x="20" y="4" width="8" height="8" className="pmark__accent" />
      )}
    </svg>
  );
}

export function Logo() {
  return (
    <svg
      className="logo"
      viewBox="0 0 20 20"
      width="20"
      height="20"
      aria-hidden="true"
    >
      <rect width="20" height="20" rx="3" />
      <path d="M5 15 L10 5 L15 15" className="logo__cut" />
      <rect x="12.5" y="12.5" width="3" height="3" className="logo__dot" />
    </svg>
  );
}

/** Five-step progress as a thin bar. Labels live in tooltips and headings. */
export function Steps({
  current,
  total = 5,
}: {
  current: number;
  total?: number;
}) {
  return (
    <span
      className="steps"
      role="img"
      aria-label={`第 ${current + 1} 步，共 ${total} 步`}
    >
      {Array.from({ length: total }, (_, i) => (
        <i
          key={i}
          className={
            i < current ? "is-done" : i === current ? "is-now" : undefined
          }
        />
      ))}
    </span>
  );
}
