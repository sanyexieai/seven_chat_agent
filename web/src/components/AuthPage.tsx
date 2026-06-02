import { useEffect, useState } from "react";
import { wsInvoke } from "../api/client";
import { useAuth } from "../stores/auth";

function inviteCodeFromUrl(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("invite")?.trim() ?? "";
}

interface AuthPageProps {
  /** 登录/注册成功后回调（用于关闭弹层等） */
  onSuccess?: () => void;
}

export function AuthPage({ onSuccess }: AuthPageProps) {
  const { login, register, authRequired } = useAuth();
  const [mode, setMode] = useState<"login" | "register">(
    inviteCodeFromUrl() ? "register" : "login",
  );
  const [loginAccount, setLoginAccount] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [inviteCode, setInviteCode] = useState(inviteCodeFromUrl());
  const [inviteHint, setInviteHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const code = inviteCode.trim();
    if (!code) {
      setInviteHint(null);
      return;
    }
    wsInvoke<{
      preview: {
        valid: boolean;
        tenant_name: string;
        role: string;
        reason?: string | null;
      };
    }>("previewTenantInvite", { code })
      .then((r) => {
        const p = r.preview;
        if (p.valid) {
          setInviteHint(`加入租户「${p.tenant_name}」· 角色 ${p.role}`);
          setMode("register");
        } else {
          setInviteHint(p.reason ?? "邀请码无效");
        }
      })
      .catch(() => setInviteHint(null));
  }, [inviteCode]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const slug = tenantSlug.trim() || undefined;
      const code = inviteCode.trim() || undefined;
      if (mode === "login") {
        await login(loginAccount, password, slug);
      } else {
        await register(email, username, password, displayName, slug, code);
      }
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-1 items-center justify-center bg-gradient-to-b from-slate-100 to-slate-50 p-6">
      <form
        onSubmit={submit}
        className="card w-full max-w-md space-y-4 p-6 shadow-lg"
      >
        <div>
          <h1 className="text-lg font-semibold text-slate-800">
            Seven Chat Agent
          </h1>
          <p className="text-sm text-slate-500">
            {authRequired ? "请登录以继续" : "登录或注册（可选）"}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className={`btn flex-1 ${mode === "login" ? "border-honey-500 bg-honey-50" : ""}`}
            onClick={() => setMode("login")}
          >
            登录
          </button>
          <button
            type="button"
            className={`btn flex-1 ${mode === "register" ? "border-honey-500 bg-honey-50" : ""}`}
            onClick={() => setMode("register")}
          >
            注册
          </button>
        </div>
        {mode === "register" && (
          <div>
            <label className="label">显示名称</label>
            <input
              className="input"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
            />
          </div>
        )}
        {mode === "login" ? (
          <div>
            <label className="label">邮箱或用户名</label>
            <input
              type="text"
              className="input"
              autoComplete="username"
              placeholder="you@example.com 或 myname"
              value={loginAccount}
              onChange={(e) => setLoginAccount(e.target.value)}
              required
            />
          </div>
        ) : (
          <>
            <div>
              <label className="label">邮箱</label>
              <input
                type="email"
                className="input"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="label">用户名</label>
              <input
                type="text"
                className="input"
                autoComplete="username"
                placeholder="2~32 位字母开头，可含数字与下划线"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                minLength={2}
                maxLength={32}
                pattern="[a-zA-Z][a-zA-Z0-9_]*"
                required
              />
            </div>
          </>
        )}
        <div>
          <label className="label">密码</label>
          <input
            type="password"
            className="input"
            autoComplete={
              mode === "login" ? "current-password" : "new-password"
            }
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </div>
        <div>
          <label className="label">租户 slug（可选，默认 default）</label>
          <input
            className="input"
            placeholder="default"
            value={tenantSlug}
            onChange={(e) => setTenantSlug(e.target.value)}
            disabled={!!inviteCode.trim()}
          />
        </div>
        {mode === "register" && (
          <div>
            <label className="label">租户邀请码（可选）</label>
            <input
              className="input"
              placeholder="通过邀请链接自动填入"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
            />
            {inviteHint && (
              <p className="mt-1 text-xs text-slate-500">{inviteHint}</p>
            )}
          </div>
        )}
        {error && (
          <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        )}
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy ? "..." : mode === "login" ? "登录" : "注册"}
        </button>
      </form>
    </div>
  );
}
