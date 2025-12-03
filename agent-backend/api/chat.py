from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from database.database import get_db
from models.database_models import ChatMessage, UserSession
from models.database_models import ChatMessageResponse, MessageCreate
from services.session_service import SessionService, MessageService
from services.pipeline_state_service import PipelineStateService
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
    agent_name: str = "general_agent"  # 智能体名称，可以在聊天时动态选择
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
        logger.info(f"收到聊天请求: user_id={request.user_id}, agent_name={request.agent_name}")
        
        # 调用智能体管理器来处理消息
        try:
            from main import agent_manager
            if agent_manager:
                # 获取智能体 - 现在从agent_name获取，可以在聊天时动态选择
                agent = agent_manager.get_agent(request.agent_name)
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
                        # 在context中添加数据库会话和session_id，以便智能体查询知识库和恢复上下文
                        enhanced_context = request.context.copy() if request.context else {}
                        enhanced_context['db_session'] = db
                        if request.session_id:
                            enhanced_context['session_id'] = request.session_id

                        # 在调用前从数据库恢复 Pipeline 状态
                        try:
                            if request.session_id:
                                from agents.pipeline import Pipeline
                                state = PipelineStateService.get_state(
                                    db=db,
                                    user_id=request.user_id,
                                    agent_name=agent.name,
                                    session_id=request.session_id,
                                )
                                if state:
                                    p = Pipeline(pipeline_id=state.get("pipeline_id"))
                                    p.import_data(state)
                                    enhanced_context["pipeline"] = p
                        except Exception as e:
                            logger.warning(f"恢复 Pipeline 状态失败: {e}")
                        
                        # 调用智能体的process_message方法
                        result = await agent.process_message(request.user_id, request.message, enhanced_context)
                        response_message = result.content
                        tools_used = result.metadata.get('tools_used', []) if result.metadata else []
                        
                        # 在调用后保存 Pipeline 状态
                        try:
                            from agents.pipeline import Pipeline
                            pipeline = enhanced_context.get("pipeline")
                            if isinstance(pipeline, Pipeline) and request.session_id:
                                state = pipeline.export()
                                PipelineStateService.save_state(
                                    db=db,
                                    user_id=request.user_id,
                                    agent_name=agent.name,
                                    session_id=request.session_id,
                                    state=state,
                                )
                        except Exception as e:
                            logger.warning(f"保存 Pipeline 状态失败: {e}")

                        logger.info(f"智能体 {agent.name} 处理消息完成，使用工具: {tools_used}")
                    else:
                        # 否则使用默认的聊天方法
                        result = await agent.chat(request.message)
                        response_message = result.get('response', '抱歉，智能体处理消息时出现错误')
                        tools_used = result.get('tools_used', [])
                    
                    agent_name = agent.description or agent.name
                else:
                    logger.info(f"未找到智能体: {request.agent_name}，将直接调用LLM")
                    # 如果没有找到智能体，直接调用LLM
                    try:
                        from utils.llm_helper import LLMHelper
                        llm_helper = LLMHelper()
                        
                        # 直接调用LLM
                        response_message = await llm_helper.call_llm(request.message)
                        tools_used = []
                        agent_name = "AI助手"
                        
                        logger.info("直接调用LLM完成")
                    except Exception as e:
                        logger.error(f"直接调用LLM失败: {str(e)}")
                        response_message = "抱歉，AI处理消息时出现错误，请稍后重试"
                        tools_used = []
                        agent_name = "系统"
            else:
                logger.info("智能体管理器未初始化，将直接调用LLM")
                # 如果智能体管理器未初始化，直接调用LLM
                try:
                    from utils.llm_helper import LLMHelper
                    llm_helper = LLMHelper()
                    
                    # 直接调用LLM
                    response_message = await llm_helper.call_llm(request.message)
                    tools_used = []
                    agent_name = "AI助手"
                    
                    logger.info("直接调用LLM完成")
                except Exception as e:
                    logger.error(f"直接调用LLM失败: {str(e)}")
                    response_message = "抱歉，AI处理消息时出现错误，请稍后重试"
                    tools_used = []
                    agent_name = "系统"
            
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
                        agent_name=agent_name
                    )
                    user_message = MessageService.create_message(db, user_message_data)
                    
                    # 保存助手回复
                    assistant_message_data = MessageCreate(
                        session_id=request.session_id,
                        user_id=request.user_id,
                        message_type="assistant",
                        content=response_message,
                        agent_name=agent_name,
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
                agent_name=agent_name,
                tools_used=tools_used,
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

@router.options("/stream")
async def chat_stream_options():
    """处理流式聊天API的OPTIONS请求"""
    return {"message": "OK"}

@router.post("/stream")
async def chat_stream(request: ChatRequest, db: Session = Depends(get_db)):
    """处理流式聊天请求
    
    此端点仅负责：
    1. 获取智能体
    2. 调用工作流引擎适配器执行
    3. 将流式响应转换为 SSE 格式并返回
    
    所有业务逻辑（保存消息、收集节点信息等）都在工作流引擎中通过钩子机制实现。
    """
    try:
        logger.info(f"收到流式聊天请求: user_id={request.user_id}, agent_name={request.agent_name}")
        
        async def generate_response():
            try:
                from main import agent_manager
                if not agent_manager:
                    raise ValueError("智能体管理器未初始化")
                
                # 获取智能体
                agent = agent_manager.get_agent(request.agent_name)
                if not agent:
                    raise ValueError(f"未找到智能体: {request.agent_name}")
                
                logger.info(f"找到智能体: {agent.name}")
                
                # 获取智能体的完整信息，包括绑定的工具
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
                
                # 在context中添加数据库会话和session_id，以便智能体查询知识库和恢复上下文
                enhanced_context = request.context.copy() if request.context else {}
                enhanced_context['db_session'] = db
                if request.session_id:
                    enhanced_context['session_id'] = request.session_id

                # 在执行工作流/流式处理前，从数据库恢复 Pipeline 状态
                try:
                    if request.session_id:
                        from agents.pipeline import Pipeline
                        state = PipelineStateService.get_state(
                            db=db,
                            user_id=request.user_id,
                            agent_name=agent.name,
                            session_id=request.session_id,
                        )
                        if state:
                            p = Pipeline(pipeline_id=state.get("pipeline_id"))
                            p.import_data(state)
                            enhanced_context["pipeline"] = p
                except Exception as e:
                    logger.warning(f"恢复 Pipeline 状态失败: {e}")
                
                # 如果有 session_id，则先保存一条用户消息到 chat_messages（与非流式接口行为对齐）
                if request.session_id:
                    try:
                        from models.database_models import MessageCreate
                        # 这里的 agent_name 采用智能体的对外名称（描述优先，其次名称）
                        stream_agent_name = agent.description if hasattr(agent, 'description') and agent.description else agent.name
                        user_message_data = MessageCreate(
                            session_id=request.session_id,
                            user_id=request.user_id,
                            message_type="user",
                            content=request.message,
                            agent_name=stream_agent_name,
                            metadata=None
                        )
                        MessageService.create_message(db, user_message_data)
                        logger.info(f"流式会话 {request.session_id} 已保存用户消息到 chat_messages")
                    except Exception as e:
                        logger.warning(f"流式会话保存用户消息失败: {str(e)}")

                # 使用工作流引擎适配器执行（优先使用工作流引擎，否则回退到智能体的 process_message_stream）
                from agents.flow.agent_adapter import execute_agent_stream
                from agents.flow.business_handler import FlowBusinessHandler
                
                # 创建业务逻辑处理器（用于获取工具使用情况和处理业务逻辑）
                business_handler = FlowBusinessHandler(db=db)
                business_handler.user_id = request.user_id
                business_handler.session_id = request.session_id
                business_handler.agent_name = agent.description if hasattr(agent, 'description') else agent.name
                
                # 记录session_id信息用于调试
                logger.info(f"流式聊天请求：session_id={request.session_id}, user_id={request.user_id}, agent_name={business_handler.agent_name}")
                
                # 执行流式处理
                assistant_message_saved = False
                async for chunk in execute_agent_stream(
                    agent=agent,
                    user_id=request.user_id,
                    message=request.message,
                    context=enhanced_context,
                    db=db,
                    session_id=request.session_id,
                    business_handler=business_handler
                ):
                    # 将 StreamChunk 转换为 SSE 格式
                    # 确保所有类型的 chunk 都被传递，包括 node_start 和 node_complete
                    chunk_data = {
                        'content': chunk.content or '',
                        'type': chunk.type,
                        'chunk_id': chunk.chunk_id,
                        'metadata': chunk.metadata or {}
                    }
                    
                    # 特殊处理某些类型
                    if chunk.type == "tool_result":
                        chunk_data['tool_name'] = chunk.metadata.get('tool_name', '') if chunk.metadata else ''
                    elif chunk.type == "final":
                        chunk_data['type'] = 'final_response'
                    elif chunk.type == "done":
                        # 获取工具使用情况
                        tools_used = business_handler.get_tools_used()
                        chunk_data['tools_used'] = tools_used
                    # node_start 和 node_complete 事件直接传递，不需要特殊处理
                    # 但确保 metadata 中包含完整的节点信息
                    elif chunk.type in ("node_start", "node_complete"):
                        # 确保 metadata 中包含节点信息
                        if chunk.metadata:
                            # metadata 已经包含了 node_id, node_type, node_name, node_label 等信息
                            # 这些信息由 BaseFlowNode._create_stream_chunk 自动添加
                            pass
                    
                    # 记录日志以便调试
                    if chunk.type in ("node_start", "node_complete"):
                        logger.debug(f"发送节点事件: type={chunk.type}, node_id={chunk.metadata.get('node_id') if chunk.metadata else 'N/A'}")
                    
                    data_chunk = f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                    yield data_chunk
                    
                    # 如果是最终块或错误块，发送完成信号
                    # 注意：不要立即 break，因为流程可能还没有执行到结束节点
                    # 继续接收后续的 chunk，直到收到 done 类型的 chunk 或者生成器结束
                    if chunk.type == "error":
                        # 错误块：立即发送完成信号并 break
                        done_data = {
                            'type': 'done',
                            'tools_used': business_handler.get_tools_used()
                        }
                        yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                        break
                    elif chunk.type == "done":
                        # done 块：发送完成信号并 break
                        done_data = {
                            'type': 'done',
                            'tools_used': business_handler.get_tools_used()
                        }
                        yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                        break
                    elif chunk.type == "final":
                        # 在收到最终内容块时，将助手完整回复保存到 chat_messages
                        if request.session_id and not assistant_message_saved:
                            try:
                                from models.database_models import MessageCreate
                                stream_agent_name = agent.description if hasattr(agent, 'description') and agent.description else agent.name
                                assistant_message_data = MessageCreate(
                                    session_id=request.session_id,
                                    user_id=request.user_id,
                                    message_type="assistant",
                                    content=chunk.content or "",
                                    agent_name=stream_agent_name,
                                    metadata={"tools_used": business_handler.get_tools_used()},
                                )
                                MessageService.create_message(db, assistant_message_data)
                                assistant_message_saved = True
                                logger.info(f"流式会话 {request.session_id} 已保存助手消息到 chat_messages")
                            except Exception as e:
                                logger.warning(f"流式会话保存助手消息失败: {str(e)}")

                        # final 块：发送完成信号，但不要立即 break，继续接收后续的 chunk
                        done_data = {
                            'type': 'done',
                            'tools_used': business_handler.get_tools_used()
                        }
                        yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                        # 不要 break，继续接收后续的 chunk（如结束节点的 chunk）

                # 流式执行结束后，若有 Pipeline，则保存状态
                try:
                    from agents.pipeline import Pipeline
                    pipeline = enhanced_context.get("pipeline")
                    if isinstance(pipeline, Pipeline) and request.session_id:
                        state = pipeline.export()
                        PipelineStateService.save_state(
                            db=db,
                            user_id=request.user_id,
                            agent_name=agent.name,
                            session_id=request.session_id,
                            state=state,
                        )
                except Exception as e:
                    logger.warning(f"保存 Pipeline 状态失败: {e}")

                logger.info(f"智能体 {agent.name} 流式处理消息完成")
                
            except Exception as e:
                logger.error(f"流式调用智能体失败: {str(e)}")
                error_data = {
                    'content': f'抱歉，智能体处理消息时出现错误: {str(e)}',
                    'type': 'error'
                }
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'tools_used': []}, ensure_ascii=False)}\n\n"
        
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
            background=None
        )
        
    except Exception as e:
        logger.error(f"处理流式聊天请求失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理聊天请求失败: {str(e)}"
        )



