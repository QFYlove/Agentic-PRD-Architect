import type { ItemStatus, Priority, StageKey } from "../data/types";
import { STAGES, STATUS_LABEL } from "../data/types";

/** Shape-coded status glyph. Shape carries the meaning; colour only assists. */
export function StatusMark({ status }: { status: ItemStatus }) {
  const label = STATUS_LABEL[status];
  return (
    <svg
      className={`mark mark--${status}`}
      viewBox="0 0 12 12"
      role="img"
      aria-label={label}
    >
      <title>{label}</title>
      {status === "confirmed" && <rect x="1" y="1" width="10" height="10" />}
      {status === "inferred" && (
        <>
          <rect x="1.5" y="1.5" width="9" height="9" className="o" />
          <path d="M1.5 10.5 L10.5 1.5 L10.5 10.5 Z" />
        </>
      )}
      {status === "assumption" && (
        <rect x="1.5" y="1.5" width="9" height="9" className="o dash" />
      )}
      {status === "proposed" && (
        <>
          <rect x="1.5" y="1.5" width="9" height="9" className="o" />
          <rect x="4" y="4" width="4" height="4" className="a" />
        </>
      )}
      {status === "open" && (
        <circle cx="6" cy="6" r="4.5" className="o a-stroke" />
      )}
      {status === "rejected" && (
        <>
          <rect x="1.5" y="1.5" width="9" height="9" className="o faint" />
          <path d="M3 3 L9 9 M9 3 L3 9" className="o faint" />
        </>
      )}
    </svg>
  );
}

export function PriorityTag({ priority }: { priority: Priority }) {
  return <span className={`ptag ptag--${priority}`}>{priority}</span>;
}

export function Id({ children }: { children: string }) {
  return <span className="id">{children}</span>;
}

/** Thin segmented track. Filled up to the current stage. */
export function StageTrack({
  stage,
  compact = false,
}: {
  stage: StageKey;
  compact?: boolean;
}) {
  const current = STAGES.findIndex((s) => s.key === stage);
  return (
    <span
      className={compact ? "track track--compact" : "track"}
      role="img"
      aria-label={`阶段 ${current + 1} / ${STAGES.length}：${STAGES[current]?.label ?? ""}`}
    >
      {STAGES.map((s, i) => (
        <span
          key={s.key}
          className={
            i < current
              ? "track__seg is-done"
              : i === current
                ? "track__seg is-now"
                : "track__seg"
          }
        />
      ))}
    </span>
  );
}

/** Deterministic flat-graphic cover for a project. Pure decoration. */
export function Cover({ seed, size = 72 }: { seed: number; size?: number }) {
  const cells = Array.from({ length: 9 }, (_, i) => (seed * 7 + i * 5) % 6);
  return (
    <svg
      className="cover"
      width={size}
      height={size}
      viewBox="0 0 72 72"
      aria-hidden="true"
    >
      <rect x="0.5" y="0.5" width="71" height="71" className="cover__frame" />
      {cells.map((v, i) => {
        const x = (i % 3) * 24;
        const y = Math.floor(i / 3) * 24;
        if (v === 0)
          return (
            <rect
              key={i}
              x={x}
              y={y}
              width="24"
              height="24"
              className="cover__ink"
            />
          );
        if (v === 1)
          return (
            <path
              key={i}
              d={`M${x} ${y + 24} L${x + 24} ${y} L${x + 24} ${y + 24} Z`}
              className="cover__ink"
            />
          );
        if (v === 2 && i === seed % 9)
          return (
            <rect
              key={i}
              x={x + 6}
              y={y + 6}
              width="12"
              height="12"
              className="cover__accent"
            />
          );
        if (v === 3)
          return (
            <circle
              key={i}
              cx={x + 12}
              cy={y + 12}
              r="7"
              className="cover__line"
            />
          );
        if (v === 4)
          return (
            <path
              key={i}
              d={`M${x} ${y + 12} H${x + 24}`}
              className="cover__line"
            />
          );
        return null;
      })}
      <path
        d="M24 0 V72 M48 0 V72 M0 24 H72 M0 48 H72"
        className="cover__grid"
      />
    </svg>
  );
}

/** Crop-mark corners for emphasised regions. */
export function Corners() {
  return (
    <span className="corners" aria-hidden="true">
      <i />
      <i />
      <i />
      <i />
    </span>
  );
}

export function LogoMark() {
  return (
    <svg className="logo" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="0" y="0" width="24" height="24" />
      <path d="M5 19 L12 5 L19 19" className="logo__cut" />
      <rect x="15" y="15" width="5" height="5" className="logo__dot" />
    </svg>
  );
}
