use std::io;
use std::time::Duration;

use anyhow::Result;
use crossterm::event::{self, Event, KeyCode, KeyEvent, KeyModifiers};
use crossterm::execute;
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use futures::{SinkExt, StreamExt};
use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem, ListState, Paragraph, Wrap};
use ratatui::{Frame, Terminal};
use tokio::sync::mpsc;
use tokio_tungstenite::tungstenite::Message as WsMsg;

use crate::api::{ApiClient, Friend, Message};

enum InputMode {
    Normal,
    Editing,
    Debug,
    Providers,
}

pub struct App {
    api: ApiClient,
    friends: Vec<Friend>,
    selected: usize,
    list_state: ListState,
    messages: Vec<Message>,
    conv_id: Option<String>,
    draft: String,
    mode: InputMode,
    status: String,
    judgments: Vec<String>,
    bus_rx: mpsc::Receiver<BusEvent>,
    providers: Vec<crate::api::Provider>,
    provider_keys: Vec<crate::api::ProviderKey>,
}

#[derive(Debug, Clone)]
enum BusEvent {
    MessageCreated(Message),
    MessageDelta {
        message_id: String,
        conversation_id: String,
        delta: String,
    },
    MessageDone(Message),
    Judgment(String),
}

pub async fn run(server: &str) -> Result<()> {
    let api = ApiClient::new(server);
    let friends = api.list_friends().await?;
    if friends.is_empty() {
        eprintln!("还没有好友。先在 web 端创建。");
        return Ok(());
    }

    let (tx, rx) = mpsc::channel(256);
    let ws_url = ws_url_for(server);
    tokio::spawn(ws_loop(ws_url, tx));

    let mut list_state = ListState::default();
    list_state.select(Some(0));
    let mut app = App {
        api: api.clone(),
        friends,
        selected: 0,
        list_state,
        messages: vec![],
        conv_id: None,
        draft: String::new(),
        mode: InputMode::Normal,
        status: "Enter 聊天 / i 编辑 / d 调试 / p Provider / q 退出".into(),
        judgments: vec![],
        bus_rx: rx,
        providers: vec![],
        provider_keys: vec![],
    };
    app.load_selected().await?;

    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = ratatui::backend::CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let res = main_loop(&mut terminal, &mut app).await;

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;
    res
}

async fn main_loop<B: ratatui::backend::Backend>(
    terminal: &mut Terminal<B>,
    app: &mut App,
) -> Result<()> {
    loop {
        while let Ok(ev) = app.bus_rx.try_recv() {
            app.apply_bus(ev);
        }
        terminal.draw(|f| draw(f, app))?;
        if event::poll(Duration::from_millis(80))? {
            if let Event::Key(key) = event::read()? {
                match app.mode {
                    InputMode::Normal => {
                        if handle_normal(app, key).await? {
                            break;
                        }
                    }
                    InputMode::Editing => handle_editing(app, key).await?,
                    InputMode::Debug => {
                        if matches!(
                            key.code,
                            KeyCode::Esc | KeyCode::Char('q') | KeyCode::Char('d')
                        ) {
                            app.mode = InputMode::Normal;
                        }
                    }
                    InputMode::Providers => {
                        if matches!(
                            key.code,
                            KeyCode::Esc | KeyCode::Char('q') | KeyCode::Char('p')
                        ) {
                            app.mode = InputMode::Normal;
                            app.status =
                                "Enter 聊天 / i 编辑 / d 调试 / p Provider / q 退出".into();
                        }
                    }
                }
            }
        }
    }
    Ok(())
}

