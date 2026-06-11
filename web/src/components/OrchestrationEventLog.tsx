import type { OrchestrationEventEntry } from "../stores/chat";
import { Collapsible } from "./Collapsible";

interface Props {
  events: OrchestrationEventEntry[];
  turnId?: string | null;
}

function logSummary(events: OrchestrationEventEntry[]): string {
  if (events.length === 0) return "编排事件";
  const last = events[events.length - 1];
  return `编排事件 · ${events.length} 条 · 最近 ${last.label}`;
}

export function OrchestrationEventLog({ events, turnId }: Props) {
  const filtered = turnId
    ? events.filter((e) => e.turnId === turnId)
    : events;
  if (filtered.length === 0) return null;

  return (
    <div className="border-b border-slate-200 bg-slate-50/90 px-3 py-1.5">
      <Collapsible
        summary={
          <span className="font-sans text-xs font-medium text-slate-700">
            {logSummary(filtered)}
          </span>
        }
        defaultOpen={false}
        tone="neutral"
      >
        <ol className="mt-1 max-h-48 space-y-1 overflow-y-auto border-l border-slate-300 pl-3 text-[11px] text-slate-700">
          {filtered.map((ev, i) => (
            <li key={`${ev.turnId}-${ev.at}-${i}`} className="relative">
              <span className="absolute -left-[13px] top-1.5 h-1.5 w-1.5 rounded-full bg-slate-400" />
              <span className="font-medium text-slate-800">{ev.label}</span>
              {ev.detail && (
                <span className="ml-1 text-slate-600">— {ev.detail}</span>
              )}
            </li>
          ))}
        </ol>
      </Collapsible>
    </div>
  );
}
