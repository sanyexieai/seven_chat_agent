import { create } from "zustand";
import { wsInvoke } from "../api/client";

const TOKEN_KEY = "seven_chat_agent_token";

export interface AuthUser {
  id: string;
  tenant_id: string;
  email: string;
  username?: string | null;
  display_name: string;
  role: string;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  authRequired: boolean;
  ready: boolean;
  init: () => Promise<void>;
  login: (
    login: string,
    password: string,
    tenantSlug?: string,
  ) => Promise<void>;
  register: (
    email: string,
    username: string,
    password: string,
    displayName: string,
    tenantSlug?: string,
    inviteCode?: string,
  ) => Promise<void>;
  logout: () => Promise<void>;
}

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export const useAuth = create<AuthState>((set, get) => ({
  token: getAuthToken(),
  user: null,
  authRequired: false,
  ready: false,
  async init() {
    const status = await wsInvoke<{ auth_required: boolean }>("authStatus", {});
    const authRequired = !!status.auth_required;
    const token = getAuthToken();
    set({ authRequired, token, ready: true });
    if (token) {
      try {
        const me = await wsInvoke<{ user: AuthUser }>("me", { auth_token: token });
        set({ user: me.user });
      } catch {
        setAuthToken(null);
        set({ token: null, user: null });
      }
    }
  },
  async login(login, password, tenantSlug) {
    const res = await wsInvoke<{
      auth: { token: string; user: AuthUser };
    }>("login", {
      login,
      password,
      tenant_slug: tenantSlug || undefined,
    });
    setAuthToken(res.auth.token);
    set({ token: res.auth.token, user: res.auth.user });
  },
  async register(email, username, password, displayName, tenantSlug, inviteCode) {
    const res = await wsInvoke<{
      auth: { token: string; user: AuthUser };
    }>("register", {
      email,
      username,
      password,
      display_name: displayName,
      tenant_slug: tenantSlug || undefined,
      invite_code: inviteCode || undefined,
    });
    setAuthToken(res.auth.token);
    set({ token: res.auth.token, user: res.auth.user });
  },
  async logout() {
    const token = get().token;
    if (token) {
      try {
        await wsInvoke("logout", { auth_token: token });
      } catch {
        /* ignore */
      }
    }
    setAuthToken(null);
    set({ token: null, user: null });
  },
}));
