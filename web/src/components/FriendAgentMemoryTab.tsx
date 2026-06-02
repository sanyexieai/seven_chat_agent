import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AssistantMemory } from "../types";

interface Props {
  friendId: string;
}

export function FriendAgentMemoryTab({ friendId }: Props) {
  const [prompt, setPrompt] = useState("");
  const [memories, setMemories] = useState<AssistantMemory[]>([]);
  const [busy, setBusy] = useState(false);

  async function preview() {
    setBusy(true);
    try {
      const r = await api.previewAssistantMemoryRecall(friendId, {
        prompt: prompt || "当前对话上下文",
        limit: 8,
      });
      setMemories(r.memories);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (friendId) void preview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [friendId]);

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        召回预览（curated 层）；实际对话时按当前 prompt 动态注入。
      </p>
      <div>
        <label className="label">模拟 prompt</label>
        <textarea
          className="input min-h-[64px] text-sm"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="输入一句用户话，预览会召回哪些记忆"
        />
      </div>
      <button type="button" className="btn text-xs" disabled={busy} onClick={() => void preview()}>
        {busy ? "召回中…" : "预览召回"}
      </button>
      <ul className="max-h-64 space-y-2 overflow-y-auto">
        {memories.map((m) => (
          <li
            key={m.id}
            className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs"
          >
            <div className="font-medium text-slate-600">
              {m.kind} · {m.tier} · imp={m.importance}
            </div>
            <div className="mt-1 whitespace-pre-wrap text-slate-700">{m.content}</div>
          </li>
        ))}
        {memories.length === 0 && (
          <li className="text-xs text-slate-400">暂无召回结果</li>
        )}
      </ul>
    </div>
  );
}
