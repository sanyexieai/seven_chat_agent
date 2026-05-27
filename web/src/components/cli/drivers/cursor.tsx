import { ComplexText, defaultComplexDecision } from "../common/ComplexText";
import { isJsonishContent } from "../common/detect";
import {
  hasStructuredMarkdown,
  introLineCount,
  parseMarkdownSegments,
  type MarkdownSegment,
} from "../common/markdownSegments";
import { Collapsible } from "../../Collapsible";
import type { CliTextDecisionContext, CliTextRenderContext } from "./types";

export function cursorComplexDecision(ctx: CliTextDecisionContext) {
  return defaultComplexDecision(ctx.content);
}

function renderSegment(
  seg: MarkdownSegment,
  opts: { streaming?: boolean; isLast?: boolean },
) {
  switch (seg.kind) {
    case "text": {
      const lines = introLineCount(seg.text);
      // 开头说明较长时单独折叠，避免占满气泡
      if (lines > 10) {
        const preview = seg.text.trim().split("\n")[0] ?? "";
        return (
          <Collapsible
            key={`intro-${preview.slice(0, 24)}`}
            tone="neutral"
            defaultOpen={!!opts.streaming}
            summary={
              <>
                <span className="text-slate-500">开头</span>
                <span className="ml-1 truncate text-slate-600">
                  {lines} 行
                  {preview ? ` · ${preview.slice(0, 60)}${preview.length > 60 ? "…" : ""}` : ""}
                </span>
              </>
            }
          >
            <pre className="cli-body max-h-[min(20rem,45vh)] overflow-y-auto whitespace-pre-wrap text-sm text-slate-800">
              {seg.text}
              {opts.streaming && opts.isLast ? <span className="cli-cursor" /> : null}
            </pre>
          </Collapsible>
        );
      }
      return (
        <pre
          key={`text-${seg.text.slice(0, 16)}`}
          className="cli-body whitespace-pre-wrap text-sm text-slate-800"
        >
          {seg.text}
          {opts.streaming && opts.isLast ? <span className="cli-cursor" /> : null}
        </pre>
      );
    }
    case "heading": {
      const preview =
        seg.body.length > 72 ? `${seg.body.slice(0, 72).trim()}…` : seg.body.trim();
      return (
        <Collapsible
          key={`h-${seg.title}`}
          tone="neutral"
          summary={
            <>
              <span className="text-indigo-600">section</span>
              <span className="ml-1 font-medium text-slate-800">{seg.title}</span>
              {preview ? (
                <span className="ml-1 truncate text-slate-500">{preview}</span>
              ) : null}
            </>
          }
        >
          <pre className="cli-body max-h-[min(20rem,45vh)] overflow-y-auto whitespace-pre-wrap text-sm text-slate-800">
            {seg.body || "（空）"}
          </pre>
        </Collapsible>
      );
    }
    case "code": {
      const lang = seg.lang || "text";
      const lines = seg.code.split("\n").length;
      return (
        <Collapsible
          key={`code-${lang}-${seg.code.slice(0, 12)}`}
          tone="tool"
          summary={
            <>
              <span className="text-sky-700">code</span>
              <span className="ml-1 text-slate-600">
                {lang} · {lines} 行
              </span>
            </>
          }
        >
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap border-l-2 border-slate-200 pl-2 font-mono text-[11px] text-slate-700">
            {seg.code}
          </pre>
        </Collapsible>
      );
    }
    default:
      return null;
  }
}

export function renderCursorText(ctx: CliTextRenderContext) {
  const raw = ctx.content;
  if (isJsonishContent(raw)) {
    return (
      <ComplexText
        content={raw}
        streaming={ctx.streaming}
        decision={cursorComplexDecision(ctx)}
      />
    );
  }

  const segments = parseMarkdownSegments(raw);
  if (!hasStructuredMarkdown(segments)) {
    return (
      <ComplexText
        content={raw}
        streaming={ctx.streaming}
        decision={cursorComplexDecision(ctx)}
      />
    );
  }

  const lastIdx = segments.length - 1;
  return (
    <div className="flex flex-col gap-2">
      {segments.map((seg, i) =>
        renderSegment(seg, {
          streaming: ctx.streaming,
          isLast: i === lastIdx,
        }),
      )}
    </div>
  );
}
