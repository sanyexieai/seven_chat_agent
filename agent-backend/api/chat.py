from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from database.database import get_db
from models.database_models import ChatMessage, UserSession
from models.database_models import ChatMessageResponse, MessageCreate
from services.session_service import SessionService, MessageService
from utils.log_helper import get_logger
from pydantic import BaseModel
import json
import asyncio

logger = get_logger("chat_api")

# 聊天请求和响应模型
class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str = None  # 会话ID，用于维护上下文
    context: Dict[str, Any] = {}
    agent_type: str = "general"
    stream: bool = False

class ChatResponse(BaseModel):
    success: bool
    message: str
    agent_name: str = "AI助手"
    tools_used: List[str] = []
    timestamp: str

router = APIRouter(prefix="/api/chat", tags=["chat"])

@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    """处理聊天请求"""
    try:
        logger.info(f"收到聊天请求: user_id={request.user_id}, agent_type={request.agent_type}")
        
        # 调用智能体管理器来处理消息
        try:
            from main import agent_manager
            if agent_manager:
                # 获取智能体
                agent = agent_manager.get_agent(request.agent_type)
                if agent:
                    logger.info(f"找到智能体: {agent.name}")
                    
                    # 获取智能体的完整信息，包括绑定的工具
                    agent_info = None
                    try:
                        from services.agent_service import AgentService
                        agent_service = AgentService()
                        agent_info = agent_service.get_agent_by_name(db, agent.name)
                        
                        # 如果智能体有绑定的工具，设置到智能体实例中
                        if agent_info and agent_info.bound_tools:
                            if hasattr(agent, 'set_bound_tools'):
                                agent.set_bound_tools(agent_info.bound_tools)
                                logger.info(f"智能体 {agent.name} 绑定了 {len(agent_info.bound_tools)} 个工具")
                    except Exception as e:
                        logger.warning(f"获取智能体信息失败: {str(e)}")
                    
                    # 调用智能体处理消息
                    if hasattr(agent, 'process_message'):
                        # 在context中添加数据库会话，以便智能体查询知识库
                        enhanced_context = request.context.copy() if request.context else {}
                        enhanced_context['db_session'] = db
                        
                        # 调用智能体的process_message方法
                        result = await agent.process_message(request.user_id, request.message, enhanced_context)
                        response_message = result.content
                        tools_used = result.metadata.get('tools_used', []) if result.metadata else []
                        
                        logger.info(f"智能体 {agent.name} 处理消息完成，使用工具: {tools_used}")
                    else:
                        # 否则使用默认的聊天方法
                        result = await agent.chat(request.message)
                        response_message = result.get('response', '抱歉，智能体处理消息时出现错误')
                        tools_used = result.get('tools_used', [])
                    
                    # 保存聊天消息到数据库
                    if request.session_id:
                        try:
                            from datetime import datetime
                            # 保存用户消息
                            from models.database_models import MessageCreate
                            user_message_data = MessageCreate(
                                session_id=request.session_id,
                                user_id=request.user_id,
                                message_type="user",
                                content=request.message,
                                agent_name=agent.description or agent.name
                            )
                            user_message = MessageService.create_message(db, user_message_data)
                            
                            # 保存助手回复
                            assistant_message_data = MessageCreate(
                                session_id=request.session_id,
                                user_id=request.user_id,
                                message_type="assistant",
                                content=response_message,
                                agent_name=agent.description or agent.name,
                                metadata={"tools_used": tools_used}
                            )
                            assistant_message = MessageService.create_message(db, assistant_message_data)
                            
                            logger.info(f"保存聊天消息: 用户消息ID={user_message.message_id}, 助手消息ID={assistant_message.message_id}")
                        except Exception as e:
                            logger.warning(f"保存聊天消息失败: {str(e)}")
                    
                    from datetime import datetime
                    response = ChatResponse(
                        success=True,
                        message=response_message,
                        agent_name=agent.description or agent.name,
                        tools_used=tools_used,
                        timestamp=datetime.now().isoformat()
                    )
                else:
                    logger.warning(f"未找到智能体: {request.agent_type}")
                    # 返回错误响应
                    response = ChatResponse(
                        success=False,
                        message=f"抱歉，未找到智能体 {request.agent_type}",
                        agent_name="系统",
                        tools_used=[],
                        timestamp=datetime.now().isoformat()
                    )
            else:
                logger.error("智能体管理器未初始化")
                response = ChatResponse(
                    success=False,
                    message="抱歉，智能体系统未初始化，请稍后重试",
                    agent_name="系统",
                    tools_used=[],
                    timestamp=datetime.now().isoformat()
                )
        except Exception as e:
            logger.error(f"调用智能体失败: {str(e)}")
            response = ChatResponse(
                success=False,
                message=f"抱歉，智能体处理消息时出现错误: {str(e)}",
                agent_name="系统",
                tools_used=[],
                timestamp=datetime.now().isoformat()
            )
        
        return response
    except Exception as e:
        logger.error(f"处理聊天请求失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理聊天请求失败: {str(e)}"
        )

