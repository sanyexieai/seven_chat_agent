use axum::body::Body;
use axum::extract::{Multipart, Path, State};
use axum::http::{header, StatusCode};
use axum::response::Response;
use axum::Json;
use seven_chat_agent_core::attachment::{
    read_attachment_bytes, save_upload, validate_attachments,
};
use seven_chat_agent_core::domain::MessageAttachment;

use crate::routes::errors::ApiError;
use crate::state::AppState;

pub async fn upload_conversation_attachments(
    State(s): State<AppState>,
    Path(conv_id): Path<String>,
    mut multipart: Multipart,
) -> Result<Json<serde_json::Value>, ApiError> {
    if s.core.store.get_conversation(&conv_id).await?.is_none() {
        return Err(ApiError::NotFound);
    }
    let data_dir = std::env::var("SEVEN_CHAT_AGENT_DATA").unwrap_or_else(|_| "data".into());
    let mut saved: Vec<MessageAttachment> = Vec::new();
    while let Some(field) = multipart
        .next_field()
        .await
            .map_err(|e| ApiError::BadRequest(format!("multipart: {e}")))?
    {
        let filename = field
            .file_name()
            .map(str::to_string)
            .unwrap_or_else(|| "file".to_string());
        let mime = field.content_type().map(str::to_string);
        let bytes = field
            .bytes()
            .await
            .map_err(|e| ApiError::BadRequest(format!("read file: {e}")))?;
        let att = save_upload(&data_dir, &conv_id, &filename, mime.as_deref(), &bytes)?;
        saved.push(att);
    }
    if saved.is_empty() {
        return Err(ApiError::BadRequest("未收到文件".into()));
    }
    Ok(Json(serde_json::json!({ "attachments": saved })))
}

pub async fn get_upload(
    State(s): State<AppState>,
    Path((conv_id, file_id)): Path<(String, String)>,
) -> Result<Response, ApiError> {
    if s.core.store.get_conversation(&conv_id).await?.is_none() {
        return Err(ApiError::NotFound);
    }
    let data_dir = std::env::var("SEVEN_CHAT_AGENT_DATA").unwrap_or_else(|_| "data".into());
    let bytes = read_attachment_bytes(&data_dir, &conv_id, &file_id)?;
    let path = seven_chat_agent_core::attachment::attachment_disk_path(&data_dir, &conv_id, &file_id);
    let mime = mime_guess::from_path(&path)
        .first()
        .map(|m| m.essence_str().to_string())
        .unwrap_or_else(|| "application/octet-stream".to_string());
    Ok(Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, mime)
        .header(header::CACHE_CONTROL, "private, max-age=3600")
        .body(Body::from(bytes))
        .unwrap())
}

#[derive(Debug, serde::Deserialize)]
pub struct SendWithAttachments {
    pub content: String,
    #[serde(default)]
    pub attachments: Vec<MessageAttachment>,
}

pub fn validate_send_attachments(
    data_dir: &str,
    conv_id: &str,
    attachments: &[MessageAttachment],
) -> Result<(), ApiError> {
    validate_attachments(data_dir, conv_id, attachments)?;
    Ok(())
}
