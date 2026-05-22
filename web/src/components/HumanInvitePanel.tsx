import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Friend } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
  humanFriends: Friend[];
}

export function HumanInvitePanel({ open, onClose, humanFriends }: Props) {
  const [friendId, setFriendId] = useState<string>("");
  const [hours, setHours] = useState(72);
  const [invites, setInvites] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (!friendId && humanFriends[0]) setFriendId(humanFriends[0].id);
    api.listInvites().then((r) => setInvites(r.invites));
  }, [open, humanFriends]);

  if (!open) return null;

  async function create() {
    if (!friendId) {
      setMsg("先创建一个 human 后端的好友");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await api.createInvite({ friend_id: friendId, expires_in_hours: hours });
      const r = await api.listInvites();
      setInvites(r.invites);
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!confirm("删除这个邀请？")) return;
    await api.deleteInvite(id);
    const r = await api.listInvites();
    setInvites(r.invites);
  }

  function inviteUrl(code: string) {
    return `${window.location.origin}/?human=${code}`;
  }

  return (
    <div className="fixed inset-0 z-30 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex h-full w-[560px] flex-col border-l border-slate-200 bg-white shadow-xl">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div>
            <div className="text-base font-semibold">真人好友邀请</div>
            <div className="text-xs text-slate-500">生成一次性邀请链接</div>
          </div>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            {humanFriends.length === 0 ? (
              <div className="text-sm text-slate-500">
                先在"添加好友"里创建一个后端类型为「真人」的好友。
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="label">真人好友</label>
                    <select
                      className="input"
                      value={friendId}
                      onChange={(e) => setFriendId(e.target.value)}
                    >
                      {humanFriends.map((f) => (
                        <option key={f.id} value={f.id}>
                          {f.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="label">有效时长（小时）</label>
                    <input
                      className="input"
                      type="number"
                      value={hours}
                      onChange={(e) => setHours(Number(e.target.value))}
                    />
                  </div>
                </div>
                <div className="mt-2 flex justify-end">
                  <button className="btn-primary" onClick={create} disabled={busy}>
                    生成邀请
                  </button>
                </div>
                {msg && (
                  <div className="mt-2 text-xs text-amber-600">{msg}</div>
                )}
              </>
            )}
          </div>
          <ul className="space-y-2">
            {invites.length === 0 && (
              <li className="text-sm text-slate-500">还没有邀请。</li>
            )}
            {invites.map((iv) => (
              <li key={iv.id} className="rounded-md border border-slate-200 p-3">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span>{iv.friend_id}</span>
                  <span>
                    {iv.used_at ? "已使用" : "未使用"} · 到期{" "}
                    {iv.expires_at?.slice(0, 10) ?? "—"}
                  </span>
                </div>
                <div className="mt-1 break-all font-mono text-sm">
                  {inviteUrl(iv.code)}
                </div>
                <div className="mt-2 flex gap-2">
                  <button
                    className="btn-ghost"
                    onClick={() =>
                      navigator.clipboard?.writeText(inviteUrl(iv.code))
                    }
                  >
                    复制链接
                  </button>
                  <button
                    className="btn-ghost text-red-600 ml-auto"
                    onClick={() => remove(iv.id)}
                  >
                    撤销
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
