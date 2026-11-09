/**
 * Deterministic structure read from Markdown: headings for the PRD table of
 * contents, section lookup for "locate this finding", and a title and summary
 * for the user's own request.
 *
 * Nothing here calls a model. The run header used to print the user's raw input
 * in full; a title and summary derived from that same text -- with the original
 * one click away -- is enough, and costs nothing.
 */

export interface OutlineHeading {
  level: number;
  text: string;
  /** 1-based source line, matching react-markdown's `node.position`. */
  line: number;
  id: string;
}

const HEADING = /^(#{1,6})\s+(.+?)\s*#*\s*$/;
const FENCE = /^\s*(```|~~~)/;
const SECTION_NUMBER = /\d+(?:\.\d+)*/;

export function headingId(line: number): string {
  return `prd-sec-${line}`;
}

/** Strip inline Markdown so a heading reads as plain text. */
export function plainText(value: string): string {
  return value
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_`~]+/g, "")
    .replace(/<[^>]+>/g, "")
    .trim();
}

export function parseOutline(markdown: string): OutlineHeading[] {
  const headings: OutlineHeading[] = [];
  let inFence = false;
  markdown.split("\n").forEach((raw, index) => {
    if (FENCE.test(raw)) {
      inFence = !inFence;
      return;
    }
    if (inFence) {
      return;
    }
    const match = HEADING.exec(raw.trimEnd());
    if (match) {
      const line = index + 1;
      headings.push({
        level: match[1]!.length,
        text: plainText(match[2]!),
        line,
        id: headingId(line),
      });
    }
  });
  return headings;
}

function normalize(value: string): string {
  return value.toLowerCase().replace(/[\s\p{P}\p{S}]+/gu, "");
}

/**
 * The heading a reviewer's `section` points at.
 *
 * `5.5 配额与限制`, `§5.5` and `5.5` all mean the same heading; a section number
 * wins over wording because reviewers paraphrase titles. Returns null rather
 * than guessing when nothing matches.
 */
export function locateSection(
  outline: OutlineHeading[],
  section: string | null | undefined,
): OutlineHeading | null {
  if (!section || section.trim() === "") {
    return null;
  }
  const number = SECTION_NUMBER.exec(section)?.[0];
  if (number) {
    const byNumber = outline.find(
      (heading) => SECTION_NUMBER.exec(heading.text)?.[0] === number,
    );
    if (byNumber) {
      return byNumber;
    }
  }
  const wanted = normalize(section.replace(SECTION_NUMBER, ""));
  if (wanted.length < 2) {
    return null;
  }
  return (
    outline.find((heading) => {
      const text = normalize(heading.text.replace(SECTION_NUMBER, ""));
      return (
        text.length >= 2 && (text.includes(wanted) || wanted.includes(text))
      );
    }) ?? null
  );
}

export interface RequestDigest {
  title: string;
  summary: string;
  /** Section names of the user's own request, when it was structured. */
  topics: string[];
  lines: number;
  characters: number;
}

const ROLE_PLAY = /^(你是|您是|作为|you are|as an?\b|act as)/i;
const PRODUCT_SENTENCE =
  /(开发|打造|构建|搭建|设计|做一[个款]|一款|产品|平台|应用|系统|\bbuild\b|\bcreate\b|\bdesign\b|\bproduct\b|\bapp\b|\bplatform\b)/i;
const LIST_MARKER = /^\s*(?:[-*+]|\d+[.)、]|[一二三四五六七八九十]+[、.])\s*/;

function sentences(text: string): string[] {
  return (text.match(/[^。！？!?.\n]+[。！？!?.]?/g) ?? [])
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 1);
}

function clip(value: string, limit: number): string {
  return value.length <= limit ? value : `${value.slice(0, limit - 1)}…`;
}

/**
 * A title and a two-sentence summary for the user's request.
 *
 * The first sentence that describes a product wins over a role-play preamble:
 * run 9fa59292's 4,993-character request opened with "你是一名资深产品经理…",
 * and the useful line -- 「我们计划开发一款面向中国及海外市场的云端下载与个人云
 * 盘一体化产品」 -- came several headings later.
 */
export function digestRequest(idea: string): RequestDigest {
  const paragraphs: string[] = [];
  const topics: string[] = [];
  let inFence = false;
  for (const raw of idea.split("\n")) {
    if (FENCE.test(raw)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) {
      continue;
    }
    const heading = HEADING.exec(raw.trim());
    if (heading) {
      const text = plainText(heading[2]!).replace(LIST_MARKER, "");
      if (text && topics.length < 6 && !topics.includes(text)) {
        topics.push(clip(text, 16));
      }
      continue;
    }
    const text = plainText(raw.replace(/^>\s*/, "").replace(LIST_MARKER, ""));
    if (text) {
      paragraphs.push(text);
    }
  }
  const all = paragraphs.flatMap(sentences);
  const useful = all.filter((sentence) => !ROLE_PLAY.test(sentence));
  const product =
    useful.find((sentence) => PRODUCT_SENTENCE.test(sentence)) ??
    useful[0] ??
    all[0] ??
    plainText(idea);
  const start = Math.max(0, useful.indexOf(product));
  const summary = clip(useful.slice(start, start + 2).join("") || product, 160);
  // A long product sentence is titled by its first clause, so the title and the
  // summary beneath it do not repeat the same line twice.
  const sentence = product.replace(/[。！？!?.]$/, "");
  const clause = sentence.split(/[，,；;：:]/)[0]?.trim() ?? sentence;
  const title = sentence.length > 32 && clause.length >= 8 ? clause : sentence;
  return {
    title: clip(title, 42),
    summary,
    topics: topics.length >= 2 ? topics : [],
    lines: idea.split("\n").length,
    characters: idea.length,
  };
}
