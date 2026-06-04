import { create } from "zustand";
import { api, connectWs } from "../api/client";
import { applyCliBlockDelta, cliBlocksToPlain } from "../cliBlocks";
import {
  emptyTaskFlowRound,
  markPhaseDone,
  type TaskFlowPhaseKey,
  type TaskFlowRound,
} from "../taskFlow";
import type {
  BusEvent,
  Conversation,
  Friend,
  GroupBundle,
  Message,
  MessageAttachment,
  Provider,
  ProviderKey,
} from "../types";

export type TargetKind = "friend" | "group";

export interface ChatTarget {
  kind: TargetKind;
  id: string;
}

export interface ThinkingState {
  status: "judging" | "will_reply" | "skip" | "speaking";
  confidence?: number;
  reason?: string | null;
  /** 实际 judge 通路：llm / heuristic / llm_failed / auto_llm / auto_heuristic */
  judgeSource?: string | null;
  configuredJudgeMode?: string;
  updatedAt: number;
}

export interface MemberJudgeVerdict {
  friendId: string;
  friendName: string;
  shouldReply: boolean;
  confidence: number;
  judgeSource: string | null;
  reason: string | null;
}

/** 本轮群聊 judge + 调度结果（用于聊天窗顶部条） */
export interface JudgeRoundBanner {
  turnId: string;
  configuredMode: string;
  scheduleMode: string;
  /** should_reply=true 且 confidence≥阈值 的人数 */
  willingToReply: number;
  threshold: number;
  pickedNames: string[];
  pickedViaFallback: boolean;
  verdicts: MemberJudgeVerdict[];
  updatedAt: number;
}

export interface OwnerNotifyBanner {
  groupId: string;
  groupName: string;
  title: string;
  body: string;
  updatedAt: number;
}

interface ChatState {
  ready: boolean;
  friends: Friend[];
  groups: GroupBundle[];
  providers: Provider[];
  providerKeys: ProviderKey[];
  target: ChatTarget | null;
  conversation: Conversation | null;
  messages: Message[];
  /** 各会话消息缓存；切换好友/群时仍接收 WS 增量，避免流式回复中途切走丢内容 */
  messageCache: Record<string, Message[]>;
  /** friendId → conversationId，切换时先展示缓存避免空白等待 */
  friendConvIndex: Record<string, string>;
  /** groupId → conversationId */
  groupConvIndex: Record<string, string>;
  /** 切换会话序号，丢弃过期的 openDm/getGroup 响应 */
  selectSeq: number;
  thinking: Record<string, ThinkingState>;
  judgeBanner: JudgeRoundBanner | null;
  ownerNotify: OwnerNotifyBanner | null;
  taskFlow: TaskFlowRound | null;
  ws: WebSocket | null;
  init: () => Promise<void>;
  reloadFriends: () => Promise<void>;
  reloadGroups: () => Promise<void>;
  reloadProviders: () => Promise<void>;
  selectFriend: (id: string) => Promise<void>;
  selectGroup: (id: string) => Promise<void>;
  sendMessage: (
    content: string,
    attachments?: MessageAttachment[],
  ) => Promise<void>;
}

