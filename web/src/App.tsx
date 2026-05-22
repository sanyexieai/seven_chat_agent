import { useEffect, useMemo, useState } from "react";
import { AssistantPanel } from "./components/AssistantPanel";
import { ChatWindow } from "./components/ChatWindow";
import { FriendEditor } from "./components/FriendEditor";
import { GroupEditor } from "./components/GroupEditor";
import { HumanInvitePanel } from "./components/HumanInvitePanel";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { Sidebar } from "./components/Sidebar";
import { useChat } from "./stores/chat";

export default function App() {
  const { ready, init, friends } = useChat();
  const [editingFriend, setEditingFriend] = useState<
    string | null | undefined
  >(undefined);
  const [editingGroup, setEditingGroup] = useState<string | null | undefined>(
    undefined,
  );
  const [assistantFriendId, setAssistantFriendId] = useState<string | null>(
    null,
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [invitesOpen, setInvitesOpen] = useState(false);
  const humanFriends = useMemo(
    () => friends.filter((f) => f.backend_kind === "human"),
    [friends],
  );

  useEffect(() => {
    init().catch((e) => console.error(e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center text-slate-400">
        正在连接 honeycomb...
      </div>
    );
  }
  return (
    <div className="flex h-full">
      <Sidebar
        onCreateFriend={() => setEditingFriend(null)}
        onEditFriend={(id) => setEditingFriend(id)}
        onCreateGroup={() => setEditingGroup(null)}
        onEditGroup={(id) => setEditingGroup(id)}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenAssistant={(id) => setAssistantFriendId(id)}
        onOpenInvites={() => setInvitesOpen(true)}
      />
      <ChatWindow />
      {editingFriend !== undefined && (
        <FriendEditor
          friendId={editingFriend ?? null}
          onClose={() => setEditingFriend(undefined)}
        />
      )}
      {editingGroup !== undefined && (
        <GroupEditor
          groupId={editingGroup ?? null}
          onClose={() => setEditingGroup(undefined)}
        />
      )}
      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
      {assistantFriendId && (
        <AssistantPanel
          friendId={assistantFriendId}
          onClose={() => setAssistantFriendId(null)}
        />
      )}
      <HumanInvitePanel
        open={invitesOpen}
        onClose={() => setInvitesOpen(false)}
        humanFriends={humanFriends}
      />
    </div>
  );
}
