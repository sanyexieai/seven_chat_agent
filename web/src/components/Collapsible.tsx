import { useId, useState, type ReactNode } from "react";

interface Props {
  summary: ReactNode;
  children: ReactNode;
  /** 默认是否展开 */
  defaultOpen?: boolean;
  /** 流式进行中时自动展开 */
  autoOpen?: boolean;
  tone?: "neutral" | "tool" | "reasoning";
}

export function Collapsible({
  summary,
  children,
  defaultOpen = false,
  autoOpen = false,
  tone = "neutral",
}: Props) {
  const [open, setOpen] = useState(defaultOpen || autoOpen);
  const id = useId();
  const border =
    tone === "tool"
      ? "border-sky-100 bg-sky-50/50"
      : tone === "reasoning"
        ? "border-violet-100 bg-violet-50/40"
        : "border-slate-100 bg-slate-50/60";

  return (
    <div className={`rounded-lg border ${border}`}>
      <button
        type="button"
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs text-slate-700 hover:bg-white/60"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
      >
        <span
          className={`inline-block shrink-0 text-[10px] text-slate-400 transition-transform ${open ? "rotate-90" : ""}`}
        >
          ▶
        </span>
        <span className="min-w-0 flex-1 font-mono">{summary}</span>
      </button>
      {open && (
        <div id={id} className="border-t border-inherit px-2 pb-2 pt-1">
          {children}
        </div>
      )}
    </div>
  );
}