export const useChat = create<ChatState>((set, get) => ({
  ready: false,
  friends: [],
  groups: [],
  providers: [],
  providerKeys: [],
  target: null,
  conversation: null,
  messages: [],
  messageCache: {},
  friendConvIndex: {},
  groupConvIndex: {},
  selectSeq: 0,
  thinking: {},
  judgeBanner: null,
  ownerNotify: null,
  taskFlow: null,
  ws: null,
  async init() {
    set({ ready: false });
    const prev = get().ws;
    if (prev && prev.readyState <= WebSocket.OPEN) {
      prev.close();
    }
    const [{ friends }, { groups }, { providers }, { provider_keys }] =
      await Promise.all([
        api.listFriends(),
        api.listGroups(),
        api.listProviders(),
        api.listProviderKeys(),
      ]);
    set({
      friends,
      groups,
      providers,
      providerKeys: provider_keys,
      ready: true,
    });
    const ws = connectWs((ev: BusEvent) => applyBusEvent(ev, set, get));
    set({ ws });
    if (friends.length > 0) {
      await get().selectFriend(friends[0].id);
    }
  },
  async reloadFriends() {
    const { friends } = await api.listFriends();
    set({ friends });
  },
  async reloadGroups() {
    const { groups } = await api.listGroups();
    set({ groups });
  },
  async reloadProviders() {
    const [{ providers }, { provider_keys }] = await Promise.all([
      api.listProviders(),
      api.listProviderKeys(),
    ]);
    set({ providers, providerKeys: provider_keys });
  },
  async selectFriend(id) {
    const seq = get().selectSeq + 1;
    set((s) => {
      const messageCache = stashActiveMessages(s);
      const cachedConvId = s.friendConvIndex[id];
      const cachedMessages = cachedConvId
        ? messageCache[cachedConvId]
        : undefined;
      const cachedConversation =
        cachedConvId && cachedMessages
          ? ({
              id: cachedConvId,
              kind: "dm" as const,
              target_id: id,
              title: null,
              last_message_at: null,
              created_at: new Date().toISOString(),
            } satisfies Conversation)
          : null;
      return {
        selectSeq: seq,
        messageCache,
        target: { kind: "friend", id },
        conversation: cachedConversation,
        messages: cachedMessages ?? [],
        thinking: {},
        judgeBanner: null,
        taskFlow: null,
      };
    });
    try {
      const { conversation, messages } = await api.openDm(id);
      set((s) => {
        if (s.selectSeq !== seq) return {};
        if (s.target?.kind !== "friend" || s.target.id !== id) return {};
        const merged = mergeMessages(messages, s.messageCache[conversation.id]);
        return {
          conversation,
          messages: merged,
          messageCache: { ...s.messageCache, [conversation.id]: merged },
          friendConvIndex: { ...s.friendConvIndex, [id]: conversation.id },
        };
      });
    } catch {
      if (get().selectSeq === seq && get().target?.id === id && !get().conversation) {
        set({ messages: [] });
      }
    }
  },
  async selectGroup(id) {
    const seq = get().selectSeq + 1;
    set((s) => {
      const messageCache = stashActiveMessages(s);
      const cachedConvId = s.groupConvIndex[id];
      const cachedMessages = cachedConvId
        ? messageCache[cachedConvId]
        : undefined;
      const cachedConversation =
        cachedConvId && cachedMessages
          ? ({
              id: cachedConvId,
              kind: "group" as const,
              target_id: id,
              title: null,
              last_message_at: null,
              created_at: new Date().toISOString(),
            } satisfies Conversation)
          : null;
      return {
        selectSeq: seq,
        messageCache,
        target: { kind: "group", id },
        conversation: cachedConversation,
        messages: cachedMessages ?? [],
        thinking: {},
        judgeBanner: null,
        taskFlow: null,
      };
    });
    try {
      const { conversation_id } = await api.getGroup(id);
      const conv = await api.listConversationMessages(conversation_id);
      set((s) => {
        if (s.selectSeq !== seq) return {};
        if (s.target?.kind !== "group" || s.target.id !== id) return {};
        const conversation: Conversation = {
          id: conversation_id,
          kind: "group",
          target_id: id,
          title: null,
          last_message_at: null,
          created_at: new Date().toISOString(),
        };
        const merged = mergeMessages(conv.messages, s.messageCache[conversation_id]);
        return {
          conversation,
          messages: merged,
          messageCache: { ...s.messageCache, [conversation_id]: merged },
          groupConvIndex: { ...s.groupConvIndex, [id]: conversation_id },
        };
      });
    } catch {
      if (get().selectSeq === seq && get().target?.id === id && !get().conversation) {
        set({ messages: [] });
      }
    }
  },
  async sendMessage(content, attachments = []) {
    const t = get().target;
    if (!t) return;
    if (t.kind === "friend") {
      const res = await api.sendDm(t.id, content, attachments);
      set((s) => ({
        friendConvIndex: { ...s.friendConvIndex, [t.id]: res.conversation_id },
      }));
    } else {
      const conv = get().conversation;
      if (!conv) return;
      await api.sendToConversation(conv.id, content, attachments);
    }
  },
}));