async fn handle_normal(app: &mut App, key: KeyEvent) -> Result<bool> {
    match key.code {
        KeyCode::Char('q') => return Ok(true),
        KeyCode::Char('j') | KeyCode::Down => {
            app.selected = (app.selected + 1).min(app.friends.len().saturating_sub(1));
            app.list_state.select(Some(app.selected));
            app.load_selected().await?;
        }
        KeyCode::Char('k') | KeyCode::Up => {
            if app.selected > 0 {
                app.selected -= 1;
            }
            app.list_state.select(Some(app.selected));
            app.load_selected().await?;
        }
        KeyCode::Enter | KeyCode::Char('i') => {
            app.mode = InputMode::Editing;
            app.status = "输入消息，Enter 发送，Esc 返回".into();
        }
        KeyCode::Char('d') => {
            app.mode = InputMode::Debug;
            app.status = "调试面板 · Esc 返回".into();
        }
        KeyCode::Char('p') => {
            app.providers = app.api.list_providers().await.unwrap_or_default();
            app.provider_keys = app.api.list_provider_keys().await.unwrap_or_default();
            app.mode = InputMode::Providers;
            app.status = format!(
                "Provider 面板 · {} providers / {} keys · Esc 返回",
                app.providers.len(),
                app.provider_keys.len()
            );
        }
        KeyCode::Char('r') => {
            app.friends = app.api.list_friends().await.unwrap_or_default();
            app.status = "已刷新好友".into();
        }
        _ => {}
    }
    Ok(false)
}

async fn handle_editing(app: &mut App, key: KeyEvent) -> Result<()> {
    match key.code {
        KeyCode::Esc => {
            app.mode = InputMode::Normal;
            app.status = "Enter 进入聊天 / i 编辑 / d 调试面板 / q 退出".into();
        }
        KeyCode::Enter => {
            if !key.modifiers.contains(KeyModifiers::SHIFT) {
                let content = std::mem::take(&mut app.draft);
                let content = content.trim().to_string();
                if !content.is_empty() {
                    if let Some(f) = app.friends.get(app.selected) {
                        app.api.send_dm(&f.id, &content).await.ok();
                    }
                }
            } else {
                app.draft.push('\n');
            }
        }
        KeyCode::Backspace => {
            app.draft.pop();
        }
        KeyCode::Char(c) => app.draft.push(c),
        _ => {}
    }
    Ok(())
}

fn draw(f: &mut Frame, app: &App) {
    let area = f.area();
    let outer = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(1)])
        .split(area);

    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Length(28), Constraint::Min(0)])
        .split(outer[0]);

    draw_friends(f, cols[0], app);

    let right = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(4)])
        .split(cols[1]);

    match app.mode {
        InputMode::Debug => draw_debug(f, right[0], app),
        InputMode::Providers => draw_providers(f, right[0], app),
        _ => draw_messages(f, right[0], app),
    }
    draw_input(f, right[1], app);
    draw_status(f, outer[1], app);
}

fn draw_providers(f: &mut Frame, area: Rect, app: &App) {
    let mut lines: Vec<Line> = Vec::new();
    if app.providers.is_empty() {
        lines.push(Line::from(Span::styled(
            "（没有 provider，可能 server 没启或还没 seed）",
            Style::default().fg(Color::DarkGray),
        )));
    }
    for p in &app.providers {
        lines.push(Line::from(vec![
            Span::styled(
                p.display_name.clone(),
                Style::default().add_modifier(Modifier::BOLD).fg(Color::Yellow),
            ),
            Span::raw(format!("  [{}]  {}", p.kind, p.base_url)),
        ]));
        if let Some(m) = &p.default_model {
            lines.push(Line::from(Span::styled(
                format!("    默认 model: {m}"),
                Style::default().fg(Color::DarkGray),
            )));
        }
        let keys: Vec<&crate::api::ProviderKey> = app
            .provider_keys
            .iter()
            .filter(|k| k.provider_id == p.id)
            .collect();
        if keys.is_empty() {
            lines.push(Line::from(Span::styled(
                "    keys: (none)",
                Style::default().fg(Color::Red),
            )));
        } else {
            for k in keys {
                lines.push(Line::from(format!(
                    "    · {} [{}]  已用 ${:.4}",
                    k.label, k.status, k.current_spent_usd
                )));
            }
        }
        lines.push(Line::from(""));
    }
    let p = Paragraph::new(lines)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title("Providers · p 切换 / Esc 返回"),
        )
        .wrap(Wrap { trim: false });
    f.render_widget(p, area);
}