@router.post("/stream")
async def chat_stream(request: ChatRequest, db: Session = Depends(get_db)):
    """处理流式聊天请求"""
    try:
        logger.info(f"收到流式聊天请求: user_id={request.user_id}, agent_type={request.agent_type}")
        
        async def generate_response():
            try:
                from main import agent_manager
                if agent_manager:
                    # 获取智能体
                    agent = agent_manager.get_agent(request.agent_type)
                    if agent:
                        logger.info(f"找到智能体: {agent.name}")
                        
                        # 获取智能体的完整信息，包括绑定的工具
                        agent_info = None
                        try:
                            from services.agent_service import AgentService
                            agent_service = AgentService()
                            agent_info = agent_service.get_agent_by_name(db, agent.name)
                            
                            # 如果智能体有绑定的工具，设置到智能体实例中
                            if agent_info and agent_info.bound_tools:
                                if hasattr(agent, 'set_bound_tools'):
                                    agent.set_bound_tools(agent_info.bound_tools)
                                    logger.info(f"智能体 {agent.name} 绑定了 {len(agent_info.bound_tools)} 个工具")
                        except Exception as e:
                            logger.warning(f"获取智能体信息失败: {str(e)}")
                        
                        # 调用智能体的流式处理方法
                        if hasattr(agent, 'process_message_stream'):
                            try:
                                # 在context中添加数据库会话，以便智能体查询知识库
                                enhanced_context = request.context.copy() if request.context else {}
                                enhanced_context['db_session'] = db
                                
                                # 调用智能体的process_message_stream方法
                                tools_used = []
                                async for chunk in agent.process_message_stream(request.user_id, request.message, enhanced_context):
                                    if chunk.type == "content":
                                        # 发送内容块
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'content'}, ensure_ascii=False)}\n\n"
                                        yield data_chunk
                                    elif chunk.type == "tool_result":
                                        # 发送工具执行结果
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'tool_result', 'tool_name': chunk.metadata.get('tool_name', '')}, ensure_ascii=False)}\n\n"
                                        yield data_chunk
                                        tools_used.append(chunk.metadata.get('tool_name', ''))
                                    elif chunk.type == "tool_error":
                                        # 发送工具错误
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'tool_error'}, ensure_ascii=False)}\n\n"
                                        yield data_chunk
                                    elif chunk.type == "final":
                                        # 发送最终响应
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'final_response'}, ensure_ascii=False)}\n\n"
                                        yield data_chunk
                                        # 保存聊天消息到数据库
                                        if request.session_id:
                                            try:
                                                from datetime import datetime
                                                # 保存用户消息
                                                from models.database_models import MessageCreate
                                                user_message_data = MessageCreate(
                                                    session_id=request.session_id,
                                                    user_id=request.user_id,
                                                    message_type="user",
                                                    content=request.message,
                                                    agent_name=agent.description or agent.name
                                                )
                                                user_message = MessageService.create_message(db, user_message_data)
                                                
                                                # 保存助手回复
                                                assistant_message_data = MessageCreate(
                                                    session_id=request.session_id,
                                                    user_id=request.user_id,
                                                    message_type="assistant",
                                                    content=chunk.content,
                                                    agent_name=agent.description or agent.name,
                                                    metadata={"tools_used": tools_used}
                                                )
                                                assistant_message = MessageService.create_message(db, assistant_message_data)
                                                
                                                logger.info(f"保存流式聊天消息: 用户消息ID={user_message.message_id}, 助手消息ID={assistant_message.message_id}")
                                            except Exception as e:
                                                logger.warning(f"保存流式聊天消息失败: {str(e)}")
                                        
                                        # 发送完成信号
                                        yield f"data: {json.dumps({'type': 'done', 'tools_used': tools_used}, ensure_ascii=False)}\n\n"
                                        break
                                    elif chunk.type == "error":
                                        # 发送错误消息
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'error'}, ensure_ascii=False)}\n\n"
                                        yield data_chunk
                                        yield f"data: {json.dumps({'type': 'done', 'tools_used': tools_used}, ensure_ascii=False)}\n\n"
                                        break
                                
                                logger.info(f"智能体 {agent.name} 流式处理消息完成，使用工具: {tools_used}")
                                
                            except Exception as e:
                                logger.error(f"智能体流式处理消息失败: {str(e)}")
                                error_message = f"抱歉，智能体处理消息时出现错误: {str(e)}"
                                yield f"data: {json.dumps({'content': error_message, 'type': 'error'}, ensure_ascii=False)}\n\n"
                                yield f"data: {json.dumps({'type': 'done', 'tools_used': []}, ensure_ascii=False)}\n\n"
                        else:
                            # 回退到简单的流式LLM调用
                            logger.warning(f"智能体 {agent.name} 没有process_message_stream方法，使用回退方案")
                            try:
                                from utils.llm_helper import get_llm_helper
                                llm_helper = get_llm_helper()
                                
                                # 构建消息
                                messages = []
                                if hasattr(agent, 'system_prompt') and agent.system_prompt:
                                    messages.append({"role": "system", "content": agent.system_prompt})
                                messages.append({"role": "user", "content": request.message})
                                
                                # 流式调用LLM
                                async for chunk in llm_helper.call_stream(messages):
                                    if chunk:
                                        data_chunk = f"data: {json.dumps({'content': chunk, 'type': 'content'}, ensure_ascii=False)}\n\n"
                                        yield data_chunk
                                
                                yield f"data: {json.dumps({'type': 'done', 'tools_used': []}, ensure_ascii=False)}\n\n"
                                
                            except Exception as llm_error:
                                logger.error(f"回退流式LLM调用失败: {str(llm_error)}")
                                error_message = f"抱歉，LLM调用失败: {str(llm_error)}"
                                yield f"data: {json.dumps({'content': error_message, 'type': 'error'}, ensure_ascii=False)}\n\n"
                                yield f"data: {json.dumps({'type': 'done', 'tools_used': []}, ensure_ascii=False)}\n\n"
                        
                    else:
                        logger.warning(f"未找到智能体: {request.agent_type}")
                        yield f"data: {json.dumps({'error': f'抱歉，未找到智能体 {request.agent_type}'}, ensure_ascii=False)}\n\n"
                else:
                    logger.error("智能体管理器未初始化")
                    yield f"data: {json.dumps({'error': '抱歉，智能体系统未初始化，请稍后重试'}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"流式调用智能体失败: {str(e)}")
                yield f"data: {json.dumps({'error': f'抱歉，智能体处理消息时出现错误: {str(e)}'}, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            generate_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*"
            },
            # 添加这些参数确保流式工作
            background=None
        )
        
    except Exception as e:
        logger.error(f"处理流式聊天请求失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理聊天请求失败: {str(e)}"
        )



