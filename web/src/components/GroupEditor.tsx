import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { providerDisplayName } from "../providerDefaults";
import { validateGroupTaskFlowReadiness } from "../groupReadiness";
import { useChat } from "../stores/chat";
import type {
  AssistantPolicyTemplate,
  GroupAssistantSettings,
  GroupJudgeSettings,
  GroupMemberConfig,
  GroupSettings,
  JudgeMode,
  MemberJudgeOverride,
} from "../types";

interface Props {
  groupId: string | null;
  onClose: () => void;
}

const defaultJudge: GroupJudgeSettings = {
  mode: "heuristic",
  threshold: 0.55,
  heuristic: {
    user_confidence: 0.72,
    friend_confidence: 0.58,
    mention_confidence: 0.92,
    user_delay_ms: 300,
    friend_delay_ms: 500,
    mention_delay_ms: 100,
  },
  llm: { provider_id: null, model: null, api_key_id: null },
  fallback_pick_top: true,
};

const defaultTaskFlow = {
  enabled: false,
  campaign_enabled: true,
  leader_only_execute: true,
  plan_enabled: true,
  plan_review_enabled: true,
  peer_vote_enabled: true,
  appoint_by_mention_enabled: true,
};

const defaultImWriteback = {
  enabled: false,
  webhook_url: null as string | null,
  inbound_secret: null as string | null,
  notify_delegate: true,
  notify_waiting_human: true,
};

const defaultAssistant: GroupAssistantSettings = {
  enabled: true,
  mode: "delegate",
  max_autonomy: "l2",
  reply_after_experts: true,
  template_id: "preset-delegate",
  autonomy_classifier: "auto",
  im_writeback: defaultImWriteback,
};

const PRIMARY_WORKSPACE_KEY = "primary";

function isRelayFriend(f: { backend_config?: Record<string, unknown> }) {
  return f.backend_config?.execution_mode === "relay";
}

const defaults: GroupSettings = {
  judge_threshold: defaultJudge.threshold,
  judge: defaultJudge,
  task_flow: defaultTaskFlow,
  assistant: defaultAssistant,
  max_replies_per_turn: 8,
  per_agent_max_per_turn: 2,
  cooldown_ms: 4000,
  human_priority: true,
  human_pause_ms: 30000,
  allow_agent_to_agent: true,
  extra_system_prompt: null,
  cli_workspace: null,
};

function normalizeSettings(raw: Partial<GroupSettings>): GroupSettings {
  const base = { ...defaults, ...raw };
  const judge = { ...defaultJudge, ...raw.judge };
  judge.threshold = judge.threshold || base.judge_threshold || 0.55;
  base.judge = {
    ...defaultJudge,
    ...judge,
    heuristic: { ...defaultJudge.heuristic, ...judge.heuristic },
    llm: { ...defaultJudge.llm, ...judge.llm },
  };
  base.judge_threshold = judge.threshold;
  base.task_flow = { ...defaultTaskFlow, ...raw.task_flow };
  base.assistant = { ...defaultAssistant, ...raw.assistant };
  return base;
}

