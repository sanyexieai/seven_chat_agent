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
                            
                            # 获取智能体的完整信息，包括绑定的工具
                            agent_info = None
                            try:
                                from services.agent_service import AgentService
                                agent_service = AgentService()
                                agent_info = agent_service.get_agent_by_name(db, agent.name)
                            except Exception as e:
                                logger.warning(f"获取智能体信息失败: {str(e)}")
                            
                            # 构建增强的系统提示词，包含工具信息
                            system_prompt = ""
                            if hasattr(agent, 'system_prompt') and agent.system_prompt:
                                system_prompt = agent.system_prompt
                            
                            # 如果有绑定的工具，添加到系统提示词中
                            if agent_info and agent_info.bound_tools:
                                tools_description = "\n\n你可以使用以下工具：\n"
                                for tool_name in agent_info.bound_tools:
                                    tools_description += f"- {tool_name}\n"
                                tools_description += "\n\n当需要使用工具时，请使用以下格式：\n"
                                tools_description += "TOOL_CALL: <工具名称> <参数>\n"
                                tools_description += "例如：TOOL_CALL: news_search query=商汤科技\n"
                                tools_description += "我会自动执行工具调用并返回结果。"
                                system_prompt += tools_description
                                logger.info(f"智能体 {agent.name} 绑定了 {len(agent_info.bound_tools)} 个工具")
                            
                            # 构建消息格式，包含聊天上下文
                            messages = []
                            if system_prompt:
                                messages.append({"role": "system", "content": system_prompt})
                            
                            # 加载聊天上下文
                            if request.session_id:
                                try:
                                    # 获取会话历史消息
                                    message_service = MessageService(db)
                                    session_messages = message_service.get_session_messages(request.session_id)
                                    
                                    # 添加历史消息到上下文（限制最近10条，避免token过多）
                                    context_messages = session_messages[-10:] if len(session_messages) > 10 else session_messages
                                    for msg in context_messages:
                                        if msg.message_type == "user":
                                            messages.append({"role": "user", "content": msg.content})
                                        elif msg.message_type == "assistant":
                                            messages.append({"role": "assistant", "content": msg.content})
                                    
                                    logger.info(f"加载了 {len(context_messages)} 条历史消息作为上下文")
                                except Exception as e:
                                    logger.warning(f"加载聊天上下文失败: {str(e)}")
                            
                            # 添加当前用户消息
                            messages.append({"role": "user", "content": request.message})
                            
                            logger.info(f"非流式端点尝试流式LLM调用，智能体: {agent.name}, 工具数量: {len(agent_info.bound_tools) if agent_info and agent_info.bound_tools else 0}")
                            
                            # 收集流式响应
                            full_response = ""
                            async for chunk in llm_helper.call_stream(messages):
                                if chunk:
                                    full_response += chunk
                            
                            if full_response:
                                response_message = full_response
                                logger.info(f"流式LLM调用成功，响应长度: {len(full_response)}")
                                
                                # 检查是否需要工具调用
                                if agent_info and agent_info.bound_tools and "TOOL_CALL:" in full_response:
                                    logger.info("检测到工具调用指令，开始执行工具")
                                    
                                    # 解析工具调用指令
                                    tool_calls = []
                                    lines = full_response.split('\n')
                                    for line in lines:
                                        if line.strip().startswith('TOOL_CALL:'):
                                            tool_call = line.strip().replace('TOOL_CALL:', '').strip()
                                            tool_calls.append(tool_call)
                                    
                                    logger.info(f"解析到 {len(tool_calls)} 个工具调用: {tool_calls}")
                                    
                                    # 执行工具调用
                                    for tool_call in tool_calls:
                                        try:
                                            # 解析工具名称和参数
                                            parts = tool_call.split(' ', 1)
                                            if len(parts) >= 2:
                                                tool_name = parts[0].strip()
                                                tool_params = parts[1].strip()
                                                
                                                # 检查工具是否在绑定列表中
                                                if tool_name in agent_info.bound_tools:
                                                    logger.info(f"执行工具调用: {tool_name} 参数: {tool_params}")
                                                    
                                                                                                    # 调用实际的MCP工具
                                                try:
                                                    from main import agent_manager
                                                    if agent_manager and hasattr(agent_manager, 'mcp_helper'):
                                                        # 解析参数
                                                        params = {}
                                                        if '=' in tool_params:
                                                            for param in tool_params.split():
                                                                if '=' in param:
                                                                    key, value = param.split('=', 1)
                                                                    params[key.strip()] = value.strip()
                                                        else:
                                                            # 如果没有=，假设是查询参数
                                                            params['query'] = tool_params
                                                        
                                                        logger.info(f"调用MCP工具 {tool_name}，参数: {params}")
                                                        
                                                        # 这里应该调用MCP工具
                                                        # 暂时返回模拟结果，后续需要集成真正的MCP调用
                                                        tool_result = f"工具 {tool_name} 执行结果: 模拟执行参数 '{params}' 的结果"
                                                    else:
                                                        tool_result = f"工具 {tool_name} 执行结果: 模拟执行参数 '{tool_params}' 的结果"
                                                except Exception as mcp_error:
                                                    logger.error(f"MCP工具调用失败: {str(mcp_error)}")
                                                    tool_result = f"工具 {tool_name} 执行失败: {str(mcp_error)}"
                                                    
                                                    # 将工具结果添加到响应中
                                                    response_message += f"\n\n{tool_result}"
                                                    tools_used.append(tool_name)
                                                else:
                                                    logger.warning(f"工具 {tool_name} 不在绑定列表中")
                                                    response_message += f"\n\n警告: 工具 {tool_name} 未绑定，无法执行"
                                            else:
                                                logger.warning(f"工具调用格式不正确: {tool_call}")
                                        except Exception as tool_error:
                                            logger.error(f"执行工具调用失败: {str(tool_error)}")
                                            response_message += f"\n\n工具执行失败: {str(tool_error)}"
                            else:
                                logger.warning("流式LLM调用返回空内容")
                                
                        except Exception as llm_error:
                            logger.error(f"非流式端点流式LLM调用失败: {str(llm_error)}")
                            # 保持原有的模拟响应
                    
                    # 保存聊天消息到数据库
                    if request.session_id:
                        try:
                            from datetime import datetime
                            message_service = MessageService(db)
                            
                            # 保存用户消息
                            user_message = message_service.create_message(
                                session_id=request.session_id,
                                user_id=request.user_id,
                                message_type="user",
                                content=request.message,
                                agent_name=agent.description or agent.name
                            )
                            
                            # 保存助手回复
                            assistant_message = message_service.create_message(
                                session_id=request.session_id,
                                user_id=request.user_id,
                                message_type="assistant",
                                content=response_message,
                                agent_name=agent.description or agent.name,
                                metadata={"tools_used": tools_used}
                            )
                            
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
                        
                        # 直接使用真正的流式LLM调用（不要先走非流式调用，否则会阻塞首字节）
                        tools_used = []
                        try:
                            from utils.llm_helper import get_llm_helper
                            llm_helper = get_llm_helper()
                            
                            # 获取智能体的完整信息，包括绑定的工具
                            agent_info = None
                            try:
                                from services.agent_service import AgentService
                                agent_service = AgentService()
                                agent_info = agent_service.get_agent_by_name(db, agent.name)
                            except Exception as e:
                                logger.warning(f"获取智能体信息失败: {str(e)}")
                            
                            # 构建增强的系统提示词，包含工具信息
                            system_prompt = ""
                            if hasattr(agent, 'system_prompt') and agent.system_prompt:
                                system_prompt = agent.system_prompt
                            
                            # 如果有绑定的工具，添加到系统提示词中
                            if agent_info and agent_info.bound_tools:
                                tools_description = "\n\n你可以使用以下工具：\n"
                                for tool_name in agent_info.bound_tools:
                                    tools_description += f"- {tool_name}\n"
                                tools_description += "\n\n当需要使用工具时，请使用以下格式：\n"
                                tools_description += "TOOL_CALL: <工具名称> <参数>\n"
                                tools_description += "例如：TOOL_CALL: news_search query=商汤科技\n"
                                tools_description += "我会自动执行工具调用并返回结果。"
                                system_prompt += tools_description
                                logger.info(f"智能体 {agent.name} 绑定了 {len(agent_info.bound_tools)} 个工具")
                            
                            # 构建消息格式，包含聊天上下文
                            messages = []
                            if system_prompt:
                                messages.append({"role": "system", "content": system_prompt})
                            
                            # 加载聊天上下文
                            if request.session_id:
                                try:
                                    # 获取会话历史消息
                                    message_service = MessageService(db)
                                    session_messages = message_service.get_session_messages(request.session_id)
                                    
                                    # 添加历史消息到上下文（限制最近10条，避免token过多）
                                    context_messages = session_messages[-10:] if len(session_messages) > 10 else session_messages
                                    for msg in context_messages:
                                        if msg.message_type == "user":
                                            messages.append({"role": "user", "content": msg.content})
                                        elif msg.message_type == "assistant":
                                            messages.append({"role": "assistant", "content": msg.content})
                                    
                                    logger.info(f"加载了 {len(context_messages)} 条历史消息作为上下文")
                                except Exception as e:
                                    logger.warning(f"加载聊天上下文失败: {str(e)}")
                            
                            # 添加当前用户消息
                            messages.append({"role": "user", "content": request.message})
                            
                            logger.info(f"开始流式LLM调用，智能体: {agent.name}, 工具数量: {len(agent_info.bound_tools) if agent_info and agent_info.bound_tools else 0}")
                            
                            # 流式调用LLM
                            chunk_count = 0
                            full_response = ""
                            async for chunk in llm_helper.call_stream(messages):
                                if chunk:
                                    chunk_count += 1
                                    full_response += chunk
                                    logger.info(f"流式返回第{chunk_count}个内容块: {chunk}")
                                    data_chunk = f"data: {json.dumps({'content': chunk, 'type': 'content'}, ensure_ascii=False)}\n\n"
                                    yield data_chunk
                                    # 强制刷新缓冲区，确保数据立即发送
                                    import asyncio
                                    await asyncio.sleep(0)  # 让出控制权，允许数据发送
                                    logger.info(f"已发送第{chunk_count}个内容块")
                            
                            # 检查是否需要工具调用
                            if agent_info and agent_info.bound_tools and "TOOL_CALL:" in full_response:
                                logger.info("检测到工具调用指令，开始执行工具")
                                
                                # 解析工具调用指令
                                tool_calls = []
                                lines = full_response.split('\n')
                                for line in lines:
                                    if line.strip().startswith('TOOL_CALL:'):
                                        tool_call = line.strip().replace('TOOL_CALL:', '').strip()
                                        tool_calls.append(tool_call)
                                
                                logger.info(f"解析到 {len(tool_calls)} 个工具调用: {tool_calls}")
                                
                                # 执行工具调用
                                for tool_call in tool_calls:
                                    try:
                                        # 解析工具名称和参数
                                        parts = tool_call.split(' ', 1)
                                        if len(parts) >= 2:
                                            tool_name = parts[0].strip()
                                            tool_params = parts[1].strip()
                                            
                                            # 检查工具是否在绑定列表中
                                            if tool_name in agent_info.bound_tools:
                                                logger.info(f"执行工具调用: {tool_name} 参数: {tool_params}")
                                                
                                                # 调用实际的MCP工具
                                                try:
                                                    from main import agent_manager
                                                    if agent_manager and hasattr(agent_manager, 'mcp_helper'):
                                                        # 解析参数
                                                        params = {}
                                                        if '=' in tool_params:
                                                            for param in tool_params.split():
                                                                if '=' in param:
                                                                    key, value = param.split('=', 1)
                                                                    params[key.strip()] = value.strip()
                                                        else:
                                                            # 如果没有=，假设是查询参数
                                                            params['query'] = tool_params
                                                        
                                                        logger.info(f"调用MCP工具 {tool_name}，参数: {params}")
                                                        
                                                        # 这里应该调用MCP工具
                                                        # 暂时返回模拟结果，后续需要集成真正的MCP调用
                                                        tool_result = f"工具 {tool_name} 执行结果: 模拟执行参数 '{params}' 的结果"
                                                    else:
                                                        tool_result = f"工具 {tool_name} 执行结果: 模拟执行参数 '{tool_params}' 的结果"
                                                except Exception as mcp_error:
                                                    logger.error(f"MCP工具调用失败: {str(mcp_error)}")
                                                    tool_result = f"工具 {tool_name} 执行失败: {str(mcp_error)}"
                                                
                                                # 发送工具执行结果
                                                yield f"data: {json.dumps({'content': f'\n\n{tool_result}', 'type': 'tool_result'}, ensure_ascii=False)}\n\n"
                                                tools_used.append(tool_name)
                                                
                                                # 让出控制权
                                                await asyncio.sleep(0)
                                            else:
                                                logger.warning(f"工具 {tool_name} 不在绑定列表中")
                                                yield f"data: {json.dumps({'content': f'\n\n警告: 工具 {tool_name} 未绑定，无法执行', 'type': 'tool_warning'}, ensure_ascii=False)}\n\n"
                                        else:
                                            logger.warning(f"工具调用格式不正确: {tool_call}")
                                    except Exception as tool_error:
                                        logger.error(f"执行工具调用失败: {str(tool_error)}")
                                        yield f"data: {json.dumps({'content': f'\n\n工具执行失败: {str(tool_error)}', 'type': 'tool_error'}, ensure_ascii=False)}\n\n"
                            
                            logger.info(f"流式调用完成，共发送{chunk_count}个内容块，使用工具: {tools_used}")
                            
                            # 保存聊天消息到数据库
                            if request.session_id:
                                try:
                                    from datetime import datetime
                                    message_service = MessageService(db)
                                    
                                    # 保存用户消息
                                    user_message = message_service.create_message(
                                        session_id=request.session_id,
                                        user_id=request.user_id,
                                        message_type="user",
                                        content=request.message,
                                        agent_name=agent.description or agent.name
                                    )
                                    
                                    # 保存助手回复（包含工具执行结果）
                                    final_response = full_response
                                    if tools_used:
                                        final_response += f"\n\n使用的工具: {', '.join(tools_used)}"
                                    
                                    assistant_message = message_service.create_message(
                                        session_id=request.session_id,
                                        user_id=request.user_id,
                                        message_type="assistant",
                                        content=final_response,
                                        agent_name=agent.description or agent.name,
                                        metadata={"tools_used": tools_used}
                                    )
                                    
                                    logger.info(f"保存流式聊天消息: 用户消息ID={user_message.message_id}, 助手消息ID={assistant_message.message_id}")
                                except Exception as e:
                                    logger.warning(f"保存流式聊天消息失败: {str(e)}")
                            
                            # 发送完成信号
                            yield f"data: {json.dumps({'type': 'done', 'tools_used': tools_used}, ensure_ascii=False)}\n\n"
                            
                        except Exception as llm_error:
                            logger.error(f"流式LLM调用失败: {str(llm_error)}")
                            # 回退到错误消息显示
                            error_message = f"抱歉，LLM调用失败: {str(llm_error)}"
                            for char in error_message:
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