import { useState } from "react";
import {
  ASSISTANT_EDITABLE_CATALOG,
  type EditMode,
} from "../assistantEditable";

export interface LlmOrganizeAction {
  prompt: string;
  label: string;
  runServerMaintenance?: boolean;
}

interface Props {
  activeTab?: string;
  onLlmAction: (action: LlmOrganizeAction) => void;
  busy?: boolean;
}

function modeLabel(m: EditMode) {
  return m === "direct" ? "直接改数据" : "对话整理";
}

function modeBadgeClass(m: EditMode) {
  return m === "direct"
    ? "bg-slate-100 text-slate-700"
    : "bg-indigo-50 text-indigo-800";
}

export function AssistantEditGuide({ activeTab, onLlmAction, busy }: Props) {
  const [open, setOpen] = useState(true);

  const items = activeTab
    ? ASSISTANT_EDITABLE_CATALOG.filter((i) =>
        i.tab.includes(
          activeTab === "sessions"
            ? "全站记忆"
            : activeTab === "knowledge"
              ? "知识库"
              : activeTab === "policy"
                ? "策略"
                : activeTab === "todo"
                  ? "TodoList"
                  : activeTab === "toolbox"
                    ? "工具箱"
                    : "",
        ),
      )
    : ASSISTANT_EDITABLE_CATALOG;

  const llmActions = items.flatMap((i) =>
    (i.llmActions ?? []).map((a) => ({ ...a, from: i.label })),
  );

  return (
    <section className="mb-4 rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <div>
          <div className="text-xs font-semibold text-slate-800">
            编辑方式说明
          </div>
          <div className="text-[11px] text-slate-500">
            直接编辑原始数据 · 或与助理对话由 LLM 整理
          </div>
        </div>
        <span className="text-slate-400">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="border-t border-slate-100 px-3 pb-3 pt-2">
          <div className="mb-3 grid gap-2 sm:grid-cols-2">
            <div className="rounded-md border border-slate-200 bg-slate-50 px-2 py-2 text-[11px] text-slate-700">
              <span className={`mr-1 rounded px-1 ${modeBadgeClass("direct")}`}>
                直接编辑
              </span>
              在面板内改字段后点保存，立即写入数据库（记忆 / 待办 / 策略等）。
            </div>
            <div className="rounded-md border border-indigo-100 bg-indigo-50/50 px-2 py-2 text-[11px] text-indigo-900">
              <span className={`mr-1 rounded px-1 ${modeBadgeClass("llm")}`}>
                对话整理
              </span>
              记忆类指令会<strong>先执行服务端维护</strong>（raw→curated ingest、
              过期清理、归档），再跳转助理私聊做复核与补充建议；落库仍可在面板
              「直接编辑」。
            </div>
          </div>

          <ul className="space-y-2">
            {items.map((item) => (
              <li
                key={item.id}
                className="rounded border border-slate-100 px-2 py-1.5 text-[11px]"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-slate-800">
                    {item.label}
                  </span>
                  <span className="text-slate-400">{item.tab}</span>
                  {item.modes.map((m) => (
                    <span
                      key={m}
                      className={`rounded px-1 py-0.5 ${modeBadgeClass(m)}`}
                    >
                      {modeLabel(m)}
                    </span>
                  ))}
                </div>
                <div className="text-slate-600">{item.description}</div>
                {item.fields.length > 0 && (
                  <div className="mt-1 text-slate-500">
                    字段：
                    {item.fields.map((f) => f.label).join("、")}
                  </div>
                )}
              </li>
            ))}
          </ul>

          {llmActions.length > 0 && (
            <div className="mt-3">
              <div className="mb-1 text-[11px] font-semibold text-indigo-900">
                对话整理快捷指令
              </div>
              <div className="flex flex-wrap gap-1">
                {llmActions.map((a) => (
                  <button
                    key={`${a.from}-${a.id}`}
                    type="button"
                    className="rounded-md border border-indigo-200 bg-white px-2 py-1 text-[11px] text-indigo-800 hover:bg-indigo-50"
                    disabled={busy}
                    onClick={() =>
                      onLlmAction({
                        prompt: a.prompt,
                        label: a.label,
                        runServerMaintenance: a.runServerMaintenance,
                      })
                    }
                    title={
                      a.runServerMaintenance
                        ? `先服务端维护再对话：${a.label}`
                        : `通过助理对话：${a.label}`
                    }
                  >
                    {a.label}
                    {a.runServerMaintenance ? " ⚙" : ""}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
