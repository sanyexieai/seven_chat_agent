import { useEffect, useState } from "react";
import { wsInvoke } from "../api/client";
import type { AgentDna } from "../types";

interface Props {
  externalCli: boolean;
}

export function FriendAgentDnaTab({ externalCli }: Props) {
  const [dna, setDna] = useState<AgentDna | null>(null);
  const [preview, setPreview] = useState("");

  useEffect(() => {
    wsInvoke<{ dna: AgentDna; rendered: string }>("previewAgentDna", {})
      .then((r) => {
        setDna(r.dna);
        setPreview(r.rendered ?? "");
      })
      .catch(() => setDna(null));
  }, []);

  return (
    <div className="space-y-3">
      {externalCli && (
        <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          当前为外链 CLI 后端，平台侧<strong>不保证</strong>注入 DNA；约束请在 CLI 产品内配置或使用工蜂实例。
        </div>
      )}
      {!externalCli && (
        <p className="text-xs text-slate-500">
          租户 DNA 只读摘要；编辑请打开「设置 → Agent DNA」。
        </p>
      )}
      {dna && (
        <>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span>执行强度：{dna.enforcement?.level ?? "standard"}</span>
            <span>·</span>
            <span>{dna.enabled ? "已启用" : "已关闭"}</span>
          </div>
          <ul className="space-y-2">
            {dna.principles.map((p) => (
              <li
                key={p.id}
                className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs"
              >
                <code className="text-slate-400">{p.id}</code>
                <div className="mt-1 text-slate-700">{p.text}</div>
              </li>
            ))}
          </ul>
          {preview && (
            <pre className="max-h-48 overflow-auto rounded bg-slate-100 p-2 text-[11px] whitespace-pre-wrap">
              {preview}
            </pre>
          )}
        </>
      )}
    </div>
  );
}
