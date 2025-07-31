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

# 获取logger实例
logger = get_logger("main")

# 全局管理器
agent_manager = AgentManager()
tool_manager = ToolManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("AI Agent System starting up...")
    await agent_manager.initialize()
    await tool_manager.initialize()
    logger.info("AI Agent System started successfully")
    
    yield
    
    # 关闭时清理
    logger.info("AI Agent System shutting down...")

app = FastAPI(title="AI Agent System", version="1.0.0", lifespan=lifespan)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """根路径"""
    return {"message": "AI Agent System API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "agents": len(agent_manager.agents)}

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """聊天接口"""
    try:
        # 处理用户消息
        response = await agent_manager.process_message(
            user_id=request.user_id,
            message=request.message,
            context=request.context
        )
        
        return ChatResponse(
            success=True,
            message=response.content,
            agent_name=response.agent_name,
            tools_used=[]
        )
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

@app.get("/api/agents")
async def get_agents():
    """获取可用智能体列表"""
    agents = agent_manager.get_available_agents()
    return {"agents": agents}

@app.get("/api/tools")
async def get_tools():
    """获取可用工具列表"""
    tools = tool_manager.get_available_tools()
    return {"tools": tools}

@app.post("/api/agents/{agent_name}/execute")
async def execute_agent(agent_name: str, request: dict):
    """执行特定智能体"""
    try:
        result = await agent_manager.execute_agent(
            agent_name=agent_name,
            params=request
        )
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 