export function GroupEditor({ groupId, onClose }: Props) {
  const { friends, providers, providerKeys, reloadGroups, selectGroup } =
    useChat();
  const [name, setName] = useState("");
  const [memberIds, setMemberIds] = useState<Set<string>>(new Set());
  const [assistantMemberId, setAssistantMemberId] = useState<string | null>(
    null,
  );
  /** 本群内各成员的 Judge 覆盖（key=friend_id） */
  const [memberJudges, setMemberJudges] = useState<
    Record<string, MemberJudgeOverride>
  >({});
  const [settings, setSettings] = useState<GroupSettings>(defaults);
  const [policyTemplates, setPolicyTemplates] = useState<
    AssistantPolicyTemplate[]
  >([]);
  const [memberLocalPaths, setMemberLocalPaths] = useState<Record<string, string>>(
    {},
  );
  const [gitUrl, setGitUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listAssistantPolicyTemplates().then((r) => setPolicyTemplates(r.templates));
  }, []);
  const readiness = useMemo(
    () =>
      validateGroupTaskFlowReadiness(
        settings,
        Array.from(memberIds),
        friends,
        providers,
        providerKeys,
      ),
    [settings, memberIds, friends, providers, providerKeys],
  );

  useEffect(() => {
    if (!groupId) {
      setName("");
      setMemberIds(new Set());
      setMemberJudges({});
      setMemberLocalPaths({});
      setGitUrl("");
      setSettings(defaults);
      return;
    }
    api.getGroup(groupId).then((bundle) => {
      setName(bundle.group.name);
      const aid =
        bundle.assistant_member_id ??
        bundle.members?.find((m) => m.role === "assistant")?.friend_id ??
        null;
      setAssistantMemberId(aid);
      const experts =
        bundle.expert_member_ids ??
        bundle.member_ids.filter((id) => id !== aid);
      setMemberIds(new Set(experts));
      const judges: Record<string, MemberJudgeOverride> = {};
      for (const m of bundle.members ?? []) {
        if (m.judge_override) {
          judges[m.friend_id] = m.judge_override;
        }
      }
      setMemberJudges(judges);
      const paths: Record<string, string> = {};
      for (const b of bundle.member_bindings ?? []) {
        if (b.local_path) paths[b.friend_id] = b.local_path;
      }
      setMemberLocalPaths(paths);
      setGitUrl(bundle.workspaces?.[0]?.git_url ?? "");
      setSettings(normalizeSettings(bundle.group.settings));
    });
  }, [groupId]);

  function toggleMember(id: string) {
    const next = new Set(memberIds);
    if (next.has(id)) {
      next.delete(id);
      const { [id]: _, ...rest } = memberJudges;
      setMemberJudges(rest);
    } else {
      next.add(id);
    }
    setMemberIds(next);
  }

  function setMemberJudge(friendId: string, override: MemberJudgeOverride) {
    setMemberJudges((prev) => ({ ...prev, [friendId]: override }));
  }

  async function save() {
    if (!name.trim()) {
      setError("群名不能为空");
      return;
    }
    if (memberIds.size === 0) {
      setError("至少选一位专家好友进群（助理会自动加入）");
      return;
    }
    const toSave = normalizeSettings(settings);
    const precheck = validateGroupTaskFlowReadiness(
      toSave,
      Array.from(memberIds),
      friends,
      providers,
      providerKeys,
    );
    if (!precheck.ready) {
      setError(precheck.errors.join("；"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const builtinAssistant = friends.find((f) => f.is_builtin);
      const aid = assistantMemberId ?? builtinAssistant?.id ?? null;
      const members: GroupMemberConfig[] = Array.from(memberIds).map(
        (friend_id) => ({
          friend_id,
          role: "member" as const,
          judge_override: memberJudges[friend_id]?.use_group_default
            ? { use_group_default: true }
            : memberJudges[friend_id] ?? null,
        }),
      );
      if (aid) {
        members.push({ friend_id: aid, role: "assistant" });
      }
      const workspaces = gitUrl.trim()
        ? [
            {
              name: "主仓库",
              kind: "git" as const,
              git_url: gitUrl.trim(),
              default_branch: "main",
              logical_key: PRIMARY_WORKSPACE_KEY,
            },
          ]
        : [];
      const member_bindings = Array.from(memberIds).flatMap((friend_id) => {
        const f = friends.find((x) => x.id === friend_id);
        if (!f || !gitUrl.trim()) return [];
        const path = memberLocalPaths[friend_id]?.trim();
        const relay = isRelayFriend(f);
        if (!relay && !path) return [];
        return [
          {
            group_workspace_id: PRIMARY_WORKSPACE_KEY,
            friend_id,
            execution_mode: relay ? "relay" : "local",
            relay_id:
              relay && typeof f.backend_config?.relay_id === "string"
                ? f.backend_config.relay_id
                : null,
            local_path: path || null,
          },
        ];
      });
      const result = await api.upsertGroup({
        id: groupId ?? undefined,
        name: name.trim(),
        avatar: null,
        settings: toSave,
        members,
        workspaces,
        member_bindings,
      });
      await reloadGroups();
      await selectGroup(result.group.id);
      onClose();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40">
      <div className="card flex max-h-[90vh] w-[640px] flex-col overflow-hidden p-0">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h2 className="text-base font-semibold">
            {groupId ? "群聊设置" : "新建群聊"}
          </h2>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <div>
            <label className="label">群名</label>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：周末研讨"
            />
          </div>
          {(() => {
            const hex = friends.find((f) => f.is_builtin);
            if (!hex) return null;
            return (
              <div className="rounded-md border border-violet-200 bg-violet-50/60 p-3">
                <div className="text-xs font-semibold text-violet-900">
                  群助理（用户代理人）
                </div>
                <p className="mt-1 text-xs text-slate-600">
                  {hex.name} 默认加入本群，代你处理小事、大事上报；不参与专家抢答。
                </p>
                <label className="mt-2 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={settings.assistant?.enabled !== false}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        assistant: {
                          ...defaultAssistant,
                          ...settings.assistant,
                          enabled: e.target.checked,
                        },
                      })
                    }
                  />
                  启用助理
                </label>
                <div className="mt-2">
                  <label className="label text-xs">策略模板</label>
                  <select
                    className="input text-xs"
                    value={settings.assistant?.template_id ?? ""}
                    onChange={(e) => {
                      const tid = e.target.value || null;
                      const tpl = policyTemplates.find((t) => t.id === tid);
                      setSettings({
                        ...settings,
                        assistant: {
                          ...defaultAssistant,
                          ...settings.assistant,
                          ...(tpl
                            ? { ...tpl.settings, template_id: tid }
                            : { template_id: tid }),
                        },
                      });
                    }}
                  >
                    <option value="">（无模板，仅自定义）</option>
                    {policyTemplates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                  {settings.assistant?.template_id && (
                    <p className="mt-1 text-[11px] text-slate-500">
                      {policyTemplates.find(
                        (t) => t.id === settings.assistant?.template_id,
                      )?.description ?? ""}
                    </p>
                  )}
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <select
                    className="input text-xs"
                    value={settings.assistant?.autonomy_classifier ?? "heuristic"}
                    title="自治等级分类"
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        assistant: {
                          ...defaultAssistant,
                          ...settings.assistant,
                          autonomy_classifier: e.target
                            .value as GroupAssistantSettings["autonomy_classifier"],
                        },
                      })
                    }
                  >
                    <option value="heuristic">分类：启发式</option>
                    <option value="auto">分类：Auto（LLM+回退）</option>
                    <option value="llm">分类：仅 LLM</option>
                  </select>
                  <select
                    className="input text-xs"
                    value={settings.assistant?.mode ?? "delegate"}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        assistant: {
                          ...defaultAssistant,
                          ...settings.assistant,
                          mode: e.target.value as
                            | "delegate"
                            | "observe"
                            | "moderate",
                        },
                      })
                    }
                  >
                    <option value="delegate">delegate（代你）</option>
                    <option value="observe">observe（仅观察）</option>
                    <option value="moderate">moderate（仅 @ 时介入）</option>
                  </select>
                  <select
                    className="input text-xs"
                    title="最高自治等级"
                    value={settings.assistant?.max_autonomy ?? "l2"}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        assistant: {
                          ...defaultAssistant,
                          ...settings.assistant,
                          max_autonomy: e.target
                            .value as typeof defaultAssistant.max_autonomy,
                        },
                      })
                    }
                  >
                    <option value="l1">最高 L1</option>
                    <option value="l2">最高 L2</option>
                    <option value="l3">最高 L3</option>
                  </select>
                </div>
                <div className="mt-3 border-t border-violet-100 pt-3">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={
                        settings.assistant?.im_writeback?.enabled === true
                      }
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          assistant: {
                            ...defaultAssistant,
                            ...settings.assistant,
                            im_writeback: {
                              ...defaultImWriteback,
                              ...settings.assistant?.im_writeback,
                              enabled: e.target.checked,
                            },
                          },
                        })
                      }
                    />
                    外部 IM 回写（Webhook）
                  </label>
                  {settings.assistant?.im_writeback?.enabled && (
                    <div className="mt-2 space-y-2">
                      <input
                        className="input text-xs"
                        placeholder="出站 Webhook URL（Telegram/企微机器人等）"
                        value={
                          settings.assistant?.im_writeback?.webhook_url ?? ""
                        }
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            assistant: {
                              ...defaultAssistant,
                              ...settings.assistant,
                              im_writeback: {
                                ...defaultImWriteback,
                                ...settings.assistant?.im_writeback,
                                enabled: true,
                                webhook_url: e.target.value || null,
                              },
                            },
                          })
                        }
                      />
                      <input
                        className="input text-xs"
                        placeholder="入站密钥（请求头 X-SevenChatAgent-Im-Secret）"
                        value={
                          settings.assistant?.im_writeback?.inbound_secret ??
                          ""
                        }
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            assistant: {
                              ...defaultAssistant,
                              ...settings.assistant,
                              im_writeback: {
                                ...defaultImWriteback,
                                ...settings.assistant?.im_writeback,
                                enabled: true,
                                inbound_secret: e.target.value || null,
                              },
                            },
                          })
                        }
                      />
                      <p className="text-[11px] leading-relaxed text-slate-500">
                        入站：
                        <code className="rounded bg-white px-1">
                          POST /api/groups/{groupId ?? "{group_id}"}/im/inbound
                        </code>
                        ，body 含{" "}
                        <code className="rounded bg-white px-1">
                          user_message
                        </code>
                        、
                        <code className="rounded bg-white px-1">
                          approve_delegate
                        </code>
                        、
                        <code className="rounded bg-white px-1">
                          reject_delegate
                        </code>
                        。
                      </p>
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
          <div>
            <label className="label">专家成员（多选，可为本群单独设 Judge）</label>
            <div className="mt-1 max-h-48 space-y-2 overflow-y-auto rounded-md border border-slate-200 bg-slate-50 p-3">
              {friends
                .filter((f) => !f.is_builtin)
                .map((f) => {
                const inGroup = memberIds.has(f.id);
                const mj =
                  memberJudges[f.id] ?? ({ use_group_default: true } as MemberJudgeOverride);
                return (
                  <div
                    key={f.id}
                    className="rounded-md border border-slate-200 bg-white p-2"
                  >
                    <label className="flex cursor-pointer items-center gap-2">
                      <input
                        type="checkbox"
                        checked={inGroup}
                        onChange={() => toggleMember(f.id)}
                      />
                      <span className="text-sm font-medium">
                        {f.name}
                        {isRelayFriend(f) && (
                          <span className="ml-1" title="远程 CLI relay">
                            🛰
                          </span>
                        )}
                        <span className="ml-1 text-xs font-normal text-slate-500">
                          · {f.backend_kind}
                        </span>
                      </span>
                    </label>
                    {inGroup && f.backend_kind !== "human" && (
                      <div className="mt-2 border-t border-slate-100 pt-2 pl-6">
                        <label className="flex items-center gap-2 text-xs">
                          <input
                            type="checkbox"
                            checked={mj.use_group_default}
                            onChange={(e) =>
                              setMemberJudge(f.id, {
                                ...mj,
                                use_group_default: e.target.checked,
                              })
                            }
                          />
                          使用本群 Judge 默认
                        </label>
                        {!mj.use_group_default && (
                          <div className="mt-2 grid grid-cols-2 gap-2">
                            <select
                              className="input text-xs"
                              value={mj.mode ?? "heuristic"}
                              onChange={(e) =>
                                setMemberJudge(f.id, {
                                  ...mj,
                                  use_group_default: false,
                                  mode: e.target.value as JudgeMode,
                                })
                              }
                            >
                              <option value="heuristic">启发式</option>
                              <option value="llm">LLM</option>
                              <option value="auto">Auto</option>
                            </select>
                            <input
                              className="input text-xs"
                              type="number"
                              step={0.05}
                              min={0}
                              max={1}
                              title="接话阈值"
                              value={mj.threshold ?? settings.judge.threshold}
                              onChange={(e) =>
                                setMemberJudge(f.id, {
                                  ...mj,
                                  use_group_default: false,
                                  threshold: Number(e.target.value),
                                })
                              }
                            />
                          </div>
                        )}
                        {inGroup && gitUrl.trim() && f.backend_kind === "pty" && (
                          <div className="mt-2 border-t border-slate-100 pt-2 pl-6">
                            <label className="label text-xs">
                              {isRelayFriend(f)
                                ? "远程执行目录（本机路径）"
                                : "本机执行目录（可选）"}
                            </label>
                            <input
                              className="input font-mono text-xs"
                              value={memberLocalPaths[f.id] ?? ""}
                              onChange={(e) =>
                                setMemberLocalPaths((prev) => ({
                                  ...prev,
                                  [f.id]: e.target.value,
                                }))
                              }
                              placeholder={
                                isRelayFriend(f)
                                  ? "/home/you/projects/my-repo"
                                  : "留空则用群服务端目录"
                              }
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-md border border-amber-200 bg-amber-50/50 p-3">
            <div className="mb-2 text-xs font-semibold text-amber-900">
              Judge（接话判断）· seven-chat-agent-judge
            </div>
            <p className="mb-3 text-xs text-slate-600">
              <strong>启发式</strong>：用固定规则打分（例如用户发言 →
              0.72 分），不调用大模型，快且免费。
              <strong>LLM</strong>：用大模型判断是否接话。
              <strong>Auto</strong>：先 LLM，失败再启发式。上方为<strong>本群默认</strong>；每位成员可在成员列表里单独覆盖（仅在本群生效）。
            </p>
            <div className="mb-3">
              <label className="label">模式</label>
              <select
                className="input"
                value={settings.judge.mode}
                onChange={(e) => {
                  const mode = e.target.value as JudgeMode;
                  setSettings({
                    ...settings,
                    judge: { ...settings.judge, mode },
                  });
                }}
              >
                <option value="heuristic">启发式（推荐）</option>
                <option value="llm">LLM</option>
                <option value="auto">Auto（LLM + 回退）</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <NumberField
                label="接话阈值 threshold"
                value={settings.judge.threshold}
                step={0.05}
                min={0}
                max={1}
                onChange={(v) =>
                  setSettings({
                    ...settings,
                    judge_threshold: v,
                    judge: { ...settings.judge, threshold: v },
                  })
                }
              />
              <div className="flex items-end gap-2 pb-1">
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={settings.judge.fallback_pick_top}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        judge: {
                          ...settings.judge,
                          fallback_pick_top: e.target.checked,
                        },
                      })
                    }
                  />
                  未过阈值时最高分兜底 1 人
                </label>
              </div>
            </div>
            {(settings.judge.mode === "heuristic" ||
              settings.judge.mode === "auto") && (
              <div className="mt-3 grid grid-cols-2 gap-3 border-t border-amber-100 pt-3">
                <NumberField
                  label="用户消息 confidence"
                  value={settings.judge.heuristic.user_confidence}
                  step={0.05}
                  min={0}
                  max={1}
                  onChange={(v) =>
                    setSettings({
                      ...settings,
                      judge: {
                        ...settings.judge,
                        heuristic: {
                          ...settings.judge.heuristic,
                          user_confidence: v,
                        },
                      },
                    })
                  }
                />
                <NumberField
                  label="成员互聊 confidence"
                  value={settings.judge.heuristic.friend_confidence}
                  step={0.05}
                  min={0}
                  max={1}
                  onChange={(v) =>
                    setSettings({
                      ...settings,
                      judge: {
                        ...settings.judge,
                        heuristic: {
                          ...settings.judge.heuristic,
                          friend_confidence: v,
                        },
                      },
                    })
                  }
                />
              </div>
            )}
            {(settings.judge.mode === "llm" ||
              settings.judge.mode === "auto") && (
              <div className="mt-3 space-y-3 border-t border-amber-100 pt-3">
                <p className="text-xs text-slate-600">
                  Provider 只表示接口类型（DeepSeek / OpenAI 等），<strong>API Key 不在 Provider 行里填写</strong>。
                  请在左侧栏点「设置」→「API Keys」添加密钥；此处可选已保存的 Key，不选则用该
                  Provider 下第一个可用 Key 或环境变量{" "}
                  <code className="text-[11px]">
                    {settings.judge.llm.provider_id
                      ? `${settings.judge.llm.provider_id.toUpperCase().replace(/-/g, "_")}_API_KEY`
                      : "PROVIDER_API_KEY"}
                  </code>
                  。
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="label">Judge Provider（群级）</label>
                    <select
                      className="input"
                      value={settings.judge.llm.provider_id ?? ""}
                      onChange={(e) => {
                        const pid = e.target.value || null;
                        const prov = providers.find((p) => p.id === pid);
                        const keys = providerKeys.filter(
                          (k) => k.provider_id === pid,
                        );
                        const keepKey =
                          settings.judge.llm.api_key_id &&
                          keys.some((k) => k.id === settings.judge.llm.api_key_id)
                            ? settings.judge.llm.api_key_id
                            : null;
                        const nextModel =
                          settings.judge.llm.model?.trim() ||
                          prov?.default_model ||
                          (pid === "deepseek" ? "deepseek-v4-flash" : null);
                        setSettings({
                          ...settings,
                          judge: {
                            ...settings.judge,
                            llm: {
                              ...settings.judge.llm,
                              provider_id: pid,
                              api_key_id: keepKey,
                              model: nextModel,
                            },
                          },
                        });
                      }}
                    >
                      <option value="">（未选：LLM judge 无法解析 Provider）</option>
                      {providers.map((p) => (
                        <option key={p.id} value={p.id}>
                          {providerDisplayName(p.display_name) || p.id}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="label">Judge 模型</label>
                    <input
                      className="input"
                      placeholder={
                        providers.find(
                          (p) => p.id === settings.judge.llm.provider_id,
                        )?.default_model || "如 gpt-4o-mini"
                      }
                      value={settings.judge.llm.model ?? ""}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          judge: {
                            ...settings.judge,
                            llm: {
                              ...settings.judge.llm,
                              model: e.target.value || null,
                            },
                          },
                        })
                      }
                    />
                  </div>
                </div>
                {settings.judge.llm.provider_id && (
                  <div>
                    <label className="label">Judge API Key（可选）</label>
                    <select
                      className="input"
                      value={settings.judge.llm.api_key_id ?? ""}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          judge: {
                            ...settings.judge,
                            llm: {
                              ...settings.judge.llm,
                              api_key_id: e.target.value || null,
                            },
                          },
                        })
                      }
                    >
                      <option value="">
                        自动（该 Provider 下第一个 active Key）
                      </option>
                      {providerKeys
                        .filter(
                          (k) =>
                            k.provider_id === settings.judge.llm.provider_id,
                        )
                        .map((k) => (
                          <option key={k.id} value={k.id}>
                            {k.label} ({k.status})
                          </option>
                        ))}
                    </select>
                    {providerKeys.filter(
                      (k) => k.provider_id === settings.judge.llm.provider_id,
                    ).length === 0 && (
                      <p className="mt-1 text-xs text-amber-800">
                        该 Provider 尚无 Key，请打开左侧「设置」→「API Keys」添加后再保存本群。
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="rounded-md border border-violet-200 bg-violet-50/50 p-3">
            <div className="mb-2 text-xs font-semibold text-violet-900">
              任务编排（竞选负责人）
            </div>
            <p className="mb-3 text-xs text-slate-600">
              开启后，用户每条消息将先经<strong>竞选 → LLM 选举负责人 → 负责人执行</strong>，不再全员「接一句闲聊」。选举需配置上方 Judge LLM Provider。
            </p>
            <label className="mb-2 flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={settings.task_flow?.enabled ?? false}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    task_flow: {
                      ...defaultTaskFlow,
                      ...settings.task_flow,
                      enabled: e.target.checked,
                    },
                  })
                }
              />
              启用任务流（推荐工程讨论群）
            </label>
            {(settings.task_flow?.enabled ?? false) && (
              <div className="mt-2 space-y-2 pl-6">
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={settings.task_flow?.campaign_enabled ?? true}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        task_flow: {
                          ...defaultTaskFlow,
                          ...settings.task_flow,
                          enabled: true,
                          campaign_enabled: e.target.checked,
                        },
                      })
                    }
                  />
                  竞选发言（每人陈述优势争取当负责人）
                </label>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={settings.task_flow?.leader_only_execute ?? true}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        task_flow: {
                          ...defaultTaskFlow,
                          ...settings.task_flow,
                          enabled: true,
                          leader_only_execute: e.target.checked,
                        },
                      })
                    }
                  />
                  仅负责人执行（本轮禁止 Agent 接龙闲聊）
                </label>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={settings.task_flow?.peer_vote_enabled ?? true}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        task_flow: {
                          ...defaultTaskFlow,
                          ...settings.task_flow,
                          enabled: true,
                          peer_vote_enabled: e.target.checked,
                        },
                      })
                    }
                  />
                  竞选后成员互投（背书），再 LLM 计票选举
                </label>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={settings.task_flow?.plan_enabled ?? true}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        task_flow: {
                          ...defaultTaskFlow,
                          ...settings.task_flow,
                          enabled: true,
                          plan_enabled: e.target.checked,
                        },
                      })
                    }
                  />
                  负责人先发布计划（本阶段不跑工具）
                </label>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={settings.task_flow?.plan_review_enabled ?? true}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        task_flow: {
                          ...defaultTaskFlow,
                          ...settings.task_flow,
                          enabled: true,
                          plan_review_enabled: e.target.checked,
                        },
                      })
                    }
                  />
                  计划发布后他人 1 条评议
                </label>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={settings.task_flow?.appoint_by_mention_enabled ?? true}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        task_flow: {
                          ...defaultTaskFlow,
                          ...settings.task_flow,
                          enabled: true,
                          appoint_by_mention_enabled: e.target.checked,
                        },
                      })
                    }
                  />
                  用户 @成员 时跳过竞选直接任命
                </label>
                <div
                  className={`mt-3 rounded-md border p-3 text-sm ${
                    readiness.ready
                      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                      : "border-amber-300 bg-amber-50 text-amber-950"
                  }`}
                >
                  <div className="mb-1 font-semibold">
                    {readiness.ready
                      ? "任务流就绪，可保存"
                      : "任务流未就绪（保存将被拒绝）"}
                  </div>
                  {readiness.task_flow_enabled && (
                    <p className="text-xs opacity-80">
                      Agent 成员 {readiness.agent_member_count} 人
                      {readiness.judge_provider_id
                        ? ` · Judge ${readiness.judge_provider_id}${
                            readiness.judge_model
                              ? ` / ${readiness.judge_model}`
                              : ""
                          }${readiness.judge_key_configured ? " · Key ✓" : " · Key ✗"}`
                        : ""}
                    </p>
                  )}
                  {readiness.errors.map((e) => (
                    <p key={e} className="mt-1 text-xs">
                      • {e}
                    </p>
                  ))}
                  {readiness.warnings.map((w) => (
                    <p key={w} className="mt-1 text-xs text-amber-800">
                      ※ {w}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 text-xs font-semibold text-slate-600">
              群聊调度参数（防风暴）
            </div>
            <div className="grid grid-cols-2 gap-3">
              <NumberField
                label="max_replies_per_turn"
                value={settings.max_replies_per_turn}
                step={1}
                onChange={(v) =>
                  setSettings({ ...settings, max_replies_per_turn: v })
                }
              />
              <NumberField
                label="per_agent_max_per_turn"
                value={settings.per_agent_max_per_turn}
                step={1}
                onChange={(v) =>
                  setSettings({ ...settings, per_agent_max_per_turn: v })
                }
              />
              <NumberField
                label="cooldown_ms"
                value={settings.cooldown_ms}
                step={500}
                onChange={(v) =>
                  setSettings({ ...settings, cooldown_ms: v })
                }
              />
              <NumberField
                label="human_pause_ms"
                value={settings.human_pause_ms}
                step={1000}
                onChange={(v) =>
                  setSettings({ ...settings, human_pause_ms: v })
                }
              />
              <div className="space-y-1">
                <label className="label">human_priority</label>
                <input
                  type="checkbox"
                  checked={settings.human_priority}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      human_priority: e.target.checked,
                    })
                  }
                />
              </div>
              <div className="space-y-1">
                <label className="label">允许好友互回</label>
                <input
                  type="checkbox"
                  checked={settings.allow_agent_to_agent}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      allow_agent_to_agent: e.target.checked,
                    })
                  }
                />
              </div>
            </div>
            <div className="mt-3">
              <label className="label">群 Git 仓库（逻辑项目）</label>
              <input
                className="input font-mono text-xs"
                value={gitUrl}
                onChange={(e) => setGitUrl(e.target.value)}
                placeholder="https://github.com/org/repo.git（可选）"
              />
              <p className="mt-1 text-xs text-slate-500">
                多机协作以 Git 为真相源；远程 CLI（🛰）成员在各自机器上 clone
                后填写「远程执行目录」，不会使用下方服务端群目录。
              </p>
            </div>
            <div className="mt-3">
              <label className="label">群共享 CLI 工作目录（仅 local 成员）</label>
              <input
                className="input font-mono text-xs"
                value={settings.cli_workspace ?? ""}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    cli_workspace: e.target.value.trim() || null,
                  })
                }
                placeholder="留空则 data/cli-workspaces/groups/<群ID>"
              />
              <p className="mt-1 text-xs text-slate-500">
                仅在本服务器执行的 Pty 成员使用；relay 成员忽略此目录。
              </p>
            </div>
            <div className="mt-3">
              <label className="label">群规 prompt（拼到每位成员人设后）</label>
              <textarea
                rows={3}
                className="input"
                value={settings.extra_system_prompt ?? ""}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    extra_system_prompt: e.target.value || null,
                  })
                }
                placeholder="例如：本群讨论 Rust 异步编程，请尽量简洁。"
              />
            </div>
          </div>

          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <button className="btn" onClick={onClose}>
            取消
          </button>
          <button
            className="btn-primary"
            onClick={save}
            disabled={
              busy || (readiness.task_flow_enabled && !readiness.ready)
            }
          >
            {busy ? "保存中..." : "保存"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function NumberField({
  label,
  value,
  step,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  step?: number;
  min?: number;
  max?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        className="input"
        type="number"
        step={step}
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