function stashActiveMessages(s: ChatState): Record<string, Message[]> {
  const cid = s.conversation?.id;
  if (!cid) return s.messageCache;
  return { ...s.messageCache, [cid]: s.messages };
}

function convMessages(s: ChatState, convId: string): Message[] {
  if (s.conversation?.id === convId) return s.messages;
  return s.messageCache[convId] ?? [];
}

function withConvMessages(
  s: ChatState,
  convId: string,
  updater: (msgs: Message[]) => Message[],
): Partial<ChatState> {
  const next = updater(convMessages(s, convId));
  const messageCache = { ...s.messageCache, [convId]: next };
  if (s.conversation?.id === convId) {
    return { messages: next, messageCache };
  }
  return { messageCache };
}

/** API 快照与 WS 缓存合并：流式中途切走时 DB 内容可能滞后于缓存 */
export function mergeMessages(apiMessages: Message[], cached?: Message[]): Message[] {
  if (!cached?.length) return apiMessages;
  const cacheById = new Map(cached.map((m) => [m.id, m]));
  const merged = apiMessages.map((m) => {
    const c = cacheById.get(m.id);
    if (!c) return m;
    if (c.content.length > m.content.length) return c;
    if (m.status === "streaming" && c.content.length >= m.content.length) return c;
    if (c.status === "done" && m.status === "streaming") return c;
    return m;
  });
  for (const c of cached) {
    if (!merged.some((m) => m.id === c.id)) merged.push(c);
  }
  merged.sort(
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );
  return merged;
}

