import type { AssistantMemory } from "../types";
import {
  MEMORY_KIND_OPTIONS,
  MEMORY_SCOPES,
  MEMORY_TIERS,
  MEMORY_IMPORTANCE,
  type MemoryDraft,
} from "../assistantEditable";
import {
  displayBody,
  importanceLabel,
  scopeBadgeClass,
  scopeLabel,
  statusLabel,
  tierBadgeClass,
  tierLabel,
} from "../memoryTier";
import { memorySourceLabel } from "../memoryLabels";

interface Props {
  memory: AssistantMemory;
  editing: boolean;
  draft: MemoryDraft;
  busy?: boolean;
  onDraftChange: (patch: Partial<MemoryDraft>) => void;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onSave: () => void;
  onDelete: () => void;
  onAssist?: () => void;
  onTogglePin?: () => void;
  compact?: boolean;
}

export function MemoryTierBadges({ memory }: { memory: AssistantMemory }) {
  return (
    <>
      <span
        className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${tierBadgeClass(memory.tier)}`}
      >
        {tierLabel(memory.tier)}
      </span>
      <span
        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${scopeBadgeClass(memory.scope)}`}
      >
        {scopeLabel(memory.scope)}
        {memory.scope_ref ? ` · ${memory.scope_ref.slice(0, 8)}` : ""}
      </span>
      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
        {importanceLabel(memory.importance)}
      </span>
      {memory.status === "archived" && (
        <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] text-slate-600">
          {statusLabel(memory.status)}
        </span>
      )}
    </>
  );
}

export function MemoryRecordEditor({
  memory,
  editing,
  draft,
  busy,
  onDraftChange,
  onStartEdit,
  onCancelEdit,
  onSave,
  onDelete,
  onAssist,
  onTogglePin,
  compact,
}: Props) {
  const source = memorySourceLabel(memory.content);

  if (editing) {
    return (
      <div className="space-y-2 rounded-md border border-honey-300 bg-honey-50/40 p-3">
        <div className="flex flex-wrap gap-2 text-[11px] text-slate-500">
          <span className="font-medium text-honey-800">直接编辑</span>
          {memory.tier === "raw" && (
            <span className="text-emerald-700">保存将提升为整理层</span>
          )}
        </div>
        <div className="grid grid-cols-12 gap-2">
          <select
            className="input col-span-3 text-xs"
            value={draft.tier}
            onChange={(e) => onDraftChange({ tier: e.target.value })}
          >
            {MEMORY_TIERS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <select
            className="input col-span-3 text-xs"
            value={draft.scope}
            onChange={(e) => onDraftChange({ scope: e.target.value })}
          >
            {MEMORY_SCOPES.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <select
            className="input col-span-2 text-xs"
            value={draft.importance}
            onChange={(e) =>
              onDraftChange({ importance: Number(e.target.value) })
            }
          >
            {MEMORY_IMPORTANCE.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <input
            className="input col-span-4 text-xs"
            placeholder="scope_ref（好友/会话 id）"
            value={draft.scope_ref}
            onChange={(e) => onDraftChange({ scope_ref: e.target.value })}
          />
        </div>
        <div className="grid grid-cols-12 gap-2">
          <select
            className="input col-span-4 text-xs"
            value={draft.kind}
            onChange={(e) => onDraftChange({ kind: e.target.value })}
          >
            {MEMORY_KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <input
            className="input col-span-2 text-xs"
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={draft.weight}
            onChange={(e) =>
              onDraftChange({ weight: Number(e.target.value) || 0 })
            }
          />
          <input
            className="input col-span-6 text-xs"
            placeholder="标题（整理层可选）"
            value={draft.title}
            onChange={(e) => onDraftChange({ title: e.target.value })}
          />
        </div>
        <input
          className="input w-full text-xs"
          placeholder="摘要（注入提示词时优先展示）"
          value={draft.summary}
          onChange={(e) => onDraftChange({ summary: e.target.value })}
        />
        <textarea
          className="input min-h-[100px] w-full text-sm"
          value={draft.content}
          onChange={(e) => onDraftChange({ content: e.target.value })}
        />
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={draft.pinned}
            onChange={(e) => onDraftChange({ pinned: e.target.checked })}
          />
          置顶
        </label>
        <div className="flex flex-wrap justify-end gap-2">
          <button className="btn-ghost text-xs" onClick={onCancelEdit} disabled={busy}>
            取消
          </button>
          <button className="btn-primary text-xs" onClick={onSave} disabled={busy}>
            保存
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <MemoryTierBadges memory={memory} />
        <span className="rounded bg-violet-50/80 px-1.5 py-0.5 text-[10px] text-violet-700">
          {source}
        </span>
        <span className="text-slate-400">
          {new Date(memory.created_at).toLocaleString()}
        </span>
        {memory.pinned && (
          <span className="rounded bg-honey-100 px-1 text-[10px] text-honey-800">
            置顶
          </span>
        )}
        <div className="ml-auto flex gap-1">
          {onTogglePin && (
            <button
              type="button"
              className={`btn-ghost px-1 py-0 text-[11px] ${
                memory.pinned
                  ? "font-semibold text-honey-800"
                  : "text-slate-600"
              }`}
              onClick={onTogglePin}
              disabled={busy}
              title={memory.pinned ? "取消置顶" : "置顶后优先注入助理提示词"}
            >
              {memory.pinned ? "取消置顶" : "置顶"}
            </button>
          )}
          <button
            className="btn-ghost px-1 py-0 text-[11px] text-honey-700"
            onClick={onStartEdit}
            disabled={busy}
          >
            编辑
          </button>
          {onAssist && memory.tier === "curated" && (
            <button
              className="btn-ghost px-1 py-0 text-[11px] text-indigo-700"
              onClick={onAssist}
              disabled={busy}
            >
              对话整理
            </button>
          )}
          <button
            className="btn-ghost px-1 py-0 text-[11px] text-red-600"
            onClick={onDelete}
            disabled={busy}
          >
            删除
          </button>
        </div>
      </div>
      {memory.title && (
        <div className="mt-1 text-sm font-medium text-slate-800">{memory.title}</div>
      )}
      <div
        className={`mt-1 whitespace-pre-wrap text-slate-700 ${
          compact ? "line-clamp-3 text-xs" : "text-sm"
        }`}
      >
        {displayBody(memory)}
      </div>
      {memory.tier === "raw" && !compact && (
        <details className="mt-1 text-[11px] text-slate-500">
          <summary className="cursor-pointer">查看原始全文</summary>
          <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2">
            {memory.content}
          </pre>
        </details>
      )}
    </>
  );
}
