import type { Message } from "../types";
import { Avatar } from "./Avatar";

interface Props {
  message: Message;
  showAvatar?: boolean;
}

export function MessageBubble({ message, showAvatar = true }: Props) {
  const isUser = message.sender_kind === "user";
  return (
    <div
      className={`flex items-end gap-2 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser && showAvatar && <Avatar name={message.sender_name} size={32} />}
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
              : "rounded-bl-md bg-white text-slate-800",
            message.status === "streaming"
              ? "ring-2 ring-honey-200"
              : "",
            message.status === "failed"
              ? "border border-red-300 bg-red-50 text-red-700"
              : "",
          ].join(" ")}
        >
          {message.content ||
            (message.status === "streaming" ? (
              <span className="text-slate-400">…</span>
            ) : (
              ""
            ))}
        </div>
      </div>
      {isUser && showAvatar && <Avatar name="我" kind="user" size={32} />}
    </div>
  );
}
