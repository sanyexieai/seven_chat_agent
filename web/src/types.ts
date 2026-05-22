export type BackendKind = "pty" | "api" | "assistant" | "human";

export type SenderKind = "user" | "friend" | "system";

export type MessageStatus =
  | "pending"
  | "streaming"
  | "done"
  | "failed"
  | "waiting_human";

export interface ProviderCapabilities {
  stream: boolean;
  tools: boolean;
  vision: boolean;
  thinking: boolean;
  context_len: number;
  embeddings: boolean;
}

export interface Provider {
  id: string;
  kind: string;
  display_name: string;
  base_url: string;
  default_model: string | null;
  capabilities: ProviderCapabilities;
  price: { input_per_mtok: number; output_per_mtok: number };
  enabled: boolean;
  created_at: string;
}

export interface ProviderKey {
  id: string;
  provider_id: string;
  label: string;
  secret_ref: string;
  rpm_limit: number | null;
  tpm_limit: number | null;
  monthly_budget_usd: number | null;
  current_spent_usd: number;
  status: string;
}

export interface Friend {
  id: string;
  name: string;
  avatar: string | null;
  system_prompt: string;
  personality: string | null;
  focus_tags: string[];
  backend_kind: BackendKind;
  backend_config: any;
  judge_provider_ref: string | null;
  enabled: boolean;
  is_builtin: boolean;
  created_at: string;
}

export interface Conversation {
  id: string;
  kind: "dm" | "group";
  target_id: string;
  title: string | null;
  last_message_at: string | null;
  created_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  turn_id: string;
  parent_id: string | null;
  sender_kind: SenderKind;
  sender_id: string;
  sender_name: string;
  content: string;
  mentions: string[];
  status: MessageStatus;
  seen_by: string[];
  model_used: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  created_at: string;
}

export interface GroupSettings {
  judge_threshold: number;
  max_replies_per_turn: number;
  per_agent_max_per_turn: number;
  cooldown_ms: number;
  human_priority: boolean;
  human_pause_ms: number;
  allow_agent_to_agent: boolean;
  extra_system_prompt: string | null;
}

export interface Group {
  id: string;
  name: string;
  avatar: string | null;
  settings: GroupSettings;
  created_at: string;
}

export interface GroupBundle {
  group: Group;
  member_ids: string[];
  conversation_id?: string;
}

export interface AssistantMemory {
  id: string;
  owner_friend_id: string;
  kind: string;
  content: string;
  source_message_id: string | null;
  weight: number;
  pinned: boolean;
  last_used_at: string | null;
  decay_score: number;
  created_at: string;
}

export interface AssistantSkill {
  id: string;
  owner_friend_id: string;
  name: string;
  version: number;
  path: string;
  description: string;
  triggers: string[];
  requires_toolsets: string[];
  platforms: string[];
  trust_level: string;
  guard_report: any;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AssistantReflection {
  id: string;
  owner_friend_id: string;
  turn_id: string;
  score: number;
  summary: string;
  lessons: string[];
  created_at: string;
}

export interface ScheduleDecision {
  friend_id: string;
  friend_name: string;
  confidence: number;
  delay_ms: number;
  reason: string | null;
}

export type BusEvent =
  | { type: "message_created"; message: Message }
  | {
      type: "message_delta";
      message_id: string;
      conversation_id: string;
      delta: string;
      thinking: boolean;
    }
  | { type: "message_done"; message: Message }
  | {
      type: "message_failed";
      message_id: string;
      conversation_id: string;
      reason: string;
    }
  | { type: "turn_started"; conversation_id: string; turn_id: string }
  | { type: "turn_ended"; conversation_id: string; turn_id: string }
  | {
      type: "judgment_decided";
      conversation_id: string;
      turn_id: string;
      friend_id: string;
      friend_name: string;
      should_reply: boolean;
      confidence: number;
      reason: string | null;
    }
  | {
      type: "scheduler_picked";
      conversation_id: string;
      turn_id: string;
      decisions: ScheduleDecision[];
    };
