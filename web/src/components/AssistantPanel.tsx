import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  AssistantGlobalSettings,
  AssistantMemory,
  AssistantQueueJob,
  AssistantQueueStats,
  AssistantReflection,
  AssistantSkill,
  AssistantTodo,
} from "../types";

interface Props {
  friendId: string | null;
  onClose: () => void;
}

type Tab = "memo" | "todo" | "toolbox" | "knowledge" | "queue" | "policy";

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
  auto_consolidate: true,
  consolidate_every_n: 1,
  evolution_enabled: true,
  auto_extract_memories: true,
  proactive_enabled: true,
  proactive_batch_size: 2,
  proactive_delegate_enabled: false,
  proactive_delegate_friend_ids: [],
  monthly_token_budget: 0,
  monthly_tokens_used: 0,
  tool_whitelist: [],
};

export function AssistantPanel({ friendId, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("memo");
  const [memos, setMemos] = useState<AssistantMemory[]>([]);
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

  async function reload() {
    const [g, memoRes, knowRes, s, r, t, done, qs, qj] = await Promise.all([
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
    setGlobal(g.settings);
    setWhitelistDraft(g.settings.tool_whitelist.join(", "));
    setDelegateFriendDraft((g.settings.proactive_delegate_friend_ids || []).join(", "));
    setMemos(memoRes.memories);
    setKnowledgeMemories(knowRes.memories);
    setSkills(s.skills);
    setReflections(r.reflections);
    setTodos(t.todos);
    setDoneTodos(done.todos);
    setQueueStats(qs.stats);
    setQueueJobs(qj.jobs);
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
    if (!friendId || tab !== "queue" || !opsAutoRefresh) return;
    const timer = window.setInterval(() => {
      reloadOps().catch(() => {});
    }, 5000);
    return () => window.clearInterval(timer);
  }, [friendId, tab, opsAutoRefresh]);

  if (!friendId) return null;

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
    setMsg(null);
    try {
      const res = await api.consolidateAssistantMemories();
      setGlobal(res.settings);
      await reload();
      setMsg("记忆整理完成");
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
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

  return (
    <div className="fixed inset-0 z-30 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex h-full w-[640px] flex-col border-l border-slate-200 bg-white shadow-xl">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div>
            <div className="text-base font-semibold">助理控制面板</div>
            <div className="text-xs text-slate-500">
              自动沉淀 · 任务回顾 / TodoList / 工具箱 / 知识库 / 队列 / 策略
            </div>
          </div>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="flex flex-wrap gap-1 border-b border-slate-200 px-5 py-2">
          {(["memo", "todo", "toolbox", "knowledge", "queue", "policy"] as Tab[]).map((t) => (
            <button
              key={t}
              className={`px-3 py-1 text-sm rounded-md ${
                tab === t
                  ? "bg-honey-100 text-honey-800 font-semibold"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
              onClick={() => setTab(t)}
            >
              {t === "memo"
                ? "任务回顾"
                : t === "todo"
                  ? "TodoList"
                : t === "toolbox"
                  ? "工具箱"
                  : t === "knowledge"
                    ? "知识库"
                    : t === "queue"
                      ? "队列"
                    : "策略"}
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
          {(tab === "memo" || tab === "toolbox" || tab === "knowledge") && (
            <div className="mb-3 rounded-md border border-violet-200 bg-violet-50/60 px-3 py-2 text-xs text-violet-900">
              以下内容均由助理在协助你时<strong>自动记录</strong>，无需手动填写。私聊/群聊观察、代发摘要会进入备忘录；回合反思与知识提取会进入知识库；固化流程会进入工具箱。
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
                      <div className="text-xs text-slate-400">
                        {new Date(m.created_at).toLocaleString()} · w=
                        {m.weight.toFixed(2)}
                      </div>
                      <div className="mt-1 text-sm">{m.content}</div>
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <div className="mb-2 text-xs font-semibold text-slate-600">
                  回合反思
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
                </div>
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
                <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                  <span>
                    待整理计数：{global.observe_streak ?? 0} /{" "}
                    {global.consolidate_every_n}
                  </span>
                  <button
                    className="btn-ghost text-xs"
                    onClick={runConsolidate}
                    disabled={busy}
                  >
                    立即整理
                  </button>
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
                {msg && <span className="text-xs text-amber-600">{msg}</span>}
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
