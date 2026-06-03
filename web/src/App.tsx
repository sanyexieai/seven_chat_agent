import { useEffect, useMemo, useState } from "react";
import { AssistantPanel } from "./components/AssistantPanel";
import { AppTopBar } from "./components/AppTopBar";
import { AuthPage } from "./components/AuthPage";
import { ChatWindow } from "./components/ChatWindow";
import { FriendEditor } from "./components/FriendEditor";
import { GroupEditor } from "./components/GroupEditor";
import { HumanInvitePanel } from "./components/HumanInvitePanel";
import { AdminManagementPanel } from "./components/AdminManagementPanel";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { Sidebar } from "./components/Sidebar";
import { useAuth } from "./stores/auth";
import { useChat } from "./stores/chat";

function openAssistantChat(
  assistantId: string,
  prompt: string,
  closePanel: () => void,
) {
  closePanel();
  void (async () => {
    const { selectFriend, sendMessage } = useChat.getState();
    await selectFriend(assistantId);
    await sendMessage(prompt);
  })();
}

export default function App() {
  const { ready: authReady, token, init: initAuth } = useAuth();
  const { ready: chatReady, init: initChat } = useChat();
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
  const [teamOpen, setTeamOpen] = useState(false);
  const { friends } = useChat();
  const humanFriends = useMemo(
    () => friends.filter((f) => f.backend_kind === "human"),
    [friends],
  );

  const canLoadChat = authReady && !!token;

  useEffect(() => {
    void initAuth().catch((e) => console.error(e));
  }, [initAuth]);

  useEffect(() => {
    if (!canLoadChat) return;
    void initChat().catch((e) => console.error(e));
  }, [canLoadChat, initChat, token]);

  if (!authReady) {
    return (
      <div className="flex h-full items-center justify-center text-slate-400">
        正在连接...
      </div>
    );
  }

  if (!token) {
    return <AuthPage />;
  }

  if (!canLoadChat) {
    return (
      <div className="flex h-full items-center justify-center text-slate-400">
        正在连接...
      </div>
    );
  }

  if (!chatReady) {
    return (
      <div className="flex h-full flex-col">
        <AppTopBar
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenInvites={() => setInvitesOpen(true)}
          onOpenTeam={() => setTeamOpen(true)}
          onOpenAuth={() => {}}
        />
        <div className="flex flex-1 items-center justify-center text-slate-400">
          正在加载会话...
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <AppTopBar
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenInvites={() => setInvitesOpen(true)}
        onOpenTeam={() => setTeamOpen(true)}
        onOpenAuth={() => {}}
      />
      <div className="flex min-h-0 flex-1">
        <Sidebar
          onCreateFriend={() => setEditingFriend(null)}
          onEditFriend={(id) => setEditingFriend(id)}
          onCreateGroup={() => setEditingGroup(null)}
          onEditGroup={(id) => setEditingGroup(id)}
          onOpenAssistant={(id) => setAssistantFriendId(id)}
        />
        <ChatWindow />
      </div>
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
        onOpenAdmin={() => setTeamOpen(true)}
      />
      {assistantFriendId && (
        <AssistantPanel
          friendId={assistantFriendId}
          onClose={() => setAssistantFriendId(null)}
          onAssistChat={(prompt) => {
            const id = assistantFriendId;
            openAssistantChat(id, prompt, () => setAssistantFriendId(null));
          }}
        />
      )}
      <HumanInvitePanel
        open={invitesOpen}
        onClose={() => setInvitesOpen(false)}
        humanFriends={humanFriends}
      />
      <AdminManagementPanel open={teamOpen} onClose={() => setTeamOpen(false)} />
    </div>
  );
}