fn draw_friends(f: &mut Frame, area: Rect, app: &App) {
    let items: Vec<ListItem> = app
        .friends
        .iter()
        .map(|fr| {
            let badge = match fr.backend_kind.as_str() {
                "assistant" => "[H]",
                "human" => "[人]",
                "pty" => "[CLI]",
                _ => "[API]",
            };
            ListItem::new(format!("{badge} {}", fr.name))
        })
        .collect();
    let list = List::new(items)
        .block(Block::default().borders(Borders::ALL).title("好友"))
        .highlight_style(Style::default().add_modifier(Modifier::BOLD).bg(Color::Yellow).fg(Color::Black))
        .highlight_symbol("▶ ");
    f.render_stateful_widget(list, area, &mut app.list_state.clone());
}

fn draw_messages(f: &mut Frame, area: Rect, app: &App) {
    let lines: Vec<Line> = app
        .messages
        .iter()
        .flat_map(|m| {
            let header_style = match m.sender_kind.as_str() {
                "user" => Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
                _ => Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD),
            };
            let mut out = vec![Line::from(vec![
                Span::styled(format!("{}", m.sender_name), header_style),
                Span::raw(format!("  ({})", m.status)),
            ])];
            for line in m.content.lines() {
                out.push(Line::from(format!("  {}", line)));
            }
            out.push(Line::from(""));
            out
        })
        .collect();
    let title = if let Some(fr) = app.friends.get(app.selected) {
        format!("聊天 · {}", fr.name)
    } else {
        "聊天".into()
    };
    let p = Paragraph::new(lines)
        .block(Block::default().borders(Borders::ALL).title(title))
        .wrap(Wrap { trim: false });
    f.render_widget(p, area);
}

fn draw_debug(f: &mut Frame, area: Rect, app: &App) {
    let lines: Vec<Line> = app
        .judgments
        .iter()
        .map(|s| Line::from(s.clone()))
        .collect();
    let p = Paragraph::new(lines)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title("调试 · judgments / scheduler"),
        )
        .wrap(Wrap { trim: false });
    f.render_widget(p, area);
}

fn draw_input(f: &mut Frame, area: Rect, app: &App) {
    let mode = match app.mode {
        InputMode::Normal => "NORMAL",
        InputMode::Editing => "INSERT",
        InputMode::Debug => "DEBUG",
        InputMode::Providers => "PROVIDER",
    };
    let p = Paragraph::new(app.draft.as_str())
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(format!("输入 [{mode}]")),
        )
        .wrap(Wrap { trim: false });
    f.render_widget(p, area);
}

fn draw_status(f: &mut Frame, area: Rect, app: &App) {
    let span = Paragraph::new(app.status.as_str()).style(Style::default().fg(Color::DarkGray));
    f.render_widget(span, area);
}

impl App {
    async fn load_selected(&mut self) -> Result<()> {
        if let Some(f) = self.friends.get(self.selected) {
            let (conv, msgs) = self.api.open_dm(&f.id).await?;
            self.conv_id = Some(conv.id);
            self.messages = msgs;
        }
        Ok(())
    }

    fn apply_bus(&mut self, ev: BusEvent) {
        match ev {
            BusEvent::MessageCreated(m) => {
                if self.conv_id.as_deref() == Some(&m.conversation_id) {
                    self.messages.push(m);
                }
            }
            BusEvent::MessageDelta {
                message_id,
                conversation_id,
                delta,
            } => {
                if self.conv_id.as_deref() == Some(&conversation_id) {
                    if let Some(m) = self.messages.iter_mut().find(|m| m.id == message_id) {
                        m.content.push_str(&delta);
                    }
                }
            }
            BusEvent::MessageDone(m) => {
                if self.conv_id.as_deref() == Some(&m.conversation_id) {
                    if let Some(slot) = self.messages.iter_mut().find(|x| x.id == m.id) {
                        *slot = m;
                    }
                }
            }
            BusEvent::Judgment(s) => {
                self.judgments.push(s);
                if self.judgments.len() > 200 {
                    let _ = self.judgments.drain(0..self.judgments.len() - 200).collect::<Vec<_>>();
                }
            }
        }
    }
}

