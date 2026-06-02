# seven-chat-agent-server + web 静态资源
# 构建: docker build -f docker/server/Dockerfile -t server .

FROM node:20-bookworm AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-bin-links
COPY web/ ./
RUN npm run build

FROM rust:1.86-bookworm AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates
COPY migrations ./migrations
COPY --from=web /app/web/dist ./web/dist
RUN cargo build --release -p seven-chat-agent-server

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/target/release/seven-chat-agent-server /usr/local/bin/
COPY --from=web /app/web/dist ./web/dist
ENV HONEYCOMB_BIND=0.0.0.0:18737 \
    HONEYCOMB_HTTPS_BIND= \
    HONEYCOMB_TLS_CERT= \
    HONEYCOMB_TLS_KEY= \
    HONEYCOMB_DATA=/app/data \
    HONEYCOMB_DB=sqlite:///app/data/seven_chat_agent.db \
    SEVEN_CHAT_AGENT_STATIC_DIR=/app/web/dist
EXPOSE 18737
EXPOSE 18743
VOLUME ["/app/data"]
ENTRYPOINT ["seven-chat-agent-server"]
