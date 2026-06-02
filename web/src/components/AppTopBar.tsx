import { UserMenu } from "./UserMenu";

interface Props {
  onOpenSettings: () => void;
  onOpenInvites: () => void;
  onOpenTeam: () => void;
  onOpenAuth: () => void;
}

export function AppTopBar({
  onOpenSettings,
  onOpenInvites,
  onOpenTeam,
  onOpenAuth,
}: Props) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white px-4">
      <div className="flex min-w-0 items-center gap-3">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-honey-600 text-sm font-bold text-white shadow-sm"
          aria-hidden
        >
          7
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold leading-tight text-slate-800">
            Seven Chat Agent
          </h1>
          <p className="truncate text-xs text-slate-500">多 Agent 聊天室</p>
        </div>
      </div>
      <UserMenu
        onOpenSettings={onOpenSettings}
        onOpenInvites={onOpenInvites}
        onOpenTeam={onOpenTeam}
        onOpenAuth={onOpenAuth}
      />
    </header>
  );
}
