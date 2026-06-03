import { useEffect, useState } from "react";
import { wsInvoke } from "../api/client";
import { useAuth } from "../stores/auth";
import { isTenantAdmin, tenantRoleLabel, type TenantRole } from "../tenantAdmin";

type TabId = "overview" | "members" | "sessions" | "conversations" | "invites";

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

interface TenantOverview {
  tenant_id: string;
  tenant_name: string;
  tenant_slug?: string | null;
  user_count: number;
  admin_count: number;
  active_session_count: number;
  conversation_count: number;
  pending_invite_count: number;
}

interface UserSessionRow {
  id: string;
  user_id: string;
  user_email: string;
  user_display_name: string;
  user_username?: string | null;
  expires_at: string;
  created_at: string;
  is_expired: boolean;
}

interface ConversationRow {
  id: string;
  kind: string;
  target_id: string;
  title?: string | null;
  scope_user_id?: string | null;
  last_message_at?: string | null;
  created_at: string;
  message_count: number;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

const TABS: { id: TabId; label: string; adminOnly?: boolean }[] = [
  { id: "overview", label: "概览" },
  { id: "members", label: "用户与成员" },
  { id: "sessions", label: "登录会话", adminOnly: true },
  { id: "conversations", label: "聊天会话", adminOnly: true },
  { id: "invites", label: "邀请", adminOnly: true },
];

function fmtTime(iso?: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function AdminManagementPanel({ open, onClose }: Props) {
  const { user } = useAuth();
  const isAdmin = isTenantAdmin(user?.role);
  const [tab, setTab] = useState<TabId>("overview");
  const [overview, setOverview] = useState<TenantOverview | null>(null);
  const [members, setMembers] = useState<TenantMember[]>([]);
  const [sessions, setSessions] = useState<UserSessionRow[]>([]);
  const [conversations, setConversations] = useState<ConversationRow[]>([]);
  const [invites, setInvites] = useState<TenantInvite[]>([]);
  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<TenantRole>("member");
  const [hours, setHours] = useState(168);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const [tenantName, setTenantName] = useState("");
  const [memberMode, setMemberMode] = useState<"create" | "edit" | null>(null);
  const [memberForm, setMemberForm] = useState({
    user_id: "",
    email: "",
    username: "",
    password: "",
    display_name: "",
    role: "member" as TenantRole,
  });
  const [editingInviteId, setEditingInviteId] = useState<string | null>(null);
  const [inviteEdit, setInviteEdit] = useState({
    invited_email: "",
    role: "member" as TenantRole,
    hours: 168,
  });
  const [editingConvId, setEditingConvId] = useState<string | null>(null);
  const [convTitle, setConvTitle] = useState("");

  const visibleTabs = TABS.filter((t) => isAdmin || !t.adminOnly);

  useEffect(() => {
    if (!open) return;
    if (!visibleTabs.some((t) => t.id === tab)) {
      setTab(visibleTabs[0]?.id ?? "members");
    }
  }, [open, isAdmin, tab, visibleTabs]);

  useEffect(() => {
    if (!open) return;
    void reloadTab(tab);
  }, [open, tab, isAdmin]);

  async function reloadTab(active: TabId) {
    setMsg(null);
    try {
      if (active === "overview" && isAdmin) {
        const r = await wsInvoke<{ overview: TenantOverview }>("getTenantAdminOverview", {});
        setOverview(r.overview);
        setTenantName(r.overview.tenant_name);
      }
      if (active === "members" || active === "overview") {
        const m = await wsInvoke<{ members: TenantMember[] }>("listTenantMembers", {});
        setMembers(m.members);
      }
      if (active === "sessions" && isAdmin) {
        const r = await wsInvoke<{ sessions: UserSessionRow[] }>("listTenantUserSessions", {
          limit: 200,
        });
        setSessions(r.sessions);
      }
      if (active === "conversations" && isAdmin) {
        const r = await wsInvoke<{ conversations: ConversationRow[] }>(
          "listTenantConversationsAdmin",
          { limit: 200 },
        );
        setConversations(r.conversations);
      }
      if (active === "invites" && isAdmin) {
        const inv = await wsInvoke<{ invites: TenantInvite[] }>("listTenantInvites", {});
        setInvites(inv.invites);
      }
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function reloadAll() {
    await reloadTab(tab);
  }

  if (!open) return null;

  async function createInvite() {
    setBusy(true);
    setMsg(null);
    try {
      await wsInvoke("createTenantInvite", {
        invited_email: email.trim() || undefined,
        role: inviteRole,
        expires_in_hours: hours,
      });
      setEmail("");
      setTab("invites");
      await reloadTab("invites");
      setMsg("邀请已生成");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeInvite(id: string) {
    if (!confirm("删除这个邀请码？")) return;
    try {
      await wsInvoke("deleteTenantInvite", { id });
      await reloadTab("invites");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function setRole(userId: string, role: TenantRole) {
    if (!confirm(`将该用户设为「${tenantRoleLabel(role)}」？`)) return;
    try {
      await wsInvoke("updateTenantMemberRole", { user_id: userId, role });
      await reloadTab("members");
      setMsg("角色已更新");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function saveTenantName() {
    if (!tenantName.trim()) return;
    try {
      await wsInvoke("updateTenantProfile", { name: tenantName.trim() });
      await reloadTab("overview");
      setMsg("租户名称已保存");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  function openCreateMember() {
    setMemberMode("create");
    setMemberForm({
      user_id: "",
      email: "",
      username: "",
      password: "",
      display_name: "",
      role: "member",
    });
  }

  function openEditMember(m: TenantMember) {
    setMemberMode("edit");
    setMemberForm({
      user_id: m.id,
      email: m.email,
      username: m.username ?? "",
      password: "",
      display_name: m.display_name,
      role: m.role as TenantRole,
    });
  }

  async function saveMember() {
    setBusy(true);
    setMsg(null);
    try {
      if (memberMode === "create") {
        await wsInvoke("createTenantMember", {
          email: memberForm.email.trim(),
          username: memberForm.username.trim(),
          password: memberForm.password,
          display_name: memberForm.display_name.trim(),
          role: memberForm.role,
        });
        setMsg("用户已创建");
      } else if (memberMode === "edit") {
        await wsInvoke("updateTenantMember", {
          user_id: memberForm.user_id,
          email: memberForm.email.trim(),
          username: memberForm.username.trim(),
          display_name: memberForm.display_name.trim(),
          role: memberForm.role,
          ...(memberForm.password ? { password: memberForm.password } : {}),
        });
        setMsg("用户已更新");
      }
      setMemberMode(null);
      await reloadTab("members");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function deleteMember(m: TenantMember) {
    if (!confirm(`确定删除用户「${m.display_name}」？其登录会话与相关数据将一并移除。`)) return;
    try {
      await wsInvoke("deleteTenantMember", { user_id: m.id });
      await reloadTab("members");
      setMsg("用户已删除");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  function openEditInvite(inv: TenantInvite) {
    setEditingInviteId(inv.id);
    setInviteEdit({
      invited_email: inv.invited_email ?? "",
      role: inv.role as TenantRole,
      hours: 168,
    });
  }

  async function saveInviteEdit() {
    if (!editingInviteId) return;
    try {
      await wsInvoke("updateTenantInvite", {
        id: editingInviteId,
        invited_email: inviteEdit.invited_email.trim()
          ? inviteEdit.invited_email.trim()
          : null,
        role: inviteEdit.role,
        expires_in_hours: inviteEdit.hours,
      });
      setEditingInviteId(null);
      await reloadTab("invites");
      setMsg("邀请已更新");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  function openEditConv(c: ConversationRow) {
    setEditingConvId(c.id);
    setConvTitle(c.title ?? "");
  }

  async function saveConvTitle() {
    if (!editingConvId) return;
    try {
      await wsInvoke("updateTenantConversationAdmin", {
        conversation_id: editingConvId,
        title: convTitle.trim() || null,
      });
      setEditingConvId(null);
      await reloadTab("conversations");
      setMsg("会话标题已更新");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function deleteConv(c: ConversationRow) {
    if (
      !confirm(
        `删除聊天会话？\n类型：${c.kind} · 目标 ${c.target_id}\n将删除该会话下全部消息（${c.message_count} 条），不可恢复。`,
      )
    )
      return;
    try {
      await wsInvoke("deleteTenantConversationAdmin", { conversation_id: c.id });
      await reloadTab("conversations");
      setMsg("会话已删除");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function purgeExpiredSessions() {
    if (!confirm("清理全部已过期的登录会话记录？")) return;
    try {
      const r = await wsInvoke<{ purged: number }>("purgeTenantExpiredSessions", {});
      await reloadTab("sessions");
      setMsg(`已清理 ${r.purged} 条过期会话`);
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function revokeSession(sessionId: string) {
    if (!confirm("吊销该登录会话？对应设备需重新登录。")) return;
    try {
      await wsInvoke("revokeTenantUserSession", { session_id: sessionId });
      await reloadTab("sessions");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function revokeUserSessions(userId: string, displayName: string) {
    const keep = userId === user?.id;
    const hint = keep
      ? "将吊销该用户除当前浏览器外的所有登录会话。"
      : "将吊销该用户全部登录会话。";
    if (!confirm(`吊销「${displayName}」的登录会话？\n${hint}`)) return;
    try {
      await wsInvoke("revokeTenantUserSessions", {
        user_id: userId,
        keep_current: keep,
      });
      await reloadTab("sessions");
      setMsg("已吊销登录会话");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  function registerUrl(code: string) {
    return `${window.location.origin}/?invite=${encodeURIComponent(code)}`;
  }

  async function copyText(text: string, code?: string) {
    try {
      await navigator.clipboard.writeText(text);
      if (code) {
        setCopiedCode(code);
        window.setTimeout(() => setCopiedCode(null), 2000);
      }
    } catch {
      setMsg("无法写入剪贴板");
    }
  }

  return (
    <div className="fixed inset-0 z-30 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex h-full w-[min(720px,100vw)] flex-col border-l border-slate-200 bg-white shadow-xl">
        <header className="border-b border-slate-200 px-5 py-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-base font-semibold">管理控制台</div>
              <div className="text-xs text-slate-500">
                租户 {user?.tenant_id} · {tenantRoleLabel(user?.role ?? "member")}
                {overview?.tenant_name ? ` · ${overview.tenant_name}` : ""}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" className="btn-ghost text-xs" onClick={() => void reloadAll()}>
                刷新
              </button>
              <button type="button" className="btn-ghost" onClick={onClose}>
                ×
              </button>
            </div>
          </div>
          <nav className="mt-3 flex flex-wrap gap-1">
            {visibleTabs.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`rounded-md px-3 py-1.5 text-xs ${
                  tab === t.id
                    ? "bg-sky-100 font-medium text-sky-900"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {!isAdmin && (
            <p className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              当前为成员身份，仅可查看成员列表。用户管理、登录会话与邀请需管理员权限。
            </p>
          )}

          {tab === "overview" && isAdmin && overview && (
            <>
              <div className="mb-4 flex flex-wrap items-end gap-2">
                <div className="min-w-[200px] flex-1">
                  <label className="label">租户名称</label>
                  <input
                    className="input"
                    value={tenantName}
                    onChange={(e) => setTenantName(e.target.value)}
                  />
                </div>
                <button
                  type="button"
                  className="btn-primary text-sm"
                  onClick={() => void saveTenantName()}
                >
                  保存
                </button>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {[
                  ["用户", overview.user_count],
                  ["管理员", overview.admin_count],
                  ["有效登录会话", overview.active_session_count],
                  ["聊天会话", overview.conversation_count],
                  ["待使用邀请", overview.pending_invite_count],
                ].map(([label, n]) => (
                  <div
                    key={label as string}
                    className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3"
                  >
                    <div className="text-xs text-slate-500">{label}</div>
                    <div className="mt-1 text-xl font-semibold text-slate-800">{n}</div>
                  </div>
                ))}
              </div>
            </>
          )}

          {(tab === "members" || (tab === "overview" && isAdmin)) && (
            <section className={tab === "overview" ? "mt-4" : ""}>
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-slate-700">用户与成员</h3>
                {isAdmin && tab === "members" && (
                  <button
                    type="button"
                    className="btn-primary text-xs"
                    onClick={openCreateMember}
                  >
                    添加用户
                  </button>
                )}
              </div>
              {isAdmin && memberMode && tab === "members" && (
                <div className="mb-3 space-y-2 rounded border border-sky-200 bg-sky-50/50 p-3">
                  <div className="text-xs font-medium text-sky-900">
                    {memberMode === "create" ? "新建用户" : "编辑用户"}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <input
                      className="input text-sm"
                      placeholder="邮箱"
                      type="email"
                      value={memberForm.email}
                      onChange={(e) =>
                        setMemberForm((f) => ({ ...f, email: e.target.value }))
                      }
                    />
                    <input
                      className="input text-sm"
                      placeholder="用户名"
                      value={memberForm.username}
                      onChange={(e) =>
                        setMemberForm((f) => ({ ...f, username: e.target.value }))
                      }
                    />
                    <input
                      className="input text-sm"
                      placeholder="显示名"
                      value={memberForm.display_name}
                      onChange={(e) =>
                        setMemberForm((f) => ({ ...f, display_name: e.target.value }))
                      }
                    />
                    <select
                      className="input text-sm"
                      value={memberForm.role}
                      onChange={(e) =>
                        setMemberForm((f) => ({
                          ...f,
                          role: e.target.value as TenantRole,
                        }))
                      }
                    >
                      <option value="member">成员</option>
                      <option value="admin">管理员</option>
                    </select>
                    <input
                      className="input text-sm sm:col-span-2"
                      placeholder={
                        memberMode === "create"
                          ? "初始密码（至少 8 位）"
                          : "新密码（留空则不修改）"
                      }
                      type="password"
                      value={memberForm.password}
                      onChange={(e) =>
                        setMemberForm((f) => ({ ...f, password: e.target.value }))
                      }
                    />
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="btn-primary text-xs"
                      disabled={busy}
                      onClick={() => void saveMember()}
                    >
                      {busy ? "保存中…" : "保存"}
                    </button>
                    <button
                      type="button"
                      className="btn-ghost text-xs"
                      onClick={() => setMemberMode(null)}
                    >
                      取消
                    </button>
                  </div>
                </div>
              )}
              <ul className="space-y-2">
                {members.map((m) => (
                  <li
                    key={m.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-200 px-3 py-2 text-sm"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{m.display_name}</span>
                        {m.id === user?.id && (
                          <span className="text-[11px] text-slate-500">（我）</span>
                        )}
                        <span
                          className={`rounded px-2 py-0.5 text-[11px] ${
                            m.role === "admin"
                              ? "bg-sky-100 text-sky-800"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {tenantRoleLabel(m.role)}
                        </span>
                      </div>
                      <div className="text-xs text-slate-500">
                        {m.username ? `@${m.username} · ` : ""}
                        {m.email}
                      </div>
                    </div>
                    {isAdmin && tab === "members" && (
                      <div className="flex flex-wrap items-center gap-1">
                        {m.id !== user?.id ? (
                          <select
                            className="input w-auto py-1 text-xs"
                            value={m.role}
                            onChange={(e) =>
                              void setRole(m.id, e.target.value as TenantRole)
                            }
                          >
                            <option value="member">成员</option>
                            <option value="admin">管理员</option>
                          </select>
                        ) : null}
                        <button
                          type="button"
                          className="btn-ghost text-xs"
                          onClick={() => openEditMember(m)}
                        >
                          编辑
                        </button>
                        {m.id !== user?.id && (
                          <button
                            type="button"
                            className="btn-ghost text-xs text-red-600"
                            onClick={() => void deleteMember(m)}
                          >
                            删除
                          </button>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {tab === "sessions" && isAdmin && (
            <section>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-slate-500">
                  租户内全部登录会话（含已过期记录）。可单条吊销或按用户批量吊销。
                </p>
                <button
                  type="button"
                  className="btn-ghost text-xs"
                  onClick={() => void purgeExpiredSessions()}
                >
                  清理已过期
                </button>
              </div>
              <ul className="space-y-2">
                {sessions.map((s) => (
                  <li
                    key={s.id}
                    className="rounded border border-slate-200 px-3 py-2 text-sm"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="font-medium">{s.user_display_name}</div>
                        <div className="text-xs text-slate-500">
                          {s.user_username ? `@${s.user_username} · ` : ""}
                          {s.user_email}
                        </div>
                        <div className="mt-1 text-[11px] text-slate-500">
                          创建 {fmtTime(s.created_at)} · 过期 {fmtTime(s.expires_at)}
                          {s.is_expired && (
                            <span className="ml-1 text-amber-700">（已过期）</span>
                          )}
                        </div>
                        <code className="mt-1 block text-[10px] text-slate-400">{s.id}</code>
                      </div>
                      <div className="flex flex-col gap-1">
                        <button
                          type="button"
                          className="btn-ghost text-xs text-red-600"
                          onClick={() => void revokeSession(s.id)}
                        >
                          吊销
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
                {sessions.length === 0 && (
                  <li className="text-xs text-slate-500">暂无登录会话</li>
                )}
              </ul>
              {members.length > 0 && (
                <div className="mt-4 rounded border border-slate-200 bg-slate-50 p-3">
                  <div className="text-xs font-medium text-slate-700">按用户吊销</div>
                  <ul className="mt-2 space-y-1">
                    {members.map((m) => (
                      <li key={m.id} className="flex items-center justify-between text-xs">
                        <span>{m.display_name}</span>
                        <button
                          type="button"
                          className="btn-ghost text-red-600"
                          onClick={() => void revokeUserSessions(m.id, m.display_name)}
                        >
                          吊销全部会话
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}

          {tab === "conversations" && isAdmin && (
            <section>
              <p className="mb-2 text-xs text-slate-500">
                租户内全部聊天会话。可修改标题或删除会话（级联删除全部消息）。
              </p>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[600px] border-collapse text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="py-2 pr-2">类型</th>
                      <th className="py-2 pr-2">标题</th>
                      <th className="py-2 pr-2">目标 ID</th>
                      <th className="py-2 pr-2">消息数</th>
                      <th className="py-2 pr-2">最近活跃</th>
                      <th className="py-2">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {conversations.map((c) => (
                      <tr key={c.id} className="border-b border-slate-100">
                        <td className="py-2 pr-2">{c.kind === "group" ? "群聊" : "私聊"}</td>
                        <td className="max-w-[120px] py-2 pr-2">
                          {editingConvId === c.id ? (
                            <input
                              className="input py-0.5 text-xs"
                              value={convTitle}
                              onChange={(e) => setConvTitle(e.target.value)}
                            />
                          ) : (
                            <span className="text-slate-700">{c.title || "—"}</span>
                          )}
                        </td>
                        <td className="max-w-[100px] truncate py-2 pr-2 font-mono text-[10px]">
                          {c.target_id}
                        </td>
                        <td className="py-2 pr-2">{c.message_count}</td>
                        <td className="py-2 whitespace-nowrap">
                          {fmtTime(c.last_message_at ?? c.created_at)}
                        </td>
                        <td className="py-2 whitespace-nowrap">
                          {editingConvId === c.id ? (
                            <>
                              <button
                                type="button"
                                className="btn-ghost text-[10px]"
                                onClick={() => void saveConvTitle()}
                              >
                                保存
                              </button>
                              <button
                                type="button"
                                className="btn-ghost text-[10px]"
                                onClick={() => setEditingConvId(null)}
                              >
                                取消
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                type="button"
                                className="btn-ghost text-[10px]"
                                onClick={() => openEditConv(c)}
                              >
                                编辑
                              </button>
                              <button
                                type="button"
                                className="btn-ghost text-[10px] text-red-600"
                                onClick={() => void deleteConv(c)}
                              >
                                删除
                              </button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {conversations.length === 0 && (
                  <p className="py-4 text-xs text-slate-500">暂无聊天会话</p>
                )}
              </div>
            </section>
          )}

          {tab === "invites" && isAdmin && (
            <section className="space-y-4">
              <div className="space-y-2 rounded border border-slate-200 bg-slate-50 p-3">
                <div>
                  <label className="label">限定邮箱（可选）</label>
                  <input
                    className="input"
                    type="email"
                    placeholder="留空则任意邮箱可注册"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="label">注册后角色</label>
                    <select
                      className="input"
                      value={inviteRole}
                      onChange={(e) => setInviteRole(e.target.value as TenantRole)}
                    >
                      <option value="member">成员</option>
                      <option value="admin">管理员</option>
                    </select>
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
                </div>
                <button
                  type="button"
                  className="btn-primary w-full text-sm"
                  disabled={busy}
                  onClick={() => void createInvite()}
                >
                  {busy ? "生成中…" : "生成邀请码"}
                </button>
              </div>
              <ul className="space-y-2">
                {invites.map((inv) => (
                  <li
                    key={inv.id}
                    className="rounded border border-slate-200 px-3 py-2 text-sm"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <code className="text-xs">{inv.code}</code>
                      <span className="text-xs text-slate-500">
                        {tenantRoleLabel(inv.role)} · {inv.used_at ? "已使用" : "有效"}
                      </span>
                    </div>
                    {inv.invited_email && (
                      <div className="text-xs text-slate-500">限定：{inv.invited_email}</div>
                    )}
                    <p className="mt-1 break-all font-mono text-[11px] text-slate-600">
                      {registerUrl(inv.code)}
                    </p>
                    {!inv.used_at && (
                      <>
                        {editingInviteId === inv.id ? (
                          <div className="mt-2 space-y-2 rounded border border-slate-200 bg-white p-2">
                            <input
                              className="input text-xs"
                              placeholder="限定邮箱（留空不限）"
                              value={inviteEdit.invited_email}
                              onChange={(e) =>
                                setInviteEdit((x) => ({
                                  ...x,
                                  invited_email: e.target.value,
                                }))
                              }
                            />
                            <div className="grid grid-cols-2 gap-2">
                              <select
                                className="input text-xs"
                                value={inviteEdit.role}
                                onChange={(e) =>
                                  setInviteEdit((x) => ({
                                    ...x,
                                    role: e.target.value as TenantRole,
                                  }))
                                }
                              >
                                <option value="member">成员</option>
                                <option value="admin">管理员</option>
                              </select>
                              <input
                                className="input text-xs"
                                type="number"
                                min={1}
                                value={inviteEdit.hours}
                                onChange={(e) =>
                                  setInviteEdit((x) => ({
                                    ...x,
                                    hours: Number(e.target.value),
                                  }))
                                }
                                title="重新计算有效期（小时）"
                              />
                            </div>
                            <div className="flex gap-2">
                              <button
                                type="button"
                                className="btn-primary text-xs"
                                onClick={() => void saveInviteEdit()}
                              >
                                保存
                              </button>
                              <button
                                type="button"
                                className="btn-ghost text-xs"
                                onClick={() => setEditingInviteId(null)}
                              >
                                取消
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="mt-2 flex flex-wrap gap-2">
                            <button
                              type="button"
                              className="btn-ghost text-xs"
                              onClick={() => void copyText(registerUrl(inv.code), inv.code)}
                            >
                              {copiedCode === inv.code ? "已复制链接" : "复制注册链接"}
                            </button>
                            <button
                              type="button"
                              className="btn-ghost text-xs"
                              onClick={() => openEditInvite(inv)}
                            >
                              编辑
                            </button>
                            <button
                              type="button"
                              className="btn-ghost text-xs text-red-600"
                              onClick={() => void removeInvite(inv.id)}
                            >
                              删除
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {msg && (
            <p
              className={`mt-3 text-sm ${msg.includes("已") ? "text-green-700" : "text-red-600"}`}
            >
              {msg}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
