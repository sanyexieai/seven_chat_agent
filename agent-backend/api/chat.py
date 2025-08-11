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

logger = get_logger("chat_api")

# 聊天请求和响应模型
class ChatRequest(BaseModel):
    user_id: str
    message: str
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
                    
                    # 调用智能体处理消息
                    if hasattr(agent, 'process_message'):
                        # 如果智能体有process_message方法，直接调用
                        result = await agent.process_message(request.user_id, request.message, request.context)
                        response_message = result.content
                        tools_used = []
                    else:
                        # 否则使用默认的聊天方法
                        result = await agent.chat(request.message)
                        response_message = result.get('response', '抱歉，智能体处理消息时出现错误')
                        tools_used = result.get('tools_used', [])
                    
                    # 如果LLM调用失败，使用模拟响应
                    if not response_message or response_message.startswith('抱歉'):
                        # 尝试使用流式LLM调用
                        try:
                            from utils.llm_helper import get_llm_helper
                            llm_helper = get_llm_helper()
                            
                            # 构建消息格式，包含系统提示词
                            messages = []
                            if hasattr(agent, 'system_prompt') and agent.system_prompt:
                                messages.append({"role": "system", "content": agent.system_prompt})
                            messages.append({"role": "user", "content": request.message})
                            
                            logger.info(f"非流式端点尝试流式LLM调用，消息: {messages}")
                            
                            # 收集流式响应
                            full_response = ""
                            async for chunk in llm_helper.call_stream(messages):
                                if chunk:
                                    full_response += chunk
                            
                            if full_response:
                                response_message = full_response
                                logger.info(f"流式LLM调用成功，响应长度: {len(full_response)}")
                            else:
                                logger.warning("流式LLM调用返回空内容")
                                
                        except Exception as llm_error:
                            logger.error(f"非流式端点流式LLM调用失败: {str(llm_error)}")
                            # 保持原有的模拟响应
                    
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
                        
                        # 直接使用真正的流式LLM调用（不要先走非流式调用，否则会阻塞首字节）
                        tools_used = []
                        try:
                            from utils.llm_helper import get_llm_helper
                            llm_helper = get_llm_helper()
                            
                            # 构建消息格式，包含系统提示词
                            messages = []
                            if hasattr(agent, 'system_prompt') and agent.system_prompt:
                                messages.append({"role": "system", "content": agent.system_prompt})
                            messages.append({"role": "user", "content": request.message})
                            
                            logger.info(f"开始流式LLM调用，消息: {messages}")
                            
                            # 流式调用LLM
                            chunk_count = 0
                            async for chunk in llm_helper.call_stream(messages):
                                if chunk:
                                    chunk_count += 1
                                    logger.info(f"流式返回第{chunk_count}个内容块: {chunk}")
                                    data_chunk = f"data: {json.dumps({'content': chunk, 'type': 'content'}, ensure_ascii=False)}\n\n"
                                    yield data_chunk
                                    # 强制刷新缓冲区，确保数据立即发送
                                    import asyncio
                                    await asyncio.sleep(0)  # 让出控制权，允许数据发送
                                    logger.info(f"已发送第{chunk_count}个内容块")
                            
                            logger.info(f"流式调用完成，共发送{chunk_count}个内容块")
                            # 发送完成信号
                            yield f"data: {json.dumps({'type': 'done', 'tools_used': tools_used}, ensure_ascii=False)}\n\n"
                            
                        except Exception as llm_error:
                            logger.error(f"流式LLM调用失败: {str(llm_error)}")
                            # 回退到逐字符显示
                            for char in response_message:
                                yield f"data: {json.dumps({'content': char, 'type': 'content'}, ensure_ascii=False)}\n\n"
                            yield f"data: {json.dumps({'type': 'done', 'tools_used': tools_used}, ensure_ascii=False)}\n\n"
                        
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



@router.get("/messages/{session_id}", response_model=List[ChatMessageResponse])
async def get_chat_messages(session_id: str, db: Session = Depends(get_db)):
    """获取聊天消息"""
    try:
        message_service = MessageService(db)
        messages = message_service.get_session_messages(session_id)
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
        message_service = MessageService(db)
        chat_message = message_service.create_message(
            session_id=message.session_id,
            user_id=message.user_id,
            message_type=message.message_type,
            content=message.content,
            agent_name=message.agent_name,
            metadata=message.metadata
        )
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