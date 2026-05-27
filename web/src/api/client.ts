import type {
  AssistantMemory,
  AssistantReflection,
  AssistantSkill,
  Conversation,
  Friend,
  GroupBundle,
  GroupMemberConfig,
  GroupSettings,
  Message,
  Provider,
  ProviderKey,
} from "../types";

const base = "/api";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => jsonFetch<{ ok: boolean }>("/health"),
  listFriends: () => jsonFetch<{ friends: Friend[] }>("/friends"),
  getFriend: (id: string) => jsonFetch<{ friend: Friend }>(`/friends/${id}`),
  upsertFriend: (body: Partial<Friend> & Record<string, any>) =>
    jsonFetch<{ friend: Friend }>("/friends", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteFriend: (id: string) =>
    jsonFetch<{ ok: boolean }>(`/friends/${id}`, { method: "DELETE" }),
  listProviders: () => jsonFetch<{ providers: Provider[] }>("/providers"),
  upsertProvider: (body: {
    id: string;
    kind: string;
    display_name: string;
    base_url: string;
    default_model?: string | null;
    capabilities?: Partial<Provider["capabilities"]>;
    price?: Partial<Provider["price"]>;
    enabled?: boolean;
  }) =>
    jsonFetch<{ provider: Provider }>("/providers", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteProvider: (id: string) =>
    jsonFetch<{ ok: boolean }>(`/providers/${id}`, { method: "DELETE" }),
  listProviderKeys: (providerId?: string) =>
    jsonFetch<{ provider_keys: ProviderKey[] }>(
      `/provider_keys${providerId ? `?provider_id=${encodeURIComponent(providerId)}` : ""}`,
    ),
  upsertProviderKey: (body: {
    id?: string;
    provider_id: string;
    label: string;
    /** 新建必填；更新可省略或空字符串表示不修改密钥 */
    secret?: string;
    rpm_limit?: number | null;
    tpm_limit?: number | null;
    monthly_budget_usd?: number | null;
  }) =>
    jsonFetch<{ provider_key: ProviderKey }>("/provider_keys", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteProviderKey: (id: string) =>
    jsonFetch<{ ok: boolean }>(`/provider_keys/${id}`, { method: "DELETE" }),
  openDm: (friendId: string) =>
    jsonFetch<{ conversation: Conversation; messages: Message[] }>(
      `/conversations/dm/${friendId}`,
    ),
  sendDm: (friendId: string, content: string) =>
    jsonFetch<{ ok: boolean; conversation_id: string }>(
      `/conversations/dm/${friendId}`,
      {
        method: "POST",
        body: JSON.stringify({ content }),
      },
    ),
  listConversationMessages: (id: string) =>
    jsonFetch<{ messages: Message[] }>(`/conversations/${id}/messages`),
  sendToConversation: (id: string, content: string) =>
    jsonFetch<{ ok: boolean }>(`/conversations/${id}/send`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  listGroups: () => jsonFetch<{ groups: GroupBundle[] }>("/groups"),
  getGroup: (id: string) =>
    jsonFetch<{
      group: GroupBundle["group"];
      member_ids: string[];
      members: GroupMemberConfig[];
      conversation_id: string;
      task_flow_readiness?: GroupBundle["task_flow_readiness"];
    }>(`/groups/${id}`),
  upsertGroup: (body: {
    id?: string;
    name: string;
    avatar?: string | null;
    settings: GroupSettings;
    members: GroupMemberConfig[];
    member_ids?: string[];
  }) =>
    jsonFetch<{
      group: GroupBundle["group"];
      member_ids: string[];
      conversation_id: string;
    }>("/groups", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listAssistantMemories: (friendId: string) =>
    jsonFetch<{ memories: AssistantMemory[] }>(
      `/assistant/${friendId}/memories`,
    ),
  addAssistantMemory: (
    friendId: string,
    body: {
      kind: string;
      content: string;
      weight: number;
      pinned?: boolean;
    },
  ) =>
    jsonFetch<{ memory: AssistantMemory }>(
      `/assistant/${friendId}/memories`,
      {
        method: "POST",
        body: JSON.stringify({
          owner_friend_id: friendId,
          source_message_id: null,
          ...body,
        }),
      },
    ),
  deleteAssistantMemory: (friendId: string, memoryId: string) =>
    jsonFetch<{ ok: boolean }>(
      `/assistant/${friendId}/memories/${memoryId}`,
      { method: "DELETE" },
    ),
  listAssistantSkills: (friendId: string) =>
    jsonFetch<{ skills: AssistantSkill[] }>(`/assistant/${friendId}/skills`),
  listAssistantReflections: (friendId: string) =>
    jsonFetch<{ reflections: AssistantReflection[] }>(
      `/assistant/${friendId}/reflections`,
    ),
  listInvites: (friendId?: string) =>
    jsonFetch<{ invites: any[] }>(
      `/invites${friendId ? `?friend_id=${encodeURIComponent(friendId)}` : ""}`,
    ),
  createInvite: (body: { friend_id: string; expires_in_hours?: number }) =>
    jsonFetch<{ invite: any }>("/invites", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteInvite: (id: string) =>
    jsonFetch<{ ok: boolean }>(`/invites/${id}`, { method: "DELETE" }),
  humanState: (code: string) =>
    jsonFetch<{ friend: Friend; session: any; messages: Message[] }>(
      `/human/${code}/state`,
    ),
  humanSend: (code: string, content: string, conversation_id?: string) =>
    jsonFetch<{ ok: boolean; conversation_id: string }>(
      `/human/${code}/send`,
      {
        method: "POST",
        body: JSON.stringify({ content, conversation_id }),
      },
    ),
  humanTyping: (code: string, duration_ms = 3000) =>
    jsonFetch<{ ok: boolean }>(`/human/${code}/typing`, {
      method: "POST",
      body: JSON.stringify({ duration_ms }),
    }),
};

export function connectWs(onEvent: (ev: any) => void): WebSocket {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/ws`);
  ws.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch {}
  };
  return ws;
}