@router.post("/sessions")
async def create_chat_session(request: dict, db: Session = Depends(get_db)):
    """创建新的聊天会话"""
    try:
        user_id = request.get("user_id")
        session_name = request.get("session_name", "新对话")
        agent_type = request.get("agent_type", "general")
        
        if not user_id:
            raise HTTPException(status_code=400, detail="用户ID不能为空")
        
        session_service = SessionService(db)
        session = session_service.create_session(
            user_id=user_id,
            session_name=session_name,
            agent_type=agent_type
        )
        
        logger.info(f"创建聊天会话: {session.session_id}")
        return {
            "success": True,
            "session_id": session.session_id,
            "session_name": session.session_name,
            "agent_type": session.agent_type,
            "created_at": session.created_at.isoformat()
        }
    except Exception as e:
        logger.error(f"创建聊天会话失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建聊天会话失败: {str(e)}"
        )

@router.get("/sessions/{user_id}")
async def get_user_sessions(user_id: str, db: Session = Depends(get_db)):
    """获取用户的所有聊天会话"""
    try:
        session_service = SessionService(db)
        sessions = session_service.get_user_sessions(user_id)
        logger.info(f"获取用户 {user_id} 的会话，共 {len(sessions)} 个")
        return {
            "success": True,
            "sessions": [
                {
                    "session_id": session.session_id,
                    "session_name": session.session_name,
                    "agent_type": session.agent_type,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat() if session.updated_at else None
                }
                for session in sessions
            ]
        }
    except Exception as e:
        logger.error(f"获取用户会话失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户会话失败: {str(e)}"
        )

