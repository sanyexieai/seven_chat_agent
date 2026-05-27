import type { ComplexTextDecision } from "../common/ComplexText";

export type CliDriverKind = "claude" | "cursor" | "worker-bee-cli" | "unknown";

export interface CliTextDecisionContext {
  content: string;
  modelUsed: string | null;
}

export type CliTextDecisionFn = (ctx: CliTextDecisionContext) => ComplexTextDecision;

export interface CliTextRenderContext extends CliTextDecisionContext {
  streaming?: boolean;
}

