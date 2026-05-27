import { hasCliBlocks } from "../cliBlocks";
import { splitMessageContent } from "../messageContent";
import type { Message } from "../types";
import { Avatar } from "./Avatar";
import { CliMessageView } from "./CliMessageView";
import { Collapsible } from "./Collapsible";
import { renderCliText } from "./cli/drivers";

interface Props {
  message: Message;
  showAvatar?: boolean;
}

export function MessageBubble({ message, showAvatar = true }: Props) {
  const isUser = message.sender_kind === "user";
  const isSystem = message.sender_kind === "system";

  return (
    <div
      className={`flex items-end gap-2 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser && showAvatar && (
        <Avatar name={message.sender_name} size={32} />
      )}
      <div className="flex max-w-[78%] flex-col gap-1">
        {!isUser && (
          <span className="text-xs text-slate-500">
            {message.sender_name}
            {message.model_used && (
              <span className="ml-2 text-slate-400">
                · {message.model_used}
              </span>
            )}
          </span>
        )}
        <div
          className={[
            "whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-relaxed shadow-sm",
            isUser
              ? "rounded-br-md bg-honey-500 text-slate-900"
              : isSystem
                ? "rounded-bl-md border border-amber-200 bg-amber-50 text-amber-950"
                : "rounded-bl-md bg-white text-slate-800",
            message.status === "streaming" ? "ring-2 ring-honey-200" : "",
            message.status === "failed"
              ? "border border-red-300 bg-red-50 text-red-700"
              : "",
          ].join(" ")}
        >
          {hasCliBlocks(message.content_blocks) ? (
            <CliMessageView
              blocks={message.content_blocks}
              streaming={message.status === "streaming"}
            />
          ) : message.content ? (
            <PlainMessageBody
              content={message.content}
              modelUsed={message.model_used}
              streaming={message.status === "streaming"}
            />
          ) : message.status === "streaming" ? (
            <span className="text-slate-400">…</span>
          ) : (
            ""
          )}
        </div>
      </div>
      {isUser && showAvatar && <Avatar name="我" kind="user" size={32} />}
    </div>
  );
}

function PlainMessageBody({
  content,
  modelUsed,
  streaming,
}: {
  content: string;
  modelUsed: string | null;
  streaming?: boolean;
}) {
  const segments = splitMessageContent(content);
  const hasTools = segments.some((s) => s.kind === "tool_json");

  if (!hasTools) {
    return renderCliText({ content, modelUsed, streaming });
  }

  return (
    <div className="flex flex-col gap-2">
      {segments.map((seg, i) =>
        seg.kind === "text" ? (
          <div key={i} className="whitespace-pre-wrap">
            {renderCliText({
              content: seg.text,
              modelUsed,
              streaming: streaming && i === segments.length - 1,
            })}
          </div>
        ) : (
          <Collapsible
            key={i}
            tone="tool"
            summary={
              <>
                <span className="text-sky-700">tool</span>
                <span className="ml-1 text-slate-600">
                  {seg.toolName ?? "call"}
                </span>
              </>
            }
          >
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-slate-700">
              {seg.raw}
            </pre>
          </Collapsible>
        ),
      )}
    </div>
  );
}