@router.get("/messages/{session_id}", response_model=List[ChatMessageResponse])
async def get_chat_messages(session_id: str, db: Session = Depends(get_db)):
    """获取聊天消息"""
    try:
        messages = MessageService.get_session_messages(db, session_id)
        logger.info(f"获取会话 {session_id} 的消息，共 {len(messages)} 条")
        return messages
    except Exception as e:
        logger.error(f"获取聊天消息失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取聊天消息失败: {str(e)}"
        )

@router.post("/messages", response_model=ChatMessageResponse)
async def create_chat_message(message: MessageCreate, db: Session = Depends(get_db)):
    """创建聊天消息"""
    try:
        from models.database_models import MessageCreate
        message_data = MessageCreate(
            session_id=message.session_id,
            user_id=message.user_id,
            message_type=message.message_type,
            content=message.content,
            agent_name=message.agent_name,
            metadata=message.metadata
        )
        chat_message = MessageService.create_message(db, message_data)
        logger.info(f"创建聊天消息: {chat_message.message_id}")
        return chat_message
    except Exception as e:
        logger.error(f"创建聊天消息失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建聊天消息失败: {str(e)}"
        )

@router.get("/sessions/{user_id}")
async def get_user_sessions(user_id: str, db: Session = Depends(get_db)):
    """获取用户的会话列表"""
    try:
        session_service = SessionService(db)
        sessions = session_service.get_user_sessions(user_id)
        logger.info(f"获取用户 {user_id} 的会话，共 {len(sessions)} 个")
        return sessions
    except Exception as e:
        logger.error(f"获取用户会话失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户会话失败: {str(e)}"
        )

@router.post("/sessions")
async def create_session(user_id: str, agent_id: int, db: Session = Depends(get_db)):
    """创建新会话"""
    try:
        session_service = SessionService(db)
        session = session_service.create_session(user_id, agent_id)
        logger.info(f"创建会话: {session.session_id}")
        return session
    except Exception as e:
        logger.error(f"创建会话失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建会话失败: {str(e)}"
        )

@router.delete("/sessions/{session_id}")
async def deactivate_session(session_id: str, db: Session = Depends(get_db)):
    """停用会话"""
    try:
        session_service = SessionService(db)
        success = session_service.deactivate_session(session_id)
        if success:
            logger.info(f"停用会话: {session_id}")
            return {"message": "会话已停用"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停用会话失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"停用会话失败: {str(e)}"
        ) 