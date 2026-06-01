import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { CliSession, Workspace } from "../types";

interface Props {
  friendId: string;
}

export function FriendWorkspacesSection({ friendId }: Props) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sessionsByWs, setSessionsByWs] = useState<Record<string, CliSession[]>>({});
  const [expandedWs, setExpandedWs] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  const reload = useCallback(async () => {
    const res = await api.listFriendWorkspaces(friendId);
    setWorkspaces(res.workspaces);
    setActiveId(res.active_workspace_id ?? null);
  }, [friendId]);

  useEffect(() => {
    reload().catch((e) => setError(e.message || String(e)));
  }, [reload]);

  async function loadSessions(wsId: string) {
    const res = await api.listWorkspaceCliSessions(friendId, wsId);
    setSessionsByWs((prev) => ({ ...prev, [wsId]: res.cli_sessions }));
  }

  async function toggleExpand(ws: Workspace) {
    if (expandedWs === ws.id) {
      setExpandedWs(null);
      return;
    }
    setExpandedWs(ws.id);
    if (!sessionsByWs[ws.id]) {
      try {
        await loadSessions(ws.id);
      } catch (e: any) {
        setError(e.message || String(e));
      }
    }
  }

  async function activate(wsId: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await api.activateFriendWorkspace(friendId, wsId);
      setActiveId(res.active_workspace_id ?? wsId);
      await reload();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function activateSession(wsId: string, sessionId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.activateWorkspaceCliSession(friendId, wsId, sessionId);
      await loadSessions(wsId);
      setMsg("已切换 CLI 续聊会话");
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function importCli(
    wsId: string,
    tool: "codex" | "claude" | "cursor",
  ) {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const res =
        tool === "codex"
          ? await api.importWorkspaceCodexSessions(friendId, wsId, {
              ingest_memories: true,
            })
          : tool === "claude"
            ? await api.importWorkspaceClaudeSessions(friendId, wsId, {
                ingest_memories: true,
              })
            : await api.importWorkspaceCursorSessions(friendId, wsId, {
                ingest_memories: true,
              });
      setSessionsByWs((prev) => ({ ...prev, [wsId]: res.cli_sessions }));
      setExpandedWs(wsId);
      const label =
        tool === "codex" ? "Codex" : tool === "claude" ? "Claude" : "Cursor";
      setMsg(
        `${label}：扫描 ${res.report.scanned}，匹配 ${res.report.matched}，导入 ${res.report.imported} 会话，记忆 ${res.report.memories_created} 条`,
      );
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function addWorkspace() {
    const name = newName.trim() || `工作区 ${workspaces.length + 1}`;
    setBusy(true);
    setError(null);
    try {
      await api.createFriendWorkspace(friendId, { name });
      setNewName("");
      await reload();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(ws: Workspace) {
    if (ws.is_default) return;
    if (!confirm(`删除工作区「${ws.name}」？目录文件不会自动删除。`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteFriendWorkspace(friendId, ws.id);
      await reload();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3">
      <div className="mb-2 flex items-center justify-between">
        <label className="label mb-0">工作区（多项目）</label>
        <span className="text-xs text-slate-500">{workspaces.length} 个</span>
      </div>
      <p className="mb-2 text-xs text-slate-500">
        可从本机 Codex（~/.codex/sessions）、Claude（~/.claude/projects）、Cursor（~/.cursor/projects/…/agent-transcripts）按工作区目录匹配导入续聊会话。
      </p>
      {error && <p className="mb-2 text-xs text-red-600">{error}</p>}
      {msg && <p className="mb-2 text-xs text-emerald-700">{msg}</p>}
      <ul className="mb-2 max-h-56 space-y-1 overflow-y-auto">
        {workspaces.map((ws) => {
          const sessions = sessionsByWs[ws.id] ?? [];
          const open = expandedWs === ws.id;
          return (
            <li
              key={ws.id}
              className={`rounded border px-2 py-1.5 text-xs ${
                ws.id === activeId
                  ? "border-emerald-400 bg-emerald-50"
                  : "border-slate-200 bg-white"
              }`}
            >
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-slate-800">
                    {ws.name}
                    {ws.is_default && (
                      <span className="ml-1 text-slate-400">（默认）</span>
                    )}
                  </div>
                  <div
                    className="truncate font-mono text-[10px] text-slate-500"
                    title={ws.path}
                  >
                    {ws.path}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap justify-end gap-1">
                  <button
                    type="button"
                    className="btn-ghost px-1.5 py-0.5 text-[10px]"
                    disabled={busy}
                    onClick={() => toggleExpand(ws)}
                  >
                    {open ? "收起" : "会话"}
                  </button>
                  {ws.id !== activeId && (
                    <button
                      type="button"
                      className="btn-ghost px-1.5 py-0.5 text-[10px]"
                      disabled={busy}
                      onClick={() => activate(ws.id)}
                    >
                      选用
                    </button>
                  )}
                  {!ws.is_default && (
                    <button
                      type="button"
                      className="btn-ghost px-1.5 py-0.5 text-[10px] text-red-600"
                      disabled={busy}
                      onClick={() => remove(ws)}
                    >
                      删
                    </button>
                  )}
                </div>
              </div>
              {open && (
                <div className="mt-2 border-t border-slate-200 pt-2">
                  <div className="mb-1 flex flex-wrap gap-1">
                    <button
                      type="button"
                      className="btn-secondary px-2 py-0.5 text-[10px]"
                      disabled={busy}
                      onClick={() => importCli(ws.id, "codex")}
                    >
                      Codex
                    </button>
                    <button
                      type="button"
                      className="btn-secondary px-2 py-0.5 text-[10px]"
                      disabled={busy}
                      onClick={() => importCli(ws.id, "claude")}
                    >
                      Claude
                    </button>
                    <button
                      type="button"
                      className="btn-secondary px-2 py-0.5 text-[10px]"
                      disabled={busy}
                      onClick={() => importCli(ws.id, "cursor")}
                    >
                      Cursor
                    </button>
                  </div>
                  {sessions.length === 0 ? (
                    <p className="text-[10px] text-slate-400">暂无 CLI 会话记录</p>
                  ) : (
                    <ul className="space-y-1">
                      {sessions.map((s) => (
                        <li
                          key={s.id}
                          className={`rounded px-1.5 py-1 ${
                            s.is_active ? "bg-emerald-100/80" : "bg-slate-50"
                          }`}
                        >
                          <div className="font-medium text-slate-700">
                            <span className="text-slate-400">{s.tool} · </span>
                            {s.label || s.native_session_id?.slice(0, 8) || "会话"}
                            {s.is_active && (
                              <span className="ml-1 text-emerald-600">· 当前</span>
                            )}
                          </div>
                          {s.native_session_id && (
                            <div className="truncate font-mono text-[10px] text-slate-500">
                              {s.native_session_id}
                            </div>
                          )}
                          {!s.is_active && s.native_session_id && (
                            <button
                              type="button"
                              className="btn-ghost mt-0.5 px-1 py-0 text-[10px]"
                              disabled={busy}
                              onClick={() => activateSession(ws.id, s.id)}
                            >
                              续聊此会话
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <div className="flex gap-2">
        <input
          className="input flex-1 text-xs"
          placeholder="新工作区名称"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button
          type="button"
          className="btn-secondary text-xs"
          disabled={busy}
          onClick={addWorkspace}
        >
          添加
        </button>
      </div>
    </div>
  );
}
