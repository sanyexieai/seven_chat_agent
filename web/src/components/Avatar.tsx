import type { BackendKind } from "../types";

interface Props {
  name: string;
  kind?: BackendKind | "user";
  size?: number;
}

const palette = [
  "#fbbf24",
  "#fb923c",
  "#f87171",
  "#a78bfa",
  "#60a5fa",
  "#34d399",
  "#22d3ee",
  "#f472b6",
];

export function Avatar({ name, kind, size = 36 }: Props) {
  const initial = (name?.trim()?.[0] ?? "?").toUpperCase();
  const colorIdx = [...name].reduce(
    (acc, ch) => acc + ch.charCodeAt(0),
    0,
  ) % palette.length;
  const bg = palette[colorIdx];
  const badge = badgeFor(kind);
  return (
    <div
      className="relative shrink-0 select-none rounded-md text-white shadow-inner"
      style={{ width: size, height: size, background: bg, fontSize: size * 0.45 }}
    >
      <div className="flex h-full w-full items-center justify-center font-semibold">
        {initial}
      </div>
      {badge && (
        <span
          className="absolute -bottom-1 -right-1 rounded-full bg-white px-1 text-[10px] font-semibold text-slate-700 shadow"
          title={badge.title}
        >
          {badge.label}
        </span>
      )}
    </div>
  );
}

function badgeFor(kind?: BackendKind | "user") {
  if (kind === "user") return null;
  switch (kind) {
    case "pty":
      return { label: "CLI", title: "CLI 接入" };
    case "api":
      return { label: "API", title: "API 模型" };
    case "assistant":
      return { label: "Hex", title: "内置助理" };
    case "human":
      return { label: "人", title: "真人好友" };
    default:
      return null;
  }
}
