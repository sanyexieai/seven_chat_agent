import type { AssistantMemory } from "./types";

export function memorySourceLabel(content: string): string {
  const first = content.split("\n")[0] ?? "";
  if (first.includes("[默认观察/")) return "会话观察";
  if (first.startsWith("[协助记录]")) return "协助回合";
  if (first.startsWith("[待办执行]") || first.startsWith("[空闲守护完成]")) {
    return "后台任务";
  }
  if (first.includes("代发") || first.includes("群聊:")) return "群协作";
  return "其他";
}

export function memoryScopeLabel(content: string): string | null {
  const first = content.split("\n")[0] ?? "";
  const marker = "[默认观察/";
  const i = first.indexOf(marker);
  if (i < 0) return null;
  const inner = first.slice(i + marker.length).replace(/\]\s*$/, "").trim();
  return inner || null;
}

export type MemoryFilter = "all" | "observe" | "assist" | "knowledge" | "pinned";

export function matchesMemoryFilter(m: AssistantMemory, filter: MemoryFilter): boolean {
  if (filter === "all") return true;
  if (filter === "pinned") return m.pinned;
  if (filter === "knowledge") {
    return ["knowledge", "fact", "preference", "project", "relation", "lesson"].includes(
      m.kind,
    );
  }
  if (filter === "observe") {
    return (m.content.split("\n")[0] ?? "").includes("[默认观察/");
  }
  if (filter === "assist") {
    return (m.content.split("\n")[0] ?? "").startsWith("[协助记录]");
  }
  return true;
}
