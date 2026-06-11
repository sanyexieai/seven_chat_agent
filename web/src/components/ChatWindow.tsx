import { Fragment, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useShallow } from "zustand/react/shallow";
import { api } from "../api/client";
import type { MessageAttachment } from "../types";
import {
  configuredJudgeModeLabel,
  intentClassifierLabel,
  judgeSourceLabel,
  memberVerdictShort,
  scheduleModeLabel,
  turnIntentLabel,
} from "../judgeLabels";
import { mergeMessages, useChat } from "../stores/chat";
import { MessageBubble } from "./MessageBubble";
import { MessageTimeDivider } from "./MessageTimeDivider";
import { shouldShowMessageTime } from "../messageTime";
import { TaskFlowPanel } from "./TaskFlowPanel";
import { OrchestrationEventLog } from "./OrchestrationEventLog";
import { Collapsible } from "./Collapsible";
import { Avatar } from "./Avatar";
import { ChatWorkspaceSwitcher } from "./ChatWorkspaceSwitcher";

interface Props {
  onEditGroup?: (groupId: string, opts?: { scrollToConsensus?: boolean }) => void;
}

export function ChatWindow({ onEditGroup }: Props) {
  const {
    friends,
    groups,
    target,
    conversation,
    messages,
    sendMessage,
    thinking,
    judgeBanner,
    turnIntentBanner,
    orchestrationLog,
    ownerNotify,
    groupPublicBanner,
    taskFlow,
  } = useChat(
    useShallow((s) => ({
      friends: s.friends,
      groups: s.groups,
      target: s.target,
      conversation: s.conversation,
      messages: s.messages,
      sendMessage: s.sendMessage,
      thinking: s.thinking,
      judgeBanner: s.judgeBanner,
      turnIntentBanner: s.turnIntentBanner,
      orchestrationLog: s.orchestrationLog,
      ownerNotify: s.ownerNotify,
      groupPublicBanner: s.groupPublicBanner,
      taskFlow: s.taskFlow,
    })),
  );
  const [draft, setDraft] = useState("");
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const sendLock = useRef(false);
  const endRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
      const orch = gb.group.settings.orchestration;
      const tf = gb.group.settings.task_flow;
      const orchParts: string[] = [];
      if (tf?.enabled) {
        orchParts.push(orch?.light_task_flow ? "轻量任务流" : "完整任务流");
      } else {
        orchParts.push("自由讨论");
      }
      orchParts.push(
        `意图·${intentClassifierLabel(orch?.intent_classifier ?? "heuristic")}`,
      );
      return {
        title: gb.group.name,
        subtitle: `${gb.member_ids.length} 位成员 · ${orchParts.join(" · ")}`,
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

  function onPickFiles(e: ChangeEvent<HTMLInputElement>) {
    const list = e.target.files;
    if (!list?.length) return;
    setPendingFiles((prev) => [...prev, ...Array.from(list)]);
    e.target.value = "";
  }

  async function resolveConversationId(): Promise<string | null> {
    if (conversation?.id) return conversation.id;
    if (target?.kind !== "friend") return null;
    const opened = await api.openDm(target.id);
    const state = useChat.getState();
    const cid = opened.conversation.id;
    const merged = mergeMessages(opened.messages, state.messageCache[cid]);
    useChat.setState({
      conversation: opened.conversation,
      messages: merged,
      messageCache: { ...state.messageCache, [cid]: merged },
    });
    return cid;
  }

  async function onSend(e?: React.FormEvent) {
    e?.preventDefault();
    const content = draft.trim();
    if ((!content && pendingFiles.length === 0) || sending || sendLock.current) {
      return;
    }
    sendLock.current = true;
    setSending(true);
    const files = [...pendingFiles];
    setDraft("");
    setPendingFiles([]);
    try {
      let attachments: MessageAttachment[] = [];
      if (files.length > 0) {
        const convId = await resolveConversationId();
        if (!convId) throw new Error("无法获取会话");
        attachments = await api.uploadConversationAttachments(convId, files);
      }
      await sendMessage(content, attachments);
    } catch (err) {
      console.error(err);
      setPendingFiles(files);
      if (content) setDraft(content);
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
      {target.kind === "group" &&
        groupPublicBanner &&
        target.id === groupPublicBanner.groupId && (
          <div className="border-b border-teal-200 bg-teal-50/90 px-3 py-1.5 text-xs text-teal-950">
            <span className="font-medium">群共识已更新</span>
            {groupPublicBanner.excerpt && (
              <span className="ml-2 text-teal-800/90">
                {groupPublicBanner.excerpt.slice(0, 120)}
                {groupPublicBanner.excerpt.length > 120 ? "…" : ""}
              </span>
            )}
            {onEditGroup && (
              <button
                type="button"
                className="ml-2 font-medium text-teal-700 underline decoration-teal-400/60 underline-offset-2 hover:text-teal-900"
                onClick={() =>
                  onEditGroup(target.id, { scrollToConsensus: true })
                }
              >
                查看群共识
              </button>
            )}
          </div>
        )}
      {target.kind === "group" && turnIntentBanner && (
        <div className="border-b border-sky-200 bg-sky-50/80 px-3 py-1.5 text-xs text-sky-950">
          <span className="font-medium">回合意图</span>
          <span className="mx-1.5 text-sky-400">·</span>
          {turnIntentLabel(turnIntentBanner.intent)}
          <span className="mx-1.5 text-sky-400">·</span>
          {intentClassifierLabel(turnIntentBanner.classifier)}
          {(turnIntentBanner.intent === "chitchat" ||
            turnIntentBanner.intent === "qa") && (
            <span className="ml-2 text-sky-700/90">（不进入任务流）</span>
          )}
        </div>
      )}
      {target.kind === "group" && (
        <OrchestrationEventLog
          events={orchestrationLog}
          turnId={turnIntentBanner?.turnId ?? taskFlow?.turnId}
        />
      )}
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
          className={`border-b px-3 py-1.5 ${
            judgeBanner.scheduleMode === "fallback"
              ? "border-amber-200 bg-amber-50/90"
              : judgeBanner.scheduleMode === "none"
                ? "border-slate-200 bg-slate-50/90"
                : judgeBanner.scheduleMode === "pending"
                  ? "border-slate-200 bg-slate-50/90"
                  : "border-emerald-200 bg-emerald-50/70"
          }`}
        >
          <Collapsible
            defaultOpen={false}
            tone={
              judgeBanner.scheduleMode === "fallback" ? "neutral" : "neutral"
            }
            summary={
              <span
                className={`font-sans text-xs font-medium ${
                  judgeBanner.scheduleMode === "fallback"
                    ? "text-amber-950"
                    : "text-slate-800"
                }`}
              >
                Judge · {configuredJudgeModeLabel(judgeBanner.configuredMode)} ·{" "}
                {scheduleModeLabel(judgeBanner.scheduleMode)} · 过阈值{" "}
                {judgeBanner.willingToReply} 人 ·{" "}
                {judgeBanner.pickedViaFallback ? "兜底" : "发言"}：
                {judgeBanner.pickedNames.length > 0
                  ? judgeBanner.pickedNames.join("、")
                  : "（无）"}
              </span>
            }
          >
            <div className="space-y-1 text-xs leading-relaxed text-slate-700">
              <p>
                配置 {configuredJudgeModeLabel(judgeBanner.configuredMode)} ·{" "}
                {scheduleModeLabel(judgeBanner.scheduleMode)} · 愿接话且过阈值{" "}
                {judgeBanner.willingToReply} 人（阈值{" "}
                {judgeBanner.threshold.toFixed(2)}）·{" "}
                {judgeBanner.pickedViaFallback ? "兜底点名" : "将发言"}：
                {judgeBanner.pickedNames.length > 0
                  ? judgeBanner.pickedNames.join("、")
                  : "（无）"}
              </p>
              {judgeBanner.verdicts.length > 0 && (
                <p className="text-[11px] text-slate-600">
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
                </p>
              )}
              {judgeBanner.scheduleMode === "fallback" &&
                judgeBanner.verdicts.every((v) => !v.shouldReply) && (
                  <p className="text-[11px] text-amber-800">
                    LLM 认为大家都不该接话，但群设置开启了「未过线兜底」，仍会强制选
                    1 人发言。若希望尊重 LLM 判断，可在群设置关闭该选项。
                  </p>
                )}
            </div>
          </Collapsible>
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
      {target.kind === "friend" &&
        friends.find((f) => f.id === target.id)?.backend_kind === "pty" && (
          <ChatWorkspaceSwitcher friendId={target.id} placement="above-input" />
        )}
      <form
        className="flex flex-col gap-2 border-t border-slate-200 bg-white px-4 py-3"
        onSubmit={onSend}
      >
        {pendingFiles.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {pendingFiles.map((f, i) => (
              <span
                key={`${f.name}-${i}`}
                className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700"
              >
                {f.type.startsWith("image/") ? "🖼" : "📎"} {f.name}
                <button
                  type="button"
                  className="ml-1 text-slate-400 hover:text-slate-700"
                  onClick={() =>
                    setPendingFiles((prev) => prev.filter((_, j) => j !== i))
                  }
                  aria-label="移除"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          accept="image/*,.txt,.md,.pdf,.json,.csv"
          onChange={onPickFiles}
        />
        <button
          type="button"
          className="btn h-10 w-10 shrink-0 px-0 text-slate-600"
          title="上传图片或文件"
          disabled={sending}
          onClick={() => fileInputRef.current?.click()}
        >
          📎
        </button>
        <textarea
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="说点什么... (Enter 发送, Shift+Enter 换行)"
          className="input min-h-10 min-w-0 flex-1 resize-none !w-auto"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
        />
        <button
          type="submit"
          className="btn-primary h-10 shrink-0 whitespace-nowrap px-5"
          disabled={sending || (!draft.trim() && pendingFiles.length === 0)}
        >
          {sending ? "..." : "发送"}
        </button>
        </div>
      </form>
    </section>
  );
}
