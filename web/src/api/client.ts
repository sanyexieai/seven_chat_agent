export interface CliAuthStatus {
  preset: string;
  authenticated: boolean;
  detail: string;
  api_key_configured: boolean;
  /** server | relay */
  auth_source?: string | null;
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
  AssistantMemoryStats,
  AssistantPolicyTemplate,
  AssistantReflection,
  AssistantQueueJob,
  AssistantQueueStats,
  AssistantSkill,
  AssistantTodo,
  CliRelayNode,
  Conversation,
  Friend,
  Workspace,
  CliSession,
  CliImportReport,
  GroupBundle,
  GroupMemberConfig,
  GroupPublicMemoriesResponse,
  GroupSettings,
  Message,
  MessageAttachment,
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

export async function wsInvoke<T>(method: string, params?: Record<string, any>): Promise<T> {
  await ensureWsApi();
  const token =
    typeof localStorage !== "undefined"
      ? localStorage.getItem("seven_chat_agent_token")
      : null;
  const merged = { ...(params ?? {}) };
  if (token && !merged.auth_token) merged.auth_token = token;
  if (!wsApi || wsApi.readyState !== WebSocket.OPEN) {
    throw new Error("ws-api not connected");
  }
  const id = `req-${Date.now()}-${++wsReqSeq}`;
  const payload = JSON.stringify({ id, method, params: merged });
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

async function httpJsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token =
    typeof localStorage !== "undefined"
      ? localStorage.getItem("seven_chat_agent_token")
      : null;
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { error?: string }).error || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  const body =
    typeof init?.body === "string" && init.body.trim()
      ? JSON.parse(init.body)
      : undefined;
  const { pathname, params } = parsePathAndQuery(path);

  // 聊天与会话切换走 HTTP，避免与 ws-api 单连接上的慢请求（助理面板、OAuth、导入等）互相排队
  if (pathname === "/friends" && method === "GET") {
    return httpJsonFetch<T>(pathname);
  }
  if (pathname === "/groups" && method === "GET") {
    return httpJsonFetch<T>(pathname);
  }
  if (/^\/groups\/[^/]+$/.test(pathname) && method === "GET") {
    return httpJsonFetch<T>(pathname);
  }
  if (/^\/groups\/[^/]+\/public-memories\/latest$/.test(pathname)) {
    return httpJsonFetch<T>(pathname, {
      method,
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  }
  if (/^\/groups\/[^/]+\/public-memories$/.test(pathname)) {
    const qs = params.toString();
    const url = qs ? `${pathname}?${qs}` : pathname;
    return httpJsonFetch<T>(url, {
      method,
      ...(body !== undefined && method !== "GET"
        ? { body: JSON.stringify(body) }
        : method !== "GET"
          ? { body: JSON.stringify({}) }
          : {}),
    });
  }
  if (pathname.startsWith("/conversations/dm/") && method === "GET") {
    return httpJsonFetch<T>(pathname);
  }
  if (pathname.startsWith("/conversations/dm/") && method === "POST") {
    return httpJsonFetch<T>(pathname, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    });
  }
  if (
    pathname.startsWith("/conversations/") &&
    pathname.endsWith("/messages") &&
    method === "GET"
  ) {
    return httpJsonFetch<T>(pathname);
  }
  if (pathname.startsWith("/conversations/") && pathname.endsWith("/send")) {
    return httpJsonFetch<T>(pathname, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    });
  }
  if (/^\/conversations\/[^/]+\/messages\/[^/]+\/delegate$/.test(pathname)) {
    return httpJsonFetch<T>(pathname, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    });
  }
  if (pathname === "/profile-frameworks" && method === "GET") {
    return httpJsonFetch<T>(pathname);
  }
  if (pathname === "/profile-frameworks" && method === "POST") {
    return httpJsonFetch<T>(pathname, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    });
  }
  if (/^\/profile-frameworks\/[^/]+$/.test(pathname) && method === "DELETE") {
    return httpJsonFetch<T>(pathname, { method: "DELETE" });
  }
  if (/^\/friends\/[^/]+\/profile$/.test(pathname)) {
    return httpJsonFetch<T>(pathname, {
      method,
      ...(body !== undefined
        ? { body: JSON.stringify(body) }
        : method !== "GET"
          ? { body: JSON.stringify({}) }
          : {}),
    });
  }

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
  if (/^\/friends\/[^/]+\/workspaces$/.test(pathname) && method === "GET") {
    return wsInvoke<T>("listFriendWorkspaces", { friend_id: pathname.split("/")[2] });
  }
  if (/^\/friends\/[^/]+\/workspaces$/.test(pathname) && method === "POST") {
    return wsInvoke<T>("createFriendWorkspace", {
      friend_id: pathname.split("/")[2],
      ...body,
    });
  }
  if (/^\/friends\/[^/]+\/workspaces\/[^/]+\/activate$/.test(pathname)) {
    const seg = pathname.split("/");
    return wsInvoke<T>("activateFriendWorkspace", {
      friend_id: seg[2],
      workspace_id: seg[4],
    });
  }
  if (/^\/friends\/[^/]+\/workspaces\/[^/]+$/.test(pathname) && method === "DELETE") {
    const seg = pathname.split("/");
    return wsInvoke<T>("deleteFriendWorkspace", {
      friend_id: seg[2],
      workspace_id: seg[4],
    });
  }
  if (/^\/friends\/[^/]+\/workspaces\/[^/]+\/cli-sessions$/.test(pathname) && method === "GET") {
    const seg = pathname.split("/");
    return wsInvoke<T>("listWorkspaceCliSessions", {
      friend_id: seg[2],
      workspace_id: seg[4],
    });
  }
  if (
    /^\/friends\/[^/]+\/workspaces\/[^/]+\/cli-sessions\/[^/]+\/activate$/.test(pathname) &&
    method === "POST"
  ) {
    const seg = pathname.split("/");
    return wsInvoke<T>("activateWorkspaceCliSession", {
      friend_id: seg[2],
      workspace_id: seg[4],
      session_id: seg[6],
    });
  }
  if (/^\/friends\/[^/]+\/workspaces\/[^/]+\/import-codex$/.test(pathname) && method === "POST") {
    const seg = pathname.split("/");
    return wsInvoke<T>("importWorkspaceCodexSessions", {
      friend_id: seg[2],
      workspace_id: seg[4],
      tool: "codex",
      ingest_memories: body?.ingest_memories ?? true,
    });
  }
  if (/^\/friends\/[^/]+\/workspaces\/[^/]+\/import-claude$/.test(pathname) && method === "POST") {
    const seg = pathname.split("/");
    return wsInvoke<T>("importWorkspaceCliSessions", {
      friend_id: seg[2],
      workspace_id: seg[4],
      tool: "claude",
      ingest_memories: body?.ingest_memories ?? true,
    });
  }
  if (/^\/friends\/[^/]+\/workspaces\/[^/]+\/import-cursor$/.test(pathname) && method === "POST") {
    const seg = pathname.split("/");
    return wsInvoke<T>("importWorkspaceCliSessions", {
      friend_id: seg[2],
      workspace_id: seg[4],
      tool: "cursor",
      ingest_memories: body?.ingest_memories ?? true,
    });
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
      content: body?.content ?? "",
      attachments: body?.attachments ?? [],
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
      content: body?.content ?? "",
      attachments: body?.attachments ?? [],
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
  if (/^\/assistant\/[^/]+\/memories\/stats$/.test(pathname) && method === "GET") {
    return wsInvoke<T>("getAssistantMemoryStats", {
      friend_id: pathname.split("/")[2],
    });
  }
  if (
    /^\/assistant\/[^/]+\/memories\/recall-preview$/.test(pathname) &&
    method === "GET"
  ) {
    return wsInvoke<T>("previewAssistantMemoryRecall", {
      friend_id: pathname.split("/")[2],
      prompt: params.get("prompt") || "",
      limit: params.get("limit") ? Number(params.get("limit")) : undefined,
    });
  }
  if (/^\/assistant\/[^/]+\/memories$/.test(pathname) && method === "GET") {
    return wsInvoke<T>("listAssistantMemories", {
      friend_id: pathname.split("/")[2],
      category: params.get("category") || undefined,
      tier: params.get("tier") || undefined,
      status: params.get("status") || undefined,
      scope: params.get("scope") || undefined,
      limit: params.get("limit") ? Number(params.get("limit")) : undefined,
    });
  }
  if (/^\/assistant\/[^/]+\/memories$/.test(pathname) && method === "POST") {
    return wsInvoke<T>("addAssistantMemory", {
      friend_id: pathname.split("/")[2],
      body,
    });
  }
  if (
    /^\/assistant\/[^/]+\/memories\/[^/]+$/.test(pathname) &&
    method === "DELETE"
  ) {
    return wsInvoke<T>("deleteAssistantMemory", {
      friend_id: pathname.split("/")[2],
      memory_id: pathname.split("/")[4],
    });
  }
  if (
    /^\/assistant\/[^/]+\/memories\/[^/]+$/.test(pathname) &&
    method === "PATCH"
  ) {
    return wsInvoke<T>("patchAssistantMemory", {
      memory_id: pathname.split("/")[4],
      ...body,
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
  listProfileFrameworks: () =>
    jsonFetch<{
      frameworks: import("../types/profile").ProfileFrameworkCatalog[];
      profile_frameworks_version?: string;
    }>("/profile-frameworks"),
  upsertProfileFramework: (body: {
    id?: string;
    name: string;
    catalog: import("../types/profile").ProfileFrameworkCatalog;
  }) =>
    jsonFetch<{ framework: import("../types/profile").ProfileFrameworkCatalog }>(
      "/profile-frameworks",
      { method: "POST", body: JSON.stringify(body) },
    ),
  deleteProfileFramework: (id: string) =>
    jsonFetch<void>(`/profile-frameworks/${id}`, { method: "DELETE" }),
  inferFriendProfile: (id: string) =>
    jsonFetch<{
      friend: Friend;
      profile: import("../types/profile").MemberProfile | null;
      reasoning: string;
    }>(`/friends/${id}/profile`, { method: "POST" }),
  getFriendProfile: (id: string) =>
    jsonFetch<{ friend_id: string; profile: import("../types/profile").MemberProfile | null }>(
      `/friends/${id}/profile`,
    ),
  upsertFriendProfile: (id: string, profile: import("../types/profile").MemberProfile) =>
    jsonFetch<{ friend: Friend; profile: import("../types/profile").MemberProfile | null }>(
      `/friends/${id}/profile`,
      { method: "PUT", body: JSON.stringify(profile) },
    ),
  deleteFriend: (id: string) =>
    jsonFetch<{ ok: boolean }>(`/friends/${id}`, { method: "DELETE" }),
  listFriendWorkspaces: (friendId: string) =>
    jsonFetch<{ workspaces: Workspace[]; active_workspace_id: string | null }>(
      `/friends/${friendId}/workspaces`,
    ),
  createFriendWorkspace: (
    friendId: string,
    body: { name: string; path?: string },
  ) =>
    jsonFetch<{ workspace: Workspace }>(`/friends/${friendId}/workspaces`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  activateFriendWorkspace: (friendId: string, workspaceId: string) =>
    jsonFetch<{ ok: boolean; active_workspace_id: string | null }>(
      `/friends/${friendId}/workspaces/${workspaceId}/activate`,
      { method: "POST" },
    ),
  deleteFriendWorkspace: (friendId: string, workspaceId: string) =>
    jsonFetch<{ ok: boolean }>(
      `/friends/${friendId}/workspaces/${workspaceId}`,
      { method: "DELETE" },
    ),
  listWorkspaceCliSessions: (friendId: string, workspaceId: string) =>
    jsonFetch<{ cli_sessions: CliSession[] }>(
      `/friends/${friendId}/workspaces/${workspaceId}/cli-sessions`,
    ),
  activateWorkspaceCliSession: (
    friendId: string,
    workspaceId: string,
    sessionId: string,
  ) =>
    jsonFetch<{ ok: boolean }>(
      `/friends/${friendId}/workspaces/${workspaceId}/cli-sessions/${sessionId}/activate`,
      { method: "POST" },
    ),
  importWorkspaceCodexSessions: (
    friendId: string,
    workspaceId: string,
    opts?: { ingest_memories?: boolean },
  ) =>
    jsonFetch<{ report: CliImportReport; cli_sessions: CliSession[] }>(
      `/friends/${friendId}/workspaces/${workspaceId}/import-codex`,
      {
        method: "POST",
        body: JSON.stringify(opts ?? { ingest_memories: true }),
      },
    ),
  importWorkspaceClaudeSessions: (
    friendId: string,
    workspaceId: string,
    opts?: { ingest_memories?: boolean },
  ) =>
    jsonFetch<{ report: CliImportReport; cli_sessions: CliSession[] }>(
      `/friends/${friendId}/workspaces/${workspaceId}/import-claude`,
      {
        method: "POST",
        body: JSON.stringify(opts ?? { ingest_memories: true }),
      },
    ),
  importWorkspaceCursorSessions: (
    friendId: string,
    workspaceId: string,
    opts?: { ingest_memories?: boolean },
  ) =>
    jsonFetch<{ report: CliImportReport; cli_sessions: CliSession[] }>(
      `/friends/${friendId}/workspaces/${workspaceId}/import-cursor`,
      {
        method: "POST",
        body: JSON.stringify(opts ?? { ingest_memories: true }),
      },
    ),
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
  sendDm: (
    friendId: string,
    content: string,
    attachments: MessageAttachment[] = [],
  ) =>
    jsonFetch<{ ok: boolean; conversation_id: string }>(
      `/conversations/dm/${friendId}`,
      {
        method: "POST",
        body: JSON.stringify({ content, attachments }),
      },
    ),
  uploadConversationAttachments: async (
    conversationId: string,
    files: File[],
  ): Promise<MessageAttachment[]> => {
    const fd = new FormData();
    for (const f of files) {
      fd.append("files", f);
    }
    const res = await fetch(`/api/conversations/${conversationId}/attachments`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as { error?: string }).error || res.statusText);
    }
    const data = (await res.json()) as { attachments: MessageAttachment[] };
    return data.attachments;
  },
  listConversationMessages: (id: string) =>
    jsonFetch<{ messages: Message[] }>(`/conversations/${id}/messages`),
  sendToConversation: (
    id: string,
    content: string,
    attachments: MessageAttachment[] = [],
  ) =>
    jsonFetch<{ ok: boolean }>(`/conversations/${id}/send`, {
      method: "POST",
      body: JSON.stringify({ content, attachments }),
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
  getEvolutionSettings: () =>
    jsonFetch<import("../types/evolution").EvolutionSettings>("/evolution/settings"),
  putEvolutionSettings: (body: import("../types/evolution").EvolutionSettings) =>
    jsonFetch<import("../types/evolution").EvolutionSettings>("/evolution/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  listEvolutionRuns: (limit = 30) =>
    jsonFetch<{ runs: import("../types/evolution").EvolutionRunSummary[] }>(
      `/evolution/runs?limit=${limit}`,
    ),
  getEvolutionRun: (id: string) =>
    jsonFetch<import("../types/evolution").EvolutionRunLog>(`/evolution/runs/${id}`),
  evolutionSyncSource: () =>
    jsonFetch<import("../types/evolution").EvolutionRunLog>(
      "/evolution/runs/sync-source",
      { method: "POST", body: "{}" },
    ),
  evolutionBuildCli: () =>
    jsonFetch<import("../types/evolution").EvolutionRunLog>(
      "/evolution/runs/build-cli",
      { method: "POST", body: "{}" },
    ),
  evolutionPipelineSyncBuild: () =>
    jsonFetch<import("../types/evolution").EvolutionRunLog>(
      "/evolution/runs/pipeline-sync-build",
      { method: "POST", body: "{}" },
    ),
  evolutionAnalyzeSource: () =>
    jsonFetch<import("../types/evolution").EvolutionAnalyzeResponse>(
      "/evolution/runs/analyze-source",
      { method: "POST", body: "{}" },
    ),
  evolutionSyncIssues: (report?: import("../types/evolution").OptimizationReport) =>
    jsonFetch<{ run: import("../types/evolution").EvolutionRunLog; sync: import("../types/evolution").IssueSyncReport }>(
      "/evolution/runs/sync-issues",
      {
        method: "POST",
        body: JSON.stringify(report ? { report } : {}),
      },
    ),
  evolutionPipelineAnalyzeIssues: () =>
    jsonFetch<import("../types/evolution").EvolutionPipelineAnalyzeResponse>(
      "/evolution/runs/pipeline-analyze-issues",
      { method: "POST", body: "{}" },
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
  /** 记忆维护可能调用 LLM，走 HTTP 避免 ws-api 长任务无响应 */
  consolidateAssistantMemories: async () => {
    const res = await fetch("/api/assistant/global-settings/consolidate", {
      method: "POST",
      headers: { "content-type": "application/json" },
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(
        text || `记忆维护失败 HTTP ${res.status}`,
      );
    }
    return res.json() as Promise<{
      ok: boolean;
      settings: AssistantGlobalSettings;
      report?: import("../types").MemoryMaintenanceReport;
    }>;
  },
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
  getGroupPublicMemories: (
    groupId: string,
    opts?: { q?: string; limit?: number; include_raw?: boolean },
  ) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    if (opts?.include_raw) params.set("include_raw", "true");
    const qs = params.toString();
    return jsonFetch<GroupPublicMemoriesResponse>(
      `/groups/${groupId}/public-memories${qs ? `?${qs}` : ""}`,
    );
  },
  rebuildGroupPublicMemories: (groupId: string) =>
    jsonFetch<{ ok: boolean; updated: boolean; latest?: { content: string; updated_at: string } }>(
      `/groups/${groupId}/public-memories`,
      { method: "POST" },
    ),
  patchGroupPublicLatest: (
    groupId: string,
    body: { pinned?: boolean; importance?: number },
  ) =>
    jsonFetch<{
      ok: boolean;
      latest: GroupPublicMemoriesResponse["latest"];
    }>(`/groups/${groupId}/public-memories/latest`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  upsertGroup: (body: {
    id?: string;
    name: string;
    avatar?: string | null;
    settings: GroupSettings;
    members: GroupMemberConfig[];
    member_ids?: string[];
    workspaces?: Array<{
      id?: string;
      name: string;
      kind?: string;
      git_url?: string | null;
      default_branch?: string | null;
      logical_key?: string | null;
    }>;
    member_bindings?: Array<{
      id?: string;
      group_workspace_id: string;
      friend_id: string;
      execution_mode?: string | null;
      relay_id?: string | null;
      local_path?: string | null;
    }>;
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
    opts?: {
      category?: "memo" | "knowledge";
      tier?: "raw" | "curated";
      status?: "active" | "archived";
      scope?: string;
      limit?: number;
    },
  ) => {
    const params = new URLSearchParams();
    if (opts?.category) params.set("category", opts.category);
    if (opts?.tier) params.set("tier", opts.tier);
    if (opts?.status) params.set("status", opts.status);
    if (opts?.scope) params.set("scope", opts.scope);
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
      tier?: string;
      scope?: string;
      scope_ref?: string;
      importance?: number;
      status?: string;
      title?: string;
      summary?: string;
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
  getAssistantMemoryStats: (friendId: string) =>
    jsonFetch<{ stats: AssistantMemoryStats }>(
      `/assistant/${friendId}/memories/stats`,
    ),
  previewAssistantMemoryRecall: (
    friendId: string,
    opts?: { prompt?: string; limit?: number },
  ) => {
    const params = new URLSearchParams();
    if (opts?.prompt != null) params.set("prompt", opts.prompt);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const q = params.toString();
    return jsonFetch<{ memories: AssistantMemory[]; prompt: string }>(
      `/assistant/${friendId}/memories/recall-preview${q ? `?${q}` : ""}`,
    );
  },
  patchAssistantMemory: (
    friendId: string,
    memoryId: string,
    body: {
      kind?: string;
      content?: string;
      weight?: number;
      pinned?: boolean;
      tier?: string;
      scope?: string;
      scope_ref?: string | null;
      importance?: number;
      status?: string;
      title?: string | null;
      summary?: string | null;
      promote_to_curated?: boolean;
    },
  ) =>
    jsonFetch<{ memory: AssistantMemory }>(
      `/assistant/${friendId}/memories/${memoryId}`,
      { method: "PATCH", body: JSON.stringify(body) },
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
  createCliRelayPairingToken: () =>
    wsInvoke<{ pairing_token: string; relay_ws_url: string }>(
      "createCliRelayPairingToken",
    ),
  listCliRelays: () => wsInvoke<{ relays: CliRelayNode[] }>("listCliRelays"),
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
