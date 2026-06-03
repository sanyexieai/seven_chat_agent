pub mod auth;
pub mod cli_relay_ws;
pub mod public_urls;
pub mod routes;
pub mod state;
pub mod static_assets;
pub mod ws;
pub mod ws_api;

pub use state::AppState;

use std::path::PathBuf;

use axum::Router;
use seven_chat_agent_core::SevenChatAgent;
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;

/// Build the full HTTP+WS router from a booted SevenChatAgent core.
///
/// 自动从 `SEVEN_CHAT_AGENT_STATIC_DIR` 环境变量读取前端静态目录；如要在代码里硬指定，
/// 调用 [`build_app_with_static`]。
pub fn build_app(core: SevenChatAgent) -> Router {
    build_app_with_static(core, static_assets::static_dir_from_env())
}

/// 与 [`build_app`] 类似，但允许显式注入静态资源目录（如 Tauri 解析过的 resource 路径）。
pub fn build_app_with_static(core: SevenChatAgent, static_dir: Option<PathBuf>) -> Router {
    let state = AppState::new(core).with_static_dir(static_dir);
    let cors = CorsLayer::new()
        .allow_methods(Any)
        .allow_headers(Any)
        .allow_origin(Any);

    let router = Router::new()
        .nest("/api", routes::api_router())
        .route("/ws", axum::routing::get(ws::ws_handler))
        .route("/ws-api", axum::routing::get(ws_api::ws_api_handler))
        .route(
            "/cli-relay",
            axum::routing::get(cli_relay_ws::cli_relay_handler),
        );
    let router = static_assets::mount(router)
        .with_state(state)
        .layer(cors)
        .layer(TraceLayer::new_for_http());
    router
}
