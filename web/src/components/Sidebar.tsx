import { useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { api } from "../api/client";
import { isWorkerBeeFriend } from "../friendKind";
import type { Friend } from "../types";
import { useChat } from "../stores/chat";
import { Avatar } from "./Avatar";

interface Props {
  onCreateFriend: () => void;
  onEditFriend: (id: string) => void;
  onCreateGroup: () => void;
  onEditGroup: (id: string) => void;
  onOpenAssistant: (id: string) => void;
}

export function Sidebar({
  onCreateFriend,
  onEditFriend,
  onCreateGroup,
  onEditGroup,
  onOpenAssistant,
}: Props) {
  const { friends, groups, target, selectFriend, selectGroup } = useChat(
    useShallow((s) => ({
      friends: s.friends,
      groups: s.groups,
      target: s.target,
      selectFriend: s.selectFriend,
      selectGroup: s.selectGroup,
    })),
  );
  const [onlineByFriend, setOnlineByFriend] = useState<Record<string, boolean>>({});
  const [onlineDetailByFriend, setOnlineDetailByFriend] = useState<Record<string, string>>({});
  const externalCliFriends = useMemo(() => friends.filter(isExternalCliFriend), [friends]);

  useEffect(() => {
    let cancelled = false;

    async function refreshOnline() {
      if (document.hidden) return;
      if (externalCliFriends.length === 0) {
        if (!cancelled) {
          setOnlineByFriend({});
          setOnlineDetailByFriend({});
        }
        return;
      }
      let relayOnline = new Set<string>();
      const hasRelayFriend = externalCliFriends.some(
        (f) => f.backend_config?.execution_mode === "relay",
      );
      if (hasRelayFriend) {
        try {
          const { relays } = await api.listCliRelays();
          relayOnline = new Set(relays.filter((r) => r.online).map((r) => r.relay_id));
        } catch {
          relayOnline = new Set();
        }
      }
      const rows = await Promise.all(
        externalCliFriends.map(async (f) => {
          try {
            const { cli_auth } = await api.getFriendCliAuth(f.id);
            const authOk = !!cli_auth?.authenticated;
            const relayMode = f.backend_config?.execution_mode === "relay";
            const relayId = String(f.backend_config?.relay_id || "");
            const relayOk = !relayMode || (!!relayId && relayOnline.has(relayId));
            return {
              id: f.id,
              online: authOk && relayOk,
              detail: relayMode
                ? authOk
                  ? relayOk
                    ? "在线（已登录 + 转发在线）"
                    : "离线（转发未在线）"
                  : "离线（CLI 未登录）"
                : authOk
                  ? "在线（CLI 已登录）"
                  : "离线（CLI 未登录）",
            };
          } catch {
            return { id: f.id, online: false, detail: "离线（状态检测失败）" };
          }
        }),
      );
      if (cancelled) return;
      const m1: Record<string, boolean> = {};
      const m2: Record<string, string> = {};
      for (const r of rows) {
        m1[r.id] = r.online;
        m2[r.id] = r.detail;
      }
      setOnlineByFriend(m1);
      setOnlineDetailByFriend(m2);
    }

    void refreshOnline();
    const t = window.setInterval(refreshOnline, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [externalCliFriends]);

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-slate-200 bg-slate-50">
      <div className="flex-1 overflow-y-auto">
        <section>
          <div className="flex items-center justify-between px-3 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <span>好友 · {friends.length}</span>
            <button
              type="button"
              className="rounded-md bg-honey-100 px-2 py-0.5 text-[11px] text-honey-800 hover:bg-honey-200"
              onClick={onCreateFriend}
              title="添加好友"
            >
              ＋
            </button>
          </div>
          {friends.length === 0 && (
            <div className="px-3 py-3 text-xs text-slate-500">
              还没有好友。点 ＋ 添加。
            </div>
          )}
          <ul>
            {friends.map((f) => (
              <li
                key={f.id}
                className={`group flex cursor-pointer items-center gap-3 border-b border-slate-100 px-3 py-2.5 hover:bg-white ${
                  target?.kind === "friend" && target.id === f.id
                    ? "bg-white"
                    : ""
                }`}
                onClick={() => selectFriend(f.id)}
              >
                <Avatar name={f.name} kind={f.backend_kind} size={36} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="truncate text-sm font-medium text-slate-800">
                      {f.name}
                      {f.is_builtin && (
                        <span className="ml-1 rounded-sm bg-honey-100 px-1 py-0.5 text-[10px] font-medium text-honey-800">
                          内置
                        </span>
                      )}
                    </div>
                    <div className="flex shrink-0 gap-1">
                      {isWorkerBeeFriend(f) && (
                        <button
                          type="button"
                          className="btn-ghost px-1 py-0.5 text-[11px] text-honey-700 opacity-0 group-hover:opacity-100"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenAssistant(f.id);
                          }}
                          title="全站记忆 / 技能 / 策略"
                        >
                          面板
                        </button>
                      )}
                      <button
                        type="button"
                        className="btn-ghost px-1 py-0.5 text-[11px] text-slate-400 opacity-0 group-hover:opacity-100"
                        onClick={(e) => {
                          e.stopPropagation();
                          onEditFriend(f.id);
                        }}
                      >
                        编辑
                      </button>
                    </div>
                  </div>
                  {isExternalCliFriend(f) ? (
                    <div
                      className={`flex items-center gap-1 text-xs ${
                        onlineByFriend[f.id] ? "text-emerald-700" : "text-slate-500"
                      }`}
                      title={onlineDetailByFriend[f.id] || "状态检测中"}
                    >
                      <span
                        className={`inline-block h-1.5 w-1.5 rounded-full ${
                          onlineByFriend[f.id] ? "bg-emerald-500" : "bg-slate-300"
                        }`}
                      />
                      <span className="truncate">
                        {onlineDetailByFriend[f.id] || "状态检测中…"}
                      </span>
                    </div>
                  ) : (
                    <div className="truncate text-xs text-slate-500">
                      {f.personality || backendLabel(f.backend_kind)}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <div className="flex items-center justify-between px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <span>群聊 · {groups.length}</span>
            <button
              type="button"
              className="rounded-md bg-honey-100 px-2 py-0.5 text-[11px] text-honey-800 hover:bg-honey-200"
              onClick={onCreateGroup}
              title="创建群聊"
            >
              ＋
            </button>
          </div>
          {groups.length === 0 && (
            <div className="px-3 py-3 text-xs text-slate-500">
              还没有群聊。点 ＋ 拉人组群。
            </div>
          )}
          <ul>
            {groups.map((gb) => (
              <li
                key={gb.group.id}
                className={`group flex cursor-pointer items-center gap-3 border-b border-slate-100 px-3 py-2.5 hover:bg-white ${
                  target?.kind === "group" && target.id === gb.group.id
                    ? "bg-white"
                    : ""
                }`}
                onClick={() => selectGroup(gb.group.id)}
              >
                <Avatar name={gb.group.name} size={36} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="truncate text-sm font-medium text-slate-800">
                      {gb.group.name}
                    </div>
                    <button
                      type="button"
                      className="btn-ghost shrink-0 px-1 py-0.5 text-[11px] text-slate-400 opacity-0 group-hover:opacity-100"
                      onClick={(e) => {
                        e.stopPropagation();
                        onEditGroup(gb.group.id);
                      }}
                    >
                      设置
                    </button>
                  </div>
                  <div className="truncate text-xs text-slate-500">
                    {gb.member_ids.length} 位成员
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </aside>
  );
}

function isExternalCliFriend(f: Friend): boolean {
  if (f.backend_kind !== "pty") return false;
  const preset = String(f.backend_config?.preset || "");
  return preset === "codex-exec" || preset === "claude" || preset === "cursor";
}

function backendLabel(kind: string) {
  switch (kind) {
    case "pty":
      return "CLI 后端";
    case "api":
      return "API 后端";
    case "assistant":
      return "工蜂 Agent";
    case "human":
      return "真人好友";
    default:
      return kind;
  }
}
