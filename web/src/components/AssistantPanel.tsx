import { useEffect, useState } from "react";
import {
  formatMemoryMaintenanceReport,
  memoryDraftFrom,
  memoryRefinePrompt,
  MEMORY_KIND_OPTIONS,
  type MemoryDraft,
} from "../assistantEditable";
import type { LlmOrganizeAction } from "./AssistantEditGuide";
import { api } from "../api/client";
import {
  matchesMemoryFilter,
  memorySourceLabel,
  type MemoryFilter,
} from "../memoryLabels";
import { AssistantEditGuide } from "./AssistantEditGuide";
import { MemoryRecordEditor } from "./MemoryRecordEditor";
import { EvolutionPanel } from "./EvolutionPanel";
import type {
  AssistantGlobalSettings,
  AssistantMemory,
  AssistantMemoryStats,
  AssistantQueueJob,
  AssistantQueueStats,
  AssistantReflection,
  AssistantSkill,
  AssistantTodo,
} from "../types";

interface Props {
  friendId: string | null;
  onClose: () => void;
  /** 跳转助理私聊并发送整理指令 */
  onAssistChat: (prompt: string) => void;
}

type Tab =
  | "sessions"
  | "memo"
  | "todo"
  | "toolbox"
  | "knowledge"
  | "queue"
  | "policy"
  | "evolution";

const CLI_PRESET_OPTIONS = [
  "worker-bee-cli",
  "codex-exec",
  "claude",
  "cursor",
] as const;

const defaultGlobal: AssistantGlobalSettings = {
  observe_enabled: true,
  observe_dm: true,
  observe_group: true,
  record_max_chars: 500,
  record_weight: 0.45,
  record_min_chars: 20,
  record_skip_low_signal: true,
  record_assist_memo: false,
  observe_dedupe_secs: 120,
  auto_consolidate: true,
  consolidate_every_n: 10,
  auto_ingest_raw: true,
  ingest_raw_batch_size: 25,
  embedding_enabled: false,
  ephemeral_ttl_hours: 168,
  evolution_enabled: true,
  evolution_token_budget_ratio: 0.1,
  evolution_token_budget_absolute: 0,
  evolution_tokens_used: 0,
  auto_extract_memories: true,
  proactive_enabled: true,
  proactive_batch_size: 2,
  proactive_delegate_enabled: false,
  proactive_delegate_friend_ids: [],
  monthly_token_budget: 0,
  monthly_tokens_used: 0,
  tool_whitelist: [],
};

