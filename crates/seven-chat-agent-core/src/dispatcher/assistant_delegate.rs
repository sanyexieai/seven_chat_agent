//! 群助理（用户代理人）独立通道：不参与 Judge 抢答，作为主人替身决策。

use crate::agent::ChatContext;
use crate::domain::{
    AssistantMode, AutonomyLevel, Friend, Group, Message, MessageStatus, SenderKind,
};
use crate::store::SqliteStore;
use crate::{Error, Result};

use super::assistant_autonomy::classify_autonomy_for_message;
use super::im_writeback::{spawn_im_writeback_notify, ImWritebackEvent};
use super::MessageDispatcher;
use super::BusEvent;

pub fn classify_autonomy(content: &str) -> AutonomyLevel {
    let lower = content.to_lowercase();
    let l4 = [
        "force push",
        "硬重置",
        "删库",
        "drop database",
        "转账",
        "付款",
        "签约",
        "合同",
        "法律责任",
    ];
    if l4.iter().any(|k| lower.contains(k)) {
        return AutonomyLevel::L4;
    }
    let l3 = [
        "删除",
        "删掉",
        "移除生产",
        "上线",
        "发布",
        "部署",
        "merge",
        "合并 pr",
        "预算",
        "采购",
        "承诺",
        "保证",
        "deploy",
        "production",
    ];
    if l3.iter().any(|k| lower.contains(k)) {
        return AutonomyLevel::L3;
    }
    let l2 = [
        "修改",
        "更新",
        "创建",
        "执行",
        "运行",
        "修复",
        "fix",
        "implement",
        "refactor",
        "run ",
        "cargo ",
        "npm ",
    ];
    if l2.iter().any(|k| lower.contains(k)) {
        return AutonomyLevel::L2;
    }
    AutonomyLevel::L1
}

pub fn user_mentions_assistant(content: &str) -> bool {
    let lower = content.to_lowercase();
    ["@助理", "@hex", " hex", "助理", "assistant"]
        .iter()
        .any(|k| lower.contains(k))
}

