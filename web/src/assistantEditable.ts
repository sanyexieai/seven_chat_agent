import type { AssistantMemory, MemoryMaintenanceReport } from "./types";

/** 编辑方式 */
export type EditMode = "direct" | "llm";

export interface EditableField {
  key: string;
  label: string;
  type: "text" | "textarea" | "number" | "boolean" | "select" | "readonly";
  options?: { value: string; label: string }[];
}

export interface EditableCatalogItem {
  id: string;
  tab: string;
  label: string;
  description: string;
  modes: EditMode[];
  fields: EditableField[];
  llmActions?: {
    id: string;
    label: string;
    prompt: string;
    /** 为 true 时先执行服务端记忆维护（ingest/过期/归档），再跳转助理私聊 */
    runServerMaintenance?: boolean;
  }[];
}

export const MEMORY_TIERS = [
  { value: "curated", label: "整理层" },
  { value: "raw", label: "原始层" },
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

export const MEMORY_KIND_OPTIONS = [
  { value: "memo", label: "备忘录 memo" },
  { value: "knowledge", label: "知识库 knowledge" },
];

/** 助理面板内可编辑项一览 */
export const ASSISTANT_EDITABLE_CATALOG: EditableCatalogItem[] = [
  {
    id: "memory",
    tab: "全站记忆 / 知识库",
    label: "长期记忆",
    description: "跨会话观察、协助记录、知识提取条目",
    modes: ["direct", "llm"],
    fields: [
      { key: "content", label: "正文", type: "textarea" },
      { key: "kind", label: "类型", type: "select", options: MEMORY_KIND_OPTIONS },
      { key: "weight", label: "权重 0~1", type: "number" },
      { key: "pinned", label: "置顶", type: "boolean" },
    ],
    llmActions: [
      {
        id: "consolidate-all",
        label: "全库去重整理",
        runServerMaintenance: true,
        prompt:
          "【记忆整理】服务端已执行 raw→curated ingest 与过期清理。请根据当前跨会话长期记忆，列出：1) 仍重复或近似的 curated 条目及建议合并写法；2) 建议删除的噪声；3) 应置顶的关键事实。需要改库时说明对应记忆 id。",
      },
      {
        id: "merge-knowledge",
        label: "合并知识库重复",
        runServerMaintenance: true,
        prompt:
          "【知识库整理】服务端已跑过记忆维护。请只针对 kind=knowledge 的 curated 记忆，合并仍重复的事实、统一表述；若建议删除某条请给出 id。",
      },
      {
        id: "prune-observe",
        label: "精简观察备忘",
        runServerMaintenance: true,
        prompt:
          "【观察备忘整理】服务端已将陈旧 raw 归档并尝试 ingest。请查看剩余观察类 raw/curated，说明哪些可删、哪些应提升为 curated（附 id）。",
      },
    ],
  },
  {
    id: "todo",
    tab: "TodoList",
    label: "待办事项",
    description: "助理任务队列中的 pending / running 项",
    modes: ["direct"],
    fields: [
      { key: "title", label: "标题", type: "text" },
      { key: "detail", label: "说明", type: "textarea" },
      { key: "priority", label: "优先级", type: "number" },
      { key: "status", label: "状态", type: "select" },
    ],
    llmActions: [
      {
        id: "plan-todos",
        label: "让助理规划待办",
        prompt:
          "【待办规划】请根据当前全站记忆，列出你建议我添加到 TodoList 的 3~5 条待办（标题 + 一句说明 + 建议优先级 1~10）。",
      },
    ],
  },
  {
    id: "policy",
    tab: "策略",
    label: "全局策略",
    description: "观察范围、沉淀开关、Token 预算、CLI 白名单",
    modes: ["direct"],
    fields: [
      { key: "observe_enabled", label: "观察总开关", type: "boolean" },
      { key: "observe_dm", label: "观察私聊", type: "boolean" },
      { key: "observe_group", label: "观察群聊", type: "boolean" },
      { key: "auto_extract_memories", label: "自动提取记忆", type: "boolean" },
      { key: "auto_consolidate", label: "自动整理", type: "boolean" },
      { key: "tool_whitelist", label: "CLI 白名单", type: "text" },
    ],
  },
  {
    id: "memory-create",
    tab: "全站记忆",
    label: "新建记忆",
    description: "手动写入一条备忘录或知识点",
    modes: ["direct"],
    fields: [
      { key: "content", label: "正文", type: "textarea" },
      { key: "kind", label: "类型", type: "select", options: MEMORY_KIND_OPTIONS },
      { key: "weight", label: "权重", type: "number" },
    ],
  },
  {
    id: "reflection",
    tab: "知识库",
    label: "回合反思",
    description: "自动生成，只读；可通过对话让助理提炼为新知识",
    modes: ["llm"],
    fields: [{ key: "summary", label: "摘要", type: "readonly" }],
    llmActions: [
      {
        id: "reflection-to-knowledge",
        label: "反思转知识",
        runServerMaintenance: true,
        prompt:
          "【反思沉淀】服务端已执行记忆维护。请阅读最近的回合反思记录，把仍有价值的教训整理成 3~8 条可写入知识库的知识点（每条独立、可复用）；若与已有 curated 重复请指出 id。",
      },
    ],
  },
  {
    id: "skill",
    tab: "工具箱",
    label: "技能 SKILL.md",
    description: "磁盘 data/skills 下文件；面板只读，请改文件或让助理同步",
    modes: ["llm"],
    fields: [{ key: "path", label: "路径", type: "readonly" }],
    llmActions: [
      {
        id: "draft-skill",
        label: "让助理起草技能",
        prompt:
          "【技能固化】请根据我们最近协作的高频流程，起草一份 SKILL.md 大纲（名称、触发词、步骤列表），我会保存到 data/skills/ 目录。",
      },
    ],
  },
];

export function formatMemoryMaintenanceReport(
  report: MemoryMaintenanceReport,
): string {
  const ing = report.ingest;
  const org = report.curated_organize;
  const lines = [
    "[服务端记忆维护已完成]",
    `· 过期删除 ${report.expired_deleted} 条`,
    `· raw ingest：待处理 ${ing.raw_considered} 条，跳过噪声 ${ing.raw_skipped_noise ?? 0} 条 → 新增 curated ${ing.curated_created} 条，归档 raw ${ing.raw_archived} 条`,
  ];
  if (ing.llm_parse_failed) {
    lines.push("· ingest：LLM 返回无法解析（请查看服务端日志）");
  }
  if (org) {
    lines.push(
      `· curated 整理：检视 ${org.curated_considered} 条，更新 ${org.updated} 条，删除 ${org.deleted} 条`,
    );
  }
  lines.push(`· 向量回填 ${report.embeddings_updated} 条`);
  return lines.join("\n");
}

export function memoryRefinePrompt(m: AssistantMemory): string {
  return [
    "【单条记忆优化】请在不丢失关键事实的前提下，精简下面这条记忆的正文，并建议合适权重(0~1)与类型(memo/knowledge)。",
    "直接给出优化后的正文即可，我会粘贴到面板保存。",
    "",
    `ID: ${m.id}`,
    `当前类型: ${m.kind}`,
    `当前权重: ${m.weight}`,
    "正文:",
    m.content,
  ].join("\n");
}

export function memoryDraftFrom(m: AssistantMemory) {
  return {
    content: m.content,
    kind: m.kind,
    weight: m.weight,
    pinned: m.pinned,
    tier: m.tier || "curated",
    scope: m.scope || "global",
    scope_ref: m.scope_ref ?? "",
    importance: m.importance ?? 1,
    status: m.status || "active",
    title: m.title ?? "",
    summary: m.summary ?? "",
  };
}

export type MemoryDraft = ReturnType<typeof memoryDraftFrom>;
