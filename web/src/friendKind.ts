import type { Friend } from "./types";

/** 工蜂 CLI 实例（含内置 Hex）：可用记忆/技能面板，与 backend_kind 无关。 */
export function isWorkerBeeFriend(f: Friend): boolean {
  if (f.backend_kind === "api" || f.backend_kind === "assistant") {
    return true;
  }
  if (f.backend_kind === "pty") {
    const preset = f.backend_config?.preset;
    return preset === "worker-bee-cli";
  }
  return false;
}
