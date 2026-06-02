# seven-chat-agent-cli-relay — 远程 CLI 转发程序
# 构建: docker build -f docker/cli-relay/Dockerfile -t cli-relay .
# 注: 容器内执行 codex/claude/cursor 需在镜像或挂载中提供对应 CLI，或仅在已安装 CLI 的宿主机用二进制部署。

FROM rust:1.80-bookworm AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates
RUN cargo build --release -p seven-chat-agent-cli-relay

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/target/release/seven-chat-agent-cli-relay /usr/local/bin/seven-chat-agent-cli-relay
ENV SEVEN_CHAT_AGENT_RELAY_WORKSPACE_ROOT=/data/cli-workspaces
VOLUME ["/data"]
ENTRYPOINT ["seven-chat-agent-cli-relay"]
