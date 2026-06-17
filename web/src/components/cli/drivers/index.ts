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
  if (m === "codex-exec" || m === "codex") return "unknown";
  return "unknown";
}

/** 结构化 CLI 块（agent_message 等）左上角引擎标签 */
export function cliDriverBlockLabel(modelUsed: string | null): string {
  const kind = driverKindFromModelUsed(modelUsed);
  switch (kind) {
    case "cursor":
      return "cursor";
    case "claude":
      return "claude";
    case "worker-bee-cli":
      return "worker-bee";
    default: {
      const m = (modelUsed ?? "").trim().toLowerCase();
      if (m.includes("codex")) return "codex";
      if (m.includes("cursor")) return "cursor";
      if (m.includes("claude")) return "claude";
      return m || "agent";
    }
  }
}

export function cliDriverBlockTone(
  modelUsed: string | null,
): "codex" | "cursor" | "claude" | "exec" | "reasoning" | "muted" {
  const kind = driverKindFromModelUsed(modelUsed);
  switch (kind) {
    case "cursor":
      return "cursor";
    case "claude":
      return "claude";
    case "worker-bee-cli":
      return "exec";
    default:
      if ((modelUsed ?? "").toLowerCase().includes("codex")) return "codex";
      return "muted";
  }
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

