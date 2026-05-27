import type { ComplexTextDecision } from "../common/ComplexText";
import { renderClaudeText } from "./claude";
import { renderCursorText } from "./cursor";
import type { CliDriverKind, CliTextDecisionContext, CliTextRenderContext } from "./types";
import { renderWorkerBeeText } from "./workerBee";

export type { CliDriverKind, CliTextDecisionContext, CliTextRenderContext } from "./types";

export function driverKindFromModelUsed(modelUsed: string | null): CliDriverKind {
  const m = (modelUsed ?? "").trim();
  if (!m) return "unknown";
  if (m === "claude") return "claude";
  if (m === "cursor") return "cursor";
  if (m === "worker-bee-cli" || m === "worker-bee") return "worker-bee-cli";
  return "unknown";
}

export function complexDecisionForCliText(
  ctx: CliTextDecisionContext,
): ComplexTextDecision {
  const kind = driverKindFromModelUsed(ctx.modelUsed);
  switch (kind) {
    // 保留：目前只供极少数场景使用；真正渲染由 renderCliText 控制
    case "claude":
    case "cursor":
    case "worker-bee-cli":
    default:
      return {
        collapse: false,
        summary: null,
      } as any;
  }
}

export function renderCliText(ctx: CliTextRenderContext) {
  const kind = driverKindFromModelUsed(ctx.modelUsed);
  switch (kind) {
    case "claude":
      return renderClaudeText(ctx);
    case "worker-bee-cli":
      return renderWorkerBeeText(ctx);
    case "cursor":
    default:
      return renderCursorText(ctx);
  }
}

