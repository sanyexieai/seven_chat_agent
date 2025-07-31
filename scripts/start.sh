#!/bin/bash

# AI Agent System 启动脚本

echo "🚀 启动 AI Agent System..."

# 检查Python版本
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ 错误: 需要 Python $required_version 或更高版本，当前版本: $python_version"
    exit 1
fi

echo "✅ Python 版本检查通过: $python_version"

# 检查Node.js版本
if ! command -v node &> /dev/null; then
    echo "❌ 错误: 未找到 Node.js，请先安装 Node.js"
    exit 1
fi

node_version=$(node --version | grep -oP '\d+\.\d+' | head -1)
required_node_version="18.0"

if [ "$(printf '%s\n' "$required_node_version" "$node_version" | sort -V | head -n1)" != "$required_node_version" ]; then
    echo "❌ 错误: 需要 Node.js $required_node_version 或更高版本，当前版本: $node_version"
    exit 1
fi

echo "✅ Node.js 版本检查通过: $node_version"

# 检查uv是否安装
if ! command -v uv &> /dev/null; then
    echo "📦 安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source ~/.bashrc
fi

echo "✅ uv 已安装"

# 检查端口占用
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null ; then
        echo "⚠️  警告: 端口 $port 已被占用"
        return 1
    fi
    return 0
}

echo "🔍 检查端口占用..."
if ! check_port 8000; then
    echo "请停止占用端口 8000 的服务"
    exit 1
fi

if ! check_port 3000; then
    echo "请停止占用端口 3000 的服务"
    exit 1
fi

echo "✅ 端口检查通过"

# 创建必要的目录
echo "📁 创建必要的目录..."
mkdir -p logs
mkdir -p data
mkdir -p uploads

# 启动后端服务
echo "🐍 启动后端服务..."
cd agent-backend

# 使用uv安装依赖
echo "📦 安装Python依赖..."
uv sync

# 启动后端
echo "🚀 启动FastAPI后端..."
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

cd ..

# 等待后端启动
echo "⏳ 等待后端服务启动..."
sleep 5

# 检查后端是否启动成功
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ 后端服务启动成功"
else
    echo "❌ 后端服务启动失败"
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

# 启动前端服务
echo "⚛️  启动前端服务..."
cd agent-ui

# 安装依赖
echo "📦 安装Node.js依赖..."
npm install

# 启动前端
echo "🚀 启动React前端..."
npm start &
FRONTEND_PID=$!

cd ..

# 等待前端启动
echo "⏳ 等待前端服务启动..."
sleep 10

# 检查前端是否启动成功
if curl -s http://localhost:3000 > /dev/null; then
    echo "✅ 前端服务启动成功"
else
    echo "❌ 前端服务启动失败"
    kill $FRONTEND_PID 2>/dev/null
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

echo ""
echo "🎉 AI Agent System 启动成功!"
echo ""
echo "📱 前端地址: http://localhost:3000"
echo "🔧 后端地址: http://localhost:8000"
echo "📚 API文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止服务"

# 等待用户中断
trap 'echo ""; echo "🛑 正在停止服务..."; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo "✅ 服务已停止"; exit 0' INT

wait 