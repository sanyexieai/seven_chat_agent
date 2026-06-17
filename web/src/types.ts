import type { CliBlock, CliBlockDelta } from "./cliBlocks";
import type { MemberProfile, MemberProfileOverlay, MemberProfileSummary } from "./types/profile";

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

/** 在线 CLI 转发节点（远程电脑上的 seven-chat-agent-cli-relay） */
export interface CliRelayAuthProbe {
  preset: string;
  authenticated: boolean;
  detail: string;
  api_key_configured: boolean;
}

export interface CliRelayNode {
  relay_id: string;
  name: string;
  host_label: string | null;
  /** 转发端上报的工作区根目录 */
  workspace_root?: string | null;
  /** 转发端本机 CLI 登录探测（preset → 状态） */
  cli_auth?: Record<string, CliRelayAuthProbe>;
  online: boolean;
  connected_at: string;
}

export type {
  MemberProfile,
  MemberProfileOverlay,
  MemberProfileSummary,
  ProfileFrameworkCatalog,
  InitiativeLevel,
  CoordinationLevel,
} from "./types/profile";

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
  active_workspace_id?: string | null;
  profile?: MemberProfile | null;
  created_at: string;
}

export interface CliSession {
  id: string;
  tenant_id: string;
  workspace_id: string;
  tool: string;
  native_session_id?: string | null;
  label?: string | null;
  source_path?: string | null;
  is_active: boolean;
  last_used_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CliImportReport {
  scanned: number;
  matched: number;
  imported: number;
  memories_created: number;
}

export interface Workspace {
  id: string;
  tenant_id: string;
  owner_friend_id: string;
  owner_user_id?: string | null;
  name: string;
  path: string;
  is_default: boolean;
  cli_session_mode?: string | null;
  cli_session_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: string;
  kind: "dm" | "group";
  target_id: string;
  title: string | null;
  last_message_at: string | null;
  scope_user_id?: string | null;
  created_at: string;
}

export interface MessageAttachment {
  id: string;
  filename: string;
  mime_type: string;
  size: number;
  url: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  turn_id: string;
  parent_id: string | null;
  sender_kind: SenderKind;
  sender_id: string;
  sender_name: string;
  /** 群助理代用户发言 */
  on_behalf_of_user?: boolean;
  content: string;
  content_blocks?: CliBlock[] | null;
  attachments?: MessageAttachment[];
  mentions: string[];
  status: MessageStatus;
  seen_by: string[];
  model_used: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  workspace_id?: string | null;
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

export type GroupMemberRole = "member" | "assistant" | "muted";

export type AssistantMode = "delegate" | "observe" | "moderate";

export type AutonomyLevel = "l0" | "l1" | "l2" | "l3" | "l4";

export type AutonomyClassifier = "heuristic" | "auto" | "llm";

export interface AssistantImWriteback {
  enabled: boolean;
  webhook_url?: string | null;
  inbound_secret?: string | null;
  notify_delegate?: boolean;
  notify_waiting_human?: boolean;
}

export interface GroupAssistantSettings {
  enabled: boolean;
  mode: AssistantMode;
  max_autonomy: AutonomyLevel;
  reply_after_experts: boolean;
  template_id?: string | null;
  autonomy_classifier?: AutonomyClassifier;
  classifier_provider_id?: string | null;
  classifier_model?: string | null;
  im_writeback?: AssistantImWriteback;
  notify_owner_proactively?: boolean;
  /** 代理人拍板后自动衔接专家执行（群聊与任务流统一） */
  continue_after_delegate_enabled?: boolean;
  continue_after_delegate_mode?: string;
}

export interface AssistantGlobalSettings {
  observe_enabled: boolean;
  observe_dm: boolean;
  observe_group: boolean;
  record_max_chars: number;
  record_weight: number;
  record_min_chars: number;
  record_skip_low_signal: boolean;
  record_assist_memo: boolean;
  observe_dedupe_secs: number;
  auto_consolidate: boolean;
  consolidate_every_n: number;
  auto_ingest_raw?: boolean;
  ingest_raw_batch_size?: number;
  embedding_enabled?: boolean;
  embedding_provider_id?: string | null;
  embedding_model?: string | null;
  ephemeral_ttl_hours?: number;
  evolution_enabled: boolean;
  evolution_token_budget_ratio?: number;
  evolution_token_budget_absolute?: number;
  evolution_tokens_used?: number;
  auto_extract_memories: boolean;
  proactive_enabled: boolean;
  proactive_batch_size: number;
  proactive_delegate_enabled: boolean;
  proactive_delegate_friend_ids: string[];
  monthly_token_budget: number;
  monthly_tokens_used: number;
  budget_period_ym?: string | null;
  tool_whitelist: string[];
  /** CLI 转发 WebSocket；空则服务端按环境变量推导 */
  cli_relay_ws_url?: string | null;
  /** `auto` | `ws` | `wss` */
  cli_relay_ws_scheme?: string;
  observe_streak?: number;
  updated_at?: string | null;
}

export interface AgentDnaPrinciple {
  id: string;
  text: string;
  required?: boolean;
}

export interface AgentDna {
  version: number;
  enabled: boolean;
  preamble: string;
  principles: AgentDnaPrinciple[];
  style?: { tone: string; language: string };
  enforcement?: { level: string };
  updated_at?: string | null;
}

export type AssistantTodoStatus = "pending" | "running" | "done" | "failed";

export interface AssistantTodo {
  id: string;
  owner_friend_id: string;
  title: string;
  detail?: string | null;
  repeat_rule?: string | null;
  next_run_at?: string | null;
  status: AssistantTodoStatus;
  priority: number;
  source_turn_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AssistantQueueJob {
  id: string;
  kind: string;
  payload?: string | null;
  attempts: number;
  max_attempts: number;
  status: string;
  last_error?: string | null;
  run_at: string;
}

export interface AssistantQueueStats {
  pending: number;
  running: number;
  done: number;
  failed: number;
  due_pending: number;
}

export interface AssistantPolicyTemplate {
  id: string;
  name: string;
  description: string | null;
  settings: GroupAssistantSettings;
  created_at: string;
}

export interface GroupTaskFlowSettings {
  enabled: boolean;
  campaign_enabled: boolean;
  leader_only_execute: boolean;
  plan_enabled?: boolean;
  plan_review_enabled?: boolean;
  peer_vote_enabled?: boolean;
  appoint_by_mention_enabled?: boolean;
  /** 沿用本群已选负责人，跳过竞选/选举/计划 */
  reuse_persisted_leader?: boolean;
  skip_plan_when_reuse_leader?: boolean;
  /** 须明确交付才结束；否则负责人继续引导，由助理监测空转 */
  require_clear_delivery?: boolean;
  /** 代理人发言后是否恢复任务流 */
  resume_after_delegate_enabled?: boolean;
  /** not_delivered | incomplete_only | judge | off */
  resume_after_delegate_mode?: string;
  resume_stagnation_suppress_rounds?: number;
  stagnation_min_leader_rounds?: number;
  stagnation_reply_similarity?: number;
}

export type IntentClassifier = "heuristic" | "auto" | "llm";

export interface GroupOrchestrationSettings {
  intent_classifier?: IntentClassifier;
  /** 轻量编排：跳过互投与计划评议 */
  light_task_flow?: boolean;
  /** 回合末自动整理群共识记忆 */
  group_memory_enabled?: boolean;
  /** 群共识记忆过期天数；0 表示不过期 */
  group_public_ttl_days?: number;
}

export interface GroupPublicMemoryLatest {
  id?: string;
  content: string;
  summary?: string | null;
  pinned?: boolean;
  importance?: number;
  updated_at: string;
}

export interface GroupPublicMemoryRaw {
  id: string;
  title?: string | null;
  content: string;
  created_at: string;
}

export interface GroupPublicMemoriesResponse {
  latest: GroupPublicMemoryLatest | null;
  raw_recent: GroupPublicMemoryRaw[];
  search_hits?: Array<{ id: string; content: string; title?: string | null }>;
}

export interface GroupSettings {
  judge_threshold: number;
  judge: GroupJudgeSettings;
  task_flow?: GroupTaskFlowSettings;
  assistant?: GroupAssistantSettings;
  orchestration?: GroupOrchestrationSettings;
  max_replies_per_turn: number;
  per_agent_max_per_turn: number;
  cooldown_ms: number;
  human_priority: boolean;
  human_pause_ms: number;
  allow_agent_to_agent: boolean;
  extra_system_prompt: string | null;
  /** 群聊共享 CLI 工作目录 */
  cli_workspace?: string | null;
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
  role?: GroupMemberRole;
  judge_override?: MemberJudgeOverride | null;
  profile_overlay?: MemberProfileOverlay | null;
  effective_profile?: MemberProfileSummary | null;
}

export interface GroupWorkspace {
  id: string;
  group_id: string;
  tenant_id: string;
  name: string;
  kind: string;
  git_url?: string | null;
  default_branch?: string | null;
  logical_key?: string | null;
  created_at: string;
}

export interface GroupMemberBinding {
  id: string;
  group_id: string;
  group_workspace_id: string;
  friend_id: string;
  execution_mode?: string | null;
  relay_id?: string | null;
  local_path?: string | null;
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
  expert_member_ids?: string[];
  assistant_member_id?: string | null;
  assistant_resolved?: GroupAssistantSettings;
  members?: GroupMemberConfig[];
  workspaces?: GroupWorkspace[];
  member_bindings?: GroupMemberBinding[];
  conversation_id?: string;
  task_flow_readiness?: GroupTaskFlowReadiness;
  profile_frameworks_version?: string;
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
  tier: string;
  scope: string;
  scope_ref: string | null;
  importance: number;
  status: string;
  title: string | null;
  summary: string | null;
  tenant_id?: string;
  expires_at?: string | null;
}

export interface MemoryIngestReport {
  raw_considered: number;
  raw_skipped_noise?: number;
  curated_created: number;
  raw_archived: number;
  llm_parse_failed?: boolean;
}

export interface CuratedOrganizeReport {
  curated_considered: number;
  updated: number;
  deleted: number;
}

export interface MemoryMaintenanceReport {
  expired_deleted: number;
  ingest: MemoryIngestReport;
  curated_organize?: CuratedOrganizeReport;
  embeddings_updated: number;
}

export interface AssistantMemoryStats {
  total: number;
  curated_active: number;
  raw_active: number;
  raw_archived: number;
  memo_count: number;
  knowledge_count: number;
  pinned_count: number;
  observe_count: number;
  assist_count: number;
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
      pitch_excerpt?: string | null;
    }
  | {
      type: "coordinator_plan";
      conversation_id: string;
      turn_id: string;
      planner_id: string;
      planner_name: string;
      assignee_ids: string[];
      assignee_names: string[];
      plan_excerpt: string;
    }
  | {
      type: "task_assignments_merged";
      conversation_id: string;
      turn_id: string;
      leader_id: string;
      leader_name: string;
      assignee_ids: string[];
      assignee_names: string[];
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
    }
  | {
      type: "assistant_owner_notify";
      conversation_id: string;
      group_id: string;
      group_name: string;
      title: string;
      body: string;
      message_id?: string | null;
    }
  | {
      type: "turn_intent_classified";
      conversation_id: string;
      turn_id: string;
      intent: string;
      classifier: string;
    }
  | {
      type: "group_public_updated";
      conversation_id: string;
      turn_id: string;
      group_id: string;
      excerpt: string;
    };
