import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useChat } from "../stores/chat";
import type { BackendKind, Friend, Provider, ProviderKey } from "../types";

interface Props {
  friendId: string | null;
  onClose: () => void;
}

export function FriendEditor({ friendId, onClose }: Props) {
  const { providers, providerKeys, reloadFriends, reloadProviders, selectFriend } =
    useChat();
  const [draft, setDraft] = useState<FriendDraft>(emptyDraft());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canDelete = !!friendId && !draft.is_builtin;

  useEffect(() => {
    if (!friendId) {
      setDraft(emptyDraft());
      return;
    }
    api.getFriend(friendId).then(({ friend }) => setDraft(fromFriend(friend)));
  }, [friendId]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      let d = draft;
      if (
        d.backend_kind === "pty" &&
        d.pty.preset === "worker-bee-cli" &&
        d.pty.api_key_secret.trim()
      ) {
        const id = await persistProviderKey({
          providerId: d.pty.provider_id,
          apiKeyId: d.pty.api_key_id,
          secret: d.pty.api_key_secret,
          label: `${d.name || "工蜂"} · ${d.pty.provider_id}`,
        });
        d = { ...d, pty: { ...d.pty, api_key_id: id, api_key_secret: "" } };
      }
      if (d.backend_kind === "pty" && !d.pty.preset.trim()) {
        setError("请选择 CLI 预设（Codex / Claude / Worker Bee 等）");
        setBusy(false);
        return;
      }
      const body = toApi(d);
      const { friend } = await api.upsertFriend(body);
      await reloadFriends();
      const keyWritten = draft.pty.api_key_secret.trim();
      if (keyWritten) {
        await reloadProviders();
      }
      await selectFriend(friend.id);
      onClose();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!friendId || draft.is_builtin) return;
    if (
      !confirm(
        `确定删除好友「${draft.name || "未命名"}」吗？\n相关私聊会话与消息会一并删除。`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.deleteFriend(friendId);
      await reloadFriends();
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
            {friendId ? "编辑好友" : "添加好友"}
          </h2>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <div>
            <label className="label">名字</label>
            <input
              className="input"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">性格 / 一句话介绍</label>
            <input
              className="input"
              value={draft.personality}
              onChange={(e) =>
                setDraft({ ...draft, personality: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label">人设 prompt</label>
            <textarea
              rows={4}
              className="input"
              value={draft.system_prompt}
              onChange={(e) =>
                setDraft({ ...draft, system_prompt: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label">关注点（逗号分隔）</label>
            <input
              className="input"
              value={draft.focus_tags.join(",")}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  focus_tags: e.target.value
                    .split(/[,，]/)
                    .map((t) => t.trim())
                    .filter(Boolean),
                })
              }
            />
          </div>
          <div>
            <label className="label">后端类型</label>
            <div className="mt-1 flex gap-2">
              {(["pty", "human"] as BackendKind[]).map((k) => (
                <button
                  key={k}
                  className={`btn ${draft.backend_kind === k ? "border-honey-500 bg-honey-50" : ""}`}
                  onClick={() => setDraft({ ...draft, backend_kind: k })}
                >
                  {backendLabel(k)}
                </button>
              ))}
            </div>
            <p className="mt-1 text-xs text-slate-500">
              **Agent** 选 CLI 引擎：外部 claude/codex，或 **Worker Bee（工蜂）**（可建多个实例；技能库、长期记忆与
              API 均在下方配置，与内置 Hex 相同模型）。
            </p>
          </div>
          {draft.backend_kind === "pty" && (
            <PtyConfigEditor
              draft={draft}
              setDraft={setDraft}
              providers={providers}
              providerKeys={providerKeys}
            />
          )}
          {draft.backend_kind === "human" && (
            <HumanConfigEditor draft={draft} setDraft={setDraft} />
          )}
          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}
        </div>
        <footer className="flex items-center justify-between gap-2 border-t border-slate-200 px-5 py-3">
          <div>
            {canDelete && (
              <button
                className="btn text-red-600 hover:bg-red-50"
                onClick={remove}
                disabled={busy}
              >
                删除好友
              </button>
            )}
            {friendId && draft.is_builtin && (
              <span className="text-xs text-slate-500">
                内置好友不可删除；重复的那条需先重启 server 自愈后再删。
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <button className="btn" onClick={onClose}>
              取消
            </button>
            <button className="btn-primary" onClick={save} disabled={busy}>
              {busy ? "保存中..." : "保存"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

interface FriendDraft {
  id: string | null;
  is_builtin: boolean;
  name: string;
  personality: string;
  system_prompt: string;
  focus_tags: string[];
  backend_kind: BackendKind;
  api: {
    provider_id: string;
    model: string;
    api_key_id: string | null;
    temperature?: number;
    max_tokens?: number;
  };
  pty: {
    preset: string;
    cmd: string;
    args: string;
    cwd: string;
    provider_id: string;
    model: string;
    api_key_id: string | null;
    /** 仅前端草稿，保存时写入 vault 后清空 */
    api_key_secret: string;
    skills_dir: string;
    memory_top_k: number;
  };
  human: {
    channel: string;
    endpoint: string;
  };
}

function emptyDraft(): FriendDraft {
  return {
    id: null,
    is_builtin: false,
    name: "",
    personality: "",
    system_prompt: "你是 [name]，活跃在 honeycomb 多 Agent 聊天室。",
    focus_tags: [],
    backend_kind: "pty",
    api: { provider_id: "openai", model: "gpt-4o-mini", api_key_id: null },
    pty: {
      preset: "claude",
      cmd: "claude",
      args: "",
      cwd: "",
      provider_id: "openai",
      model: "gpt-4o-mini",
      api_key_id: null,
      api_key_secret: "",
      skills_dir: "data/skills",
      memory_top_k: 5,
    },
    human: { channel: "invite", endpoint: "" },
  };
}

function fromFriend(f: Friend): FriendDraft {
  const draft = emptyDraft();
  draft.id = f.id;
  draft.is_builtin = f.is_builtin;
  draft.name = f.name;
  draft.personality = f.personality || "";
  draft.system_prompt = f.system_prompt || "";
  draft.focus_tags = f.focus_tags || [];
  draft.backend_kind = f.backend_kind;
  if (f.backend_kind === "api") {
    draft.backend_kind = "pty";
    draft.pty = {
      preset: "worker-bee-cli",
      cmd: ptyCmdForPreset("worker-bee-cli"),
      args: "",
      cwd: "",
      provider_id: f.backend_config?.provider_id || "",
      model: f.backend_config?.model || "",
      api_key_id: f.backend_config?.api_key_id || null,
      api_key_secret: "",
      skills_dir: f.backend_config?.skills_dir || "data/skills",
      memory_top_k: f.backend_config?.memory_top_k ?? 5,
    };
  } else if (f.backend_kind === "pty" || f.backend_kind === "assistant") {
    const rawPreset = f.backend_config?.preset;
    const preset =
      (typeof rawPreset === "string" && rawPreset.trim()) ||
      (f.backend_kind === "assistant" ? "worker-bee-cli" : "");
    const isExternal =
      preset === "codex-exec" || preset === "claude" || preset === "cursor";
    draft.backend_kind = "pty";
    draft.pty = {
      preset,
      cmd: ptyCmdForPreset(
        preset,
        f.backend_config?.cmd ||
          (preset === "codex-exec"
            ? "codex"
            : preset === "worker-bee-cli"
              ? "worker-bee"
              : "claude"),
      ),
      args:
        preset === "custom" && Array.isArray(f.backend_config?.args)
          ? f.backend_config.args.join(" ")
          : "",
      cwd: f.backend_config?.cwd || "",
      provider_id: isExternal ? "" : f.backend_config?.provider_id || "",
      model: isExternal ? "" : f.backend_config?.model || "",
      api_key_id: isExternal ? null : f.backend_config?.api_key_id || null,
      api_key_secret: "",
      skills_dir: isExternal ? "data/skills" : f.backend_config?.skills_dir || "data/skills",
      memory_top_k: isExternal ? 5 : f.backend_config?.memory_top_k ?? 5,
    };
  } else if (f.backend_kind === "human") {
    draft.human = {
      channel: f.backend_config?.channel || "invite",
      endpoint: f.backend_config?.endpoint || "",
    };
  }
  return draft;
}

function toApi(d: FriendDraft) {
  let backend_kind = d.backend_kind;
  let backend_config: any = {};
  if (d.backend_kind === "pty") {
    const preset = d.pty.preset.trim();
    if (!preset) {
      throw new Error("CLI 预设不能为空");
    }
    backend_config = {
      preset,
      ...(d.pty.cwd.trim() ? { cwd: d.pty.cwd.trim() } : {}),
    };
    if (d.pty.preset === "custom") {
      Object.assign(backend_config, {
        cmd: d.pty.cmd,
        args: d.pty.args.split(/\s+/).filter(Boolean),
      });
    }
    if (d.pty.preset === "worker-bee-cli") {
      Object.assign(backend_config, {
        preset: "worker-bee-cli",
        provider_id: d.pty.provider_id,
        model: d.pty.model,
        api_key_id: d.pty.api_key_id,
        skills_dir: d.pty.skills_dir,
        memory_top_k: d.pty.memory_top_k,
      });
    } else if (
      d.pty.preset === "codex-exec" ||
      d.pty.preset === "claude" ||
      d.pty.preset === "cursor"
    ) {
      backend_config.preset = d.pty.preset;
      backend_config.cmd = ptyCmdForPreset(d.pty.preset);
    }
  } else if (d.backend_kind === "human") {
    backend_config = {
      channel: d.human.channel,
      endpoint: d.human.endpoint,
    };
  }
  return {
    id: d.id ?? undefined,
    name: d.name,
    system_prompt: d.system_prompt.replace("[name]", d.name),
    personality: d.personality,
    focus_tags: d.focus_tags,
    backend_kind,
    backend_config,
    judge_provider_ref: null,
  };
}

async function persistProviderKey(opts: {
  providerId: string;
  apiKeyId: string | null;
  secret: string;
  label: string;
}): Promise<string> {
  const { provider_key } = await api.upsertProviderKey({
    id: opts.apiKeyId ?? undefined,
    provider_id: opts.providerId,
    label: opts.label,
    secret: opts.secret.trim(),
  });
  return provider_key.id;
}

function backendLabel(k: BackendKind) {
  switch (k) {
    case "pty":
      return "Agent (CLI)";
    case "human":
      return "真人";
    default:
      return "Agent";
  }
}

function WorkerBeeApiFields({
  providerId,
  model,
  apiKeyId,
  apiKeySecret,
  onChange,
  providers,
  providerKeys,
}: {
  providerId: string;
  model: string;
  apiKeyId: string | null;
  apiKeySecret: string;
  onChange: (api: {
    provider_id: string;
    model: string;
    api_key_id: string | null;
    api_key_secret: string;
  }) => void;
  providers: Provider[];
  providerKeys: ProviderKey[];
}) {
  const keysForProvider = providerKeys.filter((k) => k.provider_id === providerId);
  const boundKey = apiKeyId
    ? keysForProvider.find((k) => k.id === apiKeyId) ??
      providerKeys.find((k) => k.id === apiKeyId)
    : null;
  const envVar = `${providerId.toUpperCase().replace(/-/g, "_")}_API_KEY`;

  return (
    <div className="space-y-3 rounded-md border border-honey-200 bg-honey-50/40 p-3">
      <p className="text-xs text-honey-900">
        该<strong>工蜂实例</strong>绑定的平台 API：直接填写密钥（写入本地 vault），或选用「设置」里已保存的 Key。
      </p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Provider</label>
          <select
            className="input"
            value={providerId}
            onChange={(e) => {
              const nextProvider = e.target.value;
              const keys = providerKeys.filter((k) => k.provider_id === nextProvider);
              const keepKey =
                apiKeyId && keys.some((k) => k.id === apiKeyId) ? apiKeyId : null;
              onChange({
                provider_id: nextProvider,
                model,
                api_key_id: keepKey,
                api_key_secret: apiKeySecret,
              });
            }}
          >
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Model</label>
          <input
            className="input"
            value={model}
            onChange={(e) =>
              onChange({
                provider_id: providerId,
                model: e.target.value,
                api_key_id: apiKeyId,
                api_key_secret: apiKeySecret,
              })
            }
            placeholder={
              providers.find((p) => p.id === providerId)?.default_model || ""
            }
          />
        </div>
      </div>
      <div>
        <label className="label">API Key</label>
        <input
          className="input font-mono text-xs"
          type="password"
          value={apiKeySecret}
          onChange={(e) =>
            onChange({
              provider_id: providerId,
              model,
              api_key_id: apiKeyId,
              api_key_secret: e.target.value,
            })
          }
          placeholder={
            boundKey
              ? `已绑定「${boundKey.label}」，输入新密钥可轮换`
              : "sk-...（保存好友时写入本地 vault）"
          }
        />
        {keysForProvider.length > 0 && (
          <div className="mt-2">
            <label className="label text-xs text-slate-500">或选用已保存的 Key</label>
            <select
              className="input"
              value={apiKeyId ?? ""}
              onChange={(e) =>
                onChange({
                  provider_id: providerId,
                  model,
                  api_key_id: e.target.value || null,
                  api_key_secret: "",
                })
              }
            >
              <option value="">不选用（使用上方输入或环境变量）</option>
              {keysForProvider.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.label} ({k.status})
                </option>
              ))}
            </select>
          </div>
        )}
        <p className="mt-1 text-xs text-slate-500">
          {boundKey && !apiKeySecret.trim() ? (
            <>
              当前绑定：<strong>{boundKey.label}</strong>（{boundKey.provider_id}）
            </>
          ) : apiKeySecret.trim() ? (
            <>保存好友后将写入 vault 并绑定到此实例。</>
          ) : (
            <>
              未填写密钥时，可配置环境变量 <code>{envVar}</code> 作为回退。
            </>
          )}
        </p>
      </div>
    </div>
  );
}

const PTY_PRESETS: Record<string, { cmd: string; args: string; label: string }> = {
  claude: { cmd: "claude", args: "", label: "claude code（cli）" },
  cursor: { cmd: "cursor-agent", args: "", label: "cursor-agent（cli）" },
  "worker-bee-cli": { cmd: "worker-bee", args: "", label: "Worker Bee（工蜂）" },
  "codex-exec": { cmd: "codex", args: "", label: "Codex CLI" },
  custom: { cmd: "", args: "", label: "自定义" },
};

function ptyCmdForPreset(preset: string, fallbackCmd = ""): string {
  return PTY_PRESETS[preset]?.cmd ?? fallbackCmd;
}

function PtyConfigEditor({
  draft,
  setDraft,
  providers,
  providerKeys,
}: {
  draft: FriendDraft;
  setDraft: (d: FriendDraft) => void;
  providers: Provider[];
  providerKeys: ProviderKey[];
}) {
  const isCustom = draft.pty.preset === "custom";
  const isWorkerBee = draft.pty.preset === "worker-bee-cli";
  return (
    <div className="space-y-3 rounded-md border border-slate-200 bg-slate-50 p-3">
      <div>
        <label className="label">预设</label>
        <select
          className="input"
          value={draft.pty.preset}
          onChange={(e) => {
            const preset = e.target.value;
            const p = PTY_PRESETS[preset];
            const workerBee = preset === "worker-bee-cli";
            setDraft({
              ...draft,
              pty: {
                ...draft.pty,
                preset,
                cmd: p?.cmd ?? "",
                args: p?.args ?? "",
                ...(workerBee
                  ? {}
                  : {
                      provider_id: "",
                      model: "",
                      api_key_id: null,
                      api_key_secret: "",
                      skills_dir: "data/skills",
                      memory_top_k: 5,
                    }),
              },
            });
          }}
        >
          {!draft.pty.preset && (
            <option value="" disabled>
              请选择 CLI 预设
            </option>
          )}
          {Object.entries(PTY_PRESETS).map(([id, p]) => (
            <option key={id} value={id}>
              {p.label}
            </option>
          ))}
        </select>
      </div>
      {isWorkerBee && (
        <WorkerBeeApiFields
          providerId={draft.pty.provider_id}
          model={draft.pty.model}
          apiKeyId={draft.pty.api_key_id}
          apiKeySecret={draft.pty.api_key_secret}
          onChange={(api) =>
            setDraft({
              ...draft,
              pty: {
                ...draft.pty,
                provider_id: api.provider_id,
                model: api.model,
                api_key_id: api.api_key_id,
                api_key_secret: api.api_key_secret,
              },
            })
          }
          providers={providers}
          providerKeys={providerKeys}
        />
      )}
      {isWorkerBee && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">技能库目录</label>
            <input
              className="input font-mono text-xs"
              value={draft.pty.skills_dir}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  pty: { ...draft.pty, skills_dir: e.target.value },
                })
              }
            />
          </div>
          <div>
            <label className="label">记忆检索条数</label>
            <input
              type="number"
              className="input"
              min={1}
              max={20}
              value={draft.pty.memory_top_k}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  pty: {
                    ...draft.pty,
                    memory_top_k: Number(e.target.value) || 5,
                  },
                })
              }
            />
          </div>
        </div>
      )}
      <div>
        <label className="label">工作目录</label>
        <input
          className="input font-mono text-xs"
          value={draft.pty.cwd}
          onChange={(e) =>
            setDraft({ ...draft, pty: { ...draft.pty, cwd: e.target.value } })
          }
          placeholder="留空则自动：data/cli-workspaces/<好友ID>（自动建目录并 git init）"
        />
      </div>
      {isCustom ? (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">命令</label>
            <input
              className="input"
              value={draft.pty.cmd}
              onChange={(e) =>
                setDraft({ ...draft, pty: { ...draft.pty, cmd: e.target.value } })
              }
              placeholder="可执行文件名"
            />
          </div>
          <div>
            <label className="label">参数（空格分隔）</label>
            <input
              className="input"
              value={draft.pty.args}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  pty: { ...draft.pty, args: e.target.value },
                })
              }
            />
          </div>
        </div>
      ) : (
        <p className="rounded-md border border-slate-200 bg-white px-3 py-2 font-mono text-xs text-slate-600">
          命令：<strong>{ptyCmdForPreset(draft.pty.preset, draft.pty.cmd) || "—"}</strong>
          {draft.pty.args.trim() ? (
            <span className="text-slate-400">（参数由预设管理，无需填写）</span>
          ) : (
            <span className="text-slate-400"> · 由预设固定，无需填写</span>
          )}
        </p>
      )}
      <p className="text-xs text-slate-500">
        {isWorkerBee ? (
          <>
            <strong>工蜂</strong>固定执行 <code>worker-bee</code>，平台 API / 技能库 / 记忆在上方配置；与
            Codex、Claude 等外部 CLI 无关。
          </>
        ) : (
          <>
            外部 CLI（claude / codex）在子进程内完成推理。工作目录留空则{" "}
            <code>data/cli-workspaces/&lt;好友ID&gt;</code>。
          </>
        )}
      </p>
    </div>
  );
}

function HumanConfigEditor({
  draft,
  setDraft,
}: {
  draft: FriendDraft;
  setDraft: (d: FriendDraft) => void;
}) {
  return (
    <div className="space-y-3 rounded-md border border-slate-200 bg-slate-50 p-3">
      <div>
        <label className="label">接入方式</label>
        <select
          className="input"
          value={draft.human.channel}
          onChange={(e) =>
            setDraft({
              ...draft,
              human: { ...draft.human, channel: e.target.value },
            })
          }
        >
          <option value="invite">邀请链接（web 客户端）</option>
        </select>
      </div>
      <p className="text-xs text-slate-500">
        保存后到左上角"邀请"按钮里给这位真人朋友生成一次性邀请链接，对方打开后即可在群里发消息。
        真人成员不会参与自动 judge；当他/她在输入时，AI 会自动延迟出声（真人礼让）。
      </p>
    </div>
  );
}
