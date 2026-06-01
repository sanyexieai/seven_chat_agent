import { useState } from "react";
import { api } from "../api/client";
import { hasCliBlocks } from "../cliBlocks";
import { splitMessageContent } from "../messageContent";
import type { Message } from "../types";
import { Avatar } from "./Avatar";
import { CliMessageView } from "./CliMessageView";
import { MessageAttachments } from "./MessageAttachments";
import { Collapsible } from "./Collapsible";
import { renderCliText } from "./cli/drivers";

interface Props {
  message: Message;
  showAvatar?: boolean;
  conversationId?: string | null;
}

export function MessageBubble({
  message,
  showAvatar = true,
  conversationId,
}: Props) {
  const isUser = message.sender_kind === "user";
  const isSystem = message.sender_kind === "system";
  const showDelegateActions =
    !!conversationId &&
    message.status === "waiting_human" &&
    message.sender_kind === "friend";

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
            {message.on_behalf_of_user && (
              <span className="ml-1.5 rounded bg-honey-100 px-1.5 py-0.5 text-[10px] font-medium text-honey-800">
                代你
              </span>
            )}
            {message.status === "waiting_human" && (
              <span className="ml-1.5 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
                待你确认
              </span>
            )}
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
            message.status === "waiting_human"
              ? "border border-amber-200 bg-amber-50/80"
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
          ) : null}
          {message.attachments && message.attachments.length > 0 && (
            <MessageAttachments
              attachments={message.attachments}
              variant={isUser ? "user" : "assistant"}
            />
          )}
        </div>
        {showDelegateActions && (
          <DelegateActions
            conversationId={conversationId!}
            message={message}
          />
        )}
      </div>
      {isUser && showAvatar && <Avatar name="我" kind="user" size={32} />}
    </div>
  );
}

function DelegateActions({
  conversationId,
  message,
}: {
  conversationId: string;
  message: Message;
}) {
  const [busy, setBusy] = useState(false);

  async function resolve(approve: boolean) {
    if (busy) return;
    setBusy(true);
    try {
      await api.resolveDelegate(conversationId, message.id, {
        approve,
        content: message.content,
      });
    } catch (e) {
      console.error(e);
      alert(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap gap-2 pl-1">
      <button
        type="button"
        className="rounded-md bg-honey-500 px-2.5 py-1 text-xs font-medium text-slate-900 shadow-sm hover:bg-honey-400 disabled:opacity-50"
        disabled={busy}
        onClick={() => resolve(true)}
      >
        采纳代发
      </button>
      <button
        type="button"
        className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        disabled={busy}
        onClick={() => resolve(false)}
      >
        不采纳
      </button>
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
