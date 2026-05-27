/** 将 Cursor/Claude 等纯文本 Markdown 回复拆成可折叠块 */

export type MarkdownSegment =
  | { kind: "text"; text: string }
  | { kind: "heading"; title: string; body: string }
  | { kind: "code"; lang: string | null; code: string };

const CODE_FENCE = /```([\w-]*)\n?([\s\S]*?)```/g;

function splitByHeadings(text: string): MarkdownSegment[] {
  const lines = text.split("\n");
  const segments: MarkdownSegment[] = [];
  let intro: string[] = [];
  let currentTitle: string | null = null;
  let currentBody: string[] = [];

  const flushSection = () => {
    if (currentTitle === null) return;
    const body = currentBody.join("\n").trim();
    segments.push({ kind: "heading", title: currentTitle, body });
    currentTitle = null;
    currentBody = [];
  };

  for (const line of lines) {
    const hm = line.match(/^##\s+(.+)$/);
    if (hm) {
      if (currentTitle === null && intro.length) {
        const t = intro.join("\n").trim();
        if (t) segments.push({ kind: "text", text: t });
        intro = [];
      } else {
        flushSection();
      }
      currentTitle = hm[1].trim();
      continue;
    }
    if (currentTitle === null) intro.push(line);
    else currentBody.push(line);
  }
  flushSection();
  const introText = intro.join("\n").trim();
  if (introText) segments.push({ kind: "text", text: introText });
  return segments;
}

function pushTextParts(out: MarkdownSegment[], text: string) {
  const parts = splitByHeadings(text);
  if (parts.length === 0) {
    const t = text.trim();
    if (t) out.push({ kind: "text", text: t });
    return;
  }
  out.push(...parts);
}

/** 按代码围栏 + `##` 标题拆段 */
export function parseMarkdownSegments(content: string): MarkdownSegment[] {
  const out: MarkdownSegment[] = [];
  let last = 0;
  CODE_FENCE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = CODE_FENCE.exec(content)) !== null) {
    if (m.index > last) {
      pushTextParts(out, content.slice(last, m.index));
    }
    out.push({
      kind: "code",
      lang: m[1]?.trim() || null,
      code: m[2].replace(/\n$/, ""),
    });
    last = m.index + m[0].length;
  }
  const tail = content.slice(last);
  if (tail) pushTextParts(out, tail);
  if (out.length === 0 && content.trim()) {
    pushTextParts(out, content);
  }
  return out;
}

export function hasStructuredMarkdown(segments: MarkdownSegment[]): boolean {
  return segments.some((s) => s.kind === "heading" || s.kind === "code");
}

export function introLineCount(text: string): number {
  return text.split("\n").filter((l) => l.trim()).length;
}
