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
    """处理流式聊天请求"""
    try:
        logger.info(f"收到流式聊天请求: user_id={request.user_id}, agent_name={request.agent_name}")
        
        async def generate_response():
            try:
                from main import agent_manager
                if agent_manager:
                    # 获取智能体
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
                        
                        # 调用智能体的流式处理方法
                        if hasattr(agent, 'process_message_stream'):
                            try:
                                # 在context中添加数据库会话，以便智能体查询知识库
                                enhanced_context = request.context.copy() if request.context else {}
                                enhanced_context['db_session'] = db
                                
                                # 调用智能体的process_message_stream方法
                                tools_used = []
                                live_follow_segments: list[str] = []
                                collected_nodes: list[dict] = []  # 收集节点信息
                                
                                async for chunk in agent.process_message_stream(request.user_id, request.message, enhanced_context):
                                    if chunk.type == "node_start":
                                        # 发送节点开始事件，包含完整的chunk信息
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'node_start', 'chunk_id': chunk.chunk_id, 'metadata': chunk.metadata}, ensure_ascii=False)}\n\n"
                                        yield data_chunk
                                        
                                        # 收集节点信息
                                        if chunk.metadata and chunk.metadata.get('node_id'):
                                            # 检查是否已收集过该节点
                                            existing_node = next((node for node in collected_nodes if node['node_id'] == chunk.metadata['node_id']), None)
                                            if not existing_node:
                                                collected_nodes.append({
                                                    'node_id': chunk.metadata.get('node_id'),
                                                    'node_type': chunk.metadata.get('node_type'),
                                                    'node_name': chunk.metadata.get('node_name'),
                                                    'node_label': chunk.metadata.get('node_label'),
                                                    'node_metadata': chunk.metadata
                                                })
                                        
                                    elif chunk.type == "node_complete":
                                        # 发送节点完成事件，包含完整的chunk信息
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'node_complete', 'chunk_id': chunk.chunk_id, 'metadata': chunk.metadata}, ensure_ascii=False)}\n\n"
                                        yield data_chunk
                                        
                                        # 更新节点信息（如果有输出内容）
                                        if chunk.metadata and chunk.metadata.get('node_id'):
                                            existing_node = next((node for node in collected_nodes if node['node_id'] == chunk.metadata['node_id']), None)
                                            if existing_node and chunk.metadata.get('output'):
                                                existing_node['output'] = chunk.metadata.get('output')
                                    elif chunk.type == "content":
                                        # 发送内容块，包含metadata信息
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'content', 'chunk_id': chunk.chunk_id, 'metadata': chunk.metadata}, ensure_ascii=False)}\n\n"
                                        yield data_chunk
                                    elif chunk.type == "tool_result":
                                        # 发送工具执行结果
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'tool_result', 'tool_name': chunk.metadata.get('tool_name', ''), 'chunk_id': chunk.chunk_id, 'metadata': chunk.metadata}, ensure_ascii=False)}\n\n"
                                        yield data_chunk
                                        tools_used.append(chunk.metadata.get('tool_name', ''))
                                        try:
                                            tool_name = chunk.metadata.get('tool_name', '')
                                            content_str = chunk.content if isinstance(chunk.content, str) else json.dumps(chunk.content, ensure_ascii=False)
                                            live_follow_segments.append(f"[{tool_name}]\n{content_str}")
                                        except Exception:
                                            pass
                                        # 将工具执行记录保存到数据库
                                        if request.session_id:
                                            try:
                                                tool_message_data = MessageCreate(
                                                    session_id=request.session_id,
                                                    user_id=request.user_id,
                                                    message_type="tool",
                                                    content=chunk.content if isinstance(chunk.content, str) else json.dumps(chunk.content, ensure_ascii=False),
                                                    agent_name=agent.description or agent.name,
                                                    metadata={"tool_name": chunk.metadata.get('tool_name', '')}
                                                )
                                                MessageService.create_message(db, tool_message_data)
                                            except Exception as e:
                                                logger.warning(f"保存工具执行结果失败: {str(e)}")
                                    elif chunk.type == "tool_error":
                                        # 发送工具错误
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'tool_error', 'chunk_id': chunk.chunk_id, 'metadata': chunk.metadata}, ensure_ascii=False)}\n\n"
                                        yield data_chunk
                                    elif chunk.type == "final":
                                        # 发送最终响应
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'final_response', 'chunk_id': chunk.chunk_id, 'metadata': chunk.metadata}, ensure_ascii=False)}\n\n"
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

                                                # 保存节点信息（如果有的话）
                                                if hasattr(assistant_message, 'message_id') and assistant_message.message_id:
                                                    try:
                                                        # 保存所有收集到的节点信息
                                                        if collected_nodes:
                                                            from models.database_models import MessageNode
                                                            from sqlalchemy.orm import Session
                                                            
                                                            for node_info in collected_nodes:
                                                                # 创建节点记录
                                                                node_record = MessageNode(
                                                                    node_id=node_info['node_id'],
                                                                    message_id=assistant_message.message_id,
                                                                    node_type=node_info['node_type'],
                                                                    node_name=node_info['node_name'],
                                                                    node_label=node_info['node_label'],
                                                                    content=node_info.get('output', ''),  # 保存节点输出内容
                                                                    node_metadata={
                                                                        **node_info['node_metadata']
                                                                    }
                                                                )
                                                                
                                                                # 添加到数据库会话
                                                                db.add(node_record)
                                                            
                                                            # 提交所有节点记录
                                                            db.commit()
                                                            logger.info(f"成功保存 {len(collected_nodes)} 个节点信息，消息ID: {assistant_message.message_id}")
                                                        else:
                                                            logger.info(f"没有收集到节点信息，消息ID: {assistant_message.message_id}")
                                                    except Exception as e:
                                                        logger.warning(f"保存节点信息失败: {str(e)}")
                                                        # 回滚节点保存，但保持消息保存
                                                        db.rollback()
                                                
                                                # 保存实时跟随汇总（若存在则更新）
                                                try:
                                                    if live_follow_segments:
                                                        summary_text = "\n\n".join(live_follow_segments)
                                                        MessageService.upsert_workspace_summary(
                                                            db=db,
                                                            session_uuid=request.session_id,
                                                            user_id=request.user_id,
                                                            content=summary_text,
                                                            agent_name=agent.description or agent.name,
                                                            metadata={"tools_used": tools_used, "source": "stream"}
                                                        )
                                                except Exception as e:
                                                    logger.warning(f"保存实时跟随汇总失败: {str(e)}")
                                                
                                                logger.info(f"保存流式聊天消息: 用户消息ID={user_message.message_id}, 助手消息ID={assistant_message.message_id}")
                                            except Exception as e:
                                                logger.warning(f"保存流式聊天消息失败: {str(e)}")
                                        
                                        # 发送完成信号
                                        yield f"data: {json.dumps({'type': 'done', 'tools_used': tools_used}, ensure_ascii=False)}\n\n"
                                        break
                                    elif chunk.type == "error":
                                        # 发送错误消息
                                        data_chunk = f"data: {json.dumps({'content': chunk.content, 'type': 'error', 'chunk_id': chunk.chunk_id, 'metadata': chunk.metadata}, ensure_ascii=False)}\n\n"
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
                                from utils.llm_helper import LLMHelper
                                llm_helper = LLMHelper()
                                
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
                        logger.info(f"未找到智能体: {request.agent_name}，将直接调用LLM")
                        # 如果没有找到智能体，直接调用LLM
                        try:
                            from utils.llm_helper import LLMHelper
                            llm_helper = LLMHelper()
                            
                            # 构建消息
                            messages = [{"role": "user", "content": request.message}]
                            
                            # 流式调用LLM
                            async for chunk in llm_helper.call_stream(messages):
                                if chunk:
                                    data_chunk = f"data: {json.dumps({'content': chunk, 'type': 'content'}, ensure_ascii=False)}\n\n"
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
                                        agent_name="AI助手"
                                    )
                                    user_message = MessageService.create_message(db, user_message_data)
                                    
                                    # 保存助手回复（这里需要获取完整内容，暂时跳过）
                                    logger.info(f"保存用户消息: 用户消息ID={user_message.message_id}")
                                except Exception as e:
                                    logger.warning(f"保存用户消息失败: {str(e)}")
                            
                            yield f"data: {json.dumps({'type': 'done', 'tools_used': []}, ensure_ascii=False)}\n\n"
                            
                        except Exception as llm_error:
                            logger.error(f"直接调用LLM失败: {str(llm_error)}")
                            error_message = f"抱歉，AI处理消息时出现错误: {str(llm_error)}"
                            yield f"data: {json.dumps({'content': error_message, 'type': 'error'}, ensure_ascii=False)}\n\n"
                            yield f"data: {json.dumps({'type': 'done', 'tools_used': []}, ensure_ascii=False)}\n\n"
                else:
                    logger.info("智能体管理器未初始化，将直接调用LLM")
                    # 如果智能体管理器未初始化，直接调用LLM
                    try:
                        from utils.llm_helper import LLMHelper
                        llm_helper = LLMHelper()
                        
                        # 构建消息
                        messages = [{"role": "user", "content": request.message}]
                        
                        # 流式调用LLM
                        async for chunk in llm_helper.call_stream(messages):
                            if chunk:
                                data_chunk = f"data: {json.dumps({'content': chunk, 'type': 'content'}, ensure_ascii=False)}\n\n"
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
                                    agent_name="AI助手"
                                )
                                user_message = MessageService.create_message(db, user_message_data)
                                
                                logger.info(f"保存用户消息: 用户消息ID={user_message.message_id}")
                            except Exception as e:
                                logger.warning(f"保存用户消息失败: {str(e)}")
                        
                        yield f"data: {json.dumps({'type': 'done', 'tools_used': []}, ensure_ascii=False)}\n\n"
                        
                    except Exception as llm_error:
                        logger.error(f"直接调用LLM失败: {str(llm_error)}")
                        error_message = f"抱歉，AI处理消息时出现错误: {str(llm_error)}"
                        yield f"data: {json.dumps({'content': error_message, 'type': 'error'}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'type': 'done', 'tools_used': []}, ensure_ascii=False)}\n\n"
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

@router.get("/sessions/{user_id}")
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
        from services.session_service import MessageService
        messages = MessageService.get_session_messages(db, int(session_id))
        
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

@router.get("/sessions/{user_id}")
async def get_user_sessions_legacy(user_id: str, db: Session = Depends(get_db)):
    """获取用户的会话列表（兼容性端点）"""
    try:
        sessions = SessionService.get_user_sessions(db, user_id)
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