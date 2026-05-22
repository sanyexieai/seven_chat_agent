use std::path::PathBuf;
use std::sync::Arc;

use honeycomb_core::Honeycomb;

#[derive(Clone)]
pub struct AppState {
    pub core: Honeycomb,
    /// 可选的运行时静态资源目录（如 `web/dist`），由 `build_app` 时注入。
    pub static_dir: Option<Arc<PathBuf>>,
}

impl AppState {
    pub fn new(core: Honeycomb) -> Self {
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
