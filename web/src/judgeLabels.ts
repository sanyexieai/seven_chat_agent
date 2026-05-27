/** 群配置 judge 模式 */
export function configuredJudgeModeLabel(mode: string): string {
  switch (mode) {
    case "llm":
      return "LLM";
    case "heuristic":
      return "启发式";
    case "auto":
      return "Auto";
    default:
      return mode;
  }
}

/** 实际 judge 通路（与配置可能不一致） */
export function judgeSourceLabel(source: string | null | undefined): string {
  if (!source) return "未知";
  switch (source) {
    case "llm":
      return "LLM✓";
    case "heuristic":
      return "启发式";
    case "llm_failed":
      return "LLM✗";
    case "auto_llm":
      return "Auto→LLM";
    case "auto_heuristic":
      return "Auto→启发式";
    default:
      return source;
  }
}

export function scheduleModeLabel(mode: string): string {
  switch (mode) {
    case "strict":
      return "按 LLM/规则过线选人";
    case "fallback":
      return "调度兜底（LLM 均不愿接话仍强制 1 人）";
    case "none":
      return "无人发言";
    case "pending":
      return "判断中…";
    default:
      return mode;
  }
}

export function memberVerdictShort(
  name: string,
  shouldReply: boolean,
  confidence: number,
  source: string | null,
): string {
  const src = judgeSourceLabel(source);
  const action = shouldReply ? "愿接" : "不接";
  return `${name} ${src} ${action}(${confidence.toFixed(2)})`;
}
