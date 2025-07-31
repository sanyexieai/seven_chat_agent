# 使用多阶段构建
FROM node:18-alpine AS frontend-builder

# 设置工作目录
WORKDIR /app/frontend

# 复制前端文件
COPY agent-ui/package*.json ./

# 安装前端依赖
RUN npm ci --only=production

# 复制前端源代码
COPY agent-ui/ ./

# 构建前端
RUN npm run build

# Python后端阶段
FROM python:3.11-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装uv
RUN pip install uv

# 设置工作目录
WORKDIR /app

# 复制Python项目文件
COPY pyproject.toml ./
COPY agent-backend/ ./agent-backend/

# 使用uv安装Python依赖
RUN uv sync --frozen

# 复制前端构建产物
COPY --from=frontend-builder /app/frontend/build ./agent-ui/build

# 创建必要的目录
RUN mkdir -p logs data uploads

# 暴露端口
EXPOSE 8000 3000

# 创建启动脚本
RUN echo '#!/bin/bash\n\
echo "🚀 启动 AI Agent System..."\n\
\n\
# 启动后端\n\
echo "🐍 启动后端服务..."\n\
cd /app/agent-backend\n\
uv run uvicorn main:app --host 0.0.0.0 --port 8000 &\n\
BACKEND_PID=$!\n\
\n\
# 等待后端启动\n\
sleep 5\n\
\n\
# 启动前端服务器\n\
echo "⚛️ 启动前端服务..."\n\
cd /app/agent-ui\n\
npx serve -s build -l 3000 &\n\
FRONTEND_PID=$!\n\
\n\
echo "🎉 服务启动完成!"\n\
echo "📱 前端地址: http://localhost:3000"\n\
echo "🔧 后端地址: http://localhost:8000"\n\
\n\
# 等待进程\n\
wait\n\
' > /app/start.sh && chmod +x /app/start.sh

# 设置启动命令
CMD ["/app/start.sh"] 