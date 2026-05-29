import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  configuredJudgeModeLabel,
  judgeSourceLabel,
  memberVerdictShort,
  scheduleModeLabel,
} from "../judgeLabels";
import { useChat } from "../stores/chat";
import { MessageBubble } from "./MessageBubble";
import { MessageTimeDivider } from "./MessageTimeDivider";
import { shouldShowMessageTime } from "../messageTime";
import { TaskFlowPanel } from "./TaskFlowPanel";
import { Avatar } from "./Avatar";

export function ChatWindow() {
  const {
    friends,
    groups,
    target,
    conversation,
    messages,
    sendMessage,
    thinking,
    judgeBanner,
    ownerNotify,
    taskFlow,
  } = useChat();
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const sendLock = useRef(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  const header = useMemo(() => {
    if (!target) return null;
    if (target.kind === "friend") {
      const f = friends.find((f) => f.id === target.id);
      if (!f) return null;
      return {
        title: f.name,
        subtitle:
          f.focus_tags.length > 0
            ? `关注：${f.focus_tags.join(" · ")}`
            : f.personality || "",
        right:
          f.backend_kind === "api"
            ? f.backend_config?.model || ""
            : f.backend_kind,
        avatarName: f.name,
        avatarKind: f.backend_kind,
      };
    } else {
      const gb = groups.find((g) => g.group.id === target.id);
      if (!gb) return null;
      return {
        title: gb.group.name,
        subtitle: `${gb.member_ids.length} 位成员 · 群聊`,
        right: `Judge ${gb.group.settings.judge?.mode ?? "heuristic"} · ${(gb.group.settings.judge?.threshold ?? gb.group.settings.judge_threshold).toFixed(2)}`,
        avatarName: gb.group.name,
        avatarKind: undefined,
      };
    }
  }, [target, friends, groups]);

  const groupMembers = useMemo(() => {
    if (target?.kind !== "group") return [] as ReturnType<typeof friends.filter>;
    const gb = groups.find((g) => g.group.id === target.id);
    if (!gb) return [];
    return friends.filter((f) => gb.member_ids.includes(f.id));
  }, [target, friends, groups]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, messages[messages.length - 1]?.content]);

  if (!target || !header) {
    return (
      <div className="flex h-full flex-1 items-center justify-center text-slate-400">
        选择左侧的好友或群聊开始对话
      </div>
    );
  }

  async function onSend(e?: React.FormEvent) {
    e?.preventDefault();
    const content = draft.trim();
    if (!content || sending || sendLock.current) return;
    sendLock.current = true;
    setSending(true);
    setDraft("");
    try {
      await sendMessage(content);
    } catch (err) {
      console.error(err);
    } finally {
      sendLock.current = false;
      setSending(false);
    }
  }

  return (
    <section className="flex h-full flex-1 flex-col bg-gradient-to-b from-slate-100 to-slate-50">
      <header className="flex items-center gap-3 border-b border-slate-200 bg-white/80 px-4 py-3 backdrop-blur">
        <Avatar
          name={header.avatarName}
          kind={header.avatarKind as any}
          size={40}
        />
        <div className="flex-1">
          <div className="text-sm font-semibold text-slate-800">
            {header.title}
          </div>
          <div className="text-xs text-slate-500">{header.subtitle}</div>
        </div>
        <div className="text-xs text-slate-400">{header.right}</div>
      </header>
      {target.kind === "group" && taskFlow && <TaskFlowPanel round={taskFlow} />}
      {target.kind === "group" &&
        ownerNotify &&
        target.id === ownerNotify.groupId && (
          <div className="border-b border-violet-200 bg-violet-50 px-4 py-2 text-xs text-violet-950">
            <div className="font-medium">{ownerNotify.title}</div>
            <p className="mt-1 leading-relaxed">{ownerNotify.body}</p>
            <p className="mt-1 text-violet-700/80">
              代理人已代你拍板并写入备忘录；专家可继续推进。可在 Hex 助理面板查看 Todo。
            </p>
          </div>
        )}
      {target.kind === "group" && judgeBanner && (
        <div
          className={`border-b px-4 py-2 text-xs leading-relaxed ${
            judgeBanner.scheduleMode === "fallback"
              ? "border-amber-200 bg-amber-50 text-amber-950"
              : judgeBanner.scheduleMode === "none"
                ? "border-slate-200 bg-slate-50 text-slate-600"
                : judgeBanner.scheduleMode === "pending"
                  ? "border-slate-200 bg-slate-50 text-slate-600"
                  : "border-emerald-200 bg-emerald-50/80 text-emerald-950"
          }`}
        >
          <div>
            <span className="font-medium">Judge 本轮</span>
            <span className="mx-1 text-slate-400">·</span>
            配置 {configuredJudgeModeLabel(judgeBanner.configuredMode)}
            <span className="mx-1 text-slate-400">·</span>
            {scheduleModeLabel(judgeBanner.scheduleMode)}
            <span className="mx-1 text-slate-400">·</span>
            愿接话且过阈值 {judgeBanner.willingToReply} 人（阈值{" "}
            {judgeBanner.threshold.toFixed(2)}）
            <span className="mx-1 text-slate-400">·</span>
            {judgeBanner.pickedViaFallback ? "兜底点名" : "将发言"}：
            {judgeBanner.pickedNames.length > 0
              ? judgeBanner.pickedNames.join("、")
              : "（无）"}
          </div>
          {judgeBanner.verdicts.length > 0 && (
            <div className="mt-1 text-[11px] text-slate-600">
              LLM 判定：
              {judgeBanner.verdicts
                .map((v) =>
                  memberVerdictShort(
                    v.friendName,
                    v.shouldReply,
                    v.confidence,
                    v.judgeSource,
                  ),
                )
                .join(" · ")}
            </div>
          )}
          {judgeBanner.scheduleMode === "fallback" &&
            judgeBanner.verdicts.every((v) => !v.shouldReply) && (
              <div className="mt-1 text-[11px] text-amber-800">
                LLM 认为大家都不该接话，但群设置开启了「未过线兜底」，仍会强制选 1
                人发言。若希望尊重 LLM 判断，可在群设置关闭该选项。
              </div>
            )}
        </div>
      )}
      {target.kind === "group" && (
        <div className="flex gap-2 overflow-x-auto border-b border-slate-200 bg-white px-4 py-2">
          {groupMembers.map((m) => {
            const state = thinking[m.id];
            const label = state
              ? state.status === "judging"
                ? "在想..."
                : state.status === "will_reply"
                  ? "准备发言"
                  : state.status === "speaking"
                    ? "正在说"
                    : "已读不回"
              : "";
            const colorClass = state
              ? state.status === "skip"
                ? "text-slate-400"
                : state.status === "speaking"
                  ? "text-honey-700"
                  : "text-emerald-600"
              : "text-slate-400";
            const srcTag = state?.judgeSource
              ? judgeSourceLabel(state.judgeSource)
              : null;
            const srcWarn =
              state?.judgeSource === "llm_failed" ||
              (state?.configuredJudgeMode === "llm" &&
                state?.judgeSource &&
                state.judgeSource !== "llm");
            return (
              <div
                key={m.id}
                className="flex items-center gap-2 rounded-full bg-slate-100 px-2 py-1 text-xs"
              >
                <Avatar name={m.name} kind={m.backend_kind} size={20} />
                <span className="text-slate-700">{m.name}</span>
                {srcTag && (
                  <span
                    className={`text-[10px] ${srcWarn ? "text-amber-700" : "text-slate-500"}`}
                    title={state?.reason ?? undefined}
                  >
                    {srcTag}
                  </span>
                )}
                {label && (
                  <span className={`text-[10px] ${colorClass}`}>{label}</span>
                )}
              </div>
            );
          })}
        </div>
      )}
      <div className="flex-1 space-y-2 overflow-y-auto px-4 py-4 sm:px-6">
        {messages.length === 0 && (
          <div className="mt-12 text-center text-sm text-slate-400">
            {target.kind === "friend"
              ? "和这位好友开启第一次对话吧。"
              : "在群里说点什么，看大家会不会出声。"}
          </div>
        )}
        {messages.map((m, i) => {
          const prev = messages[i - 1];
          const showTime = shouldShowMessageTime(
            m.created_at,
            prev?.created_at,
          );
          return (
            <Fragment key={m.id}>
              {showTime && <MessageTimeDivider createdAt={m.created_at} />}
              <MessageBubble
                message={m}
                conversationId={conversation?.id}
              />
            </Fragment>
          );
        })}
        <div ref={endRef} />
      </div>
      <form
        className="flex items-end gap-2 border-t border-slate-200 bg-white px-4 py-3"
        onSubmit={onSend}
      >
        <textarea
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="说点什么... (Enter 发送, Shift+Enter 换行)"
          className="input resize-none"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
        />
        <button className="btn-primary h-10 px-5" disabled={sending}>
          {sending ? "..." : "发送"}
        </button>
      </form>
    </section>
  );
}
