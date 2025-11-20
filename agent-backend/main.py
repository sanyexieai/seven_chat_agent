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
from api.tools import router as tools_router
from api.files import router as files_router

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

# 添加请求日志中间件
@app.middleware("http")
async def log_requests(request, call_next):
    """记录所有HTTP请求"""
    logger.info(f"📥 请求: {request.method} {request.url.path}")
    logger.info(f"  查询参数: {dict(request.query_params)}")
    logger.info(f"  请求头: {dict(request.headers)}")
    
    # 记录请求体（如果是POST/PUT）
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            body = await request.body()
            if body:
                logger.info(f"  请求体: {body.decode()[:200]}...")
        except Exception as e:
            logger.info(f"  请求体读取失败: {e}")
    
    # 处理请求
    response = await call_next(request)
    
    logger.info(f"📤 响应: {request.method} {request.url.path} -> {response.status_code}")
    return response

# 自动检测并挂载静态文件
import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
is_production = os.path.exists(static_dir) and os.path.isdir(static_dir)

logger.info(f"环境检测: is_production={is_production}, static_dir={static_dir}")

# 注册路由（根据环境自动调整前缀）
# 注意：路由模块中已经定义了正确的prefix，这里不需要再添加
app.include_router(agents_router)
app.include_router(sessions_router)
app.include_router(chat_router)
app.include_router(mcp_router)
app.include_router(flows_router)
app.include_router(llm_config_router)
app.include_router(knowledge_base_router)
app.include_router(tools_router)
app.include_router(files_router)

logger.info("所有路由已注册完成")

# 检测路由冲突
def check_route_conflicts():
    """检测路由冲突"""
    logger.info("=== 检测路由冲突 ===")
    routes_by_path = {}
    
    for route in app.routes:
        if hasattr(route, 'path'):
            path = route.path
            methods = list(route.methods) if hasattr(route, 'methods') else []
            endpoint = getattr(route, 'endpoint', 'N/A')
            endpoint_name = getattr(endpoint, '__name__', str(endpoint)) if endpoint else 'N/A'
            
            if path not in routes_by_path:
                routes_by_path[path] = []
            
            routes_by_path[path].append({
                'methods': methods,
                'endpoint': endpoint_name
            })
    
    # 检查冲突（仅在同一路径上存在相同HTTP方法的重复绑定时告警）
    for path, route_list in routes_by_path.items():
        method_to_endpoints = {}
        for r in route_list:
            for m in r['methods']:
                method_to_endpoints.setdefault(m, []).append(r['endpoint'])
        duplicated = {m: eps for m, eps in method_to_endpoints.items() if len(eps) > 1}
        if duplicated:
            logger.warning(f"⚠️  路由冲突检测到: {path}")
            idx = 0
            for m, eps in duplicated.items():
                for ep in eps:
                    idx += 1
                    logger.warning(f"  {idx}. 方法: ['{m}'] -> {ep}")
        
        # 特别检查知识库路由
        if 'knowledge' in path.lower():
            logger.info(f"🔍 知识库路由检查: {path}")
            for i, route in enumerate(route_list):
                logger.info(f"  {i+1}. 方法: {route['methods']} -> {route['endpoint']}")
    
    logger.info("=== 路由冲突检测完成 ===")

# 执行路由冲突检测
check_route_conflicts()

# 显示所有注册的路由
logger.info("=== 已注册的路由 ===")
for route in app.routes:
    if hasattr(route, 'path'):
        methods = ', '.join(route.methods) if hasattr(route, 'methods') else 'N/A'
        endpoint = getattr(route, 'endpoint', 'N/A')
        endpoint_name = getattr(endpoint, '__name__', str(endpoint)) if endpoint else 'N/A'
        logger.info(f"路由: {route.path} [{methods}] -> {endpoint_name}")
        
        # 特别检查知识库相关路由
        if 'knowledge' in str(route.path).lower() or 'knowledge' in str(endpoint_name).lower():
            logger.info(f"  *** 知识库路由详情: {route.path} [{methods}] -> {endpoint_name}")
            if hasattr(route, 'methods'):
                logger.info(f"  支持的方法: {list(route.methods)}")
logger.info("==================")

# 静态文件挂载必须在路由注册之后
if is_production:
    logger.info(f"检测到静态文件目录: {static_dir}")
    # 检查静态文件目录内容
    if os.path.exists(static_dir):
        logger.info(f"静态文件目录内容:")
        for root, dirs, files in os.walk(static_dir):
            level = root.replace(static_dir, '').count(os.sep)
            indent = ' ' * 2 * level
            logger.info(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 2 * (level + 1)
            for file in files:
                logger.info(f"{subindent}{file}")
    
    # 修复：将静态文件挂载到/static路径，而不是根路径
    app.mount("/static", StaticFiles(directory=os.path.join(static_dir, "static")), name="static")
    logger.info("静态文件已挂载到 /static 路径")
    
    # 添加根路径处理，返回index.html
    @app.get("/")
    async def serve_index():
        from fastapi.responses import FileResponse
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Static files not found"}

# 根路径和健康检查API
@app.get("/api/")
async def root():
    """根路径"""
    return {
        "message": "Seven Chat Agent API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check_root():
    """健康检查（根路径）"""
    return {
        "status": "healthy",
        "agent_manager": "initialized" if agent_manager else "not_initialized"
    }

@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "agent_manager": "initialized" if agent_manager else "not_initialized"
    }

# 通配符路由必须在所有其他路由之后注册，用于处理前端路由
if is_production:
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        from fastapi.responses import FileResponse
        
        # 如果是API请求，直接返回404（让FastAPI处理）
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        
        # 尝试提供静态文件（非/static路径）
        file_path = os.path.join(static_dir, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        
        # 如果文件不存在，返回index.html（支持SPA路由）
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        
        raise HTTPException(status_code=404, detail="File not found")

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
                    chunk_payload = {
                        'chunk_id': chunk.chunk_id,
                        'type': chunk.type,
                        'content': chunk.content,
                        'agent_name': chunk.agent_name,
                        'metadata': chunk.metadata,
                        'is_end': chunk.is_end
                    }
                    yield "data: " + json.dumps(chunk_payload) + "\n\n"
                    
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