import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AssistantGlobalSettings } from "../types";

export type CliRelayWsScheme = "auto" | "ws" | "wss";

const SCHEME_OPTIONS: { value: CliRelayWsScheme; label: string; hint: string }[] = [
  { value: "auto", label: "自动", hint: "HTTPS/TLS 部署时用 wss，本地开发用 ws" },
  { value: "wss", label: "WSS", hint: "强制加密 WebSocket（生产推荐）" },
  { value: "ws", label: "WS", hint: "明文 WebSocket（本机开发）" },
];

function parseScheme(raw: string | undefined): CliRelayWsScheme {
  const s = (raw ?? "auto").trim().toLowerCase();
  if (s === "ws" || s === "wss") return s;
  return "auto";
}

interface Props {
  open: boolean;
}

export function CliRelayUrlSettings({ open }: Props) {
  const [url, setUrl] = useState("");
  const [scheme, setScheme] = useState<CliRelayWsScheme>("auto");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setMsg(null);
    api
      .getAssistantGlobalSettings()
      .then(({ settings }) => {
        setUrl(settings.cli_relay_ws_url?.trim() ?? "");
        setScheme(parseScheme(settings.cli_relay_ws_scheme));
      })
      .catch((e) => setMsg(e.message || String(e)));
  }, [open]);

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      const { settings: current } = await api.getAssistantGlobalSettings();
      const trimmed = url.trim();
      const next: AssistantGlobalSettings = {
        ...current,
        cli_relay_ws_url: trimmed ? trimmed : null,
        cli_relay_ws_scheme: scheme,
      };
      await api.upsertAssistantGlobalSettings(next);
      setMsg("已保存");
    } catch (e: any) {
      setMsg(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  const schemeHint = SCHEME_OPTIONS.find((o) => o.value === scheme)?.hint;

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold text-slate-700">CLI 转发</h3>
      <p className="text-xs text-slate-500">
        远程电脑上的 <code>seven-chat-agent-cli-relay</code> 连接地址与协议。地址可写完整 URL 或仅主机（如{" "}
        <code>3ye.co:18743</code>），路径默认为 <code>/cli-relay</code>。
      </p>
      <label className="label mb-1">WebSocket 协议</label>
      <div className="flex flex-wrap gap-2">
        {SCHEME_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            className={`btn text-xs ${scheme === opt.value ? "border-sky-500 bg-sky-50" : ""}`}
            onClick={() => setScheme(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>
      {schemeHint && <p className="text-xs text-slate-500">{schemeHint}</p>}
      <label className="label mb-1">连接地址</label>
      <input
        className="input font-mono text-xs"
        placeholder={
          scheme === "wss"
            ? "wss://example.com:18743/cli-relay"
            : scheme === "ws"
              ? "ws://127.0.0.1:18737/cli-relay"
              : "example.com:18743 或完整 wss://…"
        }
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <div className="flex items-center gap-2">
        <button type="button" className="btn-primary text-xs" disabled={busy} onClick={save}>
          {busy ? "保存中…" : "保存"}
        </button>
        {msg && <span className="text-xs text-slate-600">{msg}</span>}
      </div>
    </section>
  );
}
