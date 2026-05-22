import { create } from "zustand";
import { api, connectWs } from "../api/client";
import type {
  BusEvent,
  Conversation,
  Friend,
  GroupBundle,
  Message,
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
  thinking: Record<string, ThinkingState>;
  ws: WebSocket | null;
  init: () => Promise<void>;
  reloadFriends: () => Promise<void>;
  reloadGroups: () => Promise<void>;
  reloadProviders: () => Promise<void>;
  selectFriend: (id: string) => Promise<void>;
  selectGroup: (id: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
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
  thinking: {},
  ws: null,
  async init() {
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
    set({
      target: { kind: "friend", id },
      conversation: null,
      messages: [],
      thinking: {},
    });
    const { conversation, messages } = await api.openDm(id);
    set({ conversation, messages });
  },
  async selectGroup(id) {
    set({
      target: { kind: "group", id },
      conversation: null,
      messages: [],
      thinking: {},
    });
    const { conversation_id } = await api.getGroup(id);
    const conv = await api.listConversationMessages(conversation_id);
    set({
      conversation: {
        id: conversation_id,
        kind: "group",
        target_id: id,
        title: null,
        last_message_at: null,
        created_at: new Date().toISOString(),
      },
      messages: conv.messages,
    });
  },
  async sendMessage(content) {
    const t = get().target;
    if (!t) return;
    if (t.kind === "friend") {
      await api.sendDm(t.id, content);
    } else {
      const conv = get().conversation;
      if (!conv) return;
      await api.sendToConversation(conv.id, content);
    }
  },
}));

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
      if (sameConv(ev.message.conversation_id)) {
        if (state.messages.some((m) => m.id === ev.message.id)) {
          break;
        }
        set({ messages: [...state.messages, ev.message] });
        if (ev.message.sender_kind === "friend") {
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
      }
      break;
    }
    case "message_delta": {
      if (sameConv(ev.conversation_id) && !ev.thinking) {
        set({
          messages: state.messages.map((m) =>
            m.id === ev.message_id
              ? { ...m, content: m.content + ev.delta }
              : m,
          ),
        });
      }
      break;
    }
    case "message_done": {
      if (sameConv(ev.message.conversation_id)) {
        set({
          messages: state.messages.map((m) =>
            m.id === ev.message.id ? ev.message : m,
          ),
        });
        set((s) => {
          const next = { ...s.thinking };
          delete next[ev.message.sender_id];
          return { thinking: next };
        });
      }
      break;
    }
    case "message_failed": {
      if (sameConv(ev.conversation_id)) {
        set({
          messages: state.messages.map((m) =>
            m.id === ev.message_id
              ? {
                  ...m,
                  status: "failed",
                  content: `${m.content}\n[error] ${ev.reason}`,
                }
              : m,
          ),
        });
      }
      break;
    }
    case "judgment_decided": {
      if (sameConv(ev.conversation_id)) {
        set((s) => ({
          thinking: {
            ...s.thinking,
            [ev.friend_id]: {
              status: ev.should_reply ? "will_reply" : "skip",
              confidence: ev.confidence,
              reason: ev.reason,
              updatedAt: Date.now(),
            },
          },
        }));
      }
      break;
    }
    case "scheduler_picked": {
      if (sameConv(ev.conversation_id)) {
        const picked = new Set(ev.decisions.map((d) => d.friend_id));
        set((s) => ({
          thinking: Object.fromEntries(
            Object.entries(s.thinking).map(([k, v]) => [
              k,
              picked.has(k) ? { ...v, status: "will_reply" } : v,
            ]),
          ),
        }));
      }
      break;
    }
    case "turn_started": {
      if (sameConv(ev.conversation_id)) {
        set({ thinking: {} });
      }
      break;
    }
    case "turn_ended": {
      if (sameConv(ev.conversation_id)) {
        set({ thinking: {} });
      }
      break;
    }
  }
}