fn ws_url_for(server: &str) -> String {
    let s = server.trim_end_matches('/');
    if let Some(rest) = s.strip_prefix("https://") {
        format!("wss://{rest}/ws")
    } else if let Some(rest) = s.strip_prefix("http://") {
        format!("ws://{rest}/ws")
    } else {
        format!("ws://{s}/ws")
    }
}

async fn ws_loop(ws_url: String, tx: mpsc::Sender<BusEvent>) {
    loop {
        match tokio_tungstenite::connect_async(&ws_url).await {
            Ok((ws, _)) => {
                let (mut sink, mut stream) = ws.split();
                let _ = sink.send(WsMsg::Text("hello".into())).await;
                while let Some(Ok(msg)) = stream.next().await {
                    if let WsMsg::Text(t) = msg {
                        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&t) {
                            match v.get("type").and_then(|s| s.as_str()) {
                                Some("message_created") => {
                                    if let Some(m) = v
                                        .get("message")
                                        .and_then(|m| serde_json::from_value::<Message>(m.clone()).ok())
                                    {
                                        let _ = tx.send(BusEvent::MessageCreated(m)).await;
                                    }
                                }
                                Some("message_delta") => {
                                    let _ = tx
                                        .send(BusEvent::MessageDelta {
                                            message_id: v["message_id"].as_str().unwrap_or("").to_string(),
                                            conversation_id: v["conversation_id"].as_str().unwrap_or("").to_string(),
                                            delta: v["delta"].as_str().unwrap_or("").to_string(),
                                        })
                                        .await;
                                }
                                Some("message_done") => {
                                    if let Some(m) = v
                                        .get("message")
                                        .and_then(|m| serde_json::from_value::<Message>(m.clone()).ok())
                                    {
                                        let _ = tx.send(BusEvent::MessageDone(m)).await;
                                    }
                                }
                                Some("judgment_decided") => {
                                    let name = v["friend_name"].as_str().unwrap_or("");
                                    let conf = v["confidence"].as_f64().unwrap_or(0.0);
                                    let reply = v["should_reply"].as_bool().unwrap_or(false);
                                    let reason = v["reason"].as_str().unwrap_or("");
                                    let src = v["judge_source"].as_str().unwrap_or("?");
                                    let cfg = v["configured_judge_mode"].as_str().unwrap_or("?");
                                    let _ = tx
                                        .send(BusEvent::Judgment(format!(
                                            "[judge] cfg={cfg} src={src} {name} reply={reply} conf={conf:.2} {reason}"
                                        )))
                                        .await;
                                }
                                Some("scheduler_picked") => {
                                    let picks = v["decisions"]
                                        .as_array()
                                        .map(|arr| {
                                            arr.iter()
                                                .map(|d| d["friend_name"].as_str().unwrap_or("?").to_string())
                                                .collect::<Vec<_>>()
                                                .join(", ")
                                        })
                                        .unwrap_or_default();
                                    let mode = v["schedule_mode"].as_str().unwrap_or("?");
                                    let cfg = v["configured_judge_mode"].as_str().unwrap_or("?");
                                    let willing = v["willing_to_reply"].as_u64().unwrap_or(0);
                                    let _ = tx
                                        .send(BusEvent::Judgment(format!(
                                            "[scheduler] cfg={cfg} mode={mode} willing={willing} picked: {picks}"
                                        )))
                                        .await;
                                }
                                _ => {}
                            }
                        }
                    }
                }
            }
            Err(e) => {
                tracing::warn!(err=%e, "ws connect failed, retrying in 3s");
            }
        }
        tokio::time::sleep(Duration::from_secs(3)).await;
    }
}