export function AssistantPanel({ friendId, onClose, onAssistChat }: Props) {
  const [tab, setTab] = useState<Tab>("sessions");
  const [memos, setMemos] = useState<AssistantMemory[]>([]);
  const [curatedMemories, setCuratedMemories] = useState<AssistantMemory[]>([]);
  const [rawMemories, setRawMemories] = useState<AssistantMemory[]>([]);
  const [archivedRawMemories, setArchivedRawMemories] = useState<AssistantMemory[]>(
    [],
  );
  const [memoryLayerTab, setMemoryLayerTab] = useState<
    "curated" | "raw" | "archived"
  >("curated");
  const [memoryStats, setMemoryStats] = useState<AssistantMemoryStats | null>(
    null,
  );
  const [recallPreview, setRecallPreview] = useState<AssistantMemory[]>([]);
  const [recallPrompt, setRecallPrompt] = useState("");
  const [memoryFilter, setMemoryFilter] = useState<MemoryFilter>("all");
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [memoryDrafts, setMemoryDrafts] = useState<Record<string, MemoryDraft>>(
    {},
  );
  const [newMemoryDraft, setNewMemoryDraft] = useState<MemoryDraft>({
    content: "",
    kind: "knowledge",
    weight: 0.6,
    pinned: false,
    tier: "curated",
    scope: "global",
    scope_ref: "",
    importance: 2,
    status: "active",
    title: "",
    summary: "",
  });
  const [showNewMemory, setShowNewMemory] = useState(false);
  const [knowledgeMemories, setKnowledgeMemories] = useState<AssistantMemory[]>(
    [],
  );
  const [skills, setSkills] = useState<AssistantSkill[]>([]);
  const [reflections, setReflections] = useState<AssistantReflection[]>([]);
  const [todos, setTodos] = useState<AssistantTodo[]>([]);
  const [doneTodos, setDoneTodos] = useState<AssistantTodo[]>([]);
  const [queueStats, setQueueStats] = useState<AssistantQueueStats | null>(null);
  const [queueJobs, setQueueJobs] = useState<AssistantQueueJob[]>([]);
  const [global, setGlobal] = useState<AssistantGlobalSettings>(defaultGlobal);
  const [whitelistDraft, setWhitelistDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [maintaining, setMaintaining] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [opsAutoRefresh, setOpsAutoRefresh] = useState(false);
  const [todoCreateTitle, setTodoCreateTitle] = useState("");
  const [todoCreateDetail, setTodoCreateDetail] = useState("");
  const [todoCreatePriority, setTodoCreatePriority] = useState(1);
  const [todoCreateRemindSeconds, setTodoCreateRemindSeconds] = useState(0);
  const [todoEdit, setTodoEdit] = useState<
    Record<string, { title: string; detail: string; priority: number; status: AssistantTodo["status"] }>
  >({});
  const [delegateFriendDraft, setDelegateFriendDraft] = useState("");

  async function reloadRecallPreview(prompt: string) {
    if (!friendId) return;
    const res = await api.previewAssistantMemoryRecall(friendId, {
      prompt,
      limit: 8,
    });
    setRecallPreview(res.memories);
  }

  async function reload() {
    const [g, memoRes, knowRes, curatedRes, rawRes, archRes, statsRes, s, r, t, done, qs, qj] =
      await Promise.all([
      api.getAssistantGlobalSettings(),
      friendId
        ? api.listAssistantMemories(friendId, { category: "memo", limit: 120 })
        : Promise.resolve({ memories: [] }),
      friendId
        ? api.listAssistantMemories(friendId, {
            category: "knowledge",
            limit: 120,
          })
        : Promise.resolve({ memories: [] }),
      friendId
        ? api.listAssistantMemories(friendId, {
            tier: "curated",
            status: "active",
            limit: 200,
          })
        : Promise.resolve({ memories: [] }),
      friendId
        ? api.listAssistantMemories(friendId, {
            tier: "raw",
            status: "active",
            limit: 150,
          })
        : Promise.resolve({ memories: [] }),
      friendId
        ? api.listAssistantMemories(friendId, {
            tier: "raw",
            status: "archived",
            limit: 80,
          })
        : Promise.resolve({ memories: [] }),
      friendId
        ? api.getAssistantMemoryStats(friendId)
        : Promise.resolve({ stats: null as AssistantMemoryStats | null }),
      friendId ? api.listAssistantSkills(friendId) : Promise.resolve({ skills: [] }),
      friendId
        ? api.listAssistantReflections(friendId)
        : Promise.resolve({ reflections: [] }),
      friendId
        ? api.listAssistantTodos(friendId, { limit: 200 })
        : Promise.resolve({ todos: [] }),
      friendId
        ? api.listAssistantTodos(friendId, { status: "done", limit: 120 })
        : Promise.resolve({ todos: [] }),
      api.getAssistantQueueStats(),
      api.listAssistantQueueJobs({ limit: 30 }),
    ]);
    setGlobal({ ...defaultGlobal, ...g.settings });
    setWhitelistDraft(g.settings.tool_whitelist.join(", "));
    setDelegateFriendDraft((g.settings.proactive_delegate_friend_ids || []).join(", "));
    setMemos(memoRes.memories);
    setKnowledgeMemories(knowRes.memories);
    setCuratedMemories(curatedRes.memories);
    setRawMemories(rawRes.memories);
    setArchivedRawMemories(archRes.memories);
    setMemoryStats(statsRes.stats);
    setSkills(s.skills);
    setReflections(r.reflections);
    setTodos(t.todos);
    setDoneTodos(done.todos);
    setQueueStats(qs.stats);
    setQueueJobs(qj.jobs);
    await reloadRecallPreview(recallPrompt);
  }

  async function reloadOps() {
    if (!friendId) return;
    const [t, done, qs, qj] = await Promise.all([
      api.listAssistantTodos(friendId, { limit: 200 }),
      api.listAssistantTodos(friendId, { status: "done", limit: 120 }),
      api.getAssistantQueueStats(),
      api.listAssistantQueueJobs({ limit: 30 }),
    ]);
    setTodos(t.todos);
    setDoneTodos(done.todos);
    setQueueStats(qs.stats);
    setQueueJobs(qj.jobs);
  }

  useEffect(() => {
    reload();
  }, [friendId]);

  useEffect(() => {
    if (!friendId || tab !== "sessions") return;
    const timer = window.setTimeout(() => {
      reloadRecallPreview(recallPrompt).catch(() => {});
    }, 400);
    return () => window.clearTimeout(timer);
  }, [friendId, tab, recallPrompt]);

  useEffect(() => {
    if (!friendId || tab !== "queue" || !opsAutoRefresh) return;
    const timer = window.setInterval(() => {
      reloadOps().catch(() => {});
    }, 5000);
    return () => window.clearInterval(timer);
  }, [friendId, tab, opsAutoRefresh]);

  if (!friendId) return null;
  const assistantId = friendId;

  function startMemoryEdit(m: AssistantMemory) {
    setEditingMemoryId(m.id);
    setMemoryDrafts((prev) => ({
      ...prev,
      [m.id]: memoryDraftFrom(m),
    }));
  }

  function patchMemoryDraft(id: string, patch: Partial<MemoryDraft>) {
    setMemoryDrafts((prev) => {
      const base = prev[id] ?? {
        content: "",
        kind: "memo",
        weight: 0.5,
        pinned: false,
      };
      return { ...prev, [id]: { ...base, ...patch } };
    });
  }

  async function saveMemoryEdit(id: string) {
    const draft = memoryDrafts[id];
    if (!draft?.content.trim()) {
      setMsg("记忆正文不能为空");
      return;
    }
    const prev =
      curatedMemories.find((m) => m.id === id) ||
      rawMemories.find((m) => m.id === id) ||
      archivedRawMemories.find((m) => m.id === id);
    setBusy(true);
    setMsg(null);
    try {
      await api.patchAssistantMemory(assistantId, id, {
        content: draft.content.trim(),
        kind: draft.kind,
        weight: Math.min(1, Math.max(0, draft.weight)),
        pinned: draft.pinned,
        tier: draft.tier,
        scope: draft.scope,
        scope_ref: draft.scope_ref.trim() || null,
        importance: draft.importance,
        title: draft.title.trim() || null,
        summary: draft.summary.trim() || null,
        promote_to_curated: prev?.tier === "raw" || draft.tier === "curated",
      });
      setEditingMemoryId(null);
      await reload();
      setMsg("记忆已保存");
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function createMemory() {
    if (!newMemoryDraft.content.trim()) {
      setMsg("请输入记忆正文");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await api.addAssistantMemory(assistantId, {
        kind: newMemoryDraft.kind,
        content: newMemoryDraft.content.trim(),
        weight: Math.min(1, Math.max(0, newMemoryDraft.weight)),
        pinned: newMemoryDraft.pinned,
        tier: "curated",
        scope: newMemoryDraft.scope,
        scope_ref: newMemoryDraft.scope_ref.trim() || undefined,
        importance: newMemoryDraft.importance,
        title: newMemoryDraft.title.trim() || undefined,
        summary:
          newMemoryDraft.summary.trim() ||
          newMemoryDraft.content.trim().slice(0, 240),
      });
      setNewMemoryDraft({
        content: "",
        kind: "knowledge",
        weight: 0.6,
        pinned: false,
        tier: "curated",
        scope: "global",
        scope_ref: "",
        importance: 2,
        status: "active",
        title: "",
        summary: "",
      });
      setShowNewMemory(false);
      await reload();
      setMsg("已新建记忆");
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function assistViaChat(
    prompt: string,
    label: string,
    options?: { runServerMaintenance?: boolean },
  ) {
    setBusy(true);
    setMsg(null);
    try {
      let fullPrompt = prompt;
      if (options?.runServerMaintenance) {
        const res = await api.consolidateAssistantMemories();
        setGlobal(res.settings);
        await reload();
        if (res.report) {
          fullPrompt = `${prompt}\n\n${formatMemoryMaintenanceReport(res.report)}`;
          setMsg(formatMemoryMaintenanceReport(res.report));
        } else {
          setMsg(
            `已执行记忆维护并跳转助理私聊：${label}。请在面板刷新后查看整理层与原始层变化。`,
          );
        }
      } else {
        setMsg(`已跳转助理私聊：${label}（仅对话建议，未改库）`);
      }
      onAssistChat(fullPrompt);
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function assistOrganize(action: LlmOrganizeAction) {
    void assistViaChat(action.prompt, action.label, {
      runServerMaintenance: action.runServerMaintenance,
    });
  }

  async function toggleMemoryPin(m: AssistantMemory) {
    setBusy(true);
    setMsg(null);
    try {
      await api.patchAssistantMemory(assistantId, m.id, {
        pinned: !m.pinned,
      });
      await reload();
      setMsg(m.pinned ? "已取消置顶" : "已置顶，召回时会优先注入");
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function deleteMemory(m: AssistantMemory) {
    if (!window.confirm("确定删除这条记忆？")) return;
    setBusy(true);
    setMsg(null);
    try {
      await api.deleteAssistantMemory(assistantId, m.id);
      await reload();
      setMsg("记忆已删除");
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveGlobal() {
    setBusy(true);
    setMsg(null);
    try {
      const tool_whitelist = whitelistDraft
        .split(/[,，\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await api.upsertAssistantGlobalSettings({
        ...global,
        tool_whitelist,
      });
      setGlobal(res.settings);
      setWhitelistDraft(res.settings.tool_whitelist.join(", "));
      setMsg("全局策略已保存");
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runConsolidate() {
    setBusy(true);
    setMaintaining(true);
    setMsg("正在执行记忆维护（ingest / curated 去重），通常需 10～90 秒，请稍候…");
    try {
      const res = await api.consolidateAssistantMemories();
      setGlobal(res.settings);
      await reload();
      if (res.report) {
        setMsg(formatMemoryMaintenanceReport(res.report));
      } else {
        setMsg("记忆维护完成");
      }
    } catch (e: any) {
      setMsg(`维护失败：${e.message || String(e)}`);
    } finally {
      setMaintaining(false);
      setBusy(false);
    }
  }

  async function runTodosOnce() {
    if (!friendId) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await api.runAssistantTodosOnce(friendId);
      setTodos(res.todos);
      setMsg("已入队，助理将异步处理待办");
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function createTodo() {
    if (!friendId || !todoCreateTitle.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      await api.createAssistantTodo(friendId, {
        title: todoCreateTitle.trim(),
        detail: todoCreateDetail.trim() || undefined,
        priority: Number(todoCreatePriority || 1),
        remind_after_seconds:
          Number(todoCreateRemindSeconds || 0) > 0
            ? Number(todoCreateRemindSeconds || 0)
            : undefined,
      });
      setTodoCreateTitle("");
      setTodoCreateDetail("");
      setTodoCreatePriority(1);
      setTodoCreateRemindSeconds(0);
      await reloadOps();
      setMsg("已新增待办");
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function todoDraft(t: AssistantTodo) {
    return (
      todoEdit[t.id] || {
        title: t.title,
        detail: t.detail || "",
        priority: t.priority,
        status: t.status,
      }
    );
  }

  function patchTodoDraft(
    id: string,
    patch: Partial<{ title: string; detail: string; priority: number; status: AssistantTodo["status"] }>,
  ) {
    setTodoEdit((prev) => ({
      ...prev,
      [id]: { ...(prev[id] || { title: "", detail: "", priority: 1, status: "pending" }), ...patch },
    }));
  }

  async function saveTodo(t: AssistantTodo) {
    if (!friendId) return;
    const draft = todoDraft(t);
    if (!draft.title.trim()) {
      setMsg("待办标题不能为空");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await api.updateAssistantTodo(friendId, t.id, {
        title: draft.title.trim(),
        detail: draft.detail.trim() || undefined,
        priority: Number(draft.priority || 1),
        status: draft.status,
      });
      await reloadOps();
      setMsg("待办已更新");
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function replayFailedQueue() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api.replayFailedAssistantQueueJobs(100);
      await reload();
      setMsg(`已重放失败任务 ${res.replayed} 条`);
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggleWhitelistPreset(preset: string) {
    const set = new Set(global.tool_whitelist);
    if (set.has(preset)) {
      set.delete(preset);
    } else {
      set.add(preset);
    }
    const next = Array.from(set);
    setGlobal({ ...global, tool_whitelist: next });
    setWhitelistDraft(next.join(", "));
  }

  const upcomingTodos = todos.filter(
    (t) => t.status === "pending" || t.status === "running",
  );

  const recentTaskFromMemos = memos
    .filter((m) => {
      const first = m.content.split("\n")[0] ?? "";
      return (
        first.startsWith("[协助记录]") ||
        first.startsWith("[待办执行]") ||
        first.startsWith("[空闲守护完成]")
      );
    })
    .slice(0, 12)
    .map((m) => {
      const first = m.content.split("\n")[0] ?? "";
      const second = (m.content.split("\n")[1] ?? "").trim();
      const title = first.startsWith("[协助记录]")
        ? "用户与助理完成一轮协助"
        : first.replace(/^\[[^\]]+\]\s*/, "").trim() || "任务记录";
      return {
        id: `m-${m.id}`,
        title,
        detail: second,
        actor: first.startsWith("[协助记录]") ? "用户 + 助理" : "助理",
        createdAt: m.created_at,
        source: "memo" as const,
      };
    });

  const recentTaskFromDoneTodos = doneTodos.slice(0, 12).map((t) => ({
    id: `t-${t.id}`,
    title: t.title,
    detail: t.detail || "",
    actor: "助理",
    createdAt: t.updated_at || t.created_at,
    source: "todo" as const,
  }));

  const recentTaskTimeline = [...recentTaskFromDoneTodos, ...recentTaskFromMemos]
    .sort(
      (a, b) =>
        new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    )
    .slice(0, 18);

  const layerMemories = (
    memoryLayerTab === "curated"
      ? curatedMemories
      : memoryLayerTab === "raw"
        ? rawMemories
        : archivedRawMemories
  ).filter((m) => {
    if (memoryLayerTab === "curated") {
      return m.tier === "curated" && m.status !== "archived";
    }
    if (memoryLayerTab === "raw") {
      return m.tier === "raw" && m.status === "active";
    }
    return m.tier === "raw" && m.status === "archived";
  });

  const filteredMemories = layerMemories.filter((m) =>
    matchesMemoryFilter(m, memoryFilter),
  );

  const pipelineSteps = [
    {
      key: "raw",
      label: "原始归档",
      count: memoryStats?.raw_active ?? 0,
      on: global.observe_enabled,
      hint: `已归档 ${memoryStats?.raw_archived ?? 0}`,
    },
    {
      key: "curated",
      label: "整理层",
      count: memoryStats?.curated_active ?? 0,
      on: true,
      hint: "注入提示词",
    },
    {
      key: "extract",
      label: "知识提取",
      count: memoryStats?.knowledge_count ?? 0,
      on: global.auto_extract_memories,
      hint: "→ curated",
    },
    {
      key: "reflect",
      label: "反思",
      count: reflections.length,
      on: global.evolution_enabled,
      hint: "→ 全局知识",
    },
    {
      key: "recall",
      label: "召回预览",
      count: recallPreview.length,
      on: true,
      hint: "仅 curated",
    },
  ];

  return (
    <div className="fixed inset-0 z-30 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex h-full w-[640px] flex-col border-l border-slate-200 bg-white shadow-xl">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div>
            <div className="text-base font-semibold">助理控制面板</div>
            <div className="text-xs text-slate-500">
              全站记忆 · 任务回顾 / TodoList / 工具箱 / 知识库 / 队列 / 策略
            </div>
          </div>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        {msg && (
          <div
            className={`border-b px-5 py-2 text-xs whitespace-pre-wrap ${
              msg.startsWith("维护失败") || msg.startsWith("失败")
                ? "border-red-200 bg-red-50 text-red-800"
                : maintaining
                  ? "border-amber-200 bg-amber-50 text-amber-900"
                  : "border-emerald-200 bg-emerald-50 text-emerald-900"
            }`}
            role="status"
          >
            {msg}
          </div>
        )}
        <div className="flex flex-wrap gap-1 border-b border-slate-200 px-5 py-2">
          {(
            [
              "sessions",
              "memo",
              "todo",
              "toolbox",
              "knowledge",
              "queue",
              "policy",
              "evolution",
            ] as Tab[]
          ).map((t) => (
            <button
              key={t}
              className={`px-3 py-1 text-sm rounded-md ${
                tab === t
                  ? "bg-honey-100 text-honey-800 font-semibold"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
              onClick={() => setTab(t)}
            >
              {t === "sessions"
                ? "全站记忆"
                : t === "memo"
                  ? "任务回顾"
                  : t === "todo"
                    ? "TodoList"
                    : t === "toolbox"
                      ? "工具箱"
                      : t === "knowledge"
                        ? "知识库"
                        : t === "queue"
                          ? "队列"
                          : t === "policy"
                            ? "策略"
                            : "自我进化"}
            </button>
          ))}
          <button
            className="ml-auto btn-ghost"
            onClick={reload}
            title="重新加载"
          >
            刷新
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <AssistantEditGuide
            activeTab={tab}
            busy={busy}
            onLlmAction={assistOrganize}
          />
          {(tab === "sessions" ||
            tab === "memo" ||
            tab === "toolbox" ||
            tab === "knowledge") && (
            <div className="mb-3 rounded-md border border-violet-200 bg-violet-50/60 px-3 py-2 text-xs text-violet-900">
              {tab === "sessions" ? (
                <>
                  记忆<strong>不会</strong>把每条聊天原样写入：仅沉淀有信息量的观察、
                  LLM 提取的知识点，以及可选的协助流水账。与助理私聊默认不写观察/流水账，避免重复。
                </>
              ) : (
                <>
                  以下内容均由助理在协助你时<strong>自动记录</strong>
                  ，无需手动填写。私聊/群聊观察、代发摘要会进入备忘录；回合反思与知识提取会进入知识库；固化流程会进入工具箱。
                </>
              )}
            </div>
          )}
          {tab === "sessions" && (
            <div className="space-y-4">
              <section className="rounded-lg border border-slate-200 bg-slate-50/80 p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs font-semibold text-slate-700">
                    记忆处理流水线
                  </div>
                  <button
                    type="button"
                    className="rounded-md bg-honey-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-honey-700 disabled:opacity-50"
                    onClick={() => void runConsolidate()}
                    disabled={busy || maintaining}
                    title="服务端执行：过期清理、raw→curated、curated 去重，不跳转私聊"
                  >
                    {maintaining ? "维护中…" : "立即维护"}
                  </button>
                </div>
                <div className="flex flex-wrap items-stretch gap-1">
                  {pipelineSteps.map((step, i) => (
                    <div key={step.key} className="flex items-center gap-1">
                      <div
                        className={`min-w-[88px] rounded-md border px-2 py-2 text-center ${
                          step.on
                            ? "border-emerald-200 bg-white"
                            : "border-slate-200 bg-slate-100 opacity-60"
                        }`}
                      >
                        <div className="text-[11px] font-semibold text-slate-800">
                          {step.label}
                        </div>
                        <div className="text-lg font-bold text-honey-700">
                          {step.count}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          {step.hint}
                        </div>
                      </div>
                      {i < pipelineSteps.length - 1 && (
                        <span className="text-slate-300">→</span>
                      )}
                    </div>
                  ))}
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-600">
                  {memoryStats ? (
                    <>
                      <span>整理层 {memoryStats.curated_active}</span>
                      <span>原始活跃 {memoryStats.raw_active}</span>
                      <span>原始归档 {memoryStats.raw_archived}</span>
                      <span>知识 {memoryStats.knowledge_count}</span>
                    </>
                  ) : (
                    <span className="text-slate-400">统计加载中…</span>
                  )}
                </div>
              </section>

              <section className="rounded-lg border border-amber-200 bg-amber-50/50 p-3">
                <div className="text-xs font-semibold text-amber-900">
                  召回预览（模拟下一轮注入系统提示）
                </div>
                <input
                  className="input mt-2 w-full text-xs"
                  placeholder="输入假设的用户问题，查看会召回哪些记忆…"
                  value={recallPrompt}
                  onChange={(e) => setRecallPrompt(e.target.value)}
                />
                <ul className="mt-2 space-y-1">
                  {recallPreview.length === 0 && (
                    <li className="text-xs text-slate-500">
                      暂无召回结果（可尝试输入关键词，或先与助理/其他好友聊几句）
                    </li>
                  )}
                  {recallPreview.map((m, idx) => (
                    <li
                      key={m.id}
                      className="rounded border border-amber-100 bg-white px-2 py-1.5 text-xs"
                    >
                      <span className="mr-1 font-mono text-amber-700">
                        #{idx + 1}
                      </span>
                      <span className="rounded bg-slate-100 px-1 text-[10px]">
                        {memorySourceLabel(m.content)}
                      </span>
                      {m.pinned && (
                        <span className="ml-1 rounded bg-honey-100 px-1 text-[10px] text-honey-800">
                          置顶
                        </span>
                      )}
                      <span className="ml-1 text-slate-400">
                        w={m.weight.toFixed(2)}
                      </span>
                      <div className="mt-0.5 line-clamp-2 text-slate-700">
                        {m.content}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-700">
                    新建记忆（直接编辑）
                  </span>
                  <button
                    type="button"
                    className="btn-ghost text-xs"
                    onClick={() => setShowNewMemory((v) => !v)}
                  >
                    {showNewMemory ? "收起" : "展开"}
                  </button>
                </div>
                {showNewMemory && (
                  <div className="mt-2 space-y-2">
                    <div className="grid grid-cols-12 gap-2">
                      <select
                        className="input col-span-4 text-xs"
                        value={newMemoryDraft.kind}
                        onChange={(e) =>
                          setNewMemoryDraft((d) => ({
                            ...d,
                            kind: e.target.value,
                          }))
                        }
                      >
                        {MEMORY_KIND_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                      <input
                        className="input col-span-3 text-xs"
                        type="number"
                        min={0}
                        max={1}
                        step={0.05}
                        value={newMemoryDraft.weight}
                        onChange={(e) =>
                          setNewMemoryDraft((d) => ({
                            ...d,
                            weight: Number(e.target.value) || 0,
                          }))
                        }
                      />
                      <label className="col-span-5 flex items-center gap-1 text-xs">
                        <input
                          type="checkbox"
                          checked={newMemoryDraft.pinned}
                          onChange={(e) =>
                            setNewMemoryDraft((d) => ({
                              ...d,
                              pinned: e.target.checked,
                            }))
                          }
                        />
                        置顶
                      </label>
                    </div>
                    <textarea
                      className="input min-h-[80px] w-full text-sm"
                      placeholder="输入要记住的内容…"
                      value={newMemoryDraft.content}
                      onChange={(e) =>
                        setNewMemoryDraft((d) => ({
                          ...d,
                          content: e.target.value,
                        }))
                      }
                    />
                    <div className="flex justify-end">
                      <button
                        className="btn-primary text-xs"
                        onClick={createMemory}
                        disabled={busy}
                      >
                        保存到数据库
                      </button>
                    </div>
                  </div>
                )}
              </section>

              <section>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold text-slate-700">
                    记忆库
                  </span>
                  {(
                    [
                      ["curated", "整理层"],
                      ["raw", "原始活跃"],
                      ["archived", "原始归档"],
                    ] as const
                  ).map(([f, label]) => (
                    <button
                      key={f}
                      className={`rounded px-2 py-0.5 text-[11px] ${
                        memoryLayerTab === f
                          ? "bg-emerald-100 font-semibold text-emerald-900"
                          : "bg-slate-100 text-slate-600"
                      }`}
                      onClick={() => setMemoryLayerTab(f)}
                    >
                      {label}
                    </button>
                  ))}
                  {memoryLayerTab !== "archived" &&
                    (
                      [
                        ["all", "全部"],
                        ["observe", "观察"],
                        ["assist", "协助"],
                        ["knowledge", "知识"],
                        ["pinned", "置顶"],
                      ] as const
                    ).map(([f, label]) => (
                    <button
                      key={f}
                      className={`rounded px-2 py-0.5 text-[11px] ${
                        memoryFilter === f
                          ? "bg-honey-100 font-semibold text-honey-800"
                          : "bg-slate-100 text-slate-600"
                      }`}
                      onClick={() => setMemoryFilter(f)}
                    >
                      {label}
                    </button>
                    ))}
                </div>
                {memoryLayerTab === "curated" && (
                  <p className="mb-2 text-[11px] text-emerald-800">
                    整理层：经提取/反思或你手动确认的记忆，会按作用域注入助理提示词。
                    点每条右侧 <strong>置顶</strong> 可固定优先召回（或「编辑」里勾选置顶）。
                  </p>
                )}
                {memoryLayerTab === "raw" && (
                  <p className="mb-2 text-[11px] text-slate-600">
                    原始层：观察与流水账，仅供审计；编辑保存可提升为整理层。
                  </p>
                )}
                <ul className="space-y-2">
                  {filteredMemories.length === 0 && (
                    <li className="text-sm text-slate-500">
                      本层暂无记忆。
                    </li>
                  )}
                  {filteredMemories.map((m) => (
                    <li
                      key={m.id}
                      className="rounded-md border border-slate-200 p-3"
                    >
                      <MemoryRecordEditor
                        memory={m}
                        editing={editingMemoryId === m.id}
                        draft={
                          memoryDrafts[m.id] || memoryDraftFrom(m)
                        }
                        busy={busy}
                        onDraftChange={(patch) => patchMemoryDraft(m.id, patch)}
                        onStartEdit={() => startMemoryEdit(m)}
                        onCancelEdit={() => setEditingMemoryId(null)}
                        onSave={() => saveMemoryEdit(m.id)}
                        onDelete={() => deleteMemory(m)}
                        onTogglePin={() => toggleMemoryPin(m)}
                        onAssist={() =>
                          assistViaChat(memoryRefinePrompt(m), "单条记忆优化")
                        }
                      />
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
          {tab === "memo" && (
            <div className="space-y-3">
              <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                这里仅展示最近一段时间已完成/已发生的任务回顾（按时间倒序）。
              </div>
              <ul className="space-y-2">
                {recentTaskTimeline.length === 0 && (
                  <li className="text-sm text-slate-500">
                    还没有任务回顾。助理开始协助后会自动生成。
                  </li>
                )}
                {recentTaskTimeline.map((item) => (
                  <li
                    key={item.id}
                    className="rounded-md border border-slate-200 p-3"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold text-slate-700">
                        {item.actor}
                      </span>
                      <span className="text-slate-400">
                        {new Date(item.createdAt).toLocaleString()}
                      </span>
                    </div>
                    <div className="mt-1 text-sm font-medium">{item.title}</div>
                    {item.detail && (
                      <div className="mt-1 line-clamp-2 text-xs text-slate-600">
                        {item.detail}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {tab === "toolbox" && (
            <ul className="space-y-2">
              {skills.length === 0 && (
                <li className="text-sm text-slate-500">
                  还没有工具。助理在解决问题过程中会把高频流程写成{" "}
                  <code>data/skills/{friendId}/</code> 下的 SKILL.md，并自动同步到此处。
                </li>
              )}
              {skills.map((s) => (
                <li
                  key={s.id}
                  className="rounded-md border border-slate-200 p-3"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium">
                        {s.name}{" "}
                        <span className="ml-1 text-xs text-slate-500">
                          v{s.version}
                        </span>
                      </div>
                      <div className="text-xs text-slate-500">
                        信任级 {s.trust_level} · {s.path}
                      </div>
                    </div>
                  </div>
                  <div className="mt-1 text-sm">{s.description}</div>
                  {s.triggers.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {s.triggers.map((t) => (
                        <span
                          key={t}
                          className="rounded bg-honey-50 px-1.5 py-0.5 text-[11px] text-honey-800"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          {tab === "knowledge" && (
            <div className="space-y-4">
              <section>
                <div className="mb-2 text-xs font-semibold text-slate-600">
                  提炼记忆
                </div>
                <ul className="space-y-2">
                  {knowledgeMemories.length === 0 && (
                    <li className="text-sm text-slate-500">
                      还没有提炼出的知识点。助理在每轮协助结束后会自动抽取并沉淀。
                    </li>
                  )}
                  {knowledgeMemories.map((m) => (
                    <li
                      key={m.id}
                      className="rounded-md border border-slate-200 p-3"
                    >
                      <MemoryRecordEditor
                        memory={m}
                        editing={editingMemoryId === m.id}
                        draft={
                          memoryDrafts[m.id] || memoryDraftFrom(m)
                        }
                        busy={busy}
                        onDraftChange={(patch) => patchMemoryDraft(m.id, patch)}
                        onStartEdit={() => startMemoryEdit(m)}
                        onCancelEdit={() => setEditingMemoryId(null)}
                        onSave={() => saveMemoryEdit(m.id)}
                        onDelete={() => deleteMemory(m)}
                        onTogglePin={() => toggleMemoryPin(m)}
                        onAssist={() =>
                          assistViaChat(memoryRefinePrompt(m), "单条记忆优化")
                        }
                      />
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-600">
                    回合反思（只读 · 可对话整理）
                  </span>
                  <button
                    type="button"
                    className="btn-ghost text-[11px] text-indigo-700"
                    disabled={busy}
                    onClick={() =>
                      assistOrganize({
                        prompt:
                          "【反思沉淀】服务端已执行记忆维护。请阅读最近的回合反思记录，把仍有价值的教训整理成 3~8 条可写入知识库的知识点（每条独立、可复用）。",
                        label: "反思转知识",
                        runServerMaintenance: true,
                      })
                    }
                  >
                    对话整理 →
                  </button>
                </div>
                <ul className="space-y-2">
                  {reflections.length === 0 && (
                    <li className="text-sm text-slate-500">还没有反思记录。</li>
                  )}
                  {reflections.map((r) => (
                    <li
                      key={r.id}
                      className="rounded-md border border-slate-200 p-3"
                    >
                      <div className="flex items-center justify-between text-xs text-slate-500">
                        <span>turn {r.turn_id.slice(0, 8)}</span>
                        <span>
                          score{" "}
                          <span
                            className={
                              r.score >= 0.7
                                ? "text-emerald-600"
                                : r.score >= 0.4
                                  ? "text-amber-600"
                                  : "text-red-600"
                            }
                          >
                            {r.score.toFixed(2)}
                          </span>
                        </span>
                      </div>
                      <div className="mt-1 text-sm">{r.summary}</div>
                      {r.lessons.length > 0 && (
                        <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">
                          {r.lessons.map((l, i) => (
                            <li key={i}>{l}</li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
          {tab === "todo" && (
            <div className="space-y-4">
              <section className="rounded-md border border-slate-200 p-3">
                <div className="text-xs font-semibold text-slate-700">手动新增待办</div>
                <div className="mt-2 grid grid-cols-12 gap-2">
                  <input
                    className="input col-span-6 text-xs"
                    placeholder="待办标题"
                    value={todoCreateTitle}
                    onChange={(e) => setTodoCreateTitle(e.target.value)}
                  />
                  <input
                    className="input col-span-2 text-xs"
                    type="number"
                    min={1}
                    max={10}
                    value={todoCreatePriority}
                    onChange={(e) => setTodoCreatePriority(Number(e.target.value || 1))}
                    title="优先级（越大越高）"
                  />
                  <input
                    className="input col-span-2 text-xs"
                    type="number"
                    min={0}
                    value={todoCreateRemindSeconds}
                    onChange={(e) =>
                      setTodoCreateRemindSeconds(Number(e.target.value || 0))
                    }
                    title="多少秒后提醒（0=不提醒）"
                    placeholder="提醒秒数"
                  />
                  <input
                    className="input col-span-2 text-xs"
                    placeholder="简要说明（可选）"
                    value={todoCreateDetail}
                    onChange={(e) => setTodoCreateDetail(e.target.value)}
                  />
                </div>
                <div className="mt-2 flex justify-end">
                  <button className="btn-primary text-xs" onClick={createTodo} disabled={busy}>
                    新增
                  </button>
                </div>
              </section>
              <section className="rounded-md border border-slate-200 p-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-slate-700">
                    TodoList（接下来要做）
                  </div>
                  <button
                    className="btn-ghost text-xs"
                    onClick={runTodosOnce}
                    disabled={busy}
                  >
                    立即跑一轮
                  </button>
                </div>
                <ul className="mt-2 space-y-1">
                  {upcomingTodos.length === 0 && (
                    <li className="text-xs text-slate-500">暂无待办。</li>
                  )}
                  {upcomingTodos.slice(0, 30).map((t) => {
                    const d = todoDraft(t);
                    return (
                      <li
                        key={t.id}
                        className="rounded border border-slate-100 bg-slate-50 px-2 py-1 text-xs"
                      >
                        <div className="grid grid-cols-12 gap-2">
                          <input
                            className="input col-span-5 text-xs"
                            value={d.title}
                            onChange={(e) => patchTodoDraft(t.id, { title: e.target.value })}
                          />
                          <input
                            className="input col-span-2 text-xs"
                            type="number"
                            min={1}
                            max={10}
                            value={d.priority}
                            onChange={(e) =>
                              patchTodoDraft(t.id, {
                                priority: Number(e.target.value || 1),
                              })
                            }
                          />
                          <select
                            className="input col-span-2 text-xs"
                            value={d.status}
                            onChange={(e) =>
                              patchTodoDraft(t.id, {
                                status: e.target.value as AssistantTodo["status"],
                              })
                            }
                          >
                            <option value="pending">pending</option>
                            <option value="running">running</option>
                            <option value="done">done</option>
                            <option value="failed">failed</option>
                          </select>
                          <button
                            className="btn-ghost col-span-3 text-xs"
                            onClick={() => saveTodo(t)}
                            disabled={busy}
                          >
                            保存
                          </button>
                        </div>
                        <div className="mt-1">
                          <input
                            className="input w-full text-[11px]"
                            placeholder="详情（可选）"
                            value={d.detail}
                            onChange={(e) => patchTodoDraft(t.id, { detail: e.target.value })}
                          />
                        </div>
                        {(t.repeat_rule || t.next_run_at) && (
                          <div className="mt-1 text-[10px] text-slate-500">
                            {t.repeat_rule ? `周期: ${t.repeat_rule}` : ""}
                            {t.next_run_at
                              ? ` · 下次: ${new Date(t.next_run_at).toLocaleString()}`
                              : ""}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </section>
            </div>
          )}
          {tab === "queue" && (
            <div className="space-y-4">
              <section className="rounded-md border border-slate-200 p-3">
                <label className="flex items-center justify-between text-sm">
                  <span className="font-medium text-slate-700">
                    自动刷新队列状态（5 秒）
                  </span>
                  <input
                    type="checkbox"
                    checked={opsAutoRefresh}
                    onChange={(e) => setOpsAutoRefresh(e.target.checked)}
                  />
                </label>
                <p className="mt-1 text-xs text-slate-500">
                  仅在当前「队列」页生效，避免无效请求。
                </p>
              </section>

              <section className="rounded-md border border-slate-200 p-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-slate-700">
                    队列监控
                  </div>
                  <button
                    className="btn-ghost text-xs"
                    onClick={replayFailedQueue}
                    disabled={busy}
                  >
                    重放失败任务
                  </button>
                </div>
                {queueStats && (
                  <div className="mt-2 grid grid-cols-5 gap-2 text-[11px]">
                    <div className="rounded bg-slate-50 px-2 py-1">
                      pending: {queueStats.pending}
                    </div>
                    <div className="rounded bg-slate-50 px-2 py-1">
                      due: {queueStats.due_pending}
                    </div>
                    <div className="rounded bg-slate-50 px-2 py-1">
                      running: {queueStats.running}
                    </div>
                    <div className="rounded bg-slate-50 px-2 py-1">
                      done: {queueStats.done}
                    </div>
                    <div className="rounded bg-slate-50 px-2 py-1">
                      failed: {queueStats.failed}
                    </div>
                  </div>
                )}
                <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto">
                  {queueJobs.length === 0 && (
                    <li className="text-xs text-slate-500">暂无队列任务。</li>
                  )}
                  {queueJobs.map((j) => (
                    <li
                      key={j.id}
                      className="rounded border border-slate-100 bg-slate-50 px-2 py-1 text-[11px]"
                    >
                      <span className="font-medium">{j.kind}</span>
                      <span className="ml-2 text-slate-600">{j.status}</span>
                      <span className="ml-2 text-slate-500">
                        retry {j.attempts}/{j.max_attempts}
                      </span>
                      <span className="ml-2 text-slate-400">
                        {new Date(j.run_at).toLocaleString()}
                      </span>
                      {j.last_error && (
                        <div className="mt-1 text-[10px] text-red-600">
                          {j.last_error}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
          {tab === "evolution" && <EvolutionPanel />}

          {tab === "policy" && (
            <div className="space-y-4">
              <section className="rounded-md border border-violet-200 bg-violet-50/50 p-3">
                <div className="text-xs font-semibold text-violet-900">
                  可见范围（默认观察）
                </div>
                <label className="mt-2 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={global.observe_enabled}
                    onChange={(e) =>
                      setGlobal({ ...global, observe_enabled: e.target.checked })
                    }
                  />
                  启用自动观察
                </label>
                <label className="mt-1 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    disabled={!global.observe_enabled}
                    checked={global.observe_dm}
                    onChange={(e) =>
                      setGlobal({ ...global, observe_dm: e.target.checked })
                    }
                  />
                  观察私聊（用户 ↔ 好友）
                </label>
                <label className="mt-1 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    disabled={!global.observe_enabled}
                    checked={global.observe_group}
                    onChange={(e) =>
                      setGlobal({ ...global, observe_group: e.target.checked })
                    }
                  />
                  观察群聊
                </label>
              </section>

              <section className="rounded-md border border-slate-200 p-3">
                <div className="text-xs font-semibold text-slate-700">
                  记录与整理
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  写入前过滤寒暄/过短/重复；与助理私聊默认不写观察。知识靠「提取/反思」而非流水账。
                </p>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <label className="label text-xs">单条最大字符</label>
                    <input
                      className="input text-xs"
                      type="number"
                      min={80}
                      max={4000}
                      value={global.record_max_chars}
                      onChange={(e) =>
                        setGlobal({
                          ...global,
                          record_max_chars: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="label text-xs">最少写入字符</label>
                    <input
                      className="input text-xs"
                      type="number"
                      min={1}
                      max={200}
                      value={global.record_min_chars ?? 20}
                      onChange={(e) =>
                        setGlobal({
                          ...global,
                          record_min_chars: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="label text-xs">记忆权重</label>
                    <input
                      className="input text-xs"
                      type="number"
                      step={0.05}
                      min={0.05}
                      max={1}
                      value={global.record_weight}
                      onChange={(e) =>
                        setGlobal({
                          ...global,
                          record_weight: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="label text-xs">观察去重（秒）</label>
                    <input
                      className="input text-xs"
                      type="number"
                      min={0}
                      max={3600}
                      value={global.observe_dedupe_secs ?? 120}
                      onChange={(e) =>
                        setGlobal({
                          ...global,
                          observe_dedupe_secs: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                </div>
                <label className="mt-2 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={global.record_skip_low_signal ?? true}
                    onChange={(e) =>
                      setGlobal({
                        ...global,
                        record_skip_low_signal: e.target.checked,
                      })
                    }
                  />
                  跳过低信息量短句（你好/谢谢等）
                </label>
                <label className="mt-1 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={global.record_assist_memo ?? false}
                    onChange={(e) =>
                      setGlobal({
                        ...global,
                        record_assist_memo: e.target.checked,
                      })
                    }
                  />
                  与助理私聊写入「协助记录」流水账（默认关，建议用下方提取）
                </label>
                <label className="mt-2 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={global.auto_consolidate}
                    onChange={(e) =>
                      setGlobal({ ...global, auto_consolidate: e.target.checked })
                    }
                  />
                  观察后自动整理记忆
                </label>
                {global.auto_consolidate && (
                  <div className="mt-2">
                    <label className="label text-xs">每 N 条观察整理一次</label>
                    <input
                      className="input text-xs"
                      type="number"
                      min={1}
                      max={100}
                      value={global.consolidate_every_n}
                      onChange={(e) =>
                        setGlobal({
                          ...global,
                          consolidate_every_n: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                )}
                <label className="mt-2 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={global.auto_ingest_raw ?? true}
                    onChange={(e) =>
                      setGlobal({ ...global, auto_ingest_raw: e.target.checked })
                    }
                  />
                  LLM 将 raw 合并为 curated（ingest）
                </label>
                {global.auto_ingest_raw !== false && (
                  <div className="mt-2">
                    <label className="label text-xs">单次 ingest 条数</label>
                    <input
                      className="input text-xs"
                      type="number"
                      min={5}
                      max={60}
                      value={global.ingest_raw_batch_size ?? 25}
                      onChange={(e) =>
                        setGlobal({
                          ...global,
                          ingest_raw_batch_size: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                )}
                <label className="mt-2 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={global.embedding_enabled ?? false}
                    onChange={(e) =>
                      setGlobal({
                        ...global,
                        embedding_enabled: e.target.checked,
                      })
                    }
                  />
                  向量召回（需 OpenAI 兼容 /embeddings）
                </label>
                {global.embedding_enabled && (
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <div>
                      <label className="label text-xs">Embedding Provider</label>
                      <input
                        className="input text-xs"
                        placeholder="留空=助理默认"
                        value={global.embedding_provider_id ?? ""}
                        onChange={(e) =>
                          setGlobal({
                            ...global,
                            embedding_provider_id: e.target.value || null,
                          })
                        }
                      />
                    </div>
                    <div>
                      <label className="label text-xs">Embedding Model</label>
                      <input
                        className="input text-xs"
                        placeholder="text-embedding-3-small"
                        value={global.embedding_model ?? ""}
                        onChange={(e) =>
                          setGlobal({
                            ...global,
                            embedding_model: e.target.value || null,
                          })
                        }
                      />
                    </div>
                  </div>
                )}
                <div className="mt-2">
                  <label className="label text-xs">临时记忆 TTL（小时）</label>
                  <input
                    className="input text-xs"
                    type="number"
                    min={1}
                    max={8760}
                    value={global.ephemeral_ttl_hours ?? 168}
                    onChange={(e) =>
                      setGlobal({
                        ...global,
                        ephemeral_ttl_hours: Number(e.target.value),
                      })
                    }
                  />
                </div>
                <div className="mt-2 text-xs text-slate-500">
                  待整理计数：{global.observe_streak ?? 0} /{" "}
                  {global.consolidate_every_n}
                  <span className="ml-2 text-slate-400">
                    （维护按钮在「全站记忆」页流水线右上角）
                  </span>
                </div>
              </section>

              <section className="rounded-md border border-slate-200 p-3">
                <div className="text-xs font-semibold text-slate-700">
                  Token 经费
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <label className="label text-xs">月预算（token）</label>
                    <input
                      className="input text-xs"
                      type="number"
                      min={0}
                      value={global.monthly_token_budget}
                      onChange={(e) =>
                        setGlobal({
                          ...global,
                          monthly_token_budget: Number(e.target.value || 0),
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="label text-xs">本月已用</label>
                    <input
                      className="input text-xs bg-slate-50"
                      readOnly
                      value={global.monthly_tokens_used ?? 0}
                    />
                  </div>
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  预算为 0 表示不限制。周期：{global.budget_period_ym || "当月自动初始化"}。
                </p>
              </section>

              <section className="rounded-md border border-slate-200 p-3">
                <div className="text-xs font-semibold text-slate-700">
                  能力进化
                </div>
                <label className="mt-2 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={global.evolution_enabled}
                    onChange={(e) =>
                      setGlobal({ ...global, evolution_enabled: e.target.checked })
                    }
                  />
                  回合后反思并写入知识库
                </label>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <label className="label text-xs">进化池比例（0～1）</label>
                    <input
                      className="input text-xs"
                      type="number"
                      min={0}
                      max={1}
                      step={0.01}
                      value={global.evolution_token_budget_ratio ?? 0.1}
                      onChange={(e) =>
                        setGlobal({
                          ...global,
                          evolution_token_budget_ratio: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="label text-xs">进化池硬顶（0=仅比例）</label>
                    <input
                      className="input text-xs"
                      type="number"
                      min={0}
                      value={global.evolution_token_budget_absolute ?? 0}
                      onChange={(e) =>
                        setGlobal({
                          ...global,
                          evolution_token_budget_absolute: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="label text-xs">进化池本月已用</label>
                    <input
                      className="input text-xs bg-slate-50"
                      readOnly
                      value={global.evolution_tokens_used ?? 0}
                    />
                  </div>
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  反思/进化任务单独记账，与主对话月度预算隔离。
                </p>
                <label className="mt-1 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={global.auto_extract_memories}
                    onChange={(e) =>
                      setGlobal({
                        ...global,
                        auto_extract_memories: e.target.checked,
                      })
                    }
                  />
                  回合后自动提取长期记忆
                </label>
                <label className="mt-1 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={global.proactive_enabled}
                    onChange={(e) =>
                      setGlobal({ ...global, proactive_enabled: e.target.checked })
                    }
                  />
                  空闲时主动处理待办
                </label>
                <label className="mt-1 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={global.proactive_delegate_enabled}
                    onChange={(e) =>
                      setGlobal({
                        ...global,
                        proactive_delegate_enabled: e.target.checked,
                      })
                    }
                  />
                  允许调度 agent 好友执行待办
                </label>
                <div className="mt-2">
                  <label className="label text-xs">每轮最多处理待办数</label>
                  <input
                    className="input text-xs"
                    type="number"
                    min={1}
                    max={20}
                    value={global.proactive_batch_size}
                    onChange={(e) =>
                      setGlobal({
                        ...global,
                        proactive_batch_size: Number(e.target.value || 1),
                      })
                    }
                  />
                </div>
                {global.proactive_delegate_enabled && (
                  <div className="mt-2">
                    <label className="label text-xs">
                      允许调度的好友 ID（逗号分隔，留空表示不限制）
                    </label>
                    <input
                      className="input text-xs"
                      value={delegateFriendDraft}
                      onChange={(e) => {
                        const v = e.target.value;
                        setDelegateFriendDraft(v);
                        setGlobal({
                          ...global,
                          proactive_delegate_friend_ids: v
                            .split(/[,，\s]+/)
                            .map((x) => x.trim())
                            .filter(Boolean),
                        });
                      }}
                      placeholder="friend-id-1, friend-id-2"
                    />
                  </div>
                )}
              </section>

              <section className="rounded-md border border-slate-200 p-3">
                <div className="text-xs font-semibold text-slate-700">
                  CLI 工具白名单
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  留空表示不限制；填写后仅允许列出的 CLI 预设被执行。
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {CLI_PRESET_OPTIONS.map((p) => (
                    <button
                      key={p}
                      type="button"
                      className={`rounded px-2 py-0.5 text-[11px] ${
                        global.tool_whitelist.includes(p)
                          ? "bg-honey-100 text-honey-800 font-medium"
                          : "bg-slate-100 text-slate-600"
                      }`}
                      onClick={() => toggleWhitelistPreset(p)}
                    >
                      {p}
                    </button>
                  ))}
                </div>
                <input
                  className="input mt-2 text-xs"
                  placeholder="逗号分隔，如 worker-bee-cli, codex-exec"
                  value={whitelistDraft}
                  onChange={(e) => setWhitelistDraft(e.target.value)}
                />
              </section>

              <div className="flex items-center justify-end gap-2">
                <button
                  className="btn-primary"
                  onClick={saveGlobal}
                  disabled={busy}
                >
                  保存全局策略
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
