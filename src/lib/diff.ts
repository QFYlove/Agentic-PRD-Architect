/**
 * A line-level text diff for reading two PRD versions side by side.
 *
 * PRD content is Markdown, but this treats it as plain text on purpose: a
 * line/paragraph diff is stable, cheap, and needs no Markdown AST editing to
 * tell a reader what the optimizer actually rewrote.
 */

export type DiffRowKind = "added" | "removed" | "context";

export interface DiffRow {
  kind: DiffRowKind;
  text: string;
  /** 1-based line in the source document; null for added lines. */
  sourceLine: number | null;
  /** 1-based line in the target document; null for removed lines. */
  targetLine: number | null;
}

export type DiffSegment =
  | {
      type: "hunk";
      /** Nearest Markdown heading at or above the hunk, so changes keep a place. */
      heading: string | null;
      rows: DiffRow[];
    }
  | { type: "skipped"; count: number };

export interface DiffResult {
  addedCount: number;
  removedCount: number;
  segments: DiffSegment[];
  /** True when both documents are identical line for line. */
  unchanged: boolean;
}

/** Unchanged lines kept on each side of a change. */
const CONTEXT_LINES = 3;
/** Shorter unchanged runs stay visible rather than becoming a marker. */
const MIN_COLLAPSE_LINES = 2;
/**
 * Cells the quadratic table may use. A PRD is tens of lines, so this is only a
 * guard against a pathological input; past it the two documents are reported as
 * a wholesale replacement instead of hanging the tab.
 */
const MAX_LCS_CELLS = 250_000;

const HEADING = /^\s{0,3}(#{1,6})\s+(.*\S)\s*$/;

function splitLines(text: string): string[] {
  if (text === "") {
    return [];
  }
  return text.replace(/\r\n/g, "\n").split("\n");
}

/**
 * Longest-common-subsequence lengths for the suffixes of `a` and `b`, so the
 * walk below can prefer the branch that keeps more shared lines.
 */
function lcsLengths(a: string[], b: string[]): Uint32Array {
  const width = b.length + 1;
  const table = new Uint32Array((a.length + 1) * width);
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i * width + j] =
        a[i] === b[j]
          ? (table[(i + 1) * width + j + 1] ?? 0) + 1
          : Math.max(
              table[(i + 1) * width + j] ?? 0,
              table[i * width + j + 1] ?? 0,
            );
    }
  }
  return table;
}

function pushRow(
  rows: DiffRow[],
  kind: DiffRowKind,
  text: string,
  sourceLine: number | null,
  targetLine: number | null,
): void {
  rows.push({ kind, text, sourceLine, targetLine });
}

function diffRows(source: string[], target: string[]): DiffRow[] {
  const rows: DiffRow[] = [];

  // Revised documents share long identical stretches at both ends; trimming
  // them keeps the table small and the walk below on the part that changed.
  let prefix = 0;
  while (
    prefix < source.length &&
    prefix < target.length &&
    source[prefix] === target[prefix]
  ) {
    prefix += 1;
  }
  let suffix = 0;
  while (
    suffix < source.length - prefix &&
    suffix < target.length - prefix &&
    source[source.length - 1 - suffix] === target[target.length - 1 - suffix]
  ) {
    suffix += 1;
  }

  for (let index = 0; index < prefix; index += 1) {
    pushRow(rows, "context", source[index]!, index + 1, index + 1);
  }

  const a = source.slice(prefix, source.length - suffix);
  const b = target.slice(prefix, target.length - suffix);
  let sourceLine = prefix + 1;
  let targetLine = prefix + 1;

  if ((a.length + 1) * (b.length + 1) > MAX_LCS_CELLS) {
    for (const text of a) {
      pushRow(rows, "removed", text, sourceLine, null);
      sourceLine += 1;
    }
    for (const text of b) {
      pushRow(rows, "added", text, null, targetLine);
      targetLine += 1;
    }
  } else {
    const width = b.length + 1;
    const table = lcsLengths(a, b);
    let i = 0;
    let j = 0;
    while (i < a.length || j < b.length) {
      if (i < a.length && j < b.length && a[i] === b[j]) {
        pushRow(rows, "context", a[i]!, sourceLine, targetLine);
        sourceLine += 1;
        targetLine += 1;
        i += 1;
        j += 1;
        continue;
      }
      // Removals are emitted before additions at the same position so a
      // rewritten line reads as "- old" then "+ new".
      const dropSource =
        j >= b.length ||
        (i < a.length &&
          (table[(i + 1) * width + j] ?? 0) >= (table[i * width + j + 1] ?? 0));
      if (dropSource) {
        pushRow(rows, "removed", a[i]!, sourceLine, null);
        sourceLine += 1;
        i += 1;
      } else {
        pushRow(rows, "added", b[j]!, null, targetLine);
        targetLine += 1;
        j += 1;
      }
    }
  }

  for (let index = 0; index < suffix; index += 1) {
    const text = source[source.length - suffix + index]!;
    pushRow(rows, "context", text, sourceLine, targetLine);
    sourceLine += 1;
    targetLine += 1;
  }

  return rows;
}

