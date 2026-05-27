import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { validateGroupTaskFlowReadiness } from "../groupReadiness";
import { useChat } from "../stores/chat";
import type {
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

const defaults: GroupSettings = {
  judge_threshold: defaultJudge.threshold,
  judge: defaultJudge,
  task_flow: defaultTaskFlow,
  max_replies_per_turn: 8,
  per_agent_max_per_turn: 2,
  cooldown_ms: 4000,
  human_priority: true,
  human_pause_ms: 30000,
  allow_agent_to_agent: true,
  extra_system_prompt: null,
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
  return base;
}

export function GroupEditor({ groupId, onClose }: Props) {
  const { friends, providers, providerKeys, reloadGroups, selectGroup } =
    useChat();
  const [name, setName] = useState("");
  const [memberIds, setMemberIds] = useState<Set<string>>(new Set());
  /** 本群内各成员的 Judge 覆盖（key=friend_id） */
  const [memberJudges, setMemberJudges] = useState<
    Record<string, MemberJudgeOverride>
  >({});
  const [settings, setSettings] = useState<GroupSettings>(defaults);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
      setSettings(defaults);
      return;
    }
    api.getGroup(groupId).then((bundle) => {
      setName(bundle.group.name);
      setMemberIds(new Set(bundle.member_ids));
      const judges: Record<string, MemberJudgeOverride> = {};
      for (const m of bundle.members ?? []) {
        if (m.judge_override) {
          judges[m.friend_id] = m.judge_override;
        }
      }
      setMemberJudges(judges);
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
      setError("至少选一位好友进群");
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
      const members: GroupMemberConfig[] = Array.from(memberIds).map(
        (friend_id) => ({
          friend_id,
          judge_override: memberJudges[friend_id]?.use_group_default
            ? { use_group_default: true }
            : memberJudges[friend_id] ?? null,
        }),
      );
      const result = await api.upsertGroup({
        id: groupId ?? undefined,
        name: name.trim(),
        avatar: null,
        settings: toSave,
        members,
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
          <div>
            <label className="label">成员（多选，可为本群单独设 Judge）</label>
            <div className="mt-1 max-h-48 space-y-2 overflow-y-auto rounded-md border border-slate-200 bg-slate-50 p-3">
              {friends.map((f) => {
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
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-md border border-amber-200 bg-amber-50/50 p-3">
            <div className="mb-2 text-xs font-semibold text-amber-900">
              Judge（接话判断）· honeycomb-judge
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
                          {p.display_name || p.id}
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
