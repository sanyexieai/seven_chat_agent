import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  AssistantMemory,
  AssistantReflection,
  AssistantSkill,
} from "../types";

interface Props {
  friendId: string | null;
  onClose: () => void;
}

type Tab = "memories" | "skills" | "reflections";

export function AssistantPanel({ friendId, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("memories");
  const [memories, setMemories] = useState<AssistantMemory[]>([]);
  const [skills, setSkills] = useState<AssistantSkill[]>([]);
  const [reflections, setReflections] = useState<AssistantReflection[]>([]);
  const [draft, setDraft] = useState({
    kind: "fact",
    content: "",
    weight: 0.7,
    pinned: false,
  });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function reload() {
    if (!friendId) return;
    const [m, s, r] = await Promise.all([
      api.listAssistantMemories(friendId),
      api.listAssistantSkills(friendId),
      api.listAssistantReflections(friendId),
    ]);
    setMemories(m.memories);
    setSkills(s.skills);
    setReflections(r.reflections);
  }

  useEffect(() => {
    if (friendId) reload();
  }, [friendId]);

  if (!friendId) return null;

  async function addMemory() {
    if (!draft.content.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      await api.addAssistantMemory(friendId!, draft);
      setDraft({ ...draft, content: "" });
      await reload();
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeMemory(id: string) {
    if (!confirm("删除这条记忆？")) return;
    await api.deleteAssistantMemory(friendId!, id);
    await reload();
  }

  return (
    <div className="fixed inset-0 z-30 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex h-full w-[640px] flex-col border-l border-slate-200 bg-white shadow-xl">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div>
            <div className="text-base font-semibold">助理控制面板</div>
            <div className="text-xs text-slate-500">
              记忆 / 技能 / 反思 · friend_id={friendId}
            </div>
          </div>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="flex gap-1 border-b border-slate-200 px-5 py-2">
          {(["memories", "skills", "reflections"] as Tab[]).map((t) => (
            <button
              key={t}
              className={`px-3 py-1 text-sm rounded-md ${
                tab === t
                  ? "bg-honey-100 text-honey-800 font-semibold"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
              onClick={() => setTab(t)}
            >
              {t === "memories" ? "记忆" : t === "skills" ? "技能" : "反思"}
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
          {tab === "memories" && (
            <div className="space-y-4">
              <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                <div className="text-xs font-semibold text-slate-600">
                  手动写一条记忆
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <label className="label">kind</label>
                    <select
                      className="input"
                      value={draft.kind}
                      onChange={(e) =>
                        setDraft({ ...draft, kind: e.target.value })
                      }
                    >
                      <option value="fact">fact</option>
                      <option value="preference">preference</option>
                      <option value="project">project</option>
                      <option value="relation">relation</option>
                      <option value="lesson">lesson</option>
                    </select>
                  </div>
                  <div>
                    <label className="label">weight</label>
                    <input
                      className="input"
                      type="number"
                      step={0.05}
                      min={0}
                      max={1}
                      value={draft.weight}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          weight: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                </div>
                <div className="mt-2">
                  <label className="label">content</label>
                  <textarea
                    rows={3}
                    className="input"
                    value={draft.content}
                    onChange={(e) =>
                      setDraft({ ...draft, content: e.target.value })
                    }
                    placeholder="例如：用户喜欢简洁的 Rust 风格..."
                  />
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <label className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={draft.pinned}
                      onChange={(e) =>
                        setDraft({ ...draft, pinned: e.target.checked })
                      }
                    />
                    pinned（永不衰减）
                  </label>
                  <button className="btn-primary" onClick={addMemory} disabled={busy}>
                    添加
                  </button>
                </div>
                {msg && <div className="mt-2 text-xs text-amber-600">{msg}</div>}
              </div>
              <ul className="space-y-2">
                {memories.length === 0 && (
                  <li className="text-sm text-slate-500">还没有记忆。</li>
                )}
                {memories.map((m) => (
                  <li
                    key={m.id}
                    className="rounded-md border border-slate-200 p-3"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold text-slate-700">
                        {m.kind}
                      </span>
                      <span className="text-slate-400">
                        w={m.weight.toFixed(2)} · decay={m.decay_score.toFixed(2)}{" "}
                        {m.pinned && "· 📌"}
                      </span>
                    </div>
                    <div className="mt-1 whitespace-pre-wrap text-sm">
                      {m.content}
                    </div>
                    <div className="mt-2 flex justify-end">
                      <button
                        className="btn-ghost text-red-600"
                        onClick={() => removeMemory(m.id)}
                      >
                        删除
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {tab === "skills" && (
            <ul className="space-y-2">
              {skills.length === 0 && (
                <li className="text-sm text-slate-500">
                  还没有技能。把 SKILL.md 放到{" "}
                  <code>data/skills/{friendId}/</code> 目录，助理就能学到。
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
          {tab === "reflections" && (
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
          )}
        </div>
      </div>
    </div>
  );
}
