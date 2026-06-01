import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useChat } from "../stores/chat";
import type { CliSession, Workspace } from "../types";

interface Props {
  friendId: string;
  /** 贴在输入框上方时，下拉向上展开 */
  placement?: "header" | "above-input";
}

function shortPath(path: string, max = 48) {
  const p = path.trim();
  if (p.length <= max) return p;
  const head = Math.floor(max * 0.35);
  const tail = max - head - 1;
  return `${p.slice(0, head)}…${p.slice(-tail)}`;
}

/** 私聊：Codex 风格工作区条（当前目录 + 下拉切换） */
export function ChatWorkspaceSwitcher({
  friendId,
  placement = "above-input",
}: Props) {
  const { reloadFriends } = useChat();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [sessions, setSessions] = useState<CliSession[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const reload = useCallback(async () => {
    const res = await api.listFriendWorkspaces(friendId);
    setWorkspaces(res.workspaces);
    const aid = res.active_workspace_id ?? res.workspaces[0]?.id ?? "";
    setActiveId(aid);
    if (aid) {
      try {
        const s = await api.listWorkspaceCliSessions(friendId, aid);
        setSessions(s.cli_sessions);
      } catch {
        setSessions([]);
      }
    } else {
      setSessions([]);
    }
  }, [friendId]);

  useEffect(() => {
    reload().catch(() => {});
  }, [reload]);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const active = workspaces.find((w) => w.id === activeId);
  const activeSession = sessions.find((s) => s.is_active);

  async function pickWorkspace(wsId: string) {
    if (!wsId || wsId === activeId) {
      setOpen(false);
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await api.activateFriendWorkspace(friendId, wsId);
      setActiveId(wsId);
      await reloadFriends();
      await reload();
      setMsg("已切换工作区，后续 CLI 与记忆按新目录执行");
      setOpen(false);
      window.setTimeout(() => setMsg(null), 3200);
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function pickSession(sessionId: string) {
    if (!activeId || busy) return;
    setBusy(true);
    setMsg(null);
    try {
      await api.activateWorkspaceCliSession(friendId, activeId, sessionId);
      await reload();
      setMsg("已切换 CLI 续聊会话");
      window.setTimeout(() => setMsg(null), 2800);
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (workspaces.length === 0) return null;

  const dropUp = placement === "above-input";

  return (
    <div
      ref={rootRef}
      className={`relative shrink-0 border-amber-200/80 bg-gradient-to-r from-amber-50/90 to-white px-4 py-2 ${
        dropUp ? "border-t" : "border-b"
      }`}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className="shrink-0 font-medium text-amber-900/90">工作区</span>
        <button
          type="button"
          disabled={busy}
          onClick={() => setOpen((v) => !v)}
          className="flex min-w-0 max-w-full flex-1 items-center gap-2 rounded-md border border-amber-200/60 bg-white px-2.5 py-1.5 text-left shadow-sm transition hover:border-amber-300 hover:bg-amber-50/50 disabled:opacity-60"
          title={active?.path ?? "选择工作区"}
        >
          <span className="shrink-0 font-semibold text-slate-800">
            {active?.name ?? "未选择"}
            {active?.is_default ? (
              <span className="ml-1 font-normal text-slate-400">默认</span>
            ) : null}
          </span>
          {active?.path ? (
            <span
              className="min-w-0 flex-1 truncate font-mono text-[11px] text-slate-500"
              title={active.path}
            >
              {shortPath(active.path, 56)}
            </span>
          ) : null}
          <span className="shrink-0 text-slate-400" aria-hidden>
            {open ? "▴" : "▾"}
          </span>
        </button>
        {activeSession?.native_session_id && (
          <span
            className="hidden truncate font-mono text-[10px] text-slate-400 sm:inline"
            title={activeSession.native_session_id}
          >
            {activeSession.tool} · {activeSession.native_session_id.slice(0, 12)}…
          </span>
        )}
      </div>
      {msg && (
        <p className="mt-1.5 text-[11px] text-emerald-700">{msg}</p>
      )}
      {open && (
        <div
          className={`absolute left-4 right-4 z-40 max-h-[min(20rem,50vh)] overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg sm:right-auto sm:max-w-md ${
            dropUp ? "bottom-full mb-1" : "top-full mt-1"
          }`}
        >
          <p className="px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">
            切换工作区（类似 Codex -C）
          </p>
          {workspaces.map((ws) => (
            <button
              key={ws.id}
              type="button"
              disabled={busy}
              className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left text-xs hover:bg-slate-50 ${
                ws.id === activeId ? "bg-emerald-50/80" : ""
              }`}
              onClick={() => pickWorkspace(ws.id)}
            >
              <span className="flex items-center gap-2 font-medium text-slate-800">
                {ws.id === activeId && (
                  <span className="text-emerald-600">✓</span>
                )}
                {ws.name}
                {ws.is_default && (
                  <span className="font-normal text-slate-400">默认</span>
                )}
              </span>
              <span
                className="truncate font-mono text-[10px] text-slate-500"
                title={ws.path}
              >
                {ws.path}
              </span>
            </button>
          ))}
          {sessions.length > 1 && activeId && (
            <>
              <div className="my-1 border-t border-slate-100" />
              <p className="px-3 py-1 text-[10px] font-medium text-slate-400">
                续聊会话
              </p>
              {sessions.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  disabled={busy || s.is_active}
                  className={`w-full px-3 py-1.5 text-left text-[11px] hover:bg-slate-50 ${
                    s.is_active ? "text-emerald-700" : "text-slate-600"
                  }`}
                  onClick={() => pickSession(s.id)}
                >
                  <span className="text-slate-400">{s.tool} · </span>
                  {s.label || s.native_session_id?.slice(0, 20) || s.id.slice(0, 8)}
                  {s.is_active ? " · 当前" : ""}
                </button>
              ))}
            </>
          )}
          <p className="border-t border-slate-100 px-3 py-2 text-[10px] leading-relaxed text-slate-400">
            更多工作区请在好友编辑里添加；Codex/Claude 历史可在那里导入。
          </p>
        </div>
      )}
    </div>
  );
}
