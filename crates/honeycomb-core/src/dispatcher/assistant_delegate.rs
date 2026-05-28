//! 群助理（用户代理人）独立通道：不参与 Judge 抢答。

use crate::agent::ChatContext;
use crate::domain::{
    AssistantMode, AutonomyLevel, Friend, Group, Message, MessageStatus, SenderKind,
};
use crate::store::SqliteStore;
use crate::{Error, Result};

use super::assistant_autonomy::classify_autonomy_for_message;
use super::im_writeback::{spawn_im_writeback_notify, ImWritebackEvent};
use super::MessageDispatcher;

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
    ["@助理", "@hex", " hex", "助理", "assistant"].iter().any(|k| lower.contains(k))
}

fn needs_human_confirm(detected: AutonomyLevel, max: AutonomyLevel) -> bool {
    detected == AutonomyLevel::L4
        || detected == AutonomyLevel::L3
        || detected.rank() > max.rank()
}

pub fn build_delegate_prompt(group: &Group, user_msg: &Message, confirm: bool) -> String {
    let mode_hint = if confirm {
        "本条须用户确认：请以「【待你确认】」开头，列出建议与风险，不要替用户做最终决定。"
    } else {
        "本条可代用户轻量回应：语气自然，开头可用「我代主人理解：」；勿做不可逆承诺。"
    };
    format!(
        "你是群「{}」中用户的代理人（Hex 助理），不是抢话的技术专家。\n\
         {mode_hint}\n\
         用户 [{}] 刚说：\n{}\n\
         请给出一条简短、有帮助的回复。",
        group.name, user_msg.sender_name, user_msg.content
    )
}

impl MessageDispatcher {
    pub(super) async fn maybe_dispatch_group_assistant(
        &self,
        conv_id: &str,
        group: &Group,
        user_msg: &Message,
        turn_id: &str,
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
        let confirm = needs_human_confirm(detected, ast.max_autonomy);
        let force = user_mentions_assistant(&user_msg.content);

        if ast.mode == AssistantMode::Delegate
            && ast.reply_after_experts
            && !force
            && !confirm
        {
            // 已在专家轮次之后调用；无需额外等待
        }

        let conv = self
            .store
            .get_conversation(conv_id)
            .await?
            .ok_or_else(|| Error::not_found("conversation"))?;

        let agent = self.agents.get(&friend.id).await?;
        let history = self.store.recent_messages(conv_id, 60).await?;
        let mut group_for_ctx = group.clone();
        group_for_ctx.settings.assistant = ast.clone();
        let ctx = ChatContext {
            conversation_id: conv.id.clone(),
            group_settings: Some(group_for_ctx.settings),
            history,
            self_friend: friend.clone(),
            peers: experts,
        };
        let prompt = build_delegate_prompt(group, user_msg, confirm);
        let on_behalf = !confirm;
        let final_status = if confirm {
            MessageStatus::WaitingHuman
        } else {
            MessageStatus::Done
        };

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
                    on_behalf_of_user: on_behalf,
                    final_status,
                },
            )
            .await?
        {
            record_group_delegate_memory(&self.store, group, user_msg, &reply, &friend.id).await;
            if let Some(im_event) = if reply.status == MessageStatus::WaitingHuman {
                Some(ImWritebackEvent::WaitingHuman)
            } else if reply.on_behalf_of_user {
                Some(ImWritebackEvent::DelegatePosted)
            } else {
                None
            } {
                spawn_im_writeback_notify(
                    group.clone(),
                    ast.clone(),
                    conv.id.clone(),
                    reply,
                    im_event,
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
) {
    if reply.content.trim().is_empty() {
        return;
    }
    let summary = format!(
        "[群:{}] 用户: {}\n助理: {}",
        group.name,
        truncate_chars(&user_msg.content, 200),
        truncate_chars(&reply.content, 400),
    );
    if let Err(e) = store
        .insert_memory(crate::store::memory::NewMemory {
            owner_friend_id: friend_id.to_string(),
            kind: crate::assistant_accumulation::MEMORY_KIND_MEMO.to_string(),
            content: summary,
            source_message_id: Some(reply.id.clone()),
            weight: 0.55,
            pinned: false,
        })
        .await
    {
        tracing::warn!(err = %e, "group delegate memory insert failed");
    }
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