function headingsFor(rows: DiffRow[]): Array<string | null> {
  let current: string | null = null;
  return rows.map((row) => {
    const match = HEADING.exec(row.text);
    // The `#` line is the document title, not a section, so labelling the first
    // hunk with it would read as "this change is in the title" for every change
    // near the top. Sections start at `##`.
    if (match && (match[1]?.length ?? 0) > 1) {
      current = match[2] ?? null;
    }
    return current;
  });
}

function segmentsFor(rows: DiffRow[]): DiffSegment[] {
  const keep = rows.map((row) => row.kind !== "context");
  for (let index = 0; index < rows.length; index += 1) {
    if (rows[index]?.kind === "context") {
      continue;
    }
    for (
      let near = Math.max(0, index - CONTEXT_LINES);
      near <= Math.min(rows.length - 1, index + CONTEXT_LINES);
      near += 1
    ) {
      keep[near] = true;
    }
  }
  // A one-line gap between two hunks is noisier as a marker than as text.
  let run = 0;
  for (let index = 0; index <= rows.length; index += 1) {
    if (index < rows.length && !keep[index]) {
      run += 1;
      continue;
    }
    if (run > 0 && run < MIN_COLLAPSE_LINES) {
      for (let back = index - run; back < index; back += 1) {
        keep[back] = true;
      }
    }
    run = 0;
  }

  const headings = headingsFor(rows);
  const segments: DiffSegment[] = [];
  let index = 0;
  while (index < rows.length) {
    if (keep[index]) {
      const start = index;
      while (index < rows.length && keep[index]) {
        index += 1;
      }
      // Labelled by the section the first *change* sits in, not the section the
      // leading context happens to start in, which can be the previous one.
      const anchor = rows
        .slice(start, index)
        .findIndex((row) => row.kind !== "context");
      segments.push({
        type: "hunk",
        heading: headings[start + Math.max(anchor, 0)] ?? null,
        rows: rows.slice(start, index),
      });
      continue;
    }
    const start = index;
    while (index < rows.length && !keep[index]) {
      index += 1;
    }
    segments.push({ type: "skipped", count: index - start });
  }
  return segments;
}

export function diffLines(
  sourceContent: string,
  targetContent: string,
): DiffResult {
  const rows = diffRows(splitLines(sourceContent), splitLines(targetContent));
  const addedCount = rows.filter((row) => row.kind === "added").length;
  const removedCount = rows.filter((row) => row.kind === "removed").length;
  if (addedCount === 0 && removedCount === 0) {
    return { addedCount, removedCount, segments: [], unchanged: true };
  }
  return {
    addedCount,
    removedCount,
    segments: segmentsFor(rows),
    unchanged: false,
  };
}
