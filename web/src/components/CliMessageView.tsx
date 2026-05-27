import type { ReactNode } from "react";
import type { CliBlock } from "../cliBlocks";
import { Collapsible } from "./Collapsible";

interface Props {
  blocks: CliBlock[];
  streaming?: boolean;
}

export function CliMessageView({ blocks, streaming }: Props) {
  const lastIdx = blocks.length - 1;
  return (
    <div className="flex flex-col gap-2">
      {blocks.map((block, i) => (
        <CliBlockView
          key={`${block.kind}-${i}-${"item_id" in block ? block.item_id : "usage"}`}
          block={block}
          showCursor={
            streaming &&
            i === lastIdx &&
            (block.kind === "agent_message" || block.kind === "reasoning")
          }
        />
      ))}
      {streaming && blocks.length === 0 && (
        <span className="inline-flex items-center gap-1 text-slate-400">
          <span className="cli-cursor" />
        </span>
      )}
    </div>
  );
}

function CliBlockView({
  block,
  showCursor,
}: {
  block: CliBlock;
  showCursor?: boolean;
}) {
  switch (block.kind) {
    case "agent_message":
      return (
        <section className="cli-block">
          <CliLabel tone="codex">codex</CliLabel>
          <pre className="cli-body max-h-[min(24rem,50vh)] overflow-y-auto whitespace-pre-wrap">
            {block.text}
            {showCursor ? <span className="cli-cursor" /> : null}
          </pre>
        </section>
      );
    case "command_execution": {
      const running = block.status === "in_progress";
      const cmdShort =
        block.command.length > 72
          ? `${block.command.slice(0, 72)}…`
          : block.command;
      const statusLabel =
        block.status === "completed"
          ? "✓"
          : block.status === "failed"
            ? "✗"
            : "…";
      return (
        <Collapsible
          tone="tool"
          autoOpen={running}
          summary={
            <>
              <span className="text-sky-700">exec</span>
              <span className="mx-1 text-slate-400">{statusLabel}</span>
              <span className="truncate text-slate-700">▶ {cmdShort}</span>
            </>
          }
        >
          <div className="cli-cmd font-mono text-xs text-slate-800">
            ▶ {block.command}
          </div>
          {block.output ? (
            <pre className="cli-output mt-1 max-h-64 overflow-y-auto border-l-2 border-slate-200 pl-2 font-mono text-xs text-slate-600">
              {block.output}
            </pre>
          ) : null}
          {block.status !== "in_progress" && (
            <div
              className={
                block.status === "completed"
                  ? "mt-1 text-xs text-emerald-600"
                  : "mt-1 text-xs text-red-600"
              }
            >
              {block.status === "completed"
                ? "✓ succeeded"
                : block.exit_code != null
                  ? `✗ failed (exit ${block.exit_code})`
                  : "✗ failed"}
            </div>
          )}
          {running && (
            <div className="mt-1 text-xs text-amber-600">运行中…</div>
          )}
        </Collapsible>
      );
    }
    case "reasoning": {
      const preview =
        block.text.length > 60 ? `${block.text.slice(0, 60)}…` : block.text;
      return (
        <Collapsible
          tone="reasoning"
          autoOpen={!!showCursor}
          summary={
            <>
              <span className="text-violet-600">reasoning</span>
              <span className="ml-1 truncate text-violet-900/80">{preview}</span>
            </>
          }
        >
          <pre className="cli-body whitespace-pre-wrap text-violet-900/90">
            {block.text}
            {showCursor ? <span className="cli-cursor" /> : null}
          </pre>
        </Collapsible>
      );
    }
    case "todo_list":
      return (
        <Collapsible
          summary={
            <>
              <span className="text-slate-500">plan</span>
              <span className="ml-1 text-slate-600">
                {block.items.length} 项待办
              </span>
            </>
          }
        >
          <ul className="space-y-0.5 text-xs text-slate-700">
            {block.items.map((it, j) => (
              <li
                key={j}
                className={it.completed ? "text-slate-400 line-through" : ""}
              >
                {it.completed ? "✓" : "○"} {it.text}
              </li>
            ))}
          </ul>
        </Collapsible>
      );
    case "usage":
      return (
        <Collapsible
          summary={
            <span className="text-slate-500">
              tokens · in {block.input_tokens.toLocaleString()}, out{" "}
              {block.output_tokens.toLocaleString()}
            </span>
          }
        >
          <p className="text-xs text-slate-500">
            in {block.input_tokens.toLocaleString()}, out{" "}
            {block.output_tokens.toLocaleString()}
            {block.cached_input_tokens != null
              ? `, cached ${block.cached_input_tokens.toLocaleString()}`
              : ""}
          </p>
        </Collapsible>
      );
    default:
      return null;
  }
}

function CliLabel({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "codex" | "exec" | "reasoning" | "muted";
}) {
  const cls =
    tone === "codex"
      ? "text-fuchsia-700"
      : tone === "exec"
        ? "text-sky-700"
        : tone === "reasoning"
          ? "text-violet-600"
          : "text-slate-400";
  return (
    <div
      className={`mb-1 font-mono text-[11px] font-semibold uppercase tracking-wide ${cls}`}
    >
      ▎ {children}
    </div>
  );
}
