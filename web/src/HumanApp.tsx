import { useEffect, useRef, useState } from "react";
import { api, connectWs } from "./api/client";
import type { Friend, Message } from "./types";
import { Avatar } from "./components/Avatar";
import { MessageBubble } from "./components/MessageBubble";

interface Props {
  code: string;
}

export function HumanApp({ code }: Props) {
  const [friend, setFriend] = useState<Friend | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [convId, setConvId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const typingTimer = useRef<number | null>(null);

  useEffect(() => {
    api
      .humanState(code)
      .then(({ friend, messages }) => {
        setFriend(friend);
        setMessages(messages);
        setConvId(messages[0]?.conversation_id ?? null);
      })
      .catch((e) => setError(e.message || String(e)));
  }, [code]);

  useEffect(() => {
    const ws = connectWs((ev: any) => {
      switch (ev.type) {
        case "message_created":
          if (!convId || ev.message.conversation_id === convId) {
            setMessages((m) => [...m, ev.message]);
            if (!convId) setConvId(ev.message.conversation_id);
          }
          break;
        case "message_delta":
          if (!ev.thinking) {
            setMessages((ms) =>
              ms.map((m) =>
                m.id === ev.message_id
                  ? { ...m, content: m.content + ev.delta }
                  : m,
              ),
            );
          }
          break;
        case "message_done":
          setMessages((ms) =>
            ms.map((m) => (m.id === ev.message.id ? ev.message : m)),
          );
          break;
      }
    });
    return () => ws.close();
  }, [convId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const content = draft.trim();
    if (!content || busy) return;
    setBusy(true);
    setDraft("");
    try {
      const res = await api.humanSend(code, content, convId ?? undefined);
      if (!convId) setConvId(res.conversation_id);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function onChangeDraft(value: string) {
    setDraft(value);
    if (typingTimer.current) {
      window.clearTimeout(typingTimer.current);
    }
    api.humanTyping(code, 3000).catch(() => {});
    typingTimer.current = window.setTimeout(() => {}, 200);
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-50">
        <div className="card max-w-md">
          <div className="font-semibold text-red-600">邀请链接失效</div>
          <div className="mt-1 text-sm text-slate-600">{error}</div>
        </div>
      </div>
    );
  }

  if (!friend) {
    return (
      <div className="flex h-full items-center justify-center text-slate-400">
        正在认证邀请...
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-gradient-to-b from-slate-100 to-slate-50">
      <header className="flex items-center gap-3 border-b border-slate-200 bg-white/80 px-4 py-3 backdrop-blur">
        <Avatar name={friend.name} kind="human" size={40} />
        <div className="flex-1">
          <div className="text-sm font-semibold text-slate-800">
            {friend.name}
          </div>
          <div className="text-xs text-slate-500">
            你正以这位好友的身份接入 honeycomb
          </div>
        </div>
        <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700">
          在线
        </span>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <div className="mt-12 text-center text-sm text-slate-400">
            还没有人说话，先发一条试试。
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble
            key={m.id}
            message={{
              ...m,
              sender_kind:
                m.sender_kind === "friend" && m.sender_id === friend.id
                  ? "user"
                  : m.sender_kind,
            }}
          />
        ))}
        <div ref={endRef} />
      </div>
      <form
        className="flex items-end gap-2 border-t border-slate-200 bg-white px-4 py-3"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <textarea
          rows={2}
          value={draft}
          onChange={(e) => onChangeDraft(e.target.value)}
          placeholder="作为这位真人好友说点什么..."
          className="input resize-none"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button className="btn-primary h-10 px-5" disabled={busy}>
          {busy ? "..." : "发送"}
        </button>
      </form>
    </div>
  );
}
