# seven-chat-agent-desktop

Tauri 2 桌面壳。本地嵌入 `seven-chat-agent-core` 和 `seven-chat-agent-server`，编译时通过
`seven-chat-agent-server` 的 `embed-frontend` feature 把 `web/dist/` 一并烧进二进制；
进程启动后在 `127.0.0.1:18739` 监听，setup hook 会**同步等 server bind 成功**
再让 Webview 加载，避免初次 404。

## 准备

- Rust 1.80+
- Node 20+
- Tauri 系统依赖：
  - Linux: `webkit2gtk-4.1`, `libsoup-3.0`, `librsvg2-dev`, `libdbus-1-dev`
  - macOS: 内置
  - Windows: WebView2（Win11 自带，Win10 需要单独安装）
- `cargo install tauri-cli --version "^2"`

## 开发

```bash
# 先构建前端到 web/dist —— embed-frontend feature 编译时会从这里读
cd ../../web && npm install --no-bin-links && npm run build && cd -

# 启动 Tauri 开发模式（会按 tauri.conf.json 的 beforeDevCommand 起 vite）
cargo tauri dev
```

## 打包

```bash
cargo tauri build
```

会在 `target/release/bundle/` 下生成：

- `msi/` Windows MSI
- `nsis/` Windows NSIS exe
- `dmg/` macOS dmg
- `appimage/` Linux AppImage
- `deb/` Linux deb

具体 target 列表写在 `src-tauri/tauri.conf.json` 的 `bundle.targets` 字段里。
