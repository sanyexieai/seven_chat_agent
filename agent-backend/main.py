from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
import uvicorn
import asyncio
import json
import uuid
from typing import Dict, List, Any
import logging

# 导入路由
from api.agents import router as agents_router
from api.sessions import router as sessions_router
from api.chat import router as chat_router
from api.mcp import router as mcp_router
from api.flows import router as flows_router
from api.llm_config import router as llm_config_router
from api.knowledge_base import router as knowledge_base_router

# 导入数据库和智能体管理器
from database.database import engine, Base, get_db, SessionLocal
from database.migrations import run_migrations, create_default_agents
from agents.agent_manager import AgentManager
from utils.log_helper import get_logger

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = get_logger("main")

# 运行数据库迁移
logger.info("开始数据库迁移...")
from database.database import init_db
init_db()
logger.info("数据库迁移完成")

# 全局变量
agent_manager = None
active_connections: Dict[str, WebSocket] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global agent_manager
    
    # 启动时初始化
    logger.info("应用启动中...")
    agent_manager = AgentManager()
    await agent_manager.initialize()
    logger.info("应用启动完成")
    
    yield
    
    # 关闭时清理
    logger.info("应用关闭中...")
    if agent_manager:
        await agent_manager.cleanup()
    logger.info("应用关闭完成")

