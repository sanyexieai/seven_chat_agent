import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { allowedExtensionKeys } from "../profileUtils";
import { ExtensionFieldsForm } from "./ExtensionFieldsForm";
import type {
  FrameworkBinding,
  MemberProfile,
  ProfileFrameworkCatalog,
} from "../types/profile";

const INITIATIVE_LABEL: Record<string, string> = {
  proactive: "主动",
  balanced: "均衡",
  passive: "被动",
};

const COORDINATION_LABEL: Record<string, string> = {
  coordinator: "协调者",
  contributor: "协作者",
  none: "无",
};

const BUILTIN_ORDER = ["mbti_16", "agent_24"];

interface Props {
  friendId: string;
  profile: MemberProfile;
  onChange: (profile: MemberProfile) => void;
}

function emptyProfile(): MemberProfile {
  return {
    schema_version: 1,
    frameworks: [],
    use_derived_routing: true,
    routing_hints: {},
    extensions: {},
  };
}

function bindingFor(
  frameworks: FrameworkBinding[] | undefined,
  id: string,
): string {
  return frameworks?.find((f) => f.id === id)?.type_code ?? "";
}

function setBinding(
  frameworks: FrameworkBinding[],
  id: string,
  type_code: string,
): FrameworkBinding[] {
  const rest = frameworks.filter((f) => f.id !== id);
  if (!type_code) return rest;
  return [
    ...rest,
    { id, type_code, source: "user_selected", confidence: 1 },
  ];
}

function sortedCatalogs(catalogs: ProfileFrameworkCatalog[]) {
  return [...catalogs].sort((a, b) => {
    const ai = BUILTIN_ORDER.indexOf(a.id);
    const bi = BUILTIN_ORDER.indexOf(b.id);
    if (ai >= 0 && bi >= 0) return ai - bi;
    if (ai >= 0) return -1;
    if (bi >= 0) return 1;
    return a.name.localeCompare(b.name, "zh-CN");
  });
}

