import { useEffect, useState } from "react";
import { wsInvoke } from "../api/client";
import { useAuth } from "../stores/auth";

interface TenantInvite {
  id: string;
  code: string;
  invited_email?: string | null;
  role: string;
  expires_at: string;
  used_at?: string | null;
  created_at: string;
}

interface TenantMember {
  id: string;
  email: string;
  username?: string | null;
  display_name: string;
  role: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export function TenantTeamPanel({ open, onClose }: Props) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [members, setMembers] = useState<TenantMember[]>([]);
  const [invites, setInvites] = useState<TenantInvite[]>([]);
  const [email, setEmail] = useState("");
  const [hours, setHours] = useState(168);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    void reload();
  }, [open, isAdmin]);

  async function reload() {
    const m = await wsInvoke<{ members: TenantMember[] }>("listTenantMembers", {});
    setMembers(m.members);
    if (isAdmin) {
      const inv = await wsInvoke<{ invites: TenantInvite[] }>("listTenantInvites", {});
      setInvites(inv.invites);
    }
  }

  if (!open) return null;

  async function createInvite() {
    setBusy(true);
    setMsg(null);
    try {
      await wsInvoke("createTenantInvite", {
        invited_email: email.trim() || undefined,
        expires_in_hours: hours,
      });
      setEmail("");
      await reload();
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeInvite(id: string) {
    if (!confirm("删除这个租户邀请？")) return;
    await wsInvoke("deleteTenantInvite", { id });
    await reload();
  }

  async function setRole(userId: string, role: string) {
    if (!confirm(`将该成员设为 ${role}？`)) return;
    await wsInvoke("updateTenantMemberRole", { user_id: userId, role });
    await reload();
  }

  function registerUrl(code: string) {
    return `${window.location.origin}/?invite=${code}`;
  }

  return (
    <div className="fixed inset-0 z-30 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex h-full w-[560px] flex-col border-l border-slate-200 bg-white shadow-xl">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div>
            <div className="text-base font-semibold">租户团队</div>
            <div className="text-xs text-slate-500">
              {user?.tenant_id} · {isAdmin ? "管理员" : "成员"}
            </div>
          </div>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <section>
            <div className="mb-2 text-sm font-semibold text-slate-700">成员</div>
            <ul className="space-y-2">
              {members.map((m) => (
                <li
                  key={m.id}
                  className="flex items-center justify-between rounded border border-slate-200 px-3 py-2 text-sm"
                >
                  <div>
                    <div className="font-medium">{m.display_name}</div>
                    <div className="text-xs text-slate-500">
                      {m.username ? `@${m.username} · ` : ""}
                      {m.email}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">
                      {m.role}
                    </span>
                    {isAdmin && m.id !== user?.id && (
                      <select
                        className="input py-1 text-xs"
                        value={m.role}
                        onChange={(e) => void setRole(m.id, e.target.value)}
                      >
                        <option value="member">member</option>
                        <option value="admin">admin</option>
                      </select>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {isAdmin && (
            <section>
              <div className="mb-2 text-sm font-semibold text-slate-700">
                邀请新成员
              </div>
              <div className="space-y-2 rounded border border-slate-200 bg-slate-50 p-3">
                <div>
                  <label className="label">限定邮箱（可选）</label>
                  <input
                    className="input"
                    type="email"
                    placeholder="留空则任意邮箱可用"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
                <div>
                  <label className="label">有效期（小时）</label>
                  <input
                    className="input"
                    type="number"
                    min={1}
                    value={hours}
                    onChange={(e) => setHours(Number(e.target.value))}
                  />
                </div>
                <button
                  type="button"
                  className="btn w-full"
                  disabled={busy}
                  onClick={() => void createInvite()}
                >
                  生成邀请
                </button>
              </div>
              <ul className="mt-3 space-y-2">
                {invites.map((inv) => (
                  <li
                    key={inv.id}
                    className="rounded border border-slate-200 px-3 py-2 text-sm"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <code className="truncate text-xs">{inv.code}</code>
                      <span className="shrink-0 text-xs text-slate-500">
                        {inv.used_at ? "已使用" : "有效"}
                      </span>
                    </div>
                    {inv.invited_email && (
                      <div className="text-xs text-slate-500">
                        限定：{inv.invited_email}
                      </div>
                    )}
                    <div className="mt-1 break-all text-xs text-slate-600">
                      {registerUrl(inv.code)}
                    </div>
                    {!inv.used_at && (
                      <button
                        type="button"
                        className="btn-ghost mt-1 text-xs text-red-600"
                        onClick={() => void removeInvite(inv.id)}
                      >
                        删除
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {msg && <div className="text-sm text-red-600">{msg}</div>}
        </div>
      </div>
    </div>
  );
}
