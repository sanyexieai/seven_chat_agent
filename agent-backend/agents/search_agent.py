from typing import Dict, Any, AsyncGenerator, List
from agents.base_agent import BaseAgent
from models.chat_models import AgentMessage, StreamChunk, MessageType
from tools.search_tools import WebSearchTool, DocumentSearchTool
from utils.log_helper import get_logger

# 获取logger实例
logger = get_logger("search_agent")
from utils.llm_helper import get_llm_helper
from utils.mcp_helper import get_mcp_helper
import asyncio
import json

class SearchAgent(BaseAgent):
    """搜索智能体"""
    
    def __init__(self, name: str, description: str):
        super().__init__(name, description)
        self.system_prompt = """你是一个专业的搜索和信息检索智能体。
你的任务是帮助用户搜索和获取准确的信息。请根据用户的需求选择合适的搜索工具，
并提供清晰、准确的信息摘要。"""
        
        # 初始化工具
        self.add_tool(WebSearchTool())
        self.add_tool(DocumentSearchTool())
        
        # 初始化LLM助手
        try:
            self.llm_helper = get_llm_helper()
            logger.info(f"搜索智能体 {name} 初始化成功，LLM已就绪")
        except Exception as e:
            logger.warning(f"LLM初始化失败，将使用备用响应模式: {str(e)}")
            self.llm_helper = None
        
        # 初始化MCP助手
        try:
            self.mcp_helper = get_mcp_helper()
            logger.info(f"搜索智能体 {name} MCP助手初始化成功")
        except Exception as e:
            logger.warning(f"MCP助手初始化失败: {str(e)}")
            self.mcp_helper = None
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        try:
            # 分析搜索意图
            search_intent = await self._analyze_search_intent(message)
            logger.info(f"搜索意图分析: {search_intent}")
            
            # 提取关键词
            keywords = self._extract_keywords(message, search_intent)
            logger.info(f"提取关键词: {keywords}")
            
            # 执行搜索
            search_results = await self._perform_search(keywords, search_intent)
            
            # 生成响应
            response_content = await self._generate_search_response(message, search_results, search_intent)
            
            # 创建响应消息
            response = self.create_message(
                content=response_content,
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
            
            logger.info(f"搜索智能体处理完成，用户: {user_id}")
            return response
            
        except Exception as e:
            logger.error(f"搜索智能体处理消息失败: {str(e)}")
            return self.create_message(
                content=f"抱歉，搜索过程中出现了问题: {str(e)}",
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
    
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息"""
        try:
            # 分析搜索意图
            search_intent = await self._analyze_search_intent(message)
            
            # 提取关键词
            keywords = self._extract_keywords(message, search_intent)
            
            # 执行搜索
            search_results = await self._perform_search(keywords, search_intent)
            
            # 流式生成响应
            async for chunk in self._generate_search_response_stream(message, search_results, search_intent):
                yield chunk
                
        except Exception as e:
            logger.error(f"搜索智能体流式处理消息失败: {str(e)}")
            yield StreamChunk(
                type="error",
                content=f"搜索过程中出现了问题: {str(e)}",
                agent_name=self.name
            )
    
    async def _analyze_search_intent(self, message: str) -> Dict[str, Any]:
        """分析搜索意图"""
        try:
            if self.llm_helper:
                # 使用LLM分析搜索意图
                prompt = f"""请分析以下用户的搜索意图，返回JSON格式：
用户消息: {message}

请分析：
1. 搜索类型（web_search/document_search/general）
2. 搜索主题
3. 是否需要实时信息
4. 搜索范围

返回格式：
{{
    "search_type": "web_search",
    "topic": "搜索主题",
    "need_realtime": true,
    "scope": "搜索范围",
    "confidence": 0.9
}}"""
                
                response = self.llm_helper.call(prompt)
                try:
                    return json.loads(response)
                except:
                    pass
            
            # 备用分析逻辑
            message_lower = message.lower()
            if any(word in message_lower for word in ["新闻", "最新", "实时", "今天", "现在"]):
                return {
                    "search_type": "web_search",
                    "topic": "实时信息",
                    "need_realtime": True,
                    "scope": "general",
                    "confidence": 0.8
                }
            elif any(word in message_lower for word in ["文档", "文件", "资料", "报告"]):
                return {
                    "search_type": "document_search",
                    "topic": "文档资料",
                    "need_realtime": False,
                    "scope": "documents",
                    "confidence": 0.7
                }
            else:
                return {
                    "search_type": "web_search",
                    "topic": "一般信息",
                    "need_realtime": False,
                    "scope": "general",
                    "confidence": 0.6
                }
                
        except Exception as e:
            logger.error(f"搜索意图分析失败: {str(e)}")
            return {
                "search_type": "web_search",
                "topic": "一般信息",
                "need_realtime": False,
                "scope": "general",
                "confidence": 0.5
            }
    
    def _extract_keywords(self, message: str, search_intent: Dict[str, Any]) -> List[str]:
        """提取搜索关键词"""
        try:
            if self.llm_helper:
                # 使用LLM提取关键词
                prompt = f"""请从以下用户消息中提取搜索关键词：
用户消息: {message}
搜索类型: {search_intent.get('search_type', 'web_search')}

请返回关键词列表，用逗号分隔："""
                
                response = self.llm_helper.call(prompt)
                keywords = [kw.strip() for kw in response.split(',') if kw.strip()]
                if keywords:
                    return keywords
            
            # 备用关键词提取
            # 简单的分词逻辑
            import re
            words = re.findall(r'[\u4e00-\u9fa5a-zA-Z]+', message)
            # 过滤掉常见的停用词
            stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
            keywords = [word for word in words if word not in stop_words and len(word) > 1]
            
            return keywords[:5]  # 最多返回5个关键词
            
        except Exception as e:
            logger.error(f"关键词提取失败: {str(e)}")
            return [message]
    
    async def _perform_search(self, keywords: List[str], search_intent: Dict[str, Any]) -> Dict[str, Any]:
        """执行搜索"""
        try:
            search_type = search_intent.get('search_type', 'web_search')
            results = {}
            
            if search_type == 'web_search':
                # 使用网络搜索工具
                web_search_tool = next((tool for tool in self.tools if tool.name == 'web_search'), None)
                if web_search_tool:
                    search_query = ' '.join(keywords)
                    results['web_search'] = await web_search_tool.execute({
                        'query': search_query,
                        'keywords': keywords
                    })
            
            elif search_type == 'document_search':
                # 使用文档搜索工具
                doc_search_tool = next((tool for tool in self.tools if tool.name == 'document_search'), None)
                if doc_search_tool:
                    results['document_search'] = await doc_search_tool.execute({
                        'query': ' '.join(keywords),
                        'keywords': keywords
                    })
            
            # 尝试使用MCP工具
            if self.mcp_helper:
                try:
                    mcp_tools = await self.mcp_helper.get_tools()
                    for tool in mcp_tools:
                        if 'search' in tool.get('name', '').lower():
                            # 使用MCP搜索工具
                            mcp_result = await self.mcp_helper.call_tool(
                                server_name=tool.get('server_name', ''),
                                tool_name=tool.get('name', ''),
                                query=' '.join(keywords)
                            )
                            results['mcp_search'] = mcp_result
                            break
                except Exception as e:
                    logger.warning(f"MCP搜索失败: {str(e)}")
            
            return results
            
        except Exception as e:
            logger.error(f"搜索执行失败: {str(e)}")
            return {'error': str(e)}
    
    async def _generate_search_response(self, message: str, search_results: Dict[str, Any], search_intent: Dict[str, Any]) -> str:
        """生成搜索响应"""
        try:
            if self.llm_helper:
                # 使用LLM生成响应
                prompt = f"""基于以下搜索结果，为用户生成一个清晰、准确的回答：

用户问题: {message}
搜索意图: {search_intent}
搜索结果: {json.dumps(search_results, ensure_ascii=False, indent=2)}

请提供：
1. 直接回答用户问题
2. 基于搜索结果的信息
3. 如果有多个来源，请整合信息
4. 保持回答的准确性和可读性

回答："""
                
                response = self.llm_helper.call(prompt)
                return response.strip()
            
            # 备用响应生成
            return self._generate_fallback_search_response(message, search_results, search_intent)
            
        except Exception as e:
            logger.error(f"搜索响应生成失败: {str(e)}")
            return self._generate_fallback_search_response(message, search_results, search_intent)
    
    def _generate_fallback_search_response(self, message: str, search_results: Dict[str, Any], search_intent: Dict[str, Any]) -> str:
        """备用搜索响应生成"""
        if 'error' in search_results:
            return f"抱歉，搜索过程中遇到了问题：{search_results['error']}"
        
        if not search_results:
            return "抱歉，没有找到相关信息。请尝试使用不同的关键词或重新描述您的需求。"
        
        # 简单的响应生成
        response_parts = []
        response_parts.append(f"根据您的问题\"{message}\"，我为您搜索了相关信息：")
        
        for search_type, result in search_results.items():
            if search_type == 'web_search':
                response_parts.append("网络搜索结果：")
                response_parts.append(result[:200] + "..." if len(result) > 200 else result)
            elif search_type == 'document_search':
                response_parts.append("文档搜索结果：")
                response_parts.append(result[:200] + "..." if len(result) > 200 else result)
            elif search_type == 'mcp_search':
                response_parts.append("其他搜索结果：")
                response_parts.append(str(result)[:200] + "..." if len(str(result)) > 200 else str(result))
        
        return "\n\n".join(response_parts)
    
    async def _generate_search_response_stream(self, message: str, search_results: Dict[str, Any], search_intent: Dict[str, Any]) -> AsyncGenerator[StreamChunk, None]:
        """流式生成搜索响应"""
        try:
            # 生成完整响应
            full_response = await self._generate_search_response(message, search_results, search_intent)
            
            # 模拟流式输出
            words = full_response.split()
            for word in words:
                yield StreamChunk(
                    type="content",
                    content=word + " ",
                    agent_name=self.name
                )
                await asyncio.sleep(0.05)  # 模拟延迟
            
            # 发送完成信号
            yield StreamChunk(
                type="final",
                content="",
                agent_name=self.name
            )
            
        except Exception as e:
            logger.error(f"流式搜索响应生成失败: {str(e)}")
            yield StreamChunk(
                type="error",
                content=f"生成搜索响应时出现错误: {str(e)}",
                agent_name=self.name
            )
    
    def get_capabilities(self) -> Dict[str, Any]:
        """获取智能体能力"""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": [
                "网络搜索",
                "文档搜索",
                "信息整合",
                "智能分析",
                "多源搜索"
            ],
            "tools": self.get_available_tools(),
            "llm_available": self.llm_helper is not None,
            "mcp_available": self.mcp_helper is not None
        } 