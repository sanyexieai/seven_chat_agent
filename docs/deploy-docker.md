# Docker 构建与自动部署（3ye.co:9443）

公开示例站点（v2 Web）：[https://3ye.co:18743/](https://3ye.co:18743/)

打 Git 标签后，GitHub Actions 会：

1. 构建 `seven-chat-agent-server` / `seven-chat-agent-cli-relay` 镜像  
2. 推送到私有仓库 `https://3ye.co:9443/seven-chat-agent/<镜像名>:<版本>`  
3. 构建多平台 `seven-chat-agent-cli-relay` 二进制并上传到 GitHub Release Assets  
4. SSH 连接服务器，执行 `deploy/remote-up.sh` 拉取并重启容器  

## 标签约定

| 标签 | 构建 | 部署 |
|------|------|------|
| `v2.0.0` | server + cli-relay | 全部（`all`） |
| `cli-relay/2.0.0` | 仅 cli-relay | 仅 cli-relay |
| `v2.0.0-server` | 仅 server | 仅 server |

`cli-relay` 二进制会随 `v*` 和 `cli-relay/*` 标签一并发布到对应 GitHub Release。

## cli-relay 二进制资产

每次标签发布会上传以下目标平台的压缩包与校验文件（`*.sha256`）：

- `linux-amd64`
- `linux-arm64`
- `windows-amd64`
- `macos-amd64`
- `macos-arm64`

示例：

```bash
git tag v2.0.0
git push origin v2.0.0

# 只发 relay
git tag cli-relay/2.0.1
git push origin cli-relay/2.0.1
```

## GitHub Secrets

在仓库 **Settings → Secrets and variables → Actions** 配置：

| Secret | 说明 |
|--------|------|
| `REGISTRY_USERNAME` | `3ye.co:9443` 仓库用户名 |
| `REGISTRY_PASSWORD` | 仓库密码或 token |
| `SSH_HOST` | 部署服务器地址 |
| `SSH_USER` | SSH 用户 |
| `SSH_PRIVATE_KEY` | SSH 私钥（PEM） |
| `SSH_PORT` | 可选，默认 22 |
| `DEPLOY_PATH` | 可选，服务器上 compose 目录，默认 `/opt/seven-chat-agent/deploy` |

## 服务器首次准备

```bash
sudo mkdir -p /opt/seven-chat-agent/deploy
sudo chown "$USER:$USER" /opt/seven-chat-agent/deploy

# 若仓库为自签名 HTTPS，需在 /etc/docker/daemon.json 配置 insecure-registries 或安装 CA
# 示例（仅当证书不受信时）:
# { "insecure-registries": ["3ye.co:9443"] }

cd /opt/seven-chat-agent/deploy
cp .env.example .env
# 编辑 .env：API Key、助理默认模型、HTTPS（可选）、RELAY_PAIRING_TOKEN 等
# compose 通过 env_file 注入 .env，并叠加 docker-compose.yml 中的容器路径默认值
```

### 仅部署服务端

```bash
cd /opt/seven-chat-agent/deploy
export IMAGE_TAG=v2.0.0
export REGISTRY=3ye.co:9443
bash remote-up.sh server
```

浏览器访问 `http://<服务器IP>:18737`（或反向代理后的域名）。示例部署对外为 [https://3ye.co:18743/](https://3ye.co:18743/)。

### 部署 CLI 转发（可选 profile）

转发容器需能访问服务端 WebSocket，且 **配对码** 在 Web「生成配对码」后写入 `deploy/.env`：

```env
RELAY_PAIRING_TOKEN=pair_xxxxxxxx
RELAY_URL=ws://server:18737/cli-relay
```

```bash
bash remote-up.sh cli-relay
```

> **说明**：`codex` / `agent` 等 CLI 通常安装在开发者本机；容器内 relay 仅适合服务端同机联调。生产环境更推荐在远程电脑直接运行 `seven-chat-agent-cli-relay` 二进制。

## 本地一键构建并推送

`scripts/push-registry.sh` 会：

1. 读取 `deploy/.image-version`，默认 **patch +1**（也可命令行传入 `2.0.3` 或 `v2.0.3`）
2. 构建 `server` / `cli-relay` 镜像（默认两者都推，可用 `--server-only`）
3. 打标签 `:版本` 与 `:latest`，依次 `docker push`
4. 推送成功后写回 `deploy/.image-version`

在 `deploy/.env` 配置仓库账号（与 compose 共用）：

```env
REGISTRY=3ye.co:9443
REGISTRY_USERNAME=你的用户名
REGISTRY_PASSWORD=你的密码或token
```

```bash
# 自动 2.0.0 -> 2.0.1 并推送 server + cli-relay + latest
bash scripts/push-registry.sh

# 指定版本（不递增文件里的数字，但成功后会写入 2.1.0）
bash scripts/push-registry.sh 2.1.0

# 只推 server
bash scripts/push-registry.sh --server-only

# 预览命令
bash scripts/push-registry.sh --dry-run
```

部署到服务器：

```bash
cd deploy
IMAGE_TAG=2.0.1 bash remote-up.sh server
```

## 本地手动构建

```bash
# CLI 转发
docker build -f docker/cli-relay/Dockerfile -t 3ye.co:9443/seven-chat-agent/cli-relay:dev .
docker push 3ye.co:9443/seven-chat-agent/cli-relay:dev

# 服务端 + 前端
docker build -f docker/server/Dockerfile -t 3ye.co:9443/seven-chat-agent/server:dev .
docker push 3ye.co:9443/seven-chat-agent/server:dev
```

## 工作流文件

`.github/workflows/cli-release.yml`
