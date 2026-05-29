import { formatWeChatMessageTime } from "../messageTime";

interface Props {
  createdAt: string;
}

/** 微信风格居中灰色时间条 */
export function MessageTimeDivider({ createdAt }: Props) {
  const label = formatWeChatMessageTime(createdAt);
  if (!label) return null;

  return (
    <div className="flex justify-center py-1" role="separator" aria-label={label}>
      <span className="rounded px-2 py-0.5 text-[11px] leading-relaxed text-slate-500/90">
        {label}
      </span>
    </div>
  );
}
