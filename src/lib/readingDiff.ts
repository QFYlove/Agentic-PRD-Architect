/**
 * A block-level diff for reading two PRD versions as documents.
 *
 * `diff.ts` compares lines, which is the right answer for "show me the exact
 * text that changed" and the wrong one for "tell me what this revision did": a
 * line diff of Markdown puts `##`, `|---|---|` and half a table in front of the
 * reader, who then has to compile the source in their head.
 *
 * So this splits each document into whole Markdown blocks -- a heading, one list
 * item, one table, one paragraph -- and diffs those. Every unit it emits is
 * valid Markdown on its own, so the view layer can render it and the reader sees
 * a document with additions and deletions marked, not a patch.
 */

export type BlockKind =
  | "heading"
  | "table"
  | "code"
  | "list"
  | "quote"
  | "rule"
  | "paragraph";

export interface DocBlock {
  kind: BlockKind;
  /** Heading depth for `heading` blocks, null for everything else. */
  level: number | null;
  /** The block's own Markdown. Renderable without the rest of the document. */
  text: string;
}

const HEADING = /^\s{0,3}(#{1,6})\s+(.*\S)\s*$/;
const FENCE = /^\s{0,3}(`{3,}|~{3,})/;
const RULE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
const LIST_ITEM = /^\s{0,3}([-*+]|\d{1,9}[.)])\s+/;

function isBlank(line: string): boolean {
  return line.trim() === "";
}

/**
 * A GFM table's second line: pipes, dashes, colons and spaces only. Matching on
 * shape rather than column count keeps a hand-written table together even when
 * its separator is ragged.
 */
function isTableDelimiter(line: string): boolean {
  return (
    line.includes("|") && line.includes("-") && /^[\s|:-]+$/.test(line.trim())
  );
}

function breaksBlock(line: string): boolean {
  return HEADING.test(line) || FENCE.test(line) || RULE.test(line);
}

export function splitBlocks(markdown: string): DocBlock[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: DocBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index]!;
    if (isBlank(line)) {
      index += 1;
      continue;
    }

    const fence = FENCE.exec(line);
    if (fence) {
      const marker = fence[1]!;
      const start = index;
      index += 1;
      while (
        index < lines.length &&
        !lines[index]!.trimStart().startsWith(marker)
      ) {
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      blocks.push({
        kind: "code",
        level: null,
        text: lines.slice(start, index).join("\n"),
      });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({
        kind: "heading",
        level: heading[1]!.length,
        text: line.trim(),
      });
      index += 1;
      continue;
    }

    if (RULE.test(line)) {
      blocks.push({ kind: "rule", level: null, text: line.trim() });
      index += 1;
      continue;
    }

    if (
      line.includes("|") &&
      index + 1 < lines.length &&
      isTableDelimiter(lines[index + 1]!)
    ) {
      const start = index;
      index += 2;
      while (
        index < lines.length &&
        !isBlank(lines[index]!) &&
        lines[index]!.includes("|")
      ) {
        index += 1;
      }
      blocks.push({
        kind: "table",
        level: null,
        text: lines.slice(start, index).join("\n"),
      });
      continue;
    }

    // One list *item* per block, not one list. A revision that adds a single
    // requirement should read as one added bullet; keeping the whole list
    // together would reprint every sibling as changed.
    if (LIST_ITEM.test(line)) {
      const start = index;
      index += 1;
      while (
        index < lines.length &&
        !isBlank(lines[index]!) &&
        !LIST_ITEM.test(lines[index]!) &&
        !breaksBlock(lines[index]!) &&
        /^\s{2,}/.test(lines[index]!)
      ) {
        index += 1;
      }
      blocks.push({
        kind: "list",
        level: null,
        text: lines.slice(start, index).join("\n"),
      });
      continue;
    }

    const quoted = line.trimStart().startsWith(">");
    const start = index;
    index += 1;
    while (index < lines.length) {
      const next = lines[index]!;
      if (
        isBlank(next) ||
        breaksBlock(next) ||
        LIST_ITEM.test(next) ||
        quoted !== next.trimStart().startsWith(">")
      ) {
        break;
      }
      index += 1;
    }
    blocks.push({
      kind: quoted ? "quote" : "paragraph",
      level: null,
      text: lines.slice(start, index).join("\n"),
    });
  }

  return blocks;
}

export type ReadingChange = "added" | "removed" | "unchanged";

export interface ReadingBlockRow {
  type: "block";
  change: ReadingChange;
  block: DocBlock;
}

export interface ReadingSkippedRow {
  type: "skipped";
  count: number;
}

export type ReadingRow = ReadingBlockRow | ReadingSkippedRow;

export interface ReadingSection {
  /** The section's own heading text, or null for content above the first one. */
  heading: string | null;
  /** How the heading itself changed, so a wholly new section reads as new. */
  change: ReadingChange;
  changed: boolean;
  addedBlocks: number;
  removedBlocks: number;
  rows: ReadingRow[];
}

export interface ReadingDiffResult {
  sections: ReadingSection[];
  addedBlocks: number;
  removedBlocks: number;
  unchanged: boolean;
}

/** Unchanged blocks in a row before the view collapses them to a marker. */
const MIN_COLLAPSE_BLOCKS = 3;
/**
 * Cells the quadratic table may use. Blocks are far coarser than lines, so this
 * is only a guard against a pathological document; past it the two versions are
 * reported as a wholesale replacement rather than hanging the tab.
 */
const MAX_LCS_CELLS = 250_000;

function lcsLengths(a: DocBlock[], b: DocBlock[]): Uint32Array {
  const width = b.length + 1;
  const table = new Uint32Array((a.length + 1) * width);
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i * width + j] =
        a[i]!.text === b[j]!.text
          ? (table[(i + 1) * width + j + 1] ?? 0) + 1
          : Math.max(
              table[(i + 1) * width + j] ?? 0,
              table[i * width + j + 1] ?? 0,
            );
    }
  }
  return table;
}

function diffBlocks(source: DocBlock[], target: DocBlock[]): ReadingBlockRow[] {
  const rows: ReadingBlockRow[] = [];
  if ((source.length + 1) * (target.length + 1) > MAX_LCS_CELLS) {
    for (const block of source) {
      rows.push({ type: "block", change: "removed", block });
    }
    for (const block of target) {
      rows.push({ type: "block", change: "added", block });
    }
    return rows;
  }

  const width = target.length + 1;
  const table = lcsLengths(source, target);
  let i = 0;
  let j = 0;
  while (i < source.length || j < target.length) {
    if (
      i < source.length &&
      j < target.length &&
      source[i]!.text === target[j]!.text
    ) {
      rows.push({ type: "block", change: "unchanged", block: source[i]! });
      i += 1;
      j += 1;
      continue;
    }
    // A rewritten block reads as "was this" then "is now this", so the removal
    // is emitted first when the walk has no reason to prefer the other side.
    const dropSource =
      j >= target.length ||
      (i < source.length &&
        (table[(i + 1) * width + j] ?? 0) >= (table[i * width + j + 1] ?? 0));
    if (dropSource) {
      rows.push({ type: "block", change: "removed", block: source[i]! });
      i += 1;
    } else {
      rows.push({ type: "block", change: "added", block: target[j]! });
      j += 1;
    }
  }
  return rows;
}

/** Sections start at `##`: `#` is the document title, not a section. */
function startsSection(row: ReadingBlockRow): boolean {
  return row.block.kind === "heading" && (row.block.level ?? 1) > 1;
}

function collapse(rows: ReadingBlockRow[]): ReadingRow[] {
  const out: ReadingRow[] = [];
  let index = 0;
  while (index < rows.length) {
    if (rows[index]!.change !== "unchanged") {
      out.push(rows[index]!);
      index += 1;
      continue;
    }
    const start = index;
    while (index < rows.length && rows[index]!.change === "unchanged") {
      index += 1;
    }
    const run = index - start;
    // A one- or two-block gap between two changes is easier to read as context
    // than as a "3 blocks unchanged" marker interrupting the section twice.
    if (run >= MIN_COLLAPSE_BLOCKS) {
      out.push({ type: "skipped", count: run });
    } else {
      out.push(...rows.slice(start, index));
    }
  }
  return out;
}

function buildSection(
  heading: ReadingBlockRow | null,
  body: ReadingBlockRow[],
): ReadingSection {
  const addedBlocks = body.filter((row) => row.change === "added").length;
  const removedBlocks = body.filter((row) => row.change === "removed").length;
  const headingChanged = heading !== null && heading.change !== "unchanged";
  const changed = headingChanged || addedBlocks > 0 || removedBlocks > 0;
  return {
    heading: heading ? headingText(heading.block.text) : null,
    change: heading?.change ?? "unchanged",
    changed,
    addedBlocks,
    removedBlocks,
    // An untouched section is named and counted rather than reprinted: the point
    // of a reading comparison is the revision, not a second copy of the PRD.
    rows: changed
      ? collapse(body)
      : body.length > 0
        ? [{ type: "skipped", count: body.length }]
        : [],
  };
}

function headingText(text: string): string {
  return HEADING.exec(text)?.[2] ?? text;
}

export function readingDiff(
  sourceContent: string,
  targetContent: string,
): ReadingDiffResult {
  const rows = diffBlocks(
    splitBlocks(sourceContent),
    splitBlocks(targetContent),
  );
  const addedBlocks = rows.filter((row) => row.change === "added").length;
  const removedBlocks = rows.filter((row) => row.change === "removed").length;
  if (addedBlocks === 0 && removedBlocks === 0) {
    return { sections: [], addedBlocks, removedBlocks, unchanged: true };
  }

  const sections: ReadingSection[] = [];
  let heading: ReadingBlockRow | null = null;
  let body: ReadingBlockRow[] = [];
  for (const row of rows) {
    if (startsSection(row)) {
      if (heading !== null || body.length > 0) {
        sections.push(buildSection(heading, body));
      }
      heading = row;
      body = [];
      continue;
    }
    body.push(row);
  }
  if (heading !== null || body.length > 0) {
    sections.push(buildSection(heading, body));
  }

  return {
    // An unchanged run of blocks above the first heading has no name to orient a
    // reader and nothing to report, so it is dropped rather than shown as an
    // anonymous "unchanged" stub. Named sections are always listed, because
    // knowing a section was left alone is itself part of reading a revision.
    sections: sections.filter(
      (section) => section.changed || section.heading !== null,
    ),
    addedBlocks,
    removedBlocks,
    unchanged: false,
  };
}