function applyBusEvent(
  ev: BusEvent,
  set: (
    partial: Partial<ChatState> | ((s: ChatState) => Partial<ChatState>),
  ) => void,
  get: () => ChatState,
) {
  const state = get();
  const sameConv = (cid: string) =>
    !!state.conversation && cid === state.conversation.id;
  switch (ev.type) {
    case "message_created": {
      const convId = ev.message.conversation_id;
      set((s) => {
        const prev = convMessages(s, convId);
        if (prev.some((m) => m.id === ev.message.id)) return {};
        return withConvMessages(s, convId, (msgs) => [...msgs, ev.message]);
      });
      if (sameConv(convId) && ev.message.sender_kind === "friend") {
        set((s) => ({
          thinking: {
            ...s.thinking,
            [ev.message.sender_id]: {
              status: "speaking",
              updatedAt: Date.now(),
            },
          },
        }));
      }
      break;
    }
    case "message_delta": {
      if (ev.thinking) break;
      set((s) =>
        withConvMessages(s, ev.conversation_id, (msgs) =>
          msgs.map((m) =>
            m.id === ev.message_id
              ? { ...m, content: m.content + ev.delta }
              : m,
          ),
        ),
      );
      break;
    }
    case "message_cli_delta": {
      set((s) =>
        withConvMessages(s, ev.conversation_id, (msgs) =>
          msgs.map((m) => {
            if (m.id !== ev.message_id) return m;
            const content_blocks = applyCliBlockDelta(
              m.content_blocks ?? [],
              ev.delta,
            );
            return {
              ...m,
              content_blocks,
              content: cliBlocksToPlain(content_blocks),
            };
          }),
        ),
      );
      break;
    }
    case "message_done": {
      const convId = ev.message.conversation_id;
      set((s) =>
        withConvMessages(s, convId, (msgs) =>
          msgs.map((m) => (m.id === ev.message.id ? ev.message : m)),
        ),
      );
      if (sameConv(convId)) {
        set((s) => {
          const next = { ...s.thinking };
          delete next[ev.message.sender_id];
          return { thinking: next };
        });
      }
      break;
    }
    case "message_failed": {
      set((s) =>
        withConvMessages(s, ev.conversation_id, (msgs) =>
          msgs.map((m) =>
            m.id === ev.message_id
              ? {
                  ...m,
                  status: "failed",
                  content: `${m.content}\n[error] ${ev.reason}`,
                }
              : m,
          ),
        ),
      );
      break;
    }
    case "judgment_decided": {
      if (sameConv(ev.conversation_id)) {
        const verdict: MemberJudgeVerdict = {
          friendId: ev.friend_id,
          friendName: ev.friend_name,
          shouldReply: ev.should_reply,
          confidence: ev.confidence,
          judgeSource: ev.judge_source,
          reason: ev.reason,
        };
        set((s) => {
          const prev = s.judgeBanner;
          const verdicts =
            prev?.turnId === ev.turn_id
              ? [
                  ...prev.verdicts.filter((v) => v.friendId !== ev.friend_id),
                  verdict,
                ]
              : [verdict];
          return {
            thinking: {
              ...s.thinking,
              [ev.friend_id]: {
                status: ev.should_reply ? "will_reply" : "skip",
                confidence: ev.confidence,
                reason: ev.reason,
                judgeSource: ev.judge_source,
                configuredJudgeMode: ev.configured_judge_mode,
                updatedAt: Date.now(),
              },
            },
            judgeBanner: {
              turnId: ev.turn_id,
              configuredMode: ev.configured_judge_mode,
              scheduleMode: prev?.turnId === ev.turn_id ? prev.scheduleMode : "pending",
              willingToReply: prev?.turnId === ev.turn_id ? prev.willingToReply : 0,
              threshold: prev?.threshold ?? 0.55,
              pickedNames: prev?.turnId === ev.turn_id ? prev.pickedNames : [],
              pickedViaFallback: prev?.pickedViaFallback ?? false,
              verdicts,
              updatedAt: Date.now(),
            },
          };
        });
      }
      break;
    }
    case "scheduler_picked": {
      if (sameConv(ev.conversation_id)) {
        const picked = new Set(ev.decisions.map((d) => d.friend_id));
        const pickedNames = ev.decisions.map((d) => d.friend_name).filter(Boolean);
        set((s) => ({
          thinking: Object.fromEntries(
            Object.entries(s.thinking).map(([k, v]) => [
              k,
              picked.has(k)
                ? { ...v, status: "will_reply" as const }
                : v.status === "will_reply" && !picked.has(k)
                  ? { ...v, status: "skip" as const }
                  : v,
            ]),
          ),
          judgeBanner: {
            turnId: ev.turn_id,
            configuredMode: ev.configured_judge_mode,
            scheduleMode: ev.schedule_mode,
            willingToReply: ev.willing_to_reply,
            threshold: ev.judge_threshold,
            pickedNames,
            pickedViaFallback: ev.schedule_mode === "fallback",
            verdicts:
              s.judgeBanner?.turnId === ev.turn_id
                ? s.judgeBanner.verdicts
                : [],
            updatedAt: Date.now(),
          },
        }));
      }
      break;
    }
    case "task_flow_phase": {
      if (sameConv(ev.conversation_id)) {
        set((s) => {
          const base = ensureTaskFlow(s.taskFlow, ev.turn_id);
          const phase = ev.phase as TaskFlowPhaseKey | "appoint";
          let round = advanceTaskFlowPhase(base, phase, ev.detail);
          if (phase === "campaign" && !round.completedPhases.includes("campaign")) {
            round = { ...round, currentPhase: "campaign" };
          }
          return { taskFlow: round };
        });
      }
      break;
    }
    case "peer_vote": {
      if (sameConv(ev.conversation_id)) {
        set((s) => {
          const base = ensureTaskFlow(s.taskFlow, ev.turn_id);
          return {
            taskFlow: {
              ...base,
              votes: [
                ...base.votes,
                {
                  voterName: ev.voter_name,
                  endorseName: ev.endorse_name,
                  reason: ev.reason,
                  ok: true,
                },
              ],
              updatedAt: Date.now(),
            },
          };
        });
      }
      break;
    }
    case "peer_vote_failed": {
      if (sameConv(ev.conversation_id)) {
        set((s) => {
          const base = ensureTaskFlow(s.taskFlow, ev.turn_id);
          return {
            taskFlow: {
              ...base,
              votes: [
                ...base.votes,
                {
                  voterName: ev.voter_name,
                  endorseName: "—",
                  reason: "",
                  ok: false,
                  error: ev.error,
                },
              ],
              updatedAt: Date.now(),
            },
          };
        });
      }
      break;
    }
    case "plan_published": {
      if (sameConv(ev.conversation_id)) {
        set((s) => {
          const base = ensureTaskFlow(s.taskFlow, ev.turn_id);
          return {
            taskFlow: {
              ...advanceTaskFlowPhase(base, "plan", null),
              planLeader: ev.friend_name,
              updatedAt: Date.now(),
            },
          };
        });
      }
      break;
    }
    case "plan_review": {
      if (sameConv(ev.conversation_id)) {
        set((s) => {
          const base = ensureTaskFlow(s.taskFlow, ev.turn_id);
          return {
            taskFlow: {
              ...base,
              planReviews: [
                ...base.planReviews,
                {
                  name: ev.friend_name,
                  excerpt: ev.content.slice(0, 120),
                },
              ],
              updatedAt: Date.now(),
            },
          };
        });
      }
      break;
    }
    case "campaign_pitch": {
      if (sameConv(ev.conversation_id)) {
        set((s) => {
          const base = ensureTaskFlow(s.taskFlow, ev.turn_id);
          const done = base.campaignDone.includes(ev.friend_name)
            ? base.campaignDone
            : [...base.campaignDone, ev.friend_name];
          return {
            taskFlow: { ...base, campaignDone: done, updatedAt: Date.now() },
            thinking: {
              ...s.thinking,
              [ev.friend_id]: {
                status: "judging",
                reason: "竞选发言完成",
                updatedAt: Date.now(),
              },
            },
          };
        });
      }
      break;
    }
    case "leader_elected": {
      if (sameConv(ev.conversation_id)) {
        set((s) => {
          let base = ensureTaskFlow(s.taskFlow, ev.turn_id);
          base = markPhaseDone(base, "peer_vote");
          base = markPhaseDone(base, "election");
          return {
            taskFlow: {
              ...base,
              currentPhase: "election",
              election: {
                leaderName: ev.friend_name,
                reason: ev.reason,
                confidence: ev.confidence,
                electionOk: ev.election_ok,
                peerVotesSummary: ev.peer_votes_summary,
              },
              updatedAt: Date.now(),
            },
          };
        });
      }
      break;
    }
    case "turn_started": {
      if (sameConv(ev.conversation_id)) {
        set({
          thinking: {},
          judgeBanner: null,
          taskFlow: emptyTaskFlowRound(ev.turn_id),
        });
      }
      break;
    }
    case "turn_ended": {
      if (sameConv(ev.conversation_id)) {
        set({ thinking: {} });
      }
      break;
    }
    case "assistant_owner_notify": {
      set({
        ownerNotify: {
          groupId: ev.group_id,
          groupName: ev.group_name,
          title: ev.title,
          body: ev.body,
          updatedAt: Date.now(),
        },
      });
      break;
    }
  }
}

