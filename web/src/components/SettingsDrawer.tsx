import { useMemo, useState } from "react";
import { api } from "../api/client";
import { useChat } from "../stores/chat";
import type { Provider, ProviderKey } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
}

const PROVIDER_KINDS: { id: string; label: string; hint: string }[] = [
  { id: "openai_compat", label: "openai_compat", hint: "标准 OpenAI Chat Completions 兼容（DeepSeek/通义/LM Studio/vLLM/OpenRouter 等都走这个）" },
  { id: "anthropic", label: "anthropic", hint: "Anthropic Messages API（claude-*）" },
  { id: "gemini", label: "gemini", hint: "Google Generative Language API（gemini-*）" },
  { id: "ollama", label: "ollama", hint: "Ollama 本地 NDJSON 接口" },
];

export function SettingsDrawer({ open, onClose }: Props) {
  const { providers, providerKeys, reloadProviders } = useChat();
  const [providerId, setProviderId] = useState<string>(providers[0]?.id || "");
  const [label, setLabel] = useState("");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [editingProvider, setEditingProvider] = useState<Provider | "new" | null>(
    null,
  );
  const [editingKey, setEditingKey] = useState<ProviderKey | "new" | null>(null);

  if (!open) return null;

  async function addKey() {
    if (!providerId || !label.trim() || !secret.trim()) {
      setMsg("请选择 Provider、填写标签和 API Key");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await api.upsertProviderKey({
        provider_id: providerId,
        label: label.trim(),
        secret: secret.trim(),
      });
      setLabel("");
      setSecret("");
      await reloadProviders();
      setMsg("已添加 API Key");
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeKey(id: string) {
    if (!confirm("确定删除这个 API key 吗？")) return;
    await api.deleteProviderKey(id);
    await reloadProviders();
  }

  async function removeProvider(p: Provider) {
    const keyCount = providerKeys.filter((k) => k.provider_id === p.id).length;
    const extra =
      keyCount > 0
        ? `\n这会顺带删除 ${keyCount} 个 API key（ON DELETE CASCADE）。`
        : "";
    if (!confirm(`确定删除 Provider「${p.display_name}」吗？${extra}`)) return;
    try {
      await api.deleteProvider(p.id);
      await reloadProviders();
      setMsg(`已删除 ${p.display_name}`);
    } catch (e: any) {
      setMsg(e.message || String(e));
    }
  }

  return (
    <div className="fixed inset-0 z-30 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex h-full w-[560px] flex-col border-l border-slate-200 bg-white shadow-xl">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div>
            <div className="text-base font-semibold">设置</div>
            <div className="text-xs text-slate-500">Providers 与 API Keys</div>
          </div>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-4">
          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-700">Providers</h3>
              <button
                className="btn-primary text-xs"
                onClick={() => setEditingProvider("new")}
              >
                + 新增
              </button>
            </div>
            <div className="text-xs text-slate-500">
              内置已预置 10 个常见 Provider。你也可以把任何 OpenAI 兼容的自托管 / 第三方接口加进来。
            </div>
            <ul className="space-y-1">
              {providers.map((p) => (
                <li
                  key={p.id}
                  className="rounded-md border border-slate-200 px-3 py-2 text-sm"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="font-medium">{p.display_name}</div>
                      <div className="truncate text-xs text-slate-500">
                        [{p.kind}] {p.base_url}
                        {p.default_model && <span> · {p.default_model}</span>}
                      </div>
                    </div>
                    <span className="text-[11px] text-slate-400">
                      {p.capabilities.context_len.toLocaleString()} ctx
                    </span>
                    <button
                      className="btn-ghost text-xs"
                      onClick={() => setEditingProvider(p)}
                    >
                      编辑
                    </button>
                    <button
                      className="btn-ghost text-xs text-red-600"
                      onClick={() => removeProvider(p)}
                    >
                      删除
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold text-slate-700">API Keys</h3>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="label">Provider</label>
                  <select
                    className="input"
                    value={providerId}
                    onChange={(e) => setProviderId(e.target.value)}
                  >
                    {providers.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.display_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label">标签</label>
                  <input
                    className="input"
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    placeholder="例如 主号 / 个人"
                  />
                </div>
              </div>
              <div className="mt-2">
                <label className="label">API Key 密文</label>
                <input
                  className="input"
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  type="password"
                  placeholder="sk-..."
                />
                <p className="mt-1 text-xs text-slate-500">
                  默认存放在本地 vault 文件（<code>data/vault.json</code>）。
                  若 server 编译时开启 <code>keychain</code> feature，且
                  <code>secret_ref</code> 以 <code>keychain:</code> 前缀写入，会改用系统钥匙串。
                </p>
              </div>
              <div className="mt-3 flex justify-end gap-2">
                <button
                  className="btn"
                  onClick={() => {
                    setProviderId(providerId);
                    setEditingKey("new");
                  }}
                >
                  详细表单…
                </button>
                <button className="btn-primary" onClick={addKey} disabled={busy}>
                  快速添加
                </button>
              </div>
              {msg && <div className="mt-2 text-xs text-slate-600">{msg}</div>}
            </div>

            <ul className="space-y-1">
              {providerKeys.map((k) => (
                <li
                  key={k.id}
                  className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-sm"
                >
                  <div>
                    <div className="font-medium">{k.label}</div>
                    <div className="text-xs text-slate-500">
                      {k.provider_id} · {k.status} · 已用 $
                      {k.current_spent_usd.toFixed(4)}
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <button
                      className="btn-ghost text-xs"
                      onClick={() => setEditingKey(k)}
                    >
                      编辑
                    </button>
                    <button
                      className="btn-ghost text-xs text-red-600"
                      onClick={() => removeKey(k.id)}
                    >
                      删除
                    </button>
                  </div>
                </li>
              ))}
              {providerKeys.length === 0 && (
                <li className="text-xs text-slate-500">还没有 API key。</li>
              )}
            </ul>
          </section>
        </div>
      </div>
      {editingProvider && (
        <ProviderEditor
          initial={editingProvider === "new" ? null : editingProvider}
          onClose={() => setEditingProvider(null)}
          onSaved={async () => {
            await reloadProviders();
            setEditingProvider(null);
            setMsg("Provider 已保存");
          }}
        />
      )}
      {editingKey && (
        <ProviderKeyEditor
          initial={editingKey === "new" ? null : editingKey}
          providers={providers}
          onClose={() => setEditingKey(null)}
          onSaved={async () => {
            await reloadProviders();
            setEditingKey(null);
            setMsg(editingKey === "new" ? "已添加 API Key" : "API Key 已更新");
          }}
        />
      )}
    </div>
  );
}

interface ProviderKeyEditorProps {
  initial: ProviderKey | null;
  providers: Provider[];
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}

function ProviderKeyEditor({
  initial,
  providers,
  onClose,
  onSaved,
}: ProviderKeyEditorProps) {
  const isNew = !initial;
  const [providerId, setProviderId] = useState(initial?.provider_id ?? providers[0]?.id ?? "");
  const [label, setLabel] = useState(initial?.label ?? "");
  const [secret, setSecret] = useState("");
  const [rpmLimit, setRpmLimit] = useState(
    initial?.rpm_limit != null ? String(initial.rpm_limit) : "",
  );
  const [tpmLimit, setTpmLimit] = useState(
    initial?.tpm_limit != null ? String(initial.tpm_limit) : "",
  );
  const [budget, setBudget] = useState(
    initial?.monthly_budget_usd != null ? String(initial.monthly_budget_usd) : "",
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!providerId || !label.trim()) {
      setErr("请填写 Provider 与标签");
      return;
    }
    if (isNew && !secret.trim()) {
      setErr("新建时必须填写 API Key");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.upsertProviderKey({
        id: initial?.id,
        provider_id: providerId,
        label: label.trim(),
        ...(secret.trim() ? { secret: secret.trim() } : {}),
        rpm_limit: rpmLimit.trim() ? Number(rpmLimit) : null,
        tpm_limit: tpmLimit.trim() ? Number(tpmLimit) : null,
        monthly_budget_usd: budget.trim() ? Number(budget) : null,
      });
      await onSaved();
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40">
      <div className="card flex w-[480px] flex-col overflow-hidden p-0">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h2 className="text-base font-semibold">
            {isNew ? "添加 API Key" : `编辑 API Key · ${initial?.label}`}
          </h2>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="space-y-3 px-5 py-4 text-sm">
          <div>
            <label className="label">Provider</label>
            <select
              className="input"
              value={providerId}
              disabled={!isNew}
              onChange={(e) => setProviderId(e.target.value)}
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">标签</label>
            <input
              className="input"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="例如 主号 / 个人"
            />
          </div>
          <div>
            <label className="label">API Key</label>
            <input
              className="input font-mono text-xs"
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder={isNew ? "sk-..." : "留空表示不修改原密钥"}
            />
            <p className="mt-1 text-xs text-slate-500">
              保存在本地 <code>data/vault.json</code>。工蜂实例在好友编辑里选择此 Key 绑定。
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="label">RPM 上限</label>
              <input
                className="input"
                type="number"
                value={rpmLimit}
                onChange={(e) => setRpmLimit(e.target.value)}
                placeholder="可选"
              />
            </div>
            <div>
              <label className="label">TPM 上限</label>
              <input
                className="input"
                type="number"
                value={tpmLimit}
                onChange={(e) => setTpmLimit(e.target.value)}
                placeholder="可选"
              />
            </div>
            <div>
              <label className="label">月预算 $</label>
              <input
                className="input"
                type="number"
                step={0.01}
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                placeholder="可选"
              />
            </div>
          </div>
          {!isNew && (
            <p className="text-xs text-slate-500">
              状态：{initial?.status} · 已用 ${initial?.current_spent_usd.toFixed(4)}
            </p>
          )}
          {err && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {err}
            </div>
          )}
        </div>
        <footer className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <button className="btn" onClick={onClose}>
            取消
          </button>
          <button className="btn-primary" onClick={save} disabled={busy}>
            {busy ? "保存中..." : "保存"}
          </button>
        </footer>
      </div>
    </div>
  );
}

interface ProviderEditorProps {
  initial: Provider | null;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}

function ProviderEditor({ initial, onClose, onSaved }: ProviderEditorProps) {
  const isNew = !initial;
  const [form, setForm] = useState(() => initFromProvider(initial));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const idHint = useMemo(
    () =>
      isNew
        ? "唯一短名，例如 my-vllm / azure-east；保存后作为 friend.backend_config.provider_id 引用"
        : "现有 Provider 不支持改 id；改完字段直接覆盖即可",
    [isNew],
  );

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      await api.upsertProvider({
        id: form.id.trim(),
        kind: form.kind,
        display_name: form.display_name.trim() || form.id,
        base_url: form.base_url.trim(),
        default_model: form.default_model.trim() || null,
        capabilities: {
          stream: form.stream,
          tools: form.tools,
          vision: form.vision,
          thinking: form.thinking,
          embeddings: form.embeddings,
          context_len: Number(form.context_len) || 0,
        },
        price: {
          input_per_mtok: Number(form.input_per_mtok) || 0,
          output_per_mtok: Number(form.output_per_mtok) || 0,
        },
        enabled: form.enabled,
      });
      await onSaved();
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40">
      <div className="card flex max-h-[90vh] w-[640px] flex-col overflow-hidden p-0">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h2 className="text-base font-semibold">
            {isNew ? "新增 Provider" : `编辑 Provider · ${initial?.display_name}`}
          </h2>
          <button className="btn-ghost" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">ID</label>
              <input
                className="input"
                value={form.id}
                disabled={!isNew}
                onChange={(e) => setForm({ ...form, id: e.target.value })}
                placeholder="my-vllm"
              />
              <p className="mt-1 text-xs text-slate-500">{idHint}</p>
            </div>
            <div>
              <label className="label">显示名</label>
              <input
                className="input"
                value={form.display_name}
                onChange={(e) =>
                  setForm({ ...form, display_name: e.target.value })
                }
                placeholder="My vLLM 本地"
              />
            </div>
          </div>
          <div>
            <label className="label">类型 (kind)</label>
            <div className="mt-1 grid grid-cols-2 gap-2">
              {PROVIDER_KINDS.map((k) => (
                <button
                  key={k.id}
                  className={`btn text-left ${form.kind === k.id ? "border-honey-500 bg-honey-50" : ""}`}
                  onClick={() => setForm({ ...form, kind: k.id })}
                  title={k.hint}
                >
                  <span className="font-medium">{k.label}</span>
                  <div className="text-[11px] font-normal text-slate-500">
                    {k.hint}
                  </div>
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Base URL</label>
              <input
                className="input"
                value={form.base_url}
                onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                placeholder="https://api.example.com/v1"
              />
            </div>
            <div>
              <label className="label">默认 model</label>
              <input
                className="input"
                value={form.default_model}
                onChange={(e) =>
                  setForm({ ...form, default_model: e.target.value })
                }
                placeholder="gpt-4o-mini"
              />
            </div>
          </div>
          <fieldset className="rounded-md border border-slate-200 p-3">
            <legend className="px-1 text-xs font-semibold text-slate-600">
              Capabilities
            </legend>
            <div className="grid grid-cols-3 gap-2 text-xs">
              {(
                [
                  ["stream", "流式"],
                  ["tools", "工具"],
                  ["vision", "视觉"],
                  ["thinking", "推理"],
                  ["embeddings", "嵌入"],
                ] as const
              ).map(([key, label]) => (
                <label
                  key={key}
                  className="flex items-center gap-1.5 rounded border border-slate-200 px-2 py-1"
                >
                  <input
                    type="checkbox"
                    checked={(form as any)[key]}
                    onChange={(e) =>
                      setForm({ ...form, [key]: e.target.checked } as any)
                    }
                  />
                  {label}
                </label>
              ))}
              <label className="flex items-center gap-1.5 rounded border border-slate-200 px-2 py-1">
                <span>context_len</span>
                <input
                  type="number"
                  className="input !h-7 flex-1 !py-0 text-xs"
                  value={form.context_len}
                  onChange={(e) =>
                    setForm({ ...form, context_len: Number(e.target.value) })
                  }
                />
              </label>
            </div>
          </fieldset>
          <fieldset className="rounded-md border border-slate-200 p-3">
            <legend className="px-1 text-xs font-semibold text-slate-600">
              单价（美元 / 百万 tokens，用于按用量记账）
            </legend>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <label>
                输入
                <input
                  type="number"
                  step={0.01}
                  className="input"
                  value={form.input_per_mtok}
                  onChange={(e) =>
                    setForm({ ...form, input_per_mtok: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                输出
                <input
                  type="number"
                  step={0.01}
                  className="input"
                  value={form.output_per_mtok}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      output_per_mtok: Number(e.target.value),
                    })
                  }
                />
              </label>
            </div>
          </fieldset>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            />
            启用（关闭后此 Provider 不会出现在好友编辑器里）
          </label>
          {err && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {err}
            </div>
          )}
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <button className="btn" onClick={onClose}>
            取消
          </button>
          <button className="btn-primary" onClick={save} disabled={busy || !form.id.trim() || !form.base_url.trim()}>
            {busy ? "保存中..." : "保存"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function initFromProvider(p: Provider | null) {
  if (!p) {
    return {
      id: "",
      kind: "openai_compat",
      display_name: "",
      base_url: "",
      default_model: "",
      stream: true,
      tools: true,
      vision: false,
      thinking: false,
      embeddings: false,
      context_len: 32_768,
      input_per_mtok: 0,
      output_per_mtok: 0,
      enabled: true,
    };
  }
  return {
    id: p.id,
    kind: p.kind,
    display_name: p.display_name,
    base_url: p.base_url,
    default_model: p.default_model ?? "",
    stream: p.capabilities.stream,
    tools: p.capabilities.tools,
    vision: p.capabilities.vision,
    thinking: p.capabilities.thinking,
    embeddings: p.capabilities.embeddings,
    context_len: p.capabilities.context_len,
    input_per_mtok: p.price.input_per_mtok,
    output_per_mtok: p.price.output_per_mtok,
    enabled: p.enabled,
  };
}