export function FriendProfileEditor({ friendId, profile, onChange }: Props) {
  const [catalogs, setCatalogs] = useState<ProfileFrameworkCatalog[]>([]);
  const [fwVersion, setFwVersion] = useState<string | null>(null);
  const [inferBusy, setInferBusy] = useState(false);
  const [inferNote, setInferNote] = useState<string | null>(null);
  const [extensionsText, setExtensionsText] = useState("");
  const [extensionsErr, setExtensionsErr] = useState<string | null>(null);
  const [extensionsAdvanced, setExtensionsAdvanced] = useState(false);

  const loadCatalogs = useCallback(async () => {
    const r = await api.listProfileFrameworks();
    setCatalogs(r.frameworks);
    setFwVersion(r.profile_frameworks_version ?? null);
  }, []);

  useEffect(() => {
    void loadCatalogs();
  }, [loadCatalogs]);

  useEffect(() => {
    const onFocus = () => {
      void loadCatalogs();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [loadCatalogs]);

  const p = profile.frameworks?.length ? profile : emptyProfile();

  useEffect(() => {
    const ext = p.extensions ?? {};
    setExtensionsText(
      Object.keys(ext).length ? JSON.stringify(ext, null, 2) : "{}",
    );
    setExtensionsErr(null);
  }, [friendId, p.extensions]);

  const preview = useMemo(() => {
    let initiative = "balanced";
    let coordination = "none";
    for (const fb of p.frameworks ?? []) {
      const cat = catalogs.find((c) => c.id === fb.id);
      const t = cat?.types.find((x) => x.type_code === fb.type_code);
      const hints = t?.default_routing_hints;
      if (hints?.initiative) initiative = hints.initiative;
      if (hints?.coordination) coordination = hints.coordination;
    }
    return { initiative, coordination };
  }, [p.frameworks, catalogs]);

  const extKeys = useMemo(
    () => allowedExtensionKeys(p.frameworks, catalogs),
    [p.frameworks, catalogs],
  );

  function applyExtensionsJson(raw: string) {
    setExtensionsText(raw);
    const trimmed = raw.trim();
    if (!trimmed || trimmed === "{}") {
      setExtensionsErr(null);
      onChange({ ...p, extensions: {} });
      return;
    }
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        setExtensionsErr("extensions 必须是 JSON 对象");
        return;
      }
      setExtensionsErr(null);
      onChange({
        ...p,
        extensions: parsed as Record<string, unknown>,
      });
    } catch {
      setExtensionsErr("JSON 格式无效");
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/80 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-slate-700">成员画像（群聊协作）</div>
        {fwVersion && (
          <span className="font-mono text-[10px] text-slate-400">fw {fwVersion}</span>
        )}
      </div>
      <p className="text-xs text-slate-500">
        决定该 Agent 在群里的接话倾向：主动广关注、被动仅被 @、协调者拆任务等。
      </p>
      <p className="text-xs text-slate-500">
        <strong>与群共识的区别</strong>：成员画像影响 Judge/调度；群共识由助理整理、全员只读。
        成员每次发言后会自动写入<strong>本群自述</strong>（仅该成员自己的提示词会召回），不会进入他人的上下文。
      </p>

      {sortedCatalogs(catalogs).map((cat) => (
        <div key={cat.id}>
          <label className="label">
            {cat.name}
            {BUILTIN_ORDER.includes(cat.id) ? null : (
              <span className="ml-1 text-[10px] font-normal text-slate-400">
                自定义
              </span>
            )}
          </label>
          <select
            className="input"
            value={bindingFor(p.frameworks, cat.id)}
            onChange={(e) =>
              onChange({
                ...p,
                frameworks: setBinding(
                  p.frameworks ?? [],
                  cat.id,
                  e.target.value,
                ),
              })
            }
          >
            <option value="">（未选择）</option>
            {cat.types.map((t) => (
              <option key={t.type_code} value={t.type_code}>
                {t.type_code}
                {t.label_zh && t.label_zh !== t.type_code
                  ? ` · ${t.label_zh}`
                  : ""}
              </option>
            ))}
          </select>
        </div>
      ))}

      <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-600">
        <input
          type="checkbox"
          checked={p.use_derived_routing !== false}
          onChange={(e) =>
            onChange({ ...p, use_derived_routing: e.target.checked })
          }
        />
        保存时从 framework 自动推导 routing_hints
      </label>

      <div className="text-xs text-slate-600">
        类型推导预览：
        <span className="ml-1 font-medium">
          {INITIATIVE_LABEL[preview.initiative] ?? preview.initiative}
        </span>
        <span className="mx-1">·</span>
        <span className="font-medium">
          {COORDINATION_LABEL[preview.coordination] ?? preview.coordination}
        </span>
      </div>

      {extKeys.length > 0 && (
        <div>
          <label className="label">扩展字段 extensions</label>
          {!extensionsAdvanced && (
            <ExtensionFieldsForm
              frameworks={p.frameworks}
              catalogs={catalogs}
              keys={extKeys}
              value={(p.extensions as Record<string, unknown>) ?? {}}
              onChange={(next) => {
                setExtensionsErr(null);
                setExtensionsText(
                  Object.keys(next).length ? JSON.stringify(next, null, 2) : "{}",
                );
                onChange({ ...p, extensions: next });
              }}
            />
          )}
          <label className="mt-2 flex cursor-pointer items-center gap-2 text-[11px] text-slate-500">
            <input
              type="checkbox"
              checked={extensionsAdvanced}
              onChange={(e) => setExtensionsAdvanced(e.target.checked)}
            />
            高级：直接编辑 JSON
          </label>
          {extensionsAdvanced && (
            <>
              <p className="mb-1 text-[11px] text-slate-500">
                允许键：{extKeys.join("、")}
              </p>
              <textarea
                className="input min-h-[72px] font-mono text-xs"
                value={extensionsText}
                onChange={(e) => applyExtensionsJson(e.target.value)}
                spellCheck={false}
              />
            </>
          )}
          {extensionsErr && (
            <p className="mt-1 text-xs text-red-600">{extensionsErr}</p>
          )}
        </div>
      )}

      <button
        type="button"
        className="btn text-xs"
        disabled={inferBusy}
        onClick={async () => {
          setInferBusy(true);
          setInferNote(null);
          try {
            const r = await api.inferFriendProfile(friendId);
            if (r.profile) onChange(r.profile);
            setInferNote(r.reasoning || "推断完成");
          } catch (e: unknown) {
            setInferNote(e instanceof Error ? e.message : String(e));
          } finally {
            setInferBusy(false);
          }
        }}
      >
        {inferBusy ? "推断中…" : "从性格描述推断"}
      </button>
      {inferNote && <p className="text-xs text-slate-500">{inferNote}</p>}
    </div>
  );
}

export { emptyProfile as emptyMemberProfile };
