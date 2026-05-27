import { ComplexText, defaultComplexDecision } from "../common/ComplexText";
import type { CliTextDecisionContext, CliTextRenderContext } from "./types";

export function workerBeeComplexDecision(ctx: CliTextDecisionContext) {
  // 工蜂如果走 JSONL（对齐 Codex）会被自动识别并折叠；纯文本按默认阈值。
  return defaultComplexDecision(ctx.content);
}

export function renderWorkerBeeText(ctx: CliTextRenderContext) {
  return (
    <ComplexText
      content={ctx.content}
      streaming={ctx.streaming}
      decision={workerBeeComplexDecision(ctx)}
    />
  );
}

