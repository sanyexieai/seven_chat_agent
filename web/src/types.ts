import type { CliBlock, CliBlockDelta } from "./cliBlocks";

export type { CliBlock, CliBlockDelta };

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
  content_blocks?: CliBlock[] | null;
  mentions: string[];
  status: MessageStatus;
  seen_by: string[];
  model_used: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  created_at: string;
}

export type JudgeMode = "heuristic" | "llm" | "auto";

export interface HeuristicJudgeSettings {
  user_confidence: number;
  friend_confidence: number;
  mention_confidence: number;
  user_delay_ms: number;
  friend_delay_ms: number;
  mention_delay_ms: number;
}

export interface LlmJudgeSettings {
  provider_id: string | null;
  model: string | null;
  api_key_id: string | null;
}

export interface GroupJudgeSettings {
  mode: JudgeMode;
  threshold: number;
  heuristic: HeuristicJudgeSettings;
  llm: LlmJudgeSettings;
  fallback_pick_top: boolean;
}

/** 成员级 Judge 覆盖（未启用时跟群默认）。 */
export interface MemberJudgeOverride {
  use_group_default: boolean;
  mode?: JudgeMode | null;
  threshold?: number | null;
  heuristic?: HeuristicJudgeSettings | null;
  llm?: LlmJudgeSettings | null;
  fallback_pick_top?: boolean | null;
}

export interface GroupTaskFlowSettings {
  enabled: boolean;
  campaign_enabled: boolean;
  leader_only_execute: boolean;
  plan_enabled?: boolean;
  plan_review_enabled?: boolean;
  peer_vote_enabled?: boolean;
  appoint_by_mention_enabled?: boolean;
}

export interface GroupSettings {
  judge_threshold: number;
  judge: GroupJudgeSettings;
  task_flow?: GroupTaskFlowSettings;
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

export interface GroupMemberConfig {
  friend_id: string;
  judge_override?: MemberJudgeOverride | null;
}

export interface GroupTaskFlowReadiness {
  task_flow_enabled: boolean;
  ready: boolean;
  errors: string[];
  warnings: string[];
  agent_member_count: number;
  judge_provider_id: string | null;
  judge_model: string | null;
  judge_key_configured: boolean;
}

export interface GroupBundle {
  group: Group;
  member_ids: string[];
  members?: GroupMemberConfig[];
  conversation_id?: string;
  task_flow_readiness?: GroupTaskFlowReadiness;
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
  | {
      type: "message_cli_delta";
      message_id: string;
      conversation_id: string;
      delta: CliBlockDelta;
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
      judge_source: string | null;
      configured_judge_mode: string;
    }
  | {
      type: "scheduler_picked";
      conversation_id: string;
      turn_id: string;
      decisions: ScheduleDecision[];
      schedule_mode: string;
      configured_judge_mode: string;
      willing_to_reply: number;
      judge_threshold: number;
    }
  | {
      type: "task_flow_phase";
      conversation_id: string;
      turn_id: string;
      phase: string;
      detail: string | null;
    }
  | {
      type: "campaign_pitch";
      conversation_id: string;
      turn_id: string;
      friend_id: string;
      friend_name: string;
    }
  | {
      type: "leader_elected";
      conversation_id: string;
      turn_id: string;
      friend_id: string;
      friend_name: string;
      reason: string;
      confidence: number;
      election_ok: boolean;
      peer_votes_summary: string | null;
      pitches: [string, string][];
    }
  | {
      type: "peer_vote";
      conversation_id: string;
      turn_id: string;
      voter_id: string;
      voter_name: string;
      endorse_id: string;
      endorse_name: string;
      reason: string;
    }
  | {
      type: "peer_vote_failed";
      conversation_id: string;
      turn_id: string;
      voter_id: string;
      voter_name: string;
      error: string;
    }
  | {
      type: "plan_published";
      conversation_id: string;
      turn_id: string;
      friend_id: string;
      friend_name: string;
      plan_excerpt: string;
    }
  | {
      type: "plan_review";
      conversation_id: string;
      turn_id: string;
      friend_id: string;
      friend_name: string;
      content: string;
    };