@router.post("/sessions", name="create_chat_session")
async def create_chat_session(request: dict, db: Session = Depends(get_db)):
    """创建新的聊天会话"""
    try:
        user_id = request.get("user_id")
        session_name = request.get("session_name", "新对话")
        # 智能体ID现在是可选的，不强制绑定
        agent_id = request.get("agent_id")
        
        if not user_id:
            raise HTTPException(status_code=400, detail="用户ID不能为空")
        
        # 创建会话数据
        from models.database_models import SessionCreate
        session_data = SessionCreate(
            user_id=user_id,
            session_name=session_name,
            agent_id=agent_id  # 可以为None
        )
        
        session = SessionService.create_session(db, session_data)
        
        logger.info(f"创建聊天会话: {session.session_id}, 智能体: {agent_id or '未选择'}")
        return {
            "success": True,
            "id": session.id,  # 添加数字ID
            "session_id": session.session_id,
            "session_name": session.session_name,
            "agent_id": session.agent_id,
            "created_at": session.created_at.isoformat()
        }
    except Exception as e:
        logger.error(f"创建聊天会话失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建聊天会话失败: {str(e)}"
        )

@router.get("/sessions/{user_id}", name="get_user_sessions_chat")
async def get_user_sessions(user_id: str, db: Session = Depends(get_db)):
    """获取用户的所有聊天会话"""
    try:
        sessions = SessionService.get_user_sessions(db, user_id)
        logger.info(f"获取用户 {user_id} 的会话，共 {len(sessions)} 个")
        return {
            "success": True,
            "sessions": [
                {
                    "id": session.id,  # 添加数字ID
                    "session_id": session.session_id,
                    "session_name": session.session_name,
                    "agent_id": session.agent_id,  # 修复字段名
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
        # 使用 MessageService 获取消息和节点信息
        # session_id 是字符串类型（UUID），不是整数
        from services.session_service import MessageService
        messages = MessageService.get_session_messages(db, session_id)
        
        # 转换为 ChatMessageResponse 格式
        from models.database_models import ChatMessageResponse, MessageNodeResponse
        result = []
        for message in messages:
            # 转换节点信息
            node_responses = []
            if message.nodes:
                for node in message.nodes:
                    node_responses.append(MessageNodeResponse(
                        id=node.id,
                        node_id=node.node_id,
                        node_type=node.node_type,
                        node_name=node.node_name,
                        node_label=node.node_label,
                        content=node.content,  # 添加节点内容
                        node_metadata=node.node_metadata,
                        created_at=node.created_at
                    ))
            
            result.append(ChatMessageResponse(
                id=message.id,
                message_id=message.message_id,
                session_id=message.session_id,
                user_id=message.user_id,
                message_type=message.message_type,
                content=message.content,  # 添加消息内容！
                agent_name=message.agent_name,
                metadata=message.metadata,
                created_at=message.created_at,
                nodes=node_responses
            ))
        
        logger.info(f"获取会话 {session_id} 的消息，共 {len(result)} 条")
        return result
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


@router.post("/sessions")
async def create_session(user_id: str, agent_id: int, db: Session = Depends(get_db)):
    """创建新会话（兼容性端点）"""
    try:
        # 创建会话数据
        from models.database_models import SessionCreate
        session_data = SessionCreate(
            user_id=user_id,
            session_name="新对话",
            agent_id=agent_id
        )
        session = SessionService.create_session(db, session_data)
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