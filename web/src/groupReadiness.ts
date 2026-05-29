import type {
  Friend,
  GroupJudgeSettings,
  GroupSettings,
  GroupTaskFlowReadiness,
  Provider,
  ProviderKey,
} from "./types";

const defaultReadiness = (): GroupTaskFlowReadiness => ({
  task_flow_enabled: false,
  ready: true,
  errors: [],
  warnings: [],
  agent_member_count: 0,
  judge_provider_id: null,
  judge_model: null,
  judge_key_configured: false,
});

function resolveJudgeModel(
  judge: GroupJudgeSettings,
  providers: Provider[],
): { providerId: string | null; model: string | null } {
  const providerId = judge.llm.provider_id?.trim() || null;
  if (!providerId) {
    return { providerId: null, model: null };
  }
  const explicit = judge.llm.model?.trim();
  if (explicit) {
    return { providerId, model: explicit };
  }
  const p = providers.find((x) => x.id === providerId);
  const dm = p?.default_model?.trim();
  if (dm) {
    return { providerId, model: dm };
  }
  if (providerId === "deepseek") {
    return { providerId, model: "deepseek-v4-flash" };
  }
  return { providerId, model: null };
}

function judgeKeyConfigured(
  judge: GroupJudgeSettings,
  providerKeys: ProviderKey[],
): boolean {
  const providerId = judge.llm.provider_id?.trim();
  if (!providerId) return false;
  const keyId = judge.llm.api_key_id?.trim();
  if (keyId) {
    const k = providerKeys.find((x) => x.id === keyId);
    if (k?.status === "active" && k.provider_id === providerId) return true;
  }
  return providerKeys.some(
    (k) => k.status === "active" && k.provider_id === providerId,
  );
}

/** 与后端 `group_validate` 对齐的客户端预检（无法检测环境变量 API Key）。 */
export function validateGroupTaskFlowReadiness(
  settings: GroupSettings,
  memberFriendIds: string[],
  friends: Friend[],
  providers: Provider[],
  providerKeys: ProviderKey[],
): GroupTaskFlowReadiness {
  const tf = settings.task_flow;
  if (!tf?.enabled) {
    return defaultReadiness();
  }

  const errors: string[] = [];
  const warnings: string[] = [];
  const friendMap = new Map(friends.map((f) => [f.id, f]));
  let agentMemberCount = 0;
  for (const id of memberFriendIds) {
    const f = friendMap.get(id);
    if (!f) {
      warnings.push(`成员 ${id} 不存在，已忽略`);
      continue;
    }
    if (f.backend_kind !== "human") {
      agentMemberCount += 1;
    }
  }

  if (agentMemberCount === 0) {
    errors.push(
      "已开启任务流，但群内没有可执行任务的 Agent 成员（需至少一位非「人类」好友）",
    );
  } else if (
    agentMemberCount < 2 &&
    (tf.campaign_enabled || tf.peer_vote_enabled)
  ) {
    warnings.push(
      `任务流含竞选/互投，建议至少 2 位 Agent；当前仅 ${agentMemberCount} 位`,
    );
  }

  const providerId = settings.judge.llm.provider_id?.trim();
  if (!providerId) {
    errors.push(
      "任务流需要 Judge LLM：请在「群 Judge」中选择 Provider（服务端也可通过 SEVEN_CHAT_AGENT_JUDGE_PROVIDER 环境变量指定）",
    );
  } else if (!providers.some((p) => p.id === providerId)) {
    errors.push(
      `Judge Provider「${providerId}」未在系统中注册，请先在设置中配置 Provider`,
    );
  }

  const { model } = resolveJudgeModel(settings.judge, providers);
  if (providerId && !model) {
    errors.push(
      `任务流 Judge 未配置模型：请为 Provider「${providerId}」填写模型，或确保该 Provider 有默认模型`,
    );
  }

  const keyOk = providerId ? judgeKeyConfigured(settings.judge, providerKeys) : false;
  if (providerId && !keyOk) {
    errors.push(
      `Judge Provider「${providerId}」没有可用的 API Key：请在设置中添加 Key，或配置环境变量 ${providerId.toUpperCase().replace(/-/g, "_")}_API_KEY（环境变量仅服务端保存时生效）`,
    );
  }

  if (settings.judge.mode === "heuristic") {
    warnings.push(
      "群 Judge 模式为「启发式」，但任务流的竞选/互投/选举仍依赖 LLM；请确认上方 Provider 与 Key 可用",
    );
  }

  return {
    task_flow_enabled: true,
    ready: errors.length === 0,
    errors,
    warnings,
    agent_member_count: agentMemberCount,
    judge_provider_id: providerId ?? null,
    judge_model: model,
    judge_key_configured: keyOk,
  };
}