/// 是否超出代理人可拍板范围（仅用于备忘录/推送分级，不阻断群内专家）。
fn exceeds_proxy_autonomy(detected: AutonomyLevel, max: AutonomyLevel) -> bool {
    detected == AutonomyLevel::L4
        || detected == AutonomyLevel::L3
        || detected.rank() > max.rank()
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GroupAssistantPhase {
    /// 用户刚发言、专家尚未接话（轻量回应）。
    OnUserMessage,
    /// 专家/任务流已产出后，代理人综合决策（主路径）。
    AfterExperts,
}

pub fn build_delegate_prompt(
    group: &Group,
    user_msg: &Message,
    phase: GroupAssistantPhase,
    expert_summary: &str,
    owner_attention: bool,
) -> String {
    let attention_hint = if owner_attention {
        "本条涉及较高风险或超出默认可拍板范围：你仍须在群内给出**代理立场与可执行方向**（让专家继续推进），\
         勿用「请主人决定」空挡；同时用一句话标明「已记入主人备忘录并推送知悉」。"
    } else {
        "在授权范围内可直接代主人拍板，给出明确下一步，让专家能继续执行。"
    };

    match phase {
        GroupAssistantPhase::OnUserMessage => format!(
            "你是群「{}」中用户的代理人（替身），不是抢话的技术专家。\n\
             {attention_hint}\n\
             用户 [{}] 刚说：\n{}\n\
             请一条简短回应：确认收到、代为定调或协调专家，语气自然，可用「我代主人」。",
            group.name, user_msg.sender_name, user_msg.content
        ),
        GroupAssistantPhase::AfterExperts => format!(
            "你是群「{}」中用户的代理人（替身），不是普通技术专家。\n\
             {attention_hint}\n\n\
             用户原话 [{}]：\n{}\n\n\
             本轮专家/负责人发言摘要：\n{}\n\n\
             请综合后输出一条群内回复（代主人）：\n\
             1. 明确立场或下一步指令（能拍板则拍板）\n\
             2. 如需主人后续确认，仅标注「已同步主人备忘录」勿阻断讨论\n\
             3. 避免复述全文，聚焦决策与行动",
            group.name,
            user_msg.sender_name,
            user_msg.content,
            if expert_summary.trim().is_empty() {
                "（暂无其他专家发言）"
            } else {
                expert_summary
            }
        ),
    }
}

fn summarize_expert_turn(history: &[Message], assistant_id: &str) -> String {
    let mut lines = Vec::new();
    for m in history {
        if m.sender_kind != SenderKind::Friend {
            continue;
        }
        if m.sender_id == assistant_id {
            continue;
        }
        if m.on_behalf_of_user {
            continue;
        }
        let excerpt = truncate_chars(m.content.trim(), 280);
        if excerpt.is_empty() {
            continue;
        }
        lines.push(format!("- {}：{}", m.sender_name, excerpt));
    }
    if lines.len() > 8 {
        lines.truncate(8);
        lines.push("…（更多发言见上文）".into());
    }
    lines.join("\n")
}

impl MessageDispatcher {
    pub(super) async fn maybe_dispatch_group_assistant(
        &self,
        conv_id: &str,
        group: &Group,
        user_msg: &Message,
        turn_id: &str,
        phase: GroupAssistantPhase,
    ) -> Result<()> {
        if user_msg.sender_kind != SenderKind::User {
            return Ok(());
        }
        let settings = &group.settings;
        let ast = self
            .store
            .resolve_group_assistant_settings(&settings.assistant)
            .await?;
        if !ast.enabled {
            return Ok(());
        }
        match ast.mode {
            AssistantMode::Observe => return Ok(()),
            AssistantMode::Moderate => {
                if !user_mentions_assistant(&user_msg.content) {
                    return Ok(());
                }
            }
            AssistantMode::Delegate => {}
        }

        let assistant_id = match self.store.group_assistant_member_id(&group.id).await? {
            Some(id) => id,
            None => return Ok(()),
        };
        let friend = match self.store.get_friend(&assistant_id).await? {
            Some(f) if f.enabled => f,
            _ => return Ok(()),
        };

        let force = user_mentions_assistant(&user_msg.content);
        if ast.mode == AssistantMode::Delegate
            && ast.reply_after_experts
            && !force
            && phase == GroupAssistantPhase::OnUserMessage
        {
            return Ok(());
        }

        let member_configs = self.store.list_group_member_configs(&group.id).await?;
        let experts: Vec<Friend> = load_expert_friends(&self.store, &member_configs).await?;

        let detected = classify_autonomy_for_message(
            &self.store,
            &self.providers,
            &ast,
            &user_msg.content,
            &group.name,
        )
        .await;
        let owner_attention = exceeds_proxy_autonomy(detected, ast.max_autonomy);

        let conv = self
            .store
            .get_conversation(conv_id)
            .await?
            .ok_or_else(|| Error::not_found("conversation"))?;

        let agent = self.agents.get(&friend.id).await?;
        let history = self.store.recent_messages(conv_id, 60).await?;
        let expert_summary = summarize_expert_turn(&history, &friend.id);
        let mut group_for_ctx = group.clone();
        group_for_ctx.settings.assistant = ast.clone();
        let ctx = ChatContext {
            conversation_id: conv.id.clone(),
            group_id: Some(group.id.clone()),
            group_settings: Some(group_for_ctx.settings),
            history,
            self_friend: friend.clone(),
            peers: experts,
        };
        let prompt = build_delegate_prompt(
            group,
            user_msg,
            phase,
            &expert_summary,
            owner_attention,
        );

        // 代理人始终在群内代主人发言且为 done，不占用 waiting_human 阻断专家接话。
        if let Some(reply) = self
            .stream_one_reply_with_options(
                &conv,
                user_msg,
                turn_id,
                &friend,
                agent,
                ctx,
                &prompt,
                StreamReplyOptions {
                    on_behalf_of_user: true,
                    final_status: MessageStatus::Done,
                },
            )
            .await?
        {
            record_group_delegate_memory(
                &self.store,
                group,
                user_msg,
                &reply,
                &friend.id,
                owner_attention,
                detected,
            )
            .await;

            if owner_attention {
                notify_owner_attention(
                    self,
                    group,
                    &ast,
                    &conv.id,
                    turn_id,
                    &friend.id,
                    &reply,
                    detected,
                )
                .await;
            } else if ast.im_writeback.enabled {
                spawn_im_writeback_notify(
                    group.clone(),
                    ast.clone(),
                    conv.id.clone(),
                    reply,
                    ImWritebackEvent::DelegatePosted,
                );
            }
        }
        Ok(())
    }
}

async fn record_group_delegate_memory(
    store: &SqliteStore,
    group: &Group,
    user_msg: &Message,
    reply: &Message,
    friend_id: &str,
    owner_attention: bool,
    detected: AutonomyLevel,
) {
    if reply.content.trim().is_empty() {
        return;
    }
    let tag = if owner_attention {
        "[待主人知悉]"
    } else {
        "[代理决策]"
    };
    let content = format!(
        "{tag} 群:{} 自主级别检测:{:?}\n用户: {}\n代理人: {}",
        group.name,
        detected,
        truncate_chars(&user_msg.content, 200),
        truncate_chars(&reply.content, 400),
    );
    let short = crate::memory_tier::make_summary(&content, 200);
    if let Err(e) = store
        .insert_memory(crate::store::memory::NewMemory {
            owner_friend_id: friend_id.to_string(),
            kind: crate::assistant_accumulation::MEMORY_KIND_MEMO.to_string(),
            content,
            source_message_id: Some(reply.id.clone()),
            weight: if owner_attention { 0.75 } else { 0.55 },
            pinned: owner_attention,
            tier: if owner_attention {
                crate::memory_tier::TIER_CURATED.to_string()
            } else {
                crate::memory_tier::TIER_RAW.to_string()
            },
            scope: crate::memory_tier::SCOPE_CONVERSATION.to_string(),
            scope_ref: None,
            importance: if owner_attention { 2 } else { 1 },
            status: crate::memory_tier::STATUS_ACTIVE.to_string(),
            title: None,
            summary: Some(short),
            expires_at: None,
        })
        .await
    {
        tracing::warn!(err = %e, "group delegate memory insert failed");
    }
}

async fn notify_owner_attention(
    dispatcher: &MessageDispatcher,
    group: &Group,
    ast: &crate::domain::GroupAssistantSettings,
    conversation_id: &str,
    _turn_id: &str,
    assistant_id: &str,
    reply: &Message,
    detected: AutonomyLevel,
) {
    let title = format!("群「{}」代理人待你知悉", group.name);
    let body = truncate_chars(&reply.content, 320);

    if ast.notify_owner_proactively {
        dispatcher.emit(BusEvent::AssistantOwnerNotify {
            conversation_id: conversation_id.to_string(),
            group_id: group.id.clone(),
            group_name: group.name.clone(),
            title: title.clone(),
            body: body.clone(),
            message_id: Some(reply.id.clone()),
        });
    }

    let dm_note = format!(
        "[主人知悉] {title}\n风险级别检测: {:?}\n{body}\n（专家可继续推进，本条仅同步你）",
        detected
    );
    if let Ok(conv) = dispatcher.store.get_or_create_dm(assistant_id).await {
        if let Ok(msg) = dispatcher
            .store
            .insert_message(crate::store::message::NewMessage {
                conversation_id: &conv.id,
                turn_id: &reply.turn_id,
                parent_id: Some(&reply.id),
                sender_kind: SenderKind::Friend,
                sender_id: assistant_id,
                sender_name: "Hex 助理",
                content: &dm_note,
                mentions: &[],
                status: MessageStatus::Done,
                on_behalf_of_user: false,
            })
            .await
        {
            dispatcher.emit(BusEvent::MessageCreated {
                message: msg.clone(),
            });
            dispatcher.emit(BusEvent::MessageDone { message: msg });
        }
    }

    let todo_title = format!("【待确认】群「{}」代理人提请知悉", group.name);
    let _ = dispatcher
        .store
        .create_assistant_todo(
            assistant_id,
            &todo_title,
            Some(&body),
            None,
            None,
            2,
            None,
        )
        .await;

    spawn_im_writeback_notify(
        group.clone(),
        ast.clone(),
        conversation_id.to_string(),
        reply.clone(),
        ImWritebackEvent::WaitingHuman,
    );
}

fn truncate_chars(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        return s.to_string();
    }
    let mut out: String = s.chars().take(max).collect();
    out.push('…');
    out
}

pub(super) struct StreamReplyOptions {
    pub on_behalf_of_user: bool,
    pub final_status: MessageStatus,
}

async fn load_expert_friends(
    store: &SqliteStore,
    configs: &[crate::domain::GroupMemberConfig],
) -> Result<Vec<Friend>> {
    let mut out = Vec::new();
    for c in configs {
        if !c.role.participates_in_expert_scheduling() {
            continue;
        }
        if let Some(f) = store.get_friend(&c.friend_id).await? {
            if f.enabled {
                out.push(f);
            }
        }
    }
    Ok(out)
}

pub(super) async fn expert_friends_for_group(
    store: &SqliteStore,
    group_id: &str,
) -> Result<Vec<Friend>> {
    let configs = store.list_group_member_configs(group_id).await?;
    load_expert_friends(store, &configs).await
}
