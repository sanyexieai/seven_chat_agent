import json
from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from services.knowledge_base_service import KnowledgeBaseService
from utils.log_helper import get_logger

logger = get_logger("knowledge_base_agent")

class KnowledgeBaseAgent(BaseAgent):
    """知识库智能体"""
    
    def __init__(self, name: str = "knowledge_base_agent", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.kb_service = KnowledgeBaseService()
        self.system_prompt = """你是一个知识库查询助手。你的任务是：
1. 理解用户的查询意图
2. 从知识库中检索相关信息
3. 基于检索到的信息生成准确、有用的回答
4. 如果知识库中没有相关信息，要诚实地说明

请始终保持专业、准确和有用的回答。"""
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """处理用户消息"""
        try:
            logger.info(f"知识库智能体处理消息: {message}")
            
            # 从上下文中获取知识库ID
            kb_id = context.get("knowledge_base_id") if context else None
            
            if not kb_id:
                return {
                    "content": "请指定要查询的知识库ID。",
                    "agent_name": self.name,
                    "success": False
                }
            
            # 查询知识库
            from database.database import SessionLocal
            db = SessionLocal()
            try:
                result = self.kb_service.query_knowledge_base(
                    db, kb_id, message, user_id, max_results=5
                )
                
                # 构建响应
                response_content = self._format_response(result)
                
                return {
                    "content": response_content,
                    "agent_name": self.name,
                    "success": True,
                    "metadata": {
                        "knowledge_base_id": kb_id,
                        "sources": result.get("sources", []),
                        "query": message
                    }
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"知识库智能体处理消息失败: {str(e)}")
            return {
                "content": f"查询知识库时出错: {str(e)}",
                "agent_name": self.name,
                "success": False
            }
    
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None):
        """流式处理用户消息"""
        try:
            logger.info(f"知识库智能体流式处理消息: {message}")
            
            # 从上下文中获取知识库ID
            kb_id = context.get("knowledge_base_id") if context else None
            
            if not kb_id:
                yield {
                    "type": "content",
                    "content": "请指定要查询的知识库ID。",
                    "agent_name": self.name
                }
                return
            
            # 查询知识库
            from database.database import SessionLocal
            db = SessionLocal()
            try:
                result = self.kb_service.query_knowledge_base(
                    db, kb_id, message, user_id, max_results=5
                )
                
                # 流式返回响应
                response_content = self._format_response(result)
                
                # 分段返回内容
                chunks = self._split_response_into_chunks(response_content)
                for chunk in chunks:
                    yield {
                        "type": "content",
                        "content": chunk,
                        "agent_name": self.name
                    }
                
                # 返回元数据
                yield {
                    "type": "metadata",
                    "metadata": {
                        "knowledge_base_id": kb_id,
                        "sources": result.get("sources", []),
                        "query": message
                    }
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"知识库智能体流式处理消息失败: {str(e)}")
            yield {
                "type": "error",
                "content": f"查询知识库时出错: {str(e)}",
                "agent_name": self.name
            }
    
    def _format_response(self, result: Dict[str, Any]) -> str:
        """格式化响应"""
        query = result.get("query", "")
        response = result.get("response", "")
        sources = result.get("sources", [])
        
        formatted_response = f"查询: {query}\n\n"
        formatted_response += f"回答: {response}\n\n"
        
        if sources:
            formatted_response += "来源文档:\n"
            for i, source in enumerate(sources[:3], 1):  # 只显示前3个来源
                content_preview = source.get("content", "")[:100]
                similarity = source.get("similarity", 0)
                formatted_response += f"{i}. 相似度: {similarity:.2f} - {content_preview}...\n"
        
        return formatted_response
    
    def _split_response_into_chunks(self, response: str, chunk_size: int = 100) -> List[str]:
        """将响应分割成块"""
        chunks = []
        for i in range(0, len(response), chunk_size):
            chunks.append(response[i:i + chunk_size])
        return chunks
    
    def get_available_actions(self) -> List[str]:
        """获取可用的操作"""
        return [
            "query_knowledge_base",
            "list_knowledge_bases",
            "get_document_info"
        ]
    
    def get_capabilities(self) -> Dict[str, Any]:
        """获取智能体能力"""
        return {
            "name": self.name,
            "type": "knowledge_base",
            "description": "知识库查询智能体，可以查询和检索知识库中的信息",
            "capabilities": [
                "知识库查询",
                "文档检索",
                "相似度匹配",
                "上下文理解"
            ]
        } 