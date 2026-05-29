//! 给桌面壳/独立 server 提供前端静态资源。
//!
//! - 启用 `embed-frontend` feature 时，会在编译期把 `web/dist/` 用
//!   `include_dir!()` 烧进二进制（适合 Tauri 桌面包）。
//! - 默认情况下，运行时通过 `SEVEN_CHAT_AGENT_STATIC_DIR` 环境变量或
//!   `with_static_dir()` 指定目录来托管，纯 server 模式可在 vite
//!   `npm run build` 之后直接服务 `web/dist`。
//! - 两种来源都没命中时返回 404，留给上层 `/api`、`/ws` 路由继续工作。

use std::path::{Path, PathBuf};

use axum::extract::State;
use axum::http::{header, HeaderValue, StatusCode, Uri};
use axum::response::{IntoResponse, Response};
use axum::Router;

use crate::state::AppState;

const SPA_INDEX: &str = "index.html";

#[cfg(feature = "embed-frontend")]
static EMBEDDED: include_dir::Dir<'static> =
    include_dir::include_dir!("$CARGO_MANIFEST_DIR/../../web/dist");

/// 在已经配置好 `/api` 与 `/ws` 的 Router 上挂载静态资源 fallback。
pub fn mount(router: Router<AppState>) -> Router<AppState> {
    router.fallback(serve_static)
}

async fn serve_static(State(state): State<AppState>, uri: Uri) -> Response {
    let raw = uri.path();
    tracing::trace!(path = raw, "static fallback hit");
    let trimmed = raw.trim_start_matches('/');

    let runtime_dir = state.static_dir.as_deref().map(|p| p.as_path());
    if let Some(resp) = try_runtime_dir(runtime_dir, trimmed) {
        return resp;
    }

    #[cfg(feature = "embed-frontend")]
    {
        if let Some(resp) = try_embedded(trimmed) {
            return resp;
        }
    }

    #[cfg(not(feature = "embed-frontend"))]
    {
        let _ = trimmed;
    }

    not_found()
}

fn try_runtime_dir(dir: Option<&Path>, rel: &str) -> Option<Response> {
    let dir = dir?;
    if !dir.is_dir() {
        return None;
    }
    if rel.split('/').any(|seg| seg == ".." || seg.contains('\\')) {
        return None;
    }
    let candidate = if rel.is_empty() {
        dir.join(SPA_INDEX)
    } else {
        dir.join(rel)
    };
    let final_path = if candidate.is_file() {
        candidate
    } else {
        dir.join(SPA_INDEX)
    };
    if !final_path.is_file() {
        return None;
    }
    Some(file_response(&final_path))
}

fn file_response(path: &Path) -> Response {
    let bytes = match std::fs::read(path) {
        Ok(b) => b,
        Err(_) => return not_found(),
    };
    let mime = guess_mime_ext(path.extension().and_then(|s| s.to_str()).unwrap_or(""));
    build_response(mime, bytes)
}

#[cfg(feature = "embed-frontend")]
fn try_embedded(rel: &str) -> Option<Response> {
    if rel.is_empty() {
        return EMBEDDED.get_file(SPA_INDEX).map(|f| {
            build_response(
                guess_mime_ext("html"),
                f.contents().to_vec(),
            )
        });
    }
    if rel.split('/').any(|seg| seg == ".." || seg.contains('\\')) {
        return None;
    }
    if let Some(file) = EMBEDDED.get_file(rel) {
        let ext = Path::new(rel)
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("");
        return Some(build_response(guess_mime_ext(ext), file.contents().to_vec()));
    }
    EMBEDDED.get_file(SPA_INDEX).map(|f| {
        build_response(guess_mime_ext("html"), f.contents().to_vec())
    })
}

fn guess_mime_ext(ext: &str) -> &'static str {
    match ext.to_ascii_lowercase().as_str() {
        "html" => "text/html; charset=utf-8",
        "js" | "mjs" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" => "application/json",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "ico" => "image/x-icon",
        "wasm" => "application/wasm",
        "map" => "application/json",
        "txt" => "text/plain; charset=utf-8",
        "woff" => "font/woff",
        "woff2" => "font/woff2",
        _ => "application/octet-stream",
    }
}

fn build_response(mime: &'static str, bytes: Vec<u8>) -> Response {
    let mut resp = (StatusCode::OK, bytes).into_response();
    resp.headers_mut()
        .insert(header::CONTENT_TYPE, HeaderValue::from_static(mime));
    resp.headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache"));
    resp
}

fn not_found() -> Response {
    (StatusCode::NOT_FOUND, "not found").into_response()
}

/// 解析 `SEVEN_CHAT_AGENT_STATIC_DIR` 环境变量。
pub fn static_dir_from_env() -> Option<PathBuf> {
    std::env::var_os("SEVEN_CHAT_AGENT_STATIC_DIR")
        .map(PathBuf::from)
        .filter(|p| !p.as_os_str().is_empty())
}
