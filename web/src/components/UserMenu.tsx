import { useEffect, useRef, useState, type ReactNode } from "react";
import { useAuth } from "../stores/auth";
import { isTenantAdmin, tenantRoleLabel } from "../tenantAdmin";
import { Avatar } from "./Avatar";

interface Props {
  onOpenSettings: () => void;
  onOpenInvites: () => void;
  onOpenTeam: () => void;
  onOpenAuth: () => void;
}

export function UserMenu({
  onOpenSettings,
  onOpenInvites,
  onOpenTeam,
  onOpenAuth,
}: Props) {
  const { user, token, authRequired, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  async function handleLogout() {
    setOpen(false);
    await logout();
    if (authRequired) window.location.reload();
  }

  if (!token || !user) {
    return (
      <button type="button" className="btn-primary px-4" onClick={onOpenAuth}>
        登录
      </button>
    );
  }

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1.5 shadow-sm transition hover:bg-slate-50"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <Avatar name={user.display_name} kind="user" size={32} />
        <span className="hidden max-w-[8rem] truncate text-sm font-medium text-slate-800 sm:inline">
          {user.display_name}
        </span>
        <svg
          className={`h-4 w-4 shrink-0 text-slate-400 transition ${open ? "rotate-180" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-2 w-56 rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
        >
          <div className="border-b border-slate-100 px-3 py-2.5">
            <div className="truncate text-sm font-semibold text-slate-800">
              {user.display_name}
            </div>
            {user.username && (
              <div className="truncate text-xs text-slate-600">
                @{user.username}
              </div>
            )}
            <div className="truncate text-xs text-slate-500">{user.email}</div>
            <div className="mt-0.5 text-[11px] text-slate-400">
              {tenantRoleLabel(user.role)}
            </div>
          </div>
          <MenuItem onClick={() => { setOpen(false); onOpenTeam(); }}>
            {isTenantAdmin(user.role) ? "管理控制台" : "团队成员"}
          </MenuItem>
          <MenuItem onClick={() => { setOpen(false); onOpenInvites(); }}>
            真人好友邀请
          </MenuItem>
          <MenuItem onClick={() => { setOpen(false); onOpenSettings(); }}>
            设置
          </MenuItem>
          <div className="my-1 border-t border-slate-100" />
          <MenuItem danger onClick={() => void handleLogout()}>
            退出登录
          </MenuItem>
        </div>
      )}
    </div>
  );
}

function MenuItem({
  children,
  onClick,
  danger,
}: {
  children: ReactNode;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      className={`block w-full px-3 py-2 text-left text-sm transition hover:bg-slate-50 ${
        danger ? "text-red-600 hover:bg-red-50" : "text-slate-700"
      }`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
