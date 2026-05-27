/** 与后端 `worker_bee_cli::CliBlock` / `CliBlockDelta` 对齐 */

export type CommandRunStatus = "in_progress" | "completed" | "failed";

export type CliBlock =
  | { kind: "agent_message"; item_id: string; text: string }
  | {
      kind: "command_execution";
      item_id: string;
      command: string;
      output: string;
      status: CommandRunStatus;
      exit_code: number | null;
    }
  | { kind: "reasoning"; item_id: string; text: string }
  | {
      kind: "usage";
      input_tokens: number;
      output_tokens: number;
      cached_input_tokens?: number | null;
    }
  | { kind: "todo_list"; item_id: string; items: TodoItem[] };

export interface TodoItem {
  text: string;
  completed: boolean;
}

export type CliBlockDelta =
  | { op: "agent_text"; item_id: string; delta: string }
  | { op: "command_start"; item_id: string; command: string }
  | { op: "command_output"; item_id: string; delta: string }
  | {
      op: "command_finish";
      item_id: string;
      exit_code: number | null;
      status: string;
    }
  | { op: "reasoning_text"; item_id: string; delta: string }
  | {
      op: "usage";
      input_tokens: number;
      output_tokens: number;
      cached_input_tokens?: number | null;
    }
  | { op: "todo_list_set"; item_id: string; items: TodoItem[] };

function commandStatusFromCodex(
  status: string,
  exitCode: number | null,
): CommandRunStatus {
  if (exitCode === 0) return "completed";
  if (exitCode != null && exitCode !== 0) return "failed";
  if (status === "completed") return "completed";
  if (status === "failed") return "failed";
  return "in_progress";
}

export function applyCliBlockDelta(
  blocks: CliBlock[],
  delta: CliBlockDelta,
): CliBlock[] {
  const next = [...blocks];
  switch (delta.op) {
    case "agent_text": {
      const i = next.findIndex(
        (b) => b.kind === "agent_message" && b.item_id === delta.item_id,
      );
      if (i >= 0 && next[i].kind === "agent_message") {
        next[i] = { ...next[i], text: next[i].text + delta.delta };
      } else {
        next.push({
          kind: "agent_message",
          item_id: delta.item_id,
          text: delta.delta,
        });
      }
      break;
    }
    case "command_start": {
      if (
        next.some(
          (b) =>
            b.kind === "command_execution" && b.item_id === delta.item_id,
        )
      ) {
        break;
      }
      next.push({
        kind: "command_execution",
        item_id: delta.item_id,
        command: delta.command,
        output: "",
        status: "in_progress",
        exit_code: null,
      });
      break;
    }
    case "command_output": {
      const i = next.findIndex(
        (b) =>
          b.kind === "command_execution" && b.item_id === delta.item_id,
      );
      if (i >= 0 && next[i].kind === "command_execution") {
        next[i] = { ...next[i], output: next[i].output + delta.delta };
      }
      break;
    }
    case "command_finish": {
      const i = next.findIndex(
        (b) =>
          b.kind === "command_execution" && b.item_id === delta.item_id,
      );
      if (i >= 0 && next[i].kind === "command_execution") {
        next[i] = {
          ...next[i],
          exit_code: delta.exit_code,
          status: commandStatusFromCodex(delta.status, delta.exit_code),
        };
      }
      break;
    }
    case "reasoning_text": {
      const i = next.findIndex(
        (b) => b.kind === "reasoning" && b.item_id === delta.item_id,
      );
      if (i >= 0 && next[i].kind === "reasoning") {
        next[i] = { ...next[i], text: next[i].text + delta.delta };
      } else {
        next.push({
          kind: "reasoning",
          item_id: delta.item_id,
          text: delta.delta,
        });
      }
      break;
    }
    case "usage": {
      const i = next.findIndex((b) => b.kind === "usage");
      const u = {
        kind: "usage" as const,
        input_tokens: delta.input_tokens,
        output_tokens: delta.output_tokens,
        cached_input_tokens: delta.cached_input_tokens ?? null,
      };
      if (i >= 0) next[i] = u;
      else next.push(u);
      break;
    }
    case "todo_list_set": {
      const i = next.findIndex(
        (b) => b.kind === "todo_list" && b.item_id === delta.item_id,
      );
      const block = {
        kind: "todo_list" as const,
        item_id: delta.item_id,
        items: delta.items,
      };
      if (i >= 0) next[i] = block;
      else next.push(block);
      break;
    }
  }
  return next;
}

export function hasCliBlocks(
  blocks: CliBlock[] | null | undefined,
): blocks is CliBlock[] {
  return Array.isArray(blocks) && blocks.length > 0;
}

export function cliBlocksToPlain(blocks: CliBlock[]): string {
  return blocks
    .map((b) => {
      switch (b.kind) {
        case "agent_message":
          return `▎ codex\n${b.text}`;
        case "command_execution": {
          let s = `▎ exec\n▶ ${b.command}\n`;
          if (b.output) {
            for (const line of b.output.split("\n")) {
              s += line ? `  ${line}\n` : "\n";
            }
          }
          if (b.status === "completed") s += "✓ succeeded\n";
          else if (b.status === "failed") {
            s +=
              b.exit_code != null
                ? `✗ failed (exit ${b.exit_code})\n`
                : "✗ failed\n";
          }
          return s;
        }
        case "reasoning":
          return `▎ reasoning\n${b.text}`;
        case "usage": {
          const cached =
            b.cached_input_tokens != null
              ? `, cached ${b.cached_input_tokens}`
              : "";
          return `▎ tokens\nin ${b.input_tokens}, out ${b.output_tokens}${cached}\n`;
        }
        case "todo_list": {
          let s = "▎ plan\n";
          for (const it of b.items) {
            s += `${it.completed ? "✓" : "○"} ${it.text}\n`;
          }
          return s;
        }
        default:
          return "";
      }
    })
    .filter(Boolean)
    .join("\n\n");
}
