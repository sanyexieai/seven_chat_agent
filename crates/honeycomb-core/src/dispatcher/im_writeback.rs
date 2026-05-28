//! 群助理事件 → 外部 IM Webhook 出站；入站由 HTTP 路由处理。

use serde::Serialize;

use crate::domain::{Group, GroupAssistantSettings, Message, MessageStatus};

#[derive(Debug, Clone, Copy)]
pub enum ImWritebackEvent {
    /// 助理已代发（`on_behalf_of_user`）。
    DelegatePosted,
    /// 助理发出待确认草稿。
    WaitingHuman,
    /// 用户已采纳代发。
    DelegateApproved,
    /// 用户已驳回建议。
    DelegateRejected,
}

impl ImWritebackEvent {
    fn as_str(self) -> &'static str {
        match self {
            Self::DelegatePosted => "assistant_delegate",
            Self::WaitingHuman => "assistant_waiting_human",
            Self::DelegateApproved => "delegate_approved",
            Self::DelegateRejected => "delegate_rejected",
        }
    }
}

#[derive(Debug, Serialize)]
struct ImWritebackPayload {
    event: &'static str,
    group_id: String,
    group_name: String,
    conversation_id: String,
    message: Message,
    #[serde(skip_serializing_if = "Option::is_none")]
    inbound_hint: Option<InboundHint>,
}

#[derive(Debug, Serialize)]
struct InboundHint {
    /// 供外部 IM 机器人回调。
    path: String,
    header: &'static str,
    actions: Vec<InboundAction>,
}

#[derive(Debug, Serialize)]
struct InboundAction {
    action: &'static str,
    label: &'static str,
}

/// 异步 POST 到群配置的 Webhook（失败仅打日志）。
pub fn spawn_im_writeback_notify(
    group: Group,
    ast: GroupAssistantSettings,
    conversation_id: String,
    message: Message,
    event: ImWritebackEvent,
) {
    let wb = ast.im_writeback;
    if !wb.enabled {
        return;
    }
    let url = match wb.webhook_url.filter(|s| !s.trim().is_empty()) {
        Some(u) => u,
        None => return,
    };
    let should_send = match event {
        ImWritebackEvent::DelegatePosted => {
            message.on_behalf_of_user && wb.notify_delegate
        }
        ImWritebackEvent::WaitingHuman => {
            message.status == MessageStatus::WaitingHuman && wb.notify_waiting_human
        }
        ImWritebackEvent::DelegateApproved | ImWritebackEvent::DelegateRejected => true,
    };
    if !should_send {
        return;
    }

    let inbound_hint = wb.inbound_secret.as_ref().map(|_| InboundHint {
        path: format!("/api/groups/{}/im/inbound", group.id),
        header: "X-Honeycomb-Im-Secret",
        actions: match event {
            ImWritebackEvent::WaitingHuman => vec![
                InboundAction {
                    action: "approve_delegate",
                    label: "采纳代发",
                },
                InboundAction {
                    action: "reject_delegate",
                    label: "不采纳",
                },
            ],
            _ => vec![],
        },
    });

    let payload = ImWritebackPayload {
        event: event.as_str(),
        group_id: group.id.clone(),
        group_name: group.name.clone(),
        conversation_id,
        message,
        inbound_hint,
    };
    let group_id_log = payload.group_id.clone();
    let event_log = payload.event;

    tokio::spawn(async move {
        if let Err(e) = post_webhook(&url, &payload).await {
            tracing::warn!(
                group_id = %group_id_log,
                event = event_log,
                err = %e,
                "im writeback webhook failed"
            );
        }
    });
}

async fn post_webhook(url: &str, payload: &ImWritebackPayload) -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;
    let resp = client
        .post(url)
        .json(payload)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("webhook status {}", resp.status()));
    }
    Ok(())
}
