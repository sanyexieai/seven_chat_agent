from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
import json
import asyncio
from typing import Dict, List
import uvicorn

from agents.agent_manager import AgentManager
from tools.tool_manager import ToolManager
from models.chat_models import ChatRequest, ChatResponse, AgentMessage
from utils.log_helper import get_logger
from database.database import init_db
from database.migrations import init_database
from api.agents import router as agents_router
from api.sessions import router as sessions_router
from api.mcp import router as mcp_router
from api.knowledge_base import router as knowledge_base_router
from api.llm_config import router as llm_config_router
from config.llm_config_manager import llm_config_manager

# 获取logger实例
logger = get_logger("main")

# 全局管理器
agent_manager = None
tool_manager = None

# 直接初始化
logger.info("AI Agent System starting up...")

# 初始化数据库（包括迁移）
init_database()
logger.info("Database initialized")

# 确保所有表都被创建
from models.database_models import Base
from database.database import engine
Base.metadata.create_all(bind=engine)
logger.info("All database tables created")

agent_manager = AgentManager()
tool_manager = ToolManager()

# 同步初始化
import asyncio
asyncio.run(agent_manager.initialize())
asyncio.run(tool_manager.initialize())

# 初始化LLM配置管理器
llm_config_manager.initialize()
logger.info("AI Agent System started successfully")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    yield

app = FastAPI(title="AI Agent System", version="1.0.0", lifespan=lifespan)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(agents_router)
app.include_router(sessions_router)
app.include_router(mcp_router)
app.include_router(knowledge_base_router)
app.include_router(llm_config_router)

@app.get("/")
async def root():
    """根路径"""
    return {"message": "AI Agent System API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """健康检查"""
    if agent_manager is None:
        return {"status": "initializing", "agents": 0}
    return {"status": "healthy", "agents": len(agent_manager.agents)}

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """聊天接口"""
    if agent_manager is None:
        return ChatResponse(
            success=False,
            message="系统正在初始化，请稍后再试"
        )
    
    try:
        logger.info(f"聊天请求 - 用户ID: {request.user_id}, 消息: {request.message}")
        logger.info(f"指定智能体名称: {request.agent_name}")
        
        # 如果指定了智能体名称，直接使用该智能体
        if request.agent_name and request.agent_name in agent_manager.agents:
            logger.info(f"使用指定智能体: {request.agent_name}")
            agent = agent_manager.agents[request.agent_name]
            response = await agent.process_message(
                user_id=request.user_id,
                message=request.message,
                context=request.context
            )
        else:
            # 否则使用智能体选择逻辑
            logger.info("使用智能体选择逻辑")
            response = await agent_manager.process_message(
                user_id=request.user_id,
                message=request.message,
                context=request.context
            )
        
        logger.info(f"API响应处理 - 智能体: {response.agent_name}")
        logger.info(f"API响应内容: {response.content}")
        
        chat_response = ChatResponse(
            success=True,
            message=response.content,
            agent_name=response.agent_name,
            tools_used=[]
        )
        
        logger.info(f"API返回的ChatResponse: {chat_response}")
        return chat_response
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return ChatResponse(
            success=False,
            message=f"处理消息时出错: {str(e)}"
        )

@app.websocket("/ws/chat/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str):
    """WebSocket聊天接口"""
    await websocket.accept()
    
    if agent_manager is None:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "系统正在初始化，请稍后再试"
        }))
        return
    
    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # 处理消息
            response = await agent_manager.process_message_stream(
                user_id=user_id,
                message=message_data.get("message", ""),
                context=message_data.get("context", {})
            )
            
            # 流式发送响应
            async for chunk in response:
                await websocket.send_text(json.dumps(chunk))
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"处理消息时出错: {str(e)}"
        }))

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天接口"""
    if agent_manager is None:
        return StreamingResponse(
            iter([json.dumps({"type": "error", "content": "系统正在初始化，请稍后再试"})]),
            media_type="text/plain"
        )
    
    async def generate():
        try:
            logger.info(f"流式聊天请求 - 用户ID: {request.user_id}, 消息: {request.message}")
            logger.info(f"指定智能体名称: {request.agent_name}")
            
            # 如果指定了智能体名称，直接使用该智能体
            if request.agent_name and request.agent_name in agent_manager.agents:
                logger.info(f"使用指定智能体: {request.agent_name}")
                agent = agent_manager.agents[request.agent_name]
                async for chunk in agent.process_message_stream(
                    user_id=request.user_id,
                    message=request.message,
                    context=request.context
                ):
                    yield f"data: {json.dumps(chunk)}\n\n"
            else:
                # 否则使用智能体选择逻辑
                logger.info("使用智能体选择逻辑")
                async for chunk in agent_manager.process_message_stream(
                    user_id=request.user_id,
                    message=request.message,
                    context=request.context
                ):
                    yield f"data: {json.dumps(chunk)}\n\n"
                    
        except Exception as e:
            logger.error(f"流式聊天处理失败: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'content': f'处理消息时出错: {str(e)}'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/plain")



@app.get("/api/tools")
async def get_tools():
    """获取可用工具列表"""
    if tool_manager is None:
        return {"tools": []}
    tools = tool_manager.get_available_tools()
    return {"tools": tools}



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 