# AI Agent System

一个开源的端到端智能体系统，支持多种智能体设计模式和工具集成。

## 项目特点

- **多智能体架构**: 支持多种智能体设计模式（React模式、Plan and Execute模式等）
- **可插拔工具**: 支持自定义工具和子智能体的集成
- **流式输出**: 全链路流式响应
- **高并发**: 支持高并发DAG执行引擎
- **开箱即用**: 完整的端到端产品，支持二次开发

## 系统架构

```
agent-system/
├── agent-backend/     # Python FastAPI 后端服务
├── agent-ui/          # React 前端界面
├── agent-tools/       # Python 工具集合
├── docs/              # 项目文档
└── deploy/            # 部署配置
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Docker (可选)

### 启动方式

#### 方式1: Docker 一键启动

```bash
# 构建镜像
docker build -t agent-system:latest .

# 启动服务
docker run -d -p 3000:3000 -p 8000:8000 --name agent-app agent-system:latest
```

#### 方式2: 手动启动

```bash
# 启动后端
cd agent-backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 启动前端
cd agent-ui
npm install
npm start
```

## 主要功能

- **多智能体协作**: 支持多个智能体协同工作
- **工具集成**: 内置多种工具，支持自定义工具开发
- **流式对话**: 实时流式响应
- **文件处理**: 支持多种文件格式的处理
- **报告生成**: 自动生成分析报告

## 开发指南

### 添加自定义工具

在 `agent-tools/` 目录下创建新的工具模块，实现 `BaseTool` 接口。

### 添加自定义智能体

在 `agent-backend/agents/` 目录下创建新的智能体类。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License 