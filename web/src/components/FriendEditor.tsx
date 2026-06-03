import { useEffect, useState } from "react";
import { api, type CliAuthStatus } from "../api/client";
import { FriendWorkspacesSection } from "./FriendWorkspacesSection";
import { FriendAgentMemoryTab } from "./FriendAgentMemoryTab";
import { FriendAgentDnaTab } from "./FriendAgentDnaTab";
import { providerDisplayName } from "../providerDefaults";
import { useChat } from "../stores/chat";
import type {
  BackendKind,
  CliRelayNode,
  Friend,
  Provider,
  ProviderKey,
} from "../types";

interface Props {
  friendId: string | null;
  onClose: () => void;
}

export function FriendEditor({ friendId, onClose }: Props) {
  const { providers, providerKeys, reloadFriends, reloadProviders, selectFriend } =
    useChat();
  const [draft, setDraft] = useState<FriendDraft>(emptyDraft());
  const [providerBaseUrl, setProviderBaseUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentTab, setAgentTab] = useState<
    "persona" | "capability" | "memory" | "workspace" | "dna"
  >("persona");
  const canDelete = !!friendId && !draft.is_builtin;
  const isWorkerBee =
    draft.backend_kind === "pty" && draft.pty.preset === "worker-bee-cli";
  const isExternalCli =
    draft.backend_kind === "pty" &&
    !!draft.pty.preset &&
    draft.pty.preset !== "worker-bee-cli";
  const showAgentTabs = !!friendId && draft.backend_kind === "pty";
  const workerBeeProvider = providers.find((p) => p.id === draft.pty.provider_id);

  useEffect(() => {
    setProviderBaseUrl(workerBeeProvider?.base_url ?? "");
  }, [draft.pty.provider_id, workerBeeProvider?.base_url]);

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
      if (
        d.backend_kind === "pty" &&
        d.pty.preset === "worker-bee-cli" &&
        d.pty.provider_id.trim()
      ) {
        const urlDirty = await persistProviderBaseUrlIfChanged(
          d.pty.provider_id,
          providerBaseUrl,
          providers,
        );
        if (urlDirty) await reloadProviders();
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
            {friendId
              ? showAgentTabs
                ? "Agent 面板"
                : "编辑好友"
              : "添加好友"}
          </h2>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        {showAgentTabs && (
          <nav className="flex flex-wrap gap-1 border-b border-slate-200 px-5 py-2">
            {(
              [
                ["persona", "人设"],
                ["capability", "能力"],
                ...(isWorkerBee ? [["memory", "记忆"] as const] : []),
                ["workspace", "工作区"],
                ["dna", "DNA"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={`rounded px-2 py-1 text-xs ${
                  agentTab === id
                    ? "bg-honey-50 font-medium text-honey-800"
                    : "text-slate-500 hover:bg-slate-100"
                }`}
                onClick={() => setAgentTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>
        )}
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {(!showAgentTabs || agentTab === "persona") && (
            <>
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
            </>
          )}
          {draft.backend_kind === "human" && (!showAgentTabs || agentTab === "persona") && (
            <HumanConfigEditor draft={draft} setDraft={setDraft} />
          )}
          {draft.backend_kind === "pty" &&
            (!showAgentTabs || agentTab === "capability") && (
            <PtyConfigEditor
              friendId={friendId}
              draft={draft}
              setDraft={setDraft}
              providers={providers}
              providerKeys={providerKeys}
              providerBaseUrl={providerBaseUrl}
              onProviderBaseUrlChange={setProviderBaseUrl}
              hideWorkspaces={showAgentTabs}
            />
          )}
          {showAgentTabs && agentTab === "memory" && friendId && isWorkerBee && (
            <FriendAgentMemoryTab friendId={friendId} />
          )}
          {showAgentTabs && agentTab === "workspace" && (
            <div className="space-y-3">
              {friendId ? (
                <FriendWorkspacesSection friendId={friendId} />
              ) : (
                <p className="text-xs text-slate-500">保存好友后可管理工作区。</p>
              )}
              <div>
                <label className="label">工作目录（兼容 / 覆盖默认工作区）</label>
                <input
                  className="input font-mono text-xs"
                  value={draft.pty.cwd}
                  onChange={(e) =>
                    setDraft({ ...draft, pty: { ...draft.pty, cwd: e.target.value } })
                  }
                  placeholder="留空则使用当前选中的工作区路径"
                />
              </div>
            </div>
          )}
          {showAgentTabs && agentTab === "dna" && (
            <FriendAgentDnaTab externalCli={isExternalCli} />
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
    /** Codex：`oneshot` | `resume` */
    cli_session_mode: "oneshot" | "resume";
    cli_session_id: string;
    /** Codex 沙箱 */
    cli_sandbox_mode: "read-only" | "workspace-write" | "danger-full-access";
    /** 外部 CLI API Key（保存时写入 vault，不落库） */
    cli_api_key_secret: string;
    cli_api_key_configured: boolean;
    clear_cli_api_key?: boolean;
    provider_id: string;
    model: string;
    api_key_id: string | null;
    /** 仅前端草稿，保存时写入 vault 后清空 */
    api_key_secret: string;
    skills_dir: string;
    memory_top_k: number;
    /** CLI 执行位置：服务端本机或远程转发 */
    execution_mode: "local" | "relay";
    relay_id: string;
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
    system_prompt: "你是 [name]，活跃在 Seven Chat Agent 多 Agent 聊天室。",
    focus_tags: [],
    backend_kind: "pty",
    api: { provider_id: "openai", model: "gpt-4o-mini", api_key_id: null },
    pty: {
      preset: "claude",
      cmd: "claude",
      args: "",
      cwd: "",
      cli_session_mode: "oneshot",
      cli_session_id: "",
      cli_sandbox_mode: "workspace-write",
      cli_api_key_secret: "",
      cli_api_key_configured: false,
      provider_id: "openai",
      model: "gpt-4o-mini",
      api_key_id: null,
      api_key_secret: "",
      skills_dir: "data/skills",
      memory_top_k: 5,
      execution_mode: "local",
      relay_id: "",
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
      cli_session_mode: "oneshot",
      cli_session_id: "",
      cli_sandbox_mode: "workspace-write",
      cli_api_key_secret: "",
      cli_api_key_configured: false,
      provider_id: f.backend_config?.provider_id || "",
      model: f.backend_config?.model || "",
      api_key_id: f.backend_config?.api_key_id || null,
      api_key_secret: "",
      skills_dir: f.backend_config?.skills_dir || "data/skills",
      memory_top_k: f.backend_config?.memory_top_k ?? 5,
      execution_mode: "local",
      relay_id: "",
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
      cli_session_mode:
        f.backend_config?.cli_session_mode === "resume" ? "resume" : "oneshot",
      cli_session_id:
        typeof f.backend_config?.cli_session_id === "string"
          ? f.backend_config.cli_session_id
          : typeof f.backend_config?.cli_thread_id === "string"
            ? f.backend_config.cli_thread_id
            : "",
      cli_sandbox_mode: parseCodexSandboxMode(f.backend_config?.cli_sandbox_mode),
      cli_api_key_secret: "",
      cli_api_key_configured: !!f.backend_config?.cli_api_key_ref,
      provider_id: isExternal ? "" : f.backend_config?.provider_id || "",
      model: isExternal ? "" : f.backend_config?.model || "",
      api_key_id: isExternal ? null : f.backend_config?.api_key_id || null,
      api_key_secret: "",
      skills_dir: isExternal ? "data/skills" : f.backend_config?.skills_dir || "data/skills",
      memory_top_k: isExternal ? 5 : f.backend_config?.memory_top_k ?? 5,
      execution_mode:
        f.backend_config?.execution_mode === "relay" ? "relay" : "local",
      relay_id:
        typeof f.backend_config?.relay_id === "string"
          ? f.backend_config.relay_id
          : "",
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
      backend_config.cli_session_mode = d.pty.cli_session_mode;
      if (d.pty.preset === "codex-exec") {
        backend_config.cli_sandbox_mode = d.pty.cli_sandbox_mode;
      }
      if (d.pty.cli_session_mode === "resume") {
        const sid = d.pty.cli_session_id.trim();
        backend_config.cli_session_id = sid || null;
      } else {
        backend_config.cli_session_id = null;
      }
      if (d.pty.clear_cli_api_key) {
        backend_config.clear_cli_api_key = true;
      }
      if (d.pty.cli_api_key_secret.trim()) {
        backend_config.cli_api_key = d.pty.cli_api_key_secret.trim();
      }
      backend_config.execution_mode = d.pty.execution_mode;
      if (d.pty.execution_mode === "relay") {
        const rid = d.pty.relay_id.trim();
        if (!rid) {
          throw new Error("远程转发模式下请选择在线转发节点");
        }
        backend_config.relay_id = rid;
      } else {
        backend_config.relay_id = null;
      }
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

/** 工蜂绑定的 Provider Base URL 有改动时写入数据库；返回是否已保存 */
async function persistProviderBaseUrlIfChanged(
  providerId: string,
  baseUrl: string,
  providers: Provider[],
): Promise<boolean> {
  const p = providers.find((x) => x.id === providerId);
  if (!p) return false;
  const trimmed = baseUrl.trim();
  if (!trimmed || trimmed === p.base_url) return false;
  await api.upsertProvider({
    id: p.id,
    kind: p.kind,
    display_name: p.display_name,
    base_url: trimmed,
    default_model: p.default_model,
    capabilities: p.capabilities,
    price: p.price,
    enabled: p.enabled,
  });
  return true;
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
  baseUrl,
  apiKeyId,
  apiKeySecret,
  onChange,
  onBaseUrlChange,
  providers,
  providerKeys,
}: {
  providerId: string;
  model: string;
  baseUrl: string;
  apiKeyId: string | null;
  apiKeySecret: string;
  onChange: (api: {
    provider_id: string;
    model: string;
    api_key_id: string | null;
    api_key_secret: string;
  }) => void;
  onBaseUrlChange: (url: string) => void;
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
                {providerDisplayName(p.display_name)}
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
        <label className="label">Base URL</label>
        <input
          className="input font-mono text-xs"
          value={baseUrl}
          onChange={(e) => onBaseUrlChange(e.target.value)}
          placeholder={
            providers.find((p) => p.id === providerId)?.base_url ||
            "http://localhost:11434"
          }
        />
        <p className="mt-1 text-xs text-slate-500">
          修改后保存好友即写入 Provider 配置（该 Provider 下所有工蜂实例共用）。也可在「设置 →
          Providers」中编辑。
        </p>
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
  cursor: { cmd: "agent", args: "", label: "Cursor Agent（agent / cursor-agent）" },
  "worker-bee-cli": { cmd: "worker-bee", args: "", label: "Worker Bee（工蜂）" },
  "codex-exec": { cmd: "codex", args: "", label: "Codex CLI" },
  custom: { cmd: "", args: "", label: "自定义" },
};

function ptyCmdForPreset(preset: string, fallbackCmd = ""): string {
  return PTY_PRESETS[preset]?.cmd ?? fallbackCmd;
}

function cliApiKeyEnvHint(preset: string): string {
  switch (preset) {
    case "cursor":
      return "CURSOR_API_KEY（Cursor Dashboard → Integrations → API Keys）";
    case "codex-exec":
      return "OPENAI_API_KEY（或在本机执行 codex login）";
    case "claude":
      return "ANTHROPIC_API_KEY";
    default:
      return "API Key";
  }
}

function CliRelayConfigPanel({
  executionMode,
  relayId,
  cliPreset,
  onChange,
}: {
  executionMode: "local" | "relay";
  relayId: string;
  cliPreset: string;
  onChange: (patch: Partial<FriendDraft["pty"]>) => void;
}) {
  const [relays, setRelays] = useState<CliRelayNode[]>([]);
  const [relaysBusy, setRelaysBusy] = useState(false);
  const [pairingToken, setPairingToken] = useState<string | null>(null);
  const [relayWsUrl, setRelayWsUrl] = useState<string | null>(null);
  const [pairingBusy, setPairingBusy] = useState(false);
  const [relayError, setRelayError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [cmdCopied, setCmdCopied] = useState(false);

  const refreshRelays = () => {
    setRelaysBusy(true);
    setRelayError(null);
    api
      .listCliRelays()
      .then((r) => setRelays(r.relays || []))
      .catch((e) => setRelayError(e.message || String(e)))
      .finally(() => setRelaysBusy(false));
  };

  useEffect(() => {
    refreshRelays();
  }, []);

  useEffect(() => {
    if (executionMode !== "relay") return;
    const t = window.setInterval(refreshRelays, 5000);
    return () => window.clearInterval(t);
  }, [executionMode]);

  async function createPairingToken() {
    setPairingBusy(true);
    setRelayError(null);
    try {
      const { pairing_token, relay_ws_url } = await api.createCliRelayPairingToken();
      setPairingToken(pairing_token);
      setRelayWsUrl(relay_ws_url);
      setCopied(false);
    } catch (e: any) {
      setRelayError(e.message || String(e));
    } finally {
      setPairingBusy(false);
    }
  }

  async function copyToken() {
    if (!pairingToken) return;
    try {
      await navigator.clipboard.writeText(pairingToken);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setRelayError("无法写入剪贴板，请手动复制配对码");
    }
  }

  async function copyRelayCmd() {
    if (!relayCmd) return;
    try {
      await navigator.clipboard.writeText(relayCmd);
      setCmdCopied(true);
      window.setTimeout(() => setCmdCopied(false), 2000);
    } catch {
      setRelayError("无法写入剪贴板，请手动复制命令");
    }
  }

  const relayCmd =
    pairingToken && relayWsUrl
      ? `seven-chat-agent-cli-relay --url '${relayWsUrl}' --pairing-token ${pairingToken} --name my-pc`
      : null;

  return (
    <div className="space-y-3 rounded-md border border-sky-200 bg-sky-50/80 p-3">
      <label className="label mb-0">CLI 执行位置</label>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={`btn text-xs ${executionMode === "local" ? "border-sky-500 bg-white" : ""}`}
          onClick={() => onChange({ execution_mode: "local" })}
        >
          服务端本机
        </button>
        <button
          type="button"
          className={`btn text-xs ${executionMode === "relay" ? "border-sky-500 bg-white" : ""}`}
          onClick={() => onChange({ execution_mode: "relay" })}
        >
          远程电脑（转发程序）
        </button>
      </div>
      <p className="text-xs text-sky-900/90">
        {executionMode === "local"
          ? "CLI 在 seven-chat-agent-server 所在机器上启动（与改造前相同）。"
          : "CLI 在已配对的远程电脑上执行；Web 只发指令到服务端，由转发程序在本机调用 codex/claude 等。"}
      </p>

      {executionMode === "relay" && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn-primary text-xs"
              disabled={pairingBusy}
              onClick={createPairingToken}
            >
              {pairingBusy ? "生成中…" : "生成配对码（15 分钟有效）"}
            </button>
            <button
              type="button"
              className="btn-ghost text-xs"
              disabled={relaysBusy}
              onClick={refreshRelays}
            >
              {relaysBusy ? "刷新中…" : "刷新在线节点"}
            </button>
          </div>
          {relayError && (
            <p className="text-xs text-red-700">{relayError}</p>
          )}
          {pairingToken && relayWsUrl && relayCmd && (
            <div className="space-y-2 rounded border border-sky-300/70 bg-white/70 p-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-sky-900">配对码</span>
                <code className="break-all text-xs text-sky-950">{pairingToken}</code>
                <button type="button" className="btn-ghost text-xs" onClick={copyToken}>
                  {copied ? "已复制" : "复制"}
                </button>
              </div>
              <p className="break-all font-mono text-[11px] text-sky-800">{relayWsUrl}</p>
              <div className="flex flex-wrap items-center gap-2">
                <pre className="min-w-0 flex-1 overflow-x-auto rounded bg-slate-900 p-2 text-[11px] text-slate-100">
                  {relayCmd}
                </pre>
                <button type="button" className="btn-ghost text-xs" onClick={copyRelayCmd}>
                  {cmdCopied ? "已复制" : "复制命令"}
                </button>
              </div>
            </div>
          )}
          <div>
            <label className="label">绑定转发节点</label>
            {relays.length === 0 ? (
              <p className="text-xs text-amber-800">暂无在线节点。</p>
            ) : (
              <select
                className="input font-mono text-xs"
                value={relayId}
                onChange={(e) => onChange({ relay_id: e.target.value })}
              >
                <option value="">请选择…</option>
                {relays.map((r) => (
                  <option key={r.relay_id} value={r.relay_id}>
                    {r.name}
                    {r.host_label ? ` · ${r.host_label}` : ""} ({r.relay_id})
                  </option>
                ))}
              </select>
            )}
            {relayId &&
              (() => {
                const node = relays.find((r) => r.relay_id === relayId);
                const auth = cliPreset ? node?.cli_auth?.[cliPreset] : undefined;
                if (!auth) return null;
                return (
                  <p
                    className={`mt-2 text-xs ${auth.authenticated ? "text-green-800" : "text-amber-900"}`}
                  >
                    节点 CLI 探测：{auth.authenticated ? "✓" : "✗"} {auth.detail}
                  </p>
                );
              })()}
            {relayId && !relays.some((r) => r.relay_id === relayId) && (
              <p className="mt-1 text-xs text-amber-800">
                当前绑定的节点未在线，对话将失败直至重新连接。
              </p>
            )}
            {relayId && (() => {
              const node = relays.find((r) => r.relay_id === relayId);
              if (!node?.workspace_root) return null;
              return (
                <p className="mt-2 text-xs text-sky-900">
                  远程工作区根目录：<code className="break-all">{node.workspace_root}</code>
                  <br />
                  本好友目录约定为{" "}
                  <code className="break-all">
                    {node.workspace_root.replace(/\/$/, "")}/friends/&lt;好友ID&gt;
                  </code>
                  （由转发程序在远程自动创建）
                </p>
              );
            })()}
          </div>
        </>
      )}
    </div>
  );
}

function ExternalCliAuthFields({
  friendId,
  preset,
  executionMode,
  apiKeySecret,
  apiKeyConfigured,
  clearApiKey,
  onChange,
}: {
  friendId: string | null;
  preset: string;
  executionMode: "local" | "relay";
  apiKeySecret: string;
  apiKeyConfigured: boolean;
  clearApiKey?: boolean;
  onChange: (patch: Partial<FriendDraft["pty"]>) => void;
}) {
  const [status, setStatus] = useState<CliAuthStatus | null>(null);
  const [statusBusy, setStatusBusy] = useState(false);
  const [oauthBusy, setOauthBusy] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const refreshStatus = () => {
    if (!friendId) return;
    setStatusBusy(true);
    setAuthError(null);
    api
      .getFriendCliAuth(friendId)
      .then((r) => setStatus(r.cli_auth))
      .catch((e) => setAuthError(e.message || String(e)))
      .finally(() => setStatusBusy(false));
  };

  useEffect(() => {
    if (!friendId) {
      setStatus(null);
      return;
    }
    refreshStatus();
  }, [friendId, apiKeyConfigured, preset]);

  useEffect(() => {
    if (!friendId || !status?.oauth_pending) return;
    const t = window.setInterval(refreshStatus, 2000);
    return () => window.clearInterval(t);
  }, [friendId, status?.oauth_pending]);

  async function startOAuth() {
    if (!friendId) return;
    setOauthBusy(true);
    setAuthError(null);
    try {
      const { cli_auth } = await api.startFriendCliOAuth(friendId);
      setStatus(cli_auth);
    } catch (e: any) {
      setAuthError(e.message || String(e));
    } finally {
      setOauthBusy(false);
    }
  }

  async function cancelOAuth() {
    if (!friendId) return;
    setOauthBusy(true);
    try {
      const { cli_auth } = await api.cancelFriendCliOAuth(friendId);
      setStatus(cli_auth);
    } catch (e: any) {
      setAuthError(e.message || String(e));
    } finally {
      setOauthBusy(false);
    }
  }

  async function logoutOAuth() {
    if (!friendId) return;
    setOauthBusy(true);
    try {
      const { cli_auth } = await api.logoutFriendCli(friendId);
      setStatus(cli_auth);
    } catch (e: any) {
      setAuthError(e.message || String(e));
    } finally {
      setOauthBusy(false);
    }
  }

  const oauthPending = status?.oauth_pending ?? false;

  return (
    <div className="space-y-3 rounded-md border border-violet-200 bg-violet-50/80 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="label mb-0">CLI 鉴权</label>
        <div className="flex flex-wrap gap-1">
          {friendId && (
            <button
              type="button"
              className="btn-ghost text-xs"
              disabled={statusBusy || oauthBusy}
              onClick={refreshStatus}
            >
              {statusBusy ? "检测中…" : "刷新状态"}
            </button>
          )}
        </div>
      </div>

      {authError && (
        <p className="text-xs text-red-700">{authError}</p>
      )}

      {status && (
        <p
          className={`text-xs ${status.authenticated ? "text-green-800" : "text-amber-900"}`}
        >
          {status.authenticated ? "✓ 已就绪" : "✗ 未登录"}
          {status.auth_source === "relay" ? "（远程转发）" : ""}
          {status.api_key_configured ? "（API Key）" : ""}
          {status.oauth_phase === "succeeded" ? "（OAuth）" : ""}
          ：{status.oauth_message || status.detail || "—"}
        </p>
      )}

      <div className="space-y-2 rounded border border-violet-300/60 bg-white/60 p-2">
        <label className="label">服务器 OAuth 登录</label>
        <p className="text-xs text-violet-900/80">
          {executionMode === "relay" ? (
            <>
              远程转发模式下，OAuth 需在<strong>远程电脑</strong>本机完成（转发程序所在环境）。
              下方 API Key 会随任务下发到远程 CLI 环境变量。
            </>
          ) : (
            <>
              在 seven-chat-agent-server 本机启动 <code>agent login</code> /{" "}
              <code>codex login --device-auth</code> 等，登录态写在服务器用户目录（与 API Key
              二选一或并存）。
            </>
          )}
        </p>
        {!friendId ? (
          <p className="text-xs text-amber-800">请先保存好友，再使用 OAuth 登录。</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-primary text-xs"
              disabled={oauthBusy || oauthPending || executionMode === "relay"}
              title={
                executionMode === "relay"
                  ? "远程转发请在运行 cli-relay 的电脑上执行 agent login"
                  : undefined
              }
              onClick={startOAuth}
            >
              {oauthBusy ? "启动中…" : "开始 OAuth 登录"}
            </button>
            {oauthPending && (
              <button
                type="button"
                className="btn-ghost text-xs"
                disabled={oauthBusy}
                onClick={cancelOAuth}
              >
                取消登录
              </button>
            )}
            {status?.authenticated && !oauthPending && (
              <button
                type="button"
                className="btn-ghost text-xs text-red-700"
                disabled={oauthBusy}
                onClick={logoutOAuth}
              >
                登出 CLI
              </button>
            )}
          </div>
        )}
        {oauthPending && status?.oauth_instructions && (
          <p className="text-xs text-violet-900">{status.oauth_instructions}</p>
        )}
        {status?.oauth_url && (
          <div className="space-y-1">
            <a
              href={status.oauth_url}
              target="_blank"
              rel="noreferrer"
              className="break-all text-xs text-blue-700 underline"
            >
              {status.oauth_url}
            </a>
          </div>
        )}
        {status?.oauth_user_code && (
          <p className="font-mono text-sm text-violet-950">
            设备码：<strong>{status.oauth_user_code}</strong>
          </p>
        )}
      </div>

      <div>
        <label className="label">API Key（可选）</label>
        <input
          className="input font-mono text-xs"
          type="password"
          value={apiKeySecret}
          onChange={(e) =>
            onChange({
              cli_api_key_secret: e.target.value,
              clear_cli_api_key: false,
            })
          }
          placeholder={
            apiKeyConfigured
              ? "已保存密钥；输入新值可轮换"
              : `粘贴 ${cliApiKeyEnvHint(preset)}`
          }
        />
        <p className="mt-1 text-xs text-violet-900/80">
          保存好友后写入 vault，对话时注入{" "}
          <code>{cliApiKeyEnvHint(preset).split("（")[0]}</code>。
        </p>
      </div>
      {apiKeyConfigured && (
        <button
          type="button"
          className="btn-ghost text-xs text-red-700"
          onClick={() =>
            onChange({
              cli_api_key_secret: "",
              cli_api_key_configured: false,
              clear_cli_api_key: true,
            })
          }
        >
          {clearApiKey ? "保存后将清除已存 API Key" : "清除 API Key"}
        </button>
      )}
    </div>
  );
}

function cliSessionHelp(preset: string): string {
  switch (preset) {
    case "codex-exec":
      return "续接：codex exec resume <thread_id>；单次：每轮 codex exec 并拼接群聊历史。";
    case "cursor":
      return "续接：agent -p --resume <chat_id>（首轮 agent create-chat）；单次：每轮 agent -p 并拼历史。";
    case "claude":
      return "续接：claude -p --resume <session_id>；单次：每轮 claude -p 并拼历史。";
    default:
      return "";
  }
}

function cliSessionIdLabel(preset: string): string {
  switch (preset) {
    case "codex-exec":
      return "当前 thread_id";
    case "cursor":
      return "当前 chat_id";
    case "claude":
      return "当前 session_id";
    default:
      return "当前 session_id";
  }
}

function parseCodexSandboxMode(
  raw: unknown,
): "read-only" | "workspace-write" | "danger-full-access" {
  if (raw === "read-only" || raw === "danger-full-access") {
    return raw;
  }
  return "workspace-write";
}

function PtyConfigEditor({
  friendId,
  draft,
  setDraft,
  providers,
  providerKeys,
  providerBaseUrl,
  onProviderBaseUrlChange,
  hideWorkspaces = false,
}: {
  friendId: string | null;
  draft: FriendDraft;
  setDraft: (d: FriendDraft) => void;
  providers: Provider[];
  providerKeys: ProviderKey[];
  providerBaseUrl: string;
  onProviderBaseUrlChange: (url: string) => void;
  hideWorkspaces?: boolean;
}) {
  const isCustom = draft.pty.preset === "custom";
  const isWorkerBee = draft.pty.preset === "worker-bee-cli";
  const isCodex = draft.pty.preset === "codex-exec";
  const isExternalCli =
    draft.pty.preset === "codex-exec" ||
    draft.pty.preset === "claude" ||
    draft.pty.preset === "cursor";
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
          baseUrl={providerBaseUrl}
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
          onBaseUrlChange={onProviderBaseUrlChange}
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
      {isExternalCli && (
        <CliRelayConfigPanel
          executionMode={draft.pty.execution_mode}
          relayId={draft.pty.relay_id}
          cliPreset={draft.pty.preset}
          onChange={(patch) =>
            setDraft({
              ...draft,
              pty: { ...draft.pty, ...patch },
            })
          }
        />
      )}
      {isExternalCli && (
        <ExternalCliAuthFields
          friendId={draft.id}
          preset={draft.pty.preset}
          executionMode={draft.pty.execution_mode}
          apiKeySecret={draft.pty.cli_api_key_secret}
          apiKeyConfigured={draft.pty.cli_api_key_configured}
          clearApiKey={!!draft.pty.clear_cli_api_key}
          onChange={(patch) =>
            setDraft({
              ...draft,
              pty: { ...draft.pty, ...patch },
            })
          }
        />
      )}
      {isExternalCli && (
        <div className="space-y-2 rounded-md border border-slate-200 bg-white p-3">
          <div>
            <label className="label">CLI 会话模式</label>
            <select
              className="input"
              value={draft.pty.cli_session_mode}
              onChange={(e) => {
                const mode = e.target.value as "oneshot" | "resume";
                setDraft({
                  ...draft,
                  pty: {
                    ...draft.pty,
                    cli_session_mode: mode,
                    ...(mode === "oneshot" ? { cli_session_id: "" } : {}),
                  },
                });
              }}
            >
              <option value="oneshot">单次（每轮新起 CLI，拼聊天历史）</option>
              <option value="resume">续接（CLI 原生会话，不拼历史）</option>
            </select>
            <p className="mt-1 text-xs text-slate-600">{cliSessionHelp(draft.pty.preset)}</p>
          </div>
          {draft.pty.cli_session_mode === "resume" && (
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-0 flex-1">
                <label className="label">{cliSessionIdLabel(draft.pty.preset)}</label>
                <input
                  className="input font-mono text-xs"
                  readOnly
                  value={draft.pty.cli_session_id || "（首轮对话后自动写入）"}
                />
              </div>
              <button
                type="button"
                className="btn-ghost shrink-0 text-xs"
                disabled={!draft.pty.cli_session_id.trim()}
                onClick={() =>
                  setDraft({
                    ...draft,
                    pty: { ...draft.pty, cli_session_id: "" },
                  })
                }
              >
                清除会话
              </button>
            </div>
          )}
        </div>
      )}
      {isCodex && (
        <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50/80 p-3">
          <div>
            <label className="label">Codex 沙箱</label>
            <select
              className="input"
              value={draft.pty.cli_sandbox_mode}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  pty: {
                    ...draft.pty,
                    cli_sandbox_mode: parseCodexSandboxMode(e.target.value),
                  },
                })
              }
            >
              <option value="read-only">只读（read-only，Codex 默认）</option>
              <option value="workspace-write">工作区可写（workspace-write，推荐）</option>
              <option value="danger-full-access">
                完全访问（danger-full-access，仅隔离环境）
              </option>
            </select>
            <p className="mt-1 text-xs text-amber-900/80">
              由 <code>codex exec --sandbox</code> 传给 CLI。
            </p>
          </div>
        </div>
      )}
      {friendId && !hideWorkspaces ? (
        <FriendWorkspacesSection friendId={friendId} />
      ) : !hideWorkspaces ? (
        <p className="text-xs text-slate-500">
          保存好友后可在此管理多个工作区；首个默认目录为{" "}
          <code>data/cli-workspaces/&lt;好友ID&gt;</code>。
        </p>
      ) : null}
      {!hideWorkspaces && (
      <div>
        <label className="label">工作目录（兼容 / 覆盖默认工作区）</label>
        <input
          className="input font-mono text-xs"
          value={draft.pty.cwd}
          onChange={(e) =>
            setDraft({ ...draft, pty: { ...draft.pty, cwd: e.target.value } })
          }
          placeholder="留空则使用当前选中的工作区路径；群聊请在群设置里配置共享目录"
        />
      </div>
      )}
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
        ) : draft.pty.execution_mode === "relay" ? (
          <>
            外部 CLI 经转发程序在远程本机执行；<strong>工作目录由转发程序决定</strong>
            （默认 <code>~/.local/share/seven-chat-agent/cli-workspaces/friends/&lt;好友ID&gt;</code>
            ，可通过环境变量 <code>SEVEN_CHAT_AGENT_RELAY_WORKSPACE_ROOT</code> 或启动参数{" "}
            <code>--workspace-root</code> 修改）。配对后上方会显示远程上报的路径。
          </>
        ) : (
          <>
            外部 CLI（claude / codex）在子进程内完成推理。私聊工作目录留空则{" "}
            <code>data/cli-workspaces/&lt;好友ID&gt;</code>；群聊使用群设置中的共享目录。
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
