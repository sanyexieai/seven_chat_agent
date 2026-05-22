import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useChat } from "../stores/chat";
import type { GroupSettings } from "../types";

interface Props {
  groupId: string | null;
  onClose: () => void;
}

const defaults: GroupSettings = {
  judge_threshold: 0.55,
  max_replies_per_turn: 8,
  per_agent_max_per_turn: 2,
  cooldown_ms: 4000,
  human_priority: true,
  human_pause_ms: 30000,
  allow_agent_to_agent: true,
  extra_system_prompt: null,
};

export function GroupEditor({ groupId, onClose }: Props) {
  const { friends, reloadGroups, selectGroup } = useChat();
  const [name, setName] = useState("");
  const [memberIds, setMemberIds] = useState<Set<string>>(new Set());
  const [settings, setSettings] = useState<GroupSettings>(defaults);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!groupId) {
      setName("");
      setMemberIds(new Set());
      setSettings(defaults);
      return;
    }
    api.getGroup(groupId).then((bundle) => {
      setName(bundle.group.name);
      setMemberIds(new Set(bundle.member_ids));
      setSettings({ ...defaults, ...bundle.group.settings });
    });
  }, [groupId]);

  function toggleMember(id: string) {
    const next = new Set(memberIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setMemberIds(next);
  }

  async function save() {
    if (!name.trim()) {
      setError("群名不能为空");
      return;
    }
    if (memberIds.size === 0) {
      setError("至少选一位好友进群");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.upsertGroup({
        id: groupId ?? undefined,
        name: name.trim(),
        avatar: null,
        settings,
        member_ids: Array.from(memberIds),
      });
      await reloadGroups();
      await selectGroup(result.group.id);
      onClose();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40">
      <div className="card flex max-h-[90vh] w-[640px] flex-col overflow-hidden p-0">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h2 className="text-base font-semibold">
            {groupId ? "群聊设置" : "新建群聊"}
          </h2>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <div>
            <label className="label">群名</label>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：周末研讨"
            />
          </div>
          <div>
            <label className="label">成员（多选）</label>
            <div className="mt-1 grid grid-cols-2 gap-2 rounded-md border border-slate-200 bg-slate-50 p-3">
              {friends.map((f) => (
                <label
                  key={f.id}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 hover:bg-white"
                >
                  <input
                    type="checkbox"
                    checked={memberIds.has(f.id)}
                    onChange={() => toggleMember(f.id)}
                  />
                  <span className="text-sm">
                    {f.name}
                    <span className="ml-1 text-xs text-slate-500">
                      · {f.backend_kind}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 text-xs font-semibold text-slate-600">
              群聊调度参数（防风暴）
            </div>
            <div className="grid grid-cols-2 gap-3">
              <NumberField
                label="judge_threshold"
                value={settings.judge_threshold}
                step={0.05}
                min={0}
                max={1}
                onChange={(v) =>
                  setSettings({ ...settings, judge_threshold: v })
                }
              />
              <NumberField
                label="max_replies_per_turn"
                value={settings.max_replies_per_turn}
                step={1}
                onChange={(v) =>
                  setSettings({ ...settings, max_replies_per_turn: v })
                }
              />
              <NumberField
                label="per_agent_max_per_turn"
                value={settings.per_agent_max_per_turn}
                step={1}
                onChange={(v) =>
                  setSettings({ ...settings, per_agent_max_per_turn: v })
                }
              />
              <NumberField
                label="cooldown_ms"
                value={settings.cooldown_ms}
                step={500}
                onChange={(v) =>
                  setSettings({ ...settings, cooldown_ms: v })
                }
              />
              <NumberField
                label="human_pause_ms"
                value={settings.human_pause_ms}
                step={1000}
                onChange={(v) =>
                  setSettings({ ...settings, human_pause_ms: v })
                }
              />
              <div className="space-y-1">
                <label className="label">human_priority</label>
                <input
                  type="checkbox"
                  checked={settings.human_priority}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      human_priority: e.target.checked,
                    })
                  }
                />
              </div>
              <div className="space-y-1">
                <label className="label">允许好友互回</label>
                <input
                  type="checkbox"
                  checked={settings.allow_agent_to_agent}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      allow_agent_to_agent: e.target.checked,
                    })
                  }
                />
              </div>
            </div>
            <div className="mt-3">
              <label className="label">群规 prompt（拼到每位成员人设后）</label>
              <textarea
                rows={3}
                className="input"
                value={settings.extra_system_prompt ?? ""}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    extra_system_prompt: e.target.value || null,
                  })
                }
                placeholder="例如：本群讨论 Rust 异步编程，请尽量简洁。"
              />
            </div>
          </div>

          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <button className="btn" onClick={onClose}>
            取消
          </button>
          <button className="btn-primary" onClick={save} disabled={busy}>
            {busy ? "保存中..." : "保存"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function NumberField({
  label,
  value,
  step,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  step?: number;
  min?: number;
  max?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        className="input"
        type="number"
        step={step}
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
