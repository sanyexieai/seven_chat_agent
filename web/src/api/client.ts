export interface CliAuthStatus {
  preset: string;
  authenticated: boolean;
  detail: string;
  api_key_configured: boolean;
  oauth_pending: boolean;
  oauth_phase: string;
  oauth_url?: string | null;
  oauth_user_code?: string | null;
  oauth_instructions?: string | null;
  oauth_message?: string | null;
}

export interface CliOAuthSnapshot {
  phase: string;
  auth_url?: string | null;
  user_code?: string | null;
  instructions: string;
  message: string;
}

import type {
  AssistantGlobalSettings,
  AssistantMemory,
  AssistantPolicyTemplate,
  AssistantReflection,
  AssistantQueueJob,
  AssistantQueueStats,
  AssistantSkill,
  AssistantTodo,
  Conversation,
  Friend,
  GroupBundle,
  GroupMemberConfig,
  GroupSettings,
  Message,
  Provider,
  ProviderKey,
} from "../types";

type WsApiResp = { id: string; ok: boolean; result?: any; error?: string };

let wsApi: WebSocket | null = null;
let wsApiReady: Promise<void> | null = null;
let wsReqSeq = 0;
const wsPending = new Map<
  string,
  { resolve: (v: any) => void; reject: (e: Error) => void }
>();

function wsApiUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws-api`;
}

async function ensureWsApi(): Promise<void> {
  if (wsApi && wsApi.readyState === WebSocket.OPEN) return;
  if (wsApiReady) return wsApiReady;
  wsApiReady = new Promise<void>((resolve, reject) => {
    const ws = new WebSocket(wsApiUrl());
    ws.onopen = () => {
      wsApi = ws;
      resolve();
    };
    ws.onmessage = (e) => {
      let msg: WsApiResp | null = null;
      try {
        msg = JSON.parse(e.data);
      } catch {
        return;
      }
      if (!msg?.id) return;
      const p = wsPending.get(msg.id);
      if (!p) return;
      wsPending.delete(msg.id);
      if (msg.ok) p.resolve(msg.result);
      else p.reject(new Error(msg.error || "ws-api failed"));
    };
    ws.onclose = () => {
      wsApi = null;
      wsApiReady = null;
      for (const [, p] of wsPending) p.reject(new Error("ws-api disconnected"));
      wsPending.clear();
    };
    ws.onerror = () => reject(new Error("ws-api connect error"));
  });
  return wsApiReady;
}

async function wsInvoke<T>(method: string, params?: Record<string, any>): Promise<T> {
  await ensureWsApi();
  if (!wsApi || wsApi.readyState !== WebSocket.OPEN) {
    throw new Error("ws-api not connected");
  }
  const id = `req-${Date.now()}-${++wsReqSeq}`;
  const payload = JSON.stringify({ id, method, params: params ?? {} });
  const out = new Promise<T>((resolve, reject) => {
    wsPending.set(id, {
      resolve: (v) => resolve(v as T),
      reject,
    });
  });
  wsApi.send(payload);
  return out;
}

function parsePathAndQuery(path: string) {
  const [pathname, q = ""] = path.split("?");
  const params = new URLSearchParams(q);
  return { pathname, params };
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  const body =
    typeof init?.body === "string" && init.body.trim()
      ? JSON.parse(init.body)
      : undefined;
  const { pathname, params } = parsePathAndQuery(path);
  if (pathname === "/health") return wsInvoke<T>("health");
  if (pathname === "/friends" && method === "GET") return wsInvoke<T>("listFriends");
  if (/^\/friends\/[^/]+$/.test(pathname) && method === "GET") {
    return wsInvoke<T>("getFriend", { id: pathname.split("/")[2] });
  }
  if (/^\/friends\/[^/]+$/.test(pathname) && method === "DELETE") {
    return wsInvoke<T>("deleteFriend", { id: pathname.split("/")[2] });
  }
  if (pathname === "/friends" && method === "POST") {
    return wsInvoke<T>("upsertFriend", body);
  }
  if (/^\/friends\/[^/]+\/cli_auth$/.test(pathname) && method === "GET") {
    return wsInvoke<T>("getFriendCliAuth", { id: pathname.split("/")[2] });
  }
  if (/^\/friends\/[^/]+\/cli_auth\/oauth\/start$/.test(pathname)) {
    return wsInvoke<T>("startFriendCliOAuth", { id: pathname.split("/")[2] });
  }
  if (/^\/friends\/[^/]+\/cli_auth\/oauth\/cancel$/.test(pathname)) {
    return wsInvoke<T>("cancelFriendCliOAuth", { id: pathname.split("/")[2] });
  }
  if (/^\/friends\/[^/]+\/cli_auth\/logout$/.test(pathname)) {
    return wsInvoke<T>("logoutFriendCli", { id: pathname.split("/")[2] });
  }
  if (pathname === "/assistant-policy-templates" && method === "GET") {
    return wsInvoke<T>("listAssistantPolicyTemplates");
  }
  if (pathname === "/groups" && method === "GET") return wsInvoke<T>("listGroups");
  if (/^\/groups\/[^/]+$/.test(pathname) && method === "GET") {
    return wsInvoke<T>("getGroup", { id: pathname.split("/")[2] });
  }
  if (pathname === "/groups" && method === "POST") {
    return wsInvoke<T>("upsertGroup", body);
  }
  if (pathname === "/providers" && method === "GET") return wsInvoke<T>("listProviders");
  if (pathname === "/providers" && method === "POST") {
    return wsInvoke<T>("upsertProvider", body);
  }
  if (/^\/providers\/[^/]+$/.test(pathname) && method === "DELETE") {
    return wsInvoke<T>("deleteProvider", { id: pathname.split("/")[2] });
  }
  if (pathname === "/provider_keys" && method === "GET") {
    return wsInvoke<T>("listProviderKeys", {
      provider_id: params.get("provider_id") || undefined,
    });
  }
  if (pathname === "/provider_keys" && method === "POST") {
    return wsInvoke<T>("upsertProviderKey", body);
  }
  if (/^\/provider_keys\/[^/]+$/.test(pathname) && method === "DELETE") {
    return wsInvoke<T>("deleteProviderKey", { id: pathname.split("/")[2] });
  }
  if (pathname.startsWith("/conversations/dm/") && method === "GET") {
    return wsInvoke<T>("openDm", {
      friend_id: pathname.split("/").at(-1),
    });
  }
  if (pathname.startsWith("/conversations/dm/") && method === "POST") {
    return wsInvoke<T>("sendDm", {
      friend_id: pathname.split("/").at(-1),
      content: body?.content,
    });
  }
  if (pathname.startsWith("/conversations/") && pathname.endsWith("/messages")) {
    return wsInvoke<T>("listConversationMessages", {
      conversation_id: pathname.split("/")[2],
    });
  }
  if (pathname.startsWith("/conversations/") && pathname.endsWith("/send")) {
    return wsInvoke<T>("sendToConversation", {
      conversation_id: pathname.split("/")[2],
      content: body?.content,
    });
  }
  if (/^\/conversations\/[^/]+\/messages\/[^/]+\/delegate$/.test(pathname)) {
    const seg = pathname.split("/");
    return wsInvoke<T>("resolveDelegate", {
      conversation_id: seg[2],
      message_id: seg[4],
      ...body,
    });
  }
  if (pathname === "/assistant/global-settings" && method === "GET") {
    return wsInvoke<T>("getAssistantGlobalSettings");
  }
  if (pathname === "/assistant/global-settings" && method === "POST") {
    return wsInvoke<T>("upsertAssistantGlobalSettings", body);
  }
  if (pathname === "/assistant/global-settings/consolidate") {
    return wsInvoke<T>("consolidateAssistantMemories");
  }
  if (/^\/assistant\/[^/]+\/memories$/.test(pathname) && method === "GET") {
    return wsInvoke<T>("listAssistantMemories", {
      friend_id: pathname.split("/")[2],
      category: params.get("category") || undefined,
      limit: params.get("limit") ? Number(params.get("limit")) : undefined,
    });
  }
  if (/^\/assistant\/[^/]+\/memories$/.test(pathname) && method === "POST") {
    return wsInvoke<T>("addAssistantMemory", {
      friend_id: pathname.split("/")[2],
      body,
    });
  }
  if (/^\/assistant\/[^/]+\/memories\/[^/]+$/.test(pathname) && method === "DELETE") {
    return wsInvoke<T>("deleteAssistantMemory", {
      friend_id: pathname.split("/")[2],
      memory_id: pathname.split("/")[4],
    });
  }
  if (/^\/assistant\/[^/]+\/skills$/.test(pathname)) {
    return wsInvoke<T>("listAssistantSkills", { friend_id: pathname.split("/")[2] });
  }
  if (/^\/assistant\/[^/]+\/reflections$/.test(pathname)) {
    return wsInvoke<T>("listAssistantReflections", {
      friend_id: pathname.split("/")[2],
    });
  }
  if (/^\/assistant\/[^/]+\/todos$/.test(pathname) && method === "GET") {
    return wsInvoke<T>("listAssistantTodos", {
      friend_id: pathname.split("/")[2],
      status: params.get("status") || undefined,
      limit: params.get("limit") ? Number(params.get("limit")) : undefined,
    });
  }
  if (/^\/assistant\/[^/]+\/todos$/.test(pathname) && method === "POST") {
    return wsInvoke<T>("createAssistantTodo", {
      friend_id: pathname.split("/")[2],
      ...body,
    });
  }
  if (/^\/assistant\/[^/]+\/todos\/[^/]+$/.test(pathname) && method === "POST") {
    const seg = pathname.split("/");
    return wsInvoke<T>("updateAssistantTodo", {
      friend_id: seg[2],
      todo_id: seg[4],
      ...body,
    });
  }
  if (/^\/assistant\/[^/]+\/todos\/run$/.test(pathname)) {
    return wsInvoke<T>("runAssistantTodosOnce", {
      friend_id: pathname.split("/")[2],
    });
  }
  if (pathname === "/assistant/queue/jobs") {
    return wsInvoke<T>("listAssistantQueueJobs", {
      status: params.get("status") || undefined,
      limit: params.get("limit") ? Number(params.get("limit")) : undefined,
    });
  }
  if (pathname === "/assistant/queue/stats") {
    return wsInvoke<T>("getAssistantQueueStats");
  }
  if (pathname === "/assistant/queue/replay-failed") {
    return wsInvoke<T>("replayFailedAssistantQueueJobs", body);
  }
  if (pathname === "/invites" && method === "GET") {
    return wsInvoke<T>("listInvites", {
      friend_id: params.get("friend_id") || undefined,
    });
  }
  if (pathname === "/invites" && method === "POST") {
    return wsInvoke<T>("createInvite", body);
  }
  if (/^\/invites\/[^/]+$/.test(pathname) && method === "DELETE") {
    return wsInvoke<T>("deleteInvite", { id: pathname.split("/")[2] });
  }
  if (/^\/human\/[^/]+\/state$/.test(pathname)) {
    return wsInvoke<T>("humanState", { code: pathname.split("/")[2] });
  }
  if (/^\/human\/[^/]+\/send$/.test(pathname)) {
    return wsInvoke<T>("humanSend", { code: pathname.split("/")[2], ...body });
  }
  if (/^\/human\/[^/]+\/typing$/.test(pathname)) {
    return wsInvoke<T>("humanTyping", { code: pathname.split("/")[2], ...body });
  }
  throw new Error(`ws-api unsupported endpoint: ${method} ${pathname}`);
}

export const api = {
  health: () => jsonFetch<{ ok: boolean }>("/health"),
  listFriends: () => jsonFetch<{ friends: Friend[] }>("/friends"),
  getFriend: (id: string) => jsonFetch<{ friend: Friend }>(`/friends/${id}`),
  getFriendCliAuth: (id: string) =>
    jsonFetch<{ cli_auth: CliAuthStatus }>(`/friends/${id}/cli_auth`),
  startFriendCliOAuth: (id: string) =>
    jsonFetch<{ cli_auth: CliAuthStatus; oauth: CliOAuthSnapshot }>(
      `/friends/${id}/cli_auth/oauth/start`,
      { method: "POST" },
    ),
  cancelFriendCliOAuth: (id: string) =>
    jsonFetch<{ cli_auth: CliAuthStatus }>(`/friends/${id}/cli_auth/oauth/cancel`, {
      method: "POST",
    }),
  logoutFriendCli: (id: string) =>
    jsonFetch<{ cli_auth: CliAuthStatus }>(`/friends/${id}/cli_auth/logout`, {
      method: "POST",
    }),
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
  resolveDelegate: (
    conversationId: string,
    messageId: string,
    body: { approve: boolean; content?: string },
  ) =>
    jsonFetch<{ message: Message }>(
      `/conversations/${conversationId}/messages/${messageId}/delegate`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
  getAssistantGlobalSettings: () =>
    jsonFetch<{ settings: AssistantGlobalSettings }>(
      "/assistant/global-settings",
    ),
  upsertAssistantGlobalSettings: (body: AssistantGlobalSettings) =>
    jsonFetch<{ settings: AssistantGlobalSettings }>(
      "/assistant/global-settings",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
  consolidateAssistantMemories: () =>
    jsonFetch<{ ok: boolean; settings: AssistantGlobalSettings }>(
      "/assistant/global-settings/consolidate",
      { method: "POST" },
    ),
  listAssistantPolicyTemplates: () =>
    jsonFetch<{ templates: AssistantPolicyTemplate[] }>(
      "/assistant-policy-templates",
    ),
  listGroups: () => jsonFetch<{ groups: GroupBundle[] }>("/groups"),
  getGroup: (id: string) =>
    jsonFetch<
      GroupBundle & {
        conversation_id: string;
      }
    >(`/groups/${id}`),
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
  listAssistantMemories: (
    friendId: string,
    opts?: { category?: "memo" | "knowledge"; limit?: number },
  ) => {
    const params = new URLSearchParams();
    if (opts?.category) params.set("category", opts.category);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const q = params.toString();
    return jsonFetch<{ memories: AssistantMemory[] }>(
      `/assistant/${friendId}/memories${q ? `?${q}` : ""}`,
    );
  },
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
  listAssistantTodos: (
    friendId: string,
    opts?: { status?: "pending" | "running" | "done" | "failed"; limit?: number },
  ) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const q = params.toString();
    return jsonFetch<{ todos: AssistantTodo[] }>(
      `/assistant/${friendId}/todos${q ? `?${q}` : ""}`,
    );
  },
  createAssistantTodo: (
    friendId: string,
    body: {
      title: string;
      detail?: string;
      priority?: number;
      remind_after_seconds?: number;
      raw_text?: string;
    },
  ) =>
    jsonFetch<{ todo: AssistantTodo }>(`/assistant/${friendId}/todos`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateAssistantTodo: (
    friendId: string,
    todoId: string,
    body: {
      title: string;
      detail?: string;
      priority: number;
      status?: "pending" | "running" | "done" | "failed";
    },
  ) =>
    jsonFetch<{ todo: AssistantTodo }>(`/assistant/${friendId}/todos/${todoId}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  runAssistantTodosOnce: (friendId: string) =>
    jsonFetch<{ ok: boolean; queued: boolean; todos: AssistantTodo[] }>(
      `/assistant/${friendId}/todos/run`,
      { method: "POST" },
    ),
  listAssistantQueueJobs: (opts?: { status?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const q = params.toString();
    return jsonFetch<{ jobs: AssistantQueueJob[] }>(
      `/assistant/queue/jobs${q ? `?${q}` : ""}`,
    );
  },
  getAssistantQueueStats: () =>
    jsonFetch<{ stats: AssistantQueueStats }>(`/assistant/queue/stats`),
  replayFailedAssistantQueueJobs: (limit = 100) =>
    jsonFetch<{ ok: boolean; replayed: number }>(`/assistant/queue/replay-failed`, {
      method: "POST",
      body: JSON.stringify({ limit }),
    }),
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
