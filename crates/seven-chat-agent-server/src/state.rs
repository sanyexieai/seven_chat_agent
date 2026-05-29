use std::path::PathBuf;
use std::sync::Arc;

use seven_chat_agent_core::SevenChatAgent;

#[derive(Clone)]
pub struct AppState {
    pub core: SevenChatAgent,
    /// 可选的运行时静态资源目录（如 `web/dist`），由 `build_app` 时注入。
    pub static_dir: Option<Arc<PathBuf>>,
}

impl AppState {
    pub fn new(core: SevenChatAgent) -> Self {
        Self {
            core,
            static_dir: None,
        }
    }

    pub fn with_static_dir(mut self, dir: Option<PathBuf>) -> Self {
        self.static_dir = dir.map(Arc::new);
        self
    }
}
