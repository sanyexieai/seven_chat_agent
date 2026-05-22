import { isWorkerBeeFriend } from "../friendKind";
import { useChat } from "../stores/chat";
import { Avatar } from "./Avatar";

interface Props {
  onCreateFriend: () => void;
  onEditFriend: (id: string) => void;
  onCreateGroup: () => void;
  onEditGroup: (id: string) => void;
  onOpenSettings: () => void;
  onOpenAssistant: (id: string) => void;
  onOpenInvites: () => void;
}

export function Sidebar({
  onCreateFriend,
  onEditFriend,
  onCreateGroup,
  onEditGroup,
  onOpenSettings,
  onOpenAssistant,
  onOpenInvites,
}: Props) {
  const { friends, groups, target, selectFriend, selectGroup } = useChat();
  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-slate-200 bg-slate-50">
      <header className="flex items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
        <div>
          <div className="text-base font-semibold text-slate-800">honeycomb</div>
          <div className="text-xs text-slate-500">多 Agent 聊天室</div>
        </div>
        <div className="flex gap-1">
          <button
            className="btn-ghost"
            onClick={onOpenInvites}
            title="真人好友邀请"
          >
            邀请
          </button>
          <button
            className="btn-ghost"
            onClick={onOpenSettings}
            title="设置 / Provider Keys"
          >
            设置
          </button>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto">
        <section>
          <div className="flex items-center justify-between px-4 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <span>好友 · {friends.length}</span>
            <button
              className="rounded-md bg-honey-100 px-2 py-0.5 text-[11px] text-honey-800 hover:bg-honey-200"
              onClick={onCreateFriend}
            >
              ＋
            </button>
          </div>
          {friends.length === 0 && (
            <div className="px-4 py-3 text-xs text-slate-500">
              还没有好友。点 ＋ 添加。
            </div>
          )}
          <ul>
            {friends.map((f) => (
              <li
                key={f.id}
                className={`group flex cursor-pointer items-center gap-3 border-b border-slate-100 px-4 py-2.5 hover:bg-white ${
                  target?.kind === "friend" && target.id === f.id
                    ? "bg-white"
                    : ""
                }`}
                onClick={() => selectFriend(f.id)}
              >
                <Avatar name={f.name} kind={f.backend_kind} size={36} />
                <div className="flex-1 overflow-hidden">
                  <div className="flex items-center justify-between gap-2">
                    <div className="truncate text-sm font-medium text-slate-800">
                      {f.name}
                      {f.is_builtin && (
                        <span className="ml-1 rounded-sm bg-honey-100 px-1 py-0.5 text-[10px] font-medium text-honey-800">
                          内置
                        </span>
                      )}
                    </div>
                    <div className="flex gap-1">
                      {isWorkerBeeFriend(f) && (
                        <button
                          className="btn-ghost px-1 py-0.5 text-[11px] text-honey-700 opacity-0 group-hover:opacity-100"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenAssistant(f.id);
                          }}
                          title="记忆 / 技能 / 反思"
                        >
                          面板
                        </button>
                      )}
                      <button
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
                  <div className="truncate text-xs text-slate-500">
                    {f.personality || backendLabel(f.backend_kind)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <div className="flex items-center justify-between px-4 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <span>群聊 · {groups.length}</span>
            <button
              className="rounded-md bg-honey-100 px-2 py-0.5 text-[11px] text-honey-800 hover:bg-honey-200"
              onClick={onCreateGroup}
            >
              ＋
            </button>
          </div>
          {groups.length === 0 && (
            <div className="px-4 py-3 text-xs text-slate-500">
              还没有群聊。点 ＋ 拉人组群。
            </div>
          )}
          <ul>
            {groups.map((gb) => (
              <li
                key={gb.group.id}
                className={`group flex cursor-pointer items-center gap-3 border-b border-slate-100 px-4 py-2.5 hover:bg-white ${
                  target?.kind === "group" && target.id === gb.group.id
                    ? "bg-white"
                    : ""
                }`}
                onClick={() => selectGroup(gb.group.id)}
              >
                <Avatar name={gb.group.name} size={36} />
                <div className="flex-1 overflow-hidden">
                  <div className="flex items-center justify-between gap-2">
                    <div className="truncate text-sm font-medium text-slate-800">
                      {gb.group.name}
                    </div>
                    <button
                      className="btn-ghost px-1 py-0.5 text-[11px] text-slate-400 opacity-0 group-hover:opacity-100"
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
