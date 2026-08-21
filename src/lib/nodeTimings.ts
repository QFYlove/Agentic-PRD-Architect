import type { NodeTiming } from "./types";

/** Display names for the six nodes, in the order the pipeline runs them. */
const NODE_LABELS: Record<string, string> = {
  generator: "Generator",
  tech_reviewer: "Tech Reviewer",
  ux_reviewer: "UX Reviewer",
  biz_reviewer: "Biz Reviewer",
  aggregator: "Aggregator",
  optimizer: "Optimizer",
};

export interface NodeTimingRow {
  /** `Generator v2`, `Tech Reviewer v1` — the version is part of the identity. */
  label: string;
  seconds: number;
  succeeded: boolean;
  inputTokens: number;
  outputTokens: number;
  /** Set only on a retry, so a repeated label is explained rather than confusing. */
  attempt: number | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finiteNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

/**
 * The snapshot's timings as rows, or an empty list.
 *
 * Read defensively rather than trusted: `parseRunSnapshot` does not validate this
 * field, and a run recorded before timings existed has no such key at all. A
 * malformed entry is dropped instead of throwing — a telemetry panel must never
 * be the thing that stops a finished PRD from rendering.
 */
export function nodeTimingRows(value: unknown): NodeTimingRow[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const rows: NodeTimingRow[] = [];
  for (const entry of value) {
    if (!isRecord(entry) || typeof entry.node !== "string") {
      continue;
    }
    const timing = entry as unknown as NodeTiming;
    const version = finiteNumber(timing.version, 0);
    const attempt = finiteNumber(timing.attempt, 1);
    const name = NODE_LABELS[timing.node] ?? timing.node;
    rows.push({
      label: version > 0 ? `${name} v${version}` : name,
      seconds: Math.max(0, finiteNumber(timing.seconds, 0)),
      succeeded: timing.succeeded !== false,
      inputTokens: Math.max(0, finiteNumber(timing.input_tokens, 0)),
      outputTokens: Math.max(0, finiteNumber(timing.output_tokens, 0)),
      attempt: attempt > 1 ? attempt : null,
    });
  }
  return rows;
}

/** `12.4 s` — one decimal is the resolution the question needs. */
export function formatSeconds(seconds: number): string {
  return `${seconds.toFixed(1)} s`;
}

/** The slowest recorded call, used to scale the bars. Never zero. */
export function slowestSeconds(rows: NodeTimingRow[]): number {
  return rows.reduce((max, row) => Math.max(max, row.seconds), 0) || 1;
}
