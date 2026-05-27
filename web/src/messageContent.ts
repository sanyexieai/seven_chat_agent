/** 将纯文本消息拆成可读段落与可收起的工具调用块 */

export type MessageSegment =
  | { kind: "text"; text: string }
  | { kind: "tool_json"; raw: string; toolName: string | null };

const TOOL_FENCE =
  /```(?:json)?\s*\n?(\{[\s\S]*?"tool_call"[\s\S]*?\})\s*\n?```/g;

function toolNameFromJson(raw: string): string | null {
  try {
    const o = JSON.parse(raw) as {
      tool_call?: { name?: string };
    };
    return o.tool_call?.name ?? null;
  } catch {
    return null;
  }
}

export function splitMessageContent(content: string): MessageSegment[] {
  if (!content.trim()) return [];

  const segments: MessageSegment[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  TOOL_FENCE.lastIndex = 0;
  while ((m = TOOL_FENCE.exec(content)) !== null) {
    if (m.index > last) {
      const t = content.slice(last, m.index).trimEnd();
      if (t) segments.push({ kind: "text", text: t });
    }
    const raw = m[1];
    segments.push({
      kind: "tool_json",
      raw,
      toolName: toolNameFromJson(raw),
    });
    last = m.index + m[0].length;
  }
  const tail = content.slice(last);
  if (tail.trim()) segments.push({ kind: "text", text: tail });

  if (segments.length === 0) segments.push({ kind: "text", text: content });
  return segments;
}

export function hasCollapsibleToolContent(content: string): boolean {
  return splitMessageContent(content).some((s) => s.kind === "tool_json");
}
