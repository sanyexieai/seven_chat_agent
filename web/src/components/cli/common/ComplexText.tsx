import type { ReactNode } from "react";
import { Collapsible } from "../../Collapsible";
import { isJsonishContent } from "./detect";

export type ComplexTextTone = "neutral" | "tool" | "reasoning";

export interface ComplexTextDecision {
  collapse: boolean;
  summary: ReactNode;
  tone?: ComplexTextTone;
}

export function defaultComplexDecision(
  content: string,
  label?: string,
): ComplexTextDecision {
  const lines = content.split("\n").length;
  const len = content.length;
  const jsonish = isJsonishContent(content);

  // 经验阈值：
  // - JSON/JSONL 默认折叠（避免刷屏）
  // - 纯文本仅在“明显很长”时折叠，避免把正常 Markdown 回复一刀切折起来
  const collapse = jsonish || len > 2400 || lines > 80;

  const head = content.trim().split("\n")[0] ?? "";
  const preview = head.length > 80 ? `${head.slice(0, 80)}…` : head;
  const summaryLabel = label?.trim() ? label.trim() : "details";

  return {
    collapse,
    tone: jsonish ? "tool" : "neutral",
    summary: (
      <>
        <span className="text-slate-500">{summaryLabel}</span>
        <span className="ml-1 truncate text-slate-600">
          {jsonish ? "复杂输出（JSON）" : "复杂输出"}
          {" · "}
          {lines} 行
          {len ? ` · ${len.toLocaleString()} 字符` : ""}
          {preview ? ` · ${preview}` : ""}
        </span>
      </>
    ),
  };
}

export function ComplexText({
  content,
  streaming,
  decision,
  maxHeightClassName = "max-h-[min(24rem,50vh)]",
}: {
  content: string;
  streaming?: boolean;
  decision: ComplexTextDecision;
  maxHeightClassName?: string;
}) {
  if (!decision.collapse) {
    return (
      <>
        {content}
        {streaming ? <span className="cli-cursor" /> : null}
      </>
    );
  }

  return (
    <Collapsible
      tone={decision.tone ?? "neutral"}
      autoOpen={!!streaming}
      summary={decision.summary}
    >
      <pre
        className={[
          "overflow-y-auto whitespace-pre-wrap font-mono text-[11px] text-slate-700",
          maxHeightClassName,
        ].join(" ")}
      >
        {content}
        {streaming ? <span className="cli-cursor" /> : null}
      </pre>
    </Collapsible>
  );
}

