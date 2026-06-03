import { useEffect, useState } from "react";
import { wsInvoke } from "../api/client";
import { useAuth } from "../stores/auth";
import { isTenantAdmin } from "../tenantAdmin";
import type { AgentDna } from "../types";

export function AgentDnaSettings() {
  const { user } = useAuth();
  const isAdmin = isTenantAdmin(user?.role);
  const [dna, setDna] = useState<AgentDna | null>(null);
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    void reload();
  }, []);

  async function reload() {
    const r = await wsInvoke<{ dna: AgentDna; rendered?: string }>(
      "previewAgentDna",
      {},
    );
    setDna(r.dna);
    setPreview(r.rendered ?? "");
  }

  async function save() {
    if (!dna) return;
    setBusy(true);
    setMsg(null);
    try {
      await wsInvoke("upsertAgentDna", dna);
      await reload();
      setMsg("已保存 Agent DNA");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!dna) {
    return (
      <section className="rounded-md border border-slate-200 p-3 text-sm text-slate-500">
        加载 Agent DNA…
      </section>
    );
  }

  return (
    <section className="rounded-md border border-slate-200 p-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-slate-800">Agent DNA</div>
          <div className="text-xs text-slate-500">
            租户宪法 · 注入所有平台托管 Agent system 顶部
          </div>
        </div>
        <label className="flex items-center gap-1 text-xs">
          <input
            type="checkbox"
            checked={dna.enabled}
            disabled={!isAdmin}
            onChange={(e) => setDna({ ...dna, enabled: e.target.checked })}
          />
          启用
        </label>
      </div>
      <div className="mt-2">
        <label className="label text-xs">抬头</label>
        <textarea
          className="input min-h-[72px] font-mono text-xs"
          value={dna.preamble}
          readOnly={!isAdmin}
          onChange={(e) => setDna({ ...dna, preamble: e.target.value })}
        />
      </div>
      <div className="mt-2 space-y-2">
        <div className="text-xs font-medium text-slate-600">原则</div>
        {dna.principles.map((p, i) => (
          <div key={p.id} className="rounded border border-slate-100 p-2">
            <div className="text-[11px] text-slate-400">{p.id}</div>
            <textarea
              className="input mt-1 min-h-[48px] text-xs"
              value={p.text}
              readOnly={!isAdmin}
              onChange={(e) => {
                const principles = [...dna.principles];
                principles[i] = { ...p, text: e.target.value };
                setDna({ ...dna, principles });
              }}
            />
          </div>
        ))}
      </div>
      {preview && (
        <div className="mt-2">
          <label className="label text-xs">注入预览</label>
          <pre className="max-h-40 overflow-auto rounded bg-slate-50 p-2 text-[11px] whitespace-pre-wrap">
            {preview}
          </pre>
        </div>
      )}
      {isAdmin ? (
        <button
          type="button"
          className="btn-primary mt-3 w-full"
          disabled={busy}
          onClick={() => void save()}
        >
          {busy ? "保存中…" : "保存 DNA"}
        </button>
      ) : (
        <p className="mt-2 text-xs text-slate-500">仅管理员可编辑 DNA。</p>
      )}
      {msg && <p className="mt-2 text-xs text-slate-600">{msg}</p>}
    </section>
  );
}
