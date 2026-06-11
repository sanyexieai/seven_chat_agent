import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProfileFrameworkCatalog } from "../types/profile";

const BUILTIN_IDS = new Set(["mbti_16", "agent_24"]);

const EMPTY_CATALOG_TEMPLATE = `{
  "id": "my_framework",
  "name": "我的协作型",
  "version": "1",
  "types": [
    {
      "type_code": "主导·示例",
      "label_zh": "主导·示例",
      "default_routing_hints": {
        "initiative": "proactive",
        "coordination": "coordinator",
        "self_nominate": true
      },
      "prompt_snippet": "你擅长拆任务并协调成员分工。"
    }
  ],
  "extensions_schema": {
    "properties": {
      "team_role": {
        "type": "string",
        "enum": ["lead", "support", "review"]
      }
    }
  }
}`;

export function ProfileFrameworkManager() {
  const [frameworks, setFrameworks] = useState<ProfileFrameworkCatalog[]>([]);
  const [version, setVersion] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editJson, setEditJson] = useState(EMPTY_CATALOG_TEMPLATE);
  const [editId, setEditId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const r = await api.listProfileFrameworks();
    setFrameworks(r.frameworks);
    setVersion(r.profile_frameworks_version ?? null);
  }, []);

  useEffect(() => {
    void reload().catch((e) => setMsg(String(e)));
  }, [reload]);

  function openNew() {
    setEditId(null);
    setEditName("");
    setEditJson(EMPTY_CATALOG_TEMPLATE);
    setEditorOpen(true);
    setMsg(null);
  }

  function openEdit(fw: ProfileFrameworkCatalog) {
    setEditId(fw.id);
    setEditName(fw.name);
    setEditJson(JSON.stringify(fw, null, 2));
    setEditorOpen(true);
    setMsg(null);
  }

  async function saveFramework() {
    setBusy(true);
    setMsg(null);
    try {
      let catalog: ProfileFrameworkCatalog;
      try {
        catalog = JSON.parse(editJson) as ProfileFrameworkCatalog;
      } catch {
        throw new Error("catalog JSON 格式无效");
      }
      if (!catalog.types?.length) {
        throw new Error("至少包含一个 type");
      }
      const name = editName.trim() || catalog.name || "自定义 Framework";
      await api.upsertProfileFramework({
        id: editId ?? catalog.id,
        name,
        catalog: { ...catalog, name },
      });
      await reload();
      setEditorOpen(false);
      setMsg("Framework 已保存");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeFramework(id: string, name: string) {
    if (!confirm(`确定删除自定义 Framework「${name}」？`)) return;
    setBusy(true);
    setMsg(null);
    try {
      await api.deleteProfileFramework(id);
      await reload();
      setMsg(`已删除 ${name}`);
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">成员画像 Framework</h3>
        <button className="btn-primary text-xs" type="button" onClick={openNew}>
          + 自定义
        </button>
      </div>
      <p className="text-xs text-slate-500">
        内置 MBTI 16 与 Agent 24 只读；可新增租户自定义型谱供好友画像绑定。版本：
        {version ?? "—"}
      </p>
      <ul className="space-y-1">
        {frameworks.map((fw) => {
          const builtin = BUILTIN_IDS.has(fw.id);
          return (
            <li
              key={fw.id}
              className="flex items-center justify-between gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{fw.name}</span>
                  <span className="font-mono text-[11px] text-slate-400">{fw.id}</span>
                  {builtin && (
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
                      内置
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-500">
                  v{fw.version} · {fw.types.length} 型
                </div>
              </div>
              <div className="flex shrink-0 gap-1">
                {!builtin && (
                  <>
                    <button
                      type="button"
                      className="btn-ghost text-xs"
                      onClick={() => openEdit(fw)}
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      className="btn-ghost text-xs text-red-600"
                      disabled={busy}
                      onClick={() => void removeFramework(fw.id, fw.name)}
                    >
                      删除
                    </button>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {msg && <p className="text-xs text-slate-600">{msg}</p>}

      {editorOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="card flex max-h-[90vh] w-[640px] flex-col overflow-hidden p-0">
            <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
              <h2 className="text-base font-semibold">
                {editId ? `编辑 Framework · ${editName}` : "新建自定义 Framework"}
              </h2>
              <button className="btn-ghost" type="button" onClick={() => setEditorOpen(false)}>
                ×
              </button>
            </header>
            <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4 text-sm">
              <div>
                <label className="label">显示名</label>
                <input
                  className="input"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  placeholder="例如 团队角色 12 型"
                />
              </div>
              <div>
                <label className="label">Catalog JSON</label>
                <textarea
                  className="input min-h-[280px] font-mono text-xs"
                  value={editJson}
                  onChange={(e) => setEditJson(e.target.value)}
                  spellCheck={false}
                />
                <p className="mt-1 text-xs text-slate-500">
                  需含 id、name、version、types[]；每型建议带 default_routing_hints 与
                  prompt_snippet。
                </p>
              </div>
            </div>
            <footer className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3">
              <button className="btn" type="button" onClick={() => setEditorOpen(false)}>
                取消
              </button>
              <button
                className="btn-primary"
                type="button"
                onClick={() => void saveFramework()}
                disabled={busy}
              >
                {busy ? "保存中…" : "保存"}
              </button>
            </footer>
          </div>
        </div>
      )}
    </section>
  );
}