const PHASE_ORDER: TaskFlowPhaseKey[] = [
  "campaign",
  "peer_vote",
  "election",
  "plan",
  "plan_review",
  "reuse_leader",
  "execute",
  "guide",
  "delivered",
  "stalled",
];

function ensureTaskFlow(
  prev: TaskFlowRound | null,
  turnId: string,
): TaskFlowRound {
  if (prev?.turnId === turnId) return { ...prev };
  return emptyTaskFlowRound(turnId);
}

function advanceTaskFlowPhase(
  round: TaskFlowRound,
  phase: TaskFlowPhaseKey | "appoint",
  detail: string | null,
): TaskFlowRound {
  let r = { ...round };
  const prev = r.currentPhase;
  if (prev && prev !== "appoint" && PHASE_ORDER.includes(prev)) {
    r = markPhaseDone(r, prev);
  }
  if (phase !== "appoint" && prev && PHASE_ORDER.includes(phase)) {
    const prevIdx = PHASE_ORDER.indexOf(prev);
    const nextIdx = PHASE_ORDER.indexOf(phase);
    if (nextIdx > prevIdx + 1) {
      for (let i = prevIdx + 1; i < nextIdx; i++) {
        r = markPhaseDone(r, PHASE_ORDER[i]);
      }
    }
  }
  return {
    ...r,
    currentPhase: phase,
    phaseDetail: detail,
    updatedAt: Date.now(),
  };
}
