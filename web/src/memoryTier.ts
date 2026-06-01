import type { AssistantMemory } from "./types";

export const MEMORY_TIERS = [
  { value: "curated", label: "整理层", hint: "进入提示词" },
  { value: "raw", label: "原始层", hint: "归档可查" },
] as const;

export const MEMORY_SCOPES = [
  { value: "global", label: "全局" },
  { value: "user", label: "用户" },
  { value: "friend", label: "好友" },
  { value: "conversation", label: "会话" },
  { value: "ephemeral", label: "临时" },
] as const;

export const MEMORY_IMPORTANCE = [
  { value: 0, label: "临时" },
  { value: 1, label: "一般" },
  { value: 2, label: "重要" },
  { value: 3, label: "关键" },
] as const;

export function tierLabel(tier: string) {
  return MEMORY_TIERS.find((t) => t.value === tier)?.label ?? tier;
}

export function scopeLabel(scope: string) {
  return MEMORY_SCOPES.find((s) => s.value === scope)?.label ?? scope;
}

export function importanceLabel(n: number) {
  return MEMORY_IMPORTANCE.find((i) => i.value === n)?.label ?? String(n);
}

export function statusLabel(status: string) {
  return status === "archived" ? "已归档" : "活跃";
}

export function tierBadgeClass(tier: string) {
  return tier === "curated"
    ? "bg-emerald-50 text-emerald-800 border-emerald-200"
    : "bg-slate-100 text-slate-600 border-slate-200";
}

export function scopeBadgeClass(scope: string) {
  switch (scope) {
    case "global":
      return "bg-violet-50 text-violet-800";
    case "user":
      return "bg-blue-50 text-blue-800";
    case "friend":
      return "bg-amber-50 text-amber-900";
    case "conversation":
      return "bg-cyan-50 text-cyan-900";
    case "ephemeral":
      return "bg-slate-50 text-slate-500";
    default:
      return "bg-slate-50 text-slate-600";
  }
}

export function displayBody(m: AssistantMemory) {
  return m.summary?.trim() || m.content;
}
