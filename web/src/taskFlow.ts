/** 群任务流一轮状态（WebSocket 事件累积） */

export type TaskFlowPhaseKey =
  | "coordinator_plan"
  | "campaign"
  | "peer_vote"
  | "election"
  | "appoint"
  | "plan"
  | "plan_review"
  | "execute"
  | "reuse_leader"
  | "guide"
  | "delivered"
  | "stalled";

export const TASK_FLOW_PHASES: {
  key: TaskFlowPhaseKey;
  label: string;
}[] = [
  { key: "coordinator_plan", label: "⓪ 协调分工" },
  { key: "campaign", label: "① 竞选" },
  { key: "peer_vote", label: "② 互投" },
  { key: "election", label: "③ 选举" },
  { key: "plan", label: "④ 计划" },
  { key: "plan_review", label: "⑤ 评议" },
  { key: "reuse_leader", label: "沿用负责人" },
  { key: "execute", label: "⑥ 执行" },
  { key: "guide", label: "⑦ 引导" },
  { key: "delivered", label: "⑧ 交付" },
  { key: "stalled", label: "⏸ 暂停" },
];

export interface TaskFlowVote {
  voterName: string;
  endorseName: string;
  reason: string;
  ok: boolean;
  error?: string;
}

export interface TaskFlowCoordinatorPlan {
  plannerName: string;
  assigneeNames: string[];
  planExcerpt: string;
}

export interface TaskFlowSelfNomination {
  name: string;
  excerpt: string;
}

export interface TaskFlowRound {
  turnId: string;
  currentPhase: TaskFlowPhaseKey | "appoint" | null;
  phaseDetail: string | null;
  /** 已完成阶段 */
  completedPhases: TaskFlowPhaseKey[];
  campaignDone: string[];
  coordinatorPlan: TaskFlowCoordinatorPlan | null;
  selfNominations: TaskFlowSelfNomination[];
  mergedAssignees: string[] | null;
  votes: TaskFlowVote[];
  election: {
    leaderName: string;
    reason: string;
    confidence: number;
    electionOk: boolean;
    peerVotesSummary: string | null;
  } | null;
  planLeader: string | null;
  planReviews: { name: string; excerpt: string }[];
  updatedAt: number;
}

export function emptyTaskFlowRound(turnId: string): TaskFlowRound {
  return {
    turnId,
    currentPhase: null,
    phaseDetail: null,
    completedPhases: [],
    campaignDone: [],
    coordinatorPlan: null,
    selfNominations: [],
    mergedAssignees: null,
    votes: [],
    election: null,
    planLeader: null,
    planReviews: [],
    updatedAt: Date.now(),
  };
}

export function phaseLabel(key: string): string {
  const found = TASK_FLOW_PHASES.find((p) => p.key === key);
  if (found) return found.label;
  if (key === "appoint") return "任命";
  if (key === "reuse_leader") return "沿用负责人";
  if (key === "guide") return "继续引导";
  if (key === "delivered") return "已交付";
  if (key === "stalled") return "助理暂停";
  return key;
}

export function markPhaseDone(
  round: TaskFlowRound,
  phase: TaskFlowPhaseKey,
): TaskFlowRound {
  const completed = round.completedPhases.includes(phase)
    ? round.completedPhases
    : [...round.completedPhases, phase];
  return { ...round, completedPhases: completed, updatedAt: Date.now() };
}