# 创建FastAPI应用
app = FastAPI(
    title="Seven Chat Agent API",
    description="多智能体聊天系统API",
    version="1.0.0",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 自动检测并挂载静态文件
import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
is_production = os.path.exists(static_dir) and os.path.isdir(static_dir)

# 注册路由（根据环境自动调整前缀）
api_prefix = "/api" if is_production else ""
app.include_router(agents_router, prefix=api_prefix)
app.include_router(sessions_router, prefix=api_prefix)
app.include_router(chat_router, prefix=api_prefix)
app.include_router(mcp_router, prefix=api_prefix)
app.include_router(flows_router, prefix=api_prefix)
app.include_router(llm_config_router, prefix=api_prefix)
app.include_router(knowledge_base_router, prefix=api_prefix)

# 静态文件挂载必须在路由注册之后
if is_production:
    logger.info(f"检测到静态文件目录: {static_dir}")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    logger.info("静态文件已挂载到根路径 /")

# 动态注册根路径和健康检查
@app.get(f"{api_prefix}/" if api_prefix else "/")
async def root():
    """根路径"""
    return {
        "message": "Seven Chat Agent API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get(f"{api_prefix}/health" if api_prefix else "/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "agent_manager": "initialized" if agent_manager else "not_initialized"
    }

# WebSocket连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket连接已建立: {session_id}")

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket连接已断开: {session_id}")

    async def send_message(self, session_id: str, message: str):
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_text(message)
            except Exception as e:
                logger.error(f"发送消息失败: {str(e)}")
                self.disconnect(session_id)

manager = ConnectionManager()

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket端点"""
    await manager.connect(websocket, session_id)
    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # 处理消息
            user_id = message_data.get("user_id", "anonymous")
            message = message_data.get("message", "")
            agent_name = message_data.get("agent_name", "general_agent")
            
            logger.info(f"收到WebSocket消息: session_id={session_id}, user_id={user_id}, agent={agent_name}")
            
            # 获取智能体
            if not agent_manager:
                await websocket.send_text(json.dumps({
                    "error": "智能体管理器未初始化"
                }))
                continue
            
            agent = agent_manager.get_agent(agent_name)
            if not agent:
                await websocket.send_text(json.dumps({
                    "error": f"智能体 {agent_name} 不存在"
                }))
                continue
            
            # 处理消息
            try:
                context = {
                    "session_id": session_id,
                    "user_id": user_id,
                    "websocket": websocket
                }
                
                # 流式处理
                async for chunk in agent.process_message_stream(user_id, message, context):
                    chunk_data = {
                        "chunk_id": chunk.chunk_id,
                        "type": chunk.type,
                        "content": chunk.content,
                        "agent_name": chunk.agent_name,
                        "metadata": chunk.metadata,
                        "is_end": chunk.is_end
                    }
                    await websocket.send_text(json.dumps(chunk_data))
                    
                    if chunk.is_end:
                        break
                        
            except Exception as e:
                logger.error(f"处理消息失败: {str(e)}")
                await websocket.send_text(json.dumps({
                    "error": f"处理消息失败: {str(e)}"
                }))
                
    except WebSocketDisconnect:
        manager.disconnect(session_id)
        logger.info(f"WebSocket连接断开: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket错误: {str(e)}")
        manager.disconnect(session_id)

@app.post("/api/chat")
async def chat(request: Dict[str, Any]):
    """普通聊天API"""
    try:
        user_id = request.get("user_id", "anonymous")
        message = request.get("message", "")
        agent_id = request.get("agent_id")
        agent_name = request.get("agent_name", "general_agent")
        session_id = request.get("session_id", str(uuid.uuid4()))
        
        logger.info(f"收到聊天请求: user_id={user_id}, agent_id={agent_id}, agent_name={agent_name}")
        
        if not agent_manager:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="智能体管理器未初始化"
            )
        
        # 如果提供了agent_id，优先使用agent_id查找智能体
        if agent_id:
            # 从数据库获取智能体信息
            db = SessionLocal()
            try:
                from models.database_models import Agent
                db_agent = db.query(Agent).filter(Agent.id == agent_id).first()
                if db_agent:
                    agent_name = db_agent.name
                else:
                    raise HTTPException(
                        status_code=status.HTP_404_NOT_FOUND,
                        detail=f"智能体ID {agent_id} 不存在"
                    )
            finally:
                db.close()
        
        agent = agent_manager.get_agent(agent_name)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"智能体 {agent_name} 不存在"
            )
        
        context = {
            "session_id": session_id,
            "user_id": user_id
        }
        
        # 处理消息
        response = await agent.process_message(user_id, message, context)
        
        return {
            "content": response.content,
            "agent_name": response.agent_name,
            "type": response.type,
            "metadata": response.metadata,
            "session_id": session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"聊天API错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"聊天API错误: {str(e)}"
        )

@app.post("/api/chat/stream")
async def chat_stream(request: Dict[str, Any]):
    """流式聊天API"""
    try:
        user_id = request.get("user_id", "anonymous")
        message = request.get("message", "")
        agent_id = request.get("agent_id")
        agent_name = request.get("agent_name", "general_agent")
        session_id = request.get("session_id", str(uuid.uuid4()))
        
        logger.info(f"收到聊天请求: user_id={user_id}, agent_id={agent_id}, agent_name={agent_name}")
        
        if not agent_manager:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="智能体管理器未初始化"
            )
        
        # 如果提供了agent_id，优先使用agent_id查找智能体
        if agent_id:
            # 从数据库获取智能体信息
            db = SessionLocal()
            try:
                from models.database_models import Agent
                db_agent = db.query(Agent).filter(Agent.id == agent_id).first()
                if db_agent:
                    agent_name = db_agent.name
                else:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"智能体ID {agent_id} 不存在"
                    )
            finally:
                db.close()
        
        agent = agent_manager.get_agent(agent_name)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"智能体 {agent_name} 不存在"
            )
        
        context = {
            "session_id": session_id,
            "user_id": user_id
        }
        
        # 返回流式响应
        async def generate_response():
            try:
                async for chunk in agent.process_message_stream(user_id, message, context):
                    yield f"data: {json.dumps({
                        'chunk_id': chunk.chunk_id,
                        'type': chunk.type,
                        'content': chunk.content,
                        'agent_name': chunk.agent_name,
                        'metadata': chunk.metadata,
                        'is_end': chunk.is_end
                    })}\n\n"
                    
                    if chunk.is_end:
                        break
            except Exception as e:
                logger.error(f"生成响应失败: {str(e)}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return StreamingResponse(content=generate_response(), media_type="text/event-stream")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"聊天API错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"聊天API错误: {str(e)}"
        )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    ) 