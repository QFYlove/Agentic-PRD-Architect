// A deliberately small Markdown subset for the prototype's PRD sections.
// Lines: "| a | b |" table rows (first row = header), "1. " ordered, "- "
// unordered, "> " quote, anything else a paragraph.

export type Block =
  | { kind: "p"; text: string }
  | { kind: "quote"; text: string }
  | { kind: "ol"; items: string[] }
  | { kind: "ul"; items: string[] }
  | { kind: "table"; head: string[]; rows: string[][] };

export function parseBlocks(body: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of body.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const last = blocks[blocks.length - 1];
    if (line.startsWith("|")) {
      const cells = line
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => cell.trim());
      if (last?.kind === "table") last.rows.push(cells);
      else blocks.push({ kind: "table", head: cells, rows: [] });
    } else if (/^\d+\.\s/.test(line)) {
      const text = line.replace(/^\d+\.\s/, "");
      if (last?.kind === "ol") last.items.push(text);
      else blocks.push({ kind: "ol", items: [text] });
    } else if (line.startsWith("- ")) {
      const text = line.slice(2);
      if (last?.kind === "ul") last.items.push(text);
      else blocks.push({ kind: "ul", items: [text] });
    } else if (line.startsWith("> ")) {
      blocks.push({ kind: "quote", text: line.slice(2) });
    } else {
      blocks.push({ kind: "p", text: line });
    }
  }
  return blocks;
}

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "anchor"; id: string; text: string }
  | { kind: "fact"; label: string };

const INLINE =
  /\[\[([A-Z]+-\d+)\|([^\]]+)\]\]|\[(用户输入|假设|待确认|建议|已验证事实)\]/g;

export function parseInline(text: string): Inline[] {
  const parts: Inline[] = [];
  let cursor = 0;
  for (const match of text.matchAll(INLINE)) {
    const start = match.index;
    if (start > cursor)
      parts.push({ kind: "text", text: text.slice(cursor, start) });
    const [whole, id, quoted, label] = match;
    if (id && quoted) parts.push({ kind: "anchor", id, text: quoted });
    else if (label) parts.push({ kind: "fact", label });
    cursor = start + whole.length;
  }
  if (cursor < text.length)
    parts.push({ kind: "text", text: text.slice(cursor) });
  return parts;
}

/** Plain-text rendering used for export and character counts. */
export function stripInline(text: string): string {
  return text.replace(/\[\[[A-Z]+-\d+\|([^\]]+)\]\]/g, "$1");
}

export function toMarkdown(
  sections: { num: string; title: string; level: 1 | 2; body: string }[],
  title: string,
): string {
  const out: string[] = [`# ${title}`, ""];
  for (const section of sections) {
    out.push(
      `${section.level === 1 ? "##" : "###"} ${section.num} ${section.title}`,
      "",
    );
    for (const block of parseBlocks(stripInline(section.body))) {
      if (block.kind === "p") out.push(block.text);
      if (block.kind === "quote") out.push(`> ${block.text}`);
      if (block.kind === "ol")
        block.items.forEach((item, i) => out.push(`${i + 1}. ${item}`));
      if (block.kind === "ul")
        block.items.forEach((item) => out.push(`- ${item}`));
      if (block.kind === "table") {
        out.push(`| ${block.head.join(" | ")} |`);
        out.push(`| ${block.head.map(() => "---").join(" | ")} |`);
        block.rows.forEach((row) => out.push(`| ${row.join(" | ")} |`));
      }
      out.push("");
    }
  }
  return out.join("\n");
}
