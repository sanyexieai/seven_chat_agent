import { ComplexText, defaultComplexDecision } from "../common/ComplexText";
import { isJsonishContent } from "../common/detect";
import type { CliTextDecisionContext, CliTextRenderContext } from "./types";

export function claudeComplexDecision(ctx: CliTextDecisionContext) {
  // Claude `-p --output-format json` 常见 JSON/JSONL；defaultComplexDecision 会自动折叠 JSON/JSONL。
  // 纯文本时尽量不折叠（阈值已在 defaultComplexDecision 内做得更宽松）。
  return defaultComplexDecision(ctx.content);
}

function extractTextFromAny(v: any): string[] {
  const out: string[] = [];
  const push = (s: any) => {
    if (typeof s !== "string") return;
    const t = s.trimEnd();
    if (!t) return;
    out.push(t);
  };

  if (!v || typeof v !== "object") return out;
  push(v.text);
  push(v.delta);
  if (typeof v.content === "string") push(v.content);

  const mc = v.message?.content;
  if (Array.isArray(mc)) {
    for (const it of mc) {
      push(it?.text);
      if (typeof it?.content === "string") push(it.content);
    }
  }

  push(v.item?.text);
  push(v.item?.output_text);

  return out;
}

function extractClaudeJsonText(raw: string): { text: string; lines: number } {
  const lines = raw.split("\n");
  const chunks: string[] = [];
  for (const line of lines) {
    const t = line.trim();
    if (!t) continue;
    let v: any;
    try {
      v = JSON.parse(t);
    } catch {
      continue;
    }
    for (const s of extractTextFromAny(v)) chunks.push(s);
  }

  const dedup: string[] = [];
  for (const s of chunks) {
    if (dedup.length === 0 || dedup[dedup.length - 1] !== s) dedup.push(s);
  }
  return { text: dedup.join("\n").trim(), lines: lines.length };
}

export function renderClaudeText(ctx: CliTextRenderContext) {
  const raw = ctx.content;
  if (!isJsonishContent(raw)) {
    return (
      <ComplexText
        content={raw}
        streaming={ctx.streaming}
        decision={claudeComplexDecision(ctx)}
      />
    );
  }

  const extracted = extractClaudeJsonText(raw);
  if (!extracted.text) {
    return (
      <ComplexText
        content={raw}
        streaming={ctx.streaming}
        decision={{
          ...defaultComplexDecision(raw),
          collapse: true,
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="whitespace-pre-wrap">
        {extracted.text}
        {ctx.streaming ? <span className="cli-cursor" /> : null}
      </span>
      <ComplexText
        content={raw}
        decision={{
          collapse: true,
          tone: "tool",
          summary: (
            <>
              <span className="text-sky-700">raw</span>
              <span className="ml-1 truncate text-slate-600">
                claude json · {extracted.lines} 行 ·{" "}
                {raw.length.toLocaleString()} 字符
              </span>
            </>
          ),
        }}
      />
    </div>
  );
}

