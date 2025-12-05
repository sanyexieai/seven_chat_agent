"""记忆提炼服务：通过 LLM 从潜意识记忆中提取重点，存储为短期/长期记忆"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from models.database_models import MemoryRecord, MemoryRecordCreate
from services.memory_service import MemoryService
from utils.llm_helper import get_llm_helper
from utils.log_helper import get_logger
from agents.pipeline import Pipeline

logger = get_logger("memory_refinement")


class MemoryRefinementService:
    """记忆提炼服务
    
    职责：
    - 从潜意识记忆（subconscious）中提取重点信息
    - 通过 LLM 分析并分类为短期记忆（short_term）或长期记忆（long_term）
    - 将提炼后的记忆存储到数据库
    """
    
    def __init__(self):
        self.memory_service = MemoryService()
        self.llm_helper = get_llm_helper()
    
    async def refine_memories(
        self,
        db: Session,
        user_id: str,
        agent_name: str,
        session_id: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """从潜意识记忆中提取重点，并存储为短期/长期记忆
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            agent_name: 智能体名称
            session_id: 会话ID（可选，如果提供则只处理该会话的记忆）
            limit: 每次处理的潜意识记忆数量
            
        Returns:
            提炼结果统计
        """
        try:
            # 1) 直接查询未提炼的潜意识记忆（不依赖向量搜索）
            from models.database_models import MemoryRecord
            q = db.query(MemoryRecord).filter(
                MemoryRecord.is_active == True,
                MemoryRecord.memory_type == Pipeline.MEMORY_TYPE_SUBCONSCIOUS,
                MemoryRecord.user_id == user_id,
                MemoryRecord.agent_name == agent_name,
            )
            if session_id:
                q = q.filter(MemoryRecord.session_id == session_id)
            
            # 排除已经提炼过的（source 不是 "refined_from_subconscious"）
            # 按创建时间倒序，取最新的 limit 条
            records = q.order_by(MemoryRecord.created_at.desc()).limit(limit).all()
            
            subconscious_memories = []
            for r in records:
                subconscious_memories.append({
                    "id": r.id,
                    "user_id": r.user_id,
                    "agent_name": r.agent_name,
                    "session_id": r.session_id,
                    "memory_type": r.memory_type,
                    "category": r.category,
                    "source": r.source,
                    "content": r.content,
                    "metadata": r.memory_metadata or {},
                    "created_at": r.created_at,
                })
            
            if not subconscious_memories:
                return {
                    "processed": 0,
                    "short_term_created": 0,
                    "long_term_created": 0,
                    "errors": 0,
                }
            
            # 2) 批量提取重点
            refined_count = 0
            short_term_count = 0
            long_term_count = 0
            error_count = 0
            
            for memory in subconscious_memories:
                try:
                    result = await self._extract_key_points(
                        content=memory.get("content", ""),
                        metadata=memory.get("metadata", {}),
                    )
                    
                    if result:
                        # 根据重要性分类存储
                        for point in result.get("key_points", []):
                            importance = point.get("importance", "medium")
                            content = point.get("content", "")
                            category = point.get("category", "extracted")
                            
                            if importance in ["high", "critical"]:
                                # 长期记忆：重要信息
                                target_type = Pipeline.MEMORY_TYPE_LONG_TERM
                                long_term_count += 1
                            else:
                                # 短期记忆：一般信息
                                target_type = Pipeline.MEMORY_TYPE_SHORT_TERM
                                short_term_count += 1
                            
                            # 创建提炼后的记忆
                            refined_record = MemoryRecordCreate(
                                user_id=user_id,
                                agent_name=agent_name,
                                session_id=session_id or memory.get("session_id"),
                                memory_type=target_type,
                                category=category,
                                source="refined_from_subconscious",
                                content=content,
                                metadata={
                                    "original_memory_id": memory.get("id"),
                                    "importance": importance,
                                    "extracted_at": datetime.utcnow().isoformat(),
                                },
                            )
                            self.memory_service.create_memory(
                                db=db,
                                data=refined_record,
                                auto_embed=True,
                            )
                        
                        refined_count += 1
                except Exception as e:
                    logger.error(f"提炼记忆失败 (memory_id={memory.get('id')}): {e}")
                    error_count += 1
            
            return {
                "processed": refined_count,
                "short_term_created": short_term_count,
                "long_term_created": long_term_count,
                "errors": error_count,
            }
        except Exception as e:
            logger.error(f"记忆提炼过程失败: {e}")
            return {
                "processed": 0,
                "short_term_created": 0,
                "long_term_created": 0,
                "errors": 1,
            }
    
    async def _extract_key_points(
        self,
        content: str,
        metadata: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """使用 LLM 从内容中提取关键点
        
        Returns:
            {
                "key_points": [
                    {
                        "content": "提取的关键信息",
                        "importance": "high|medium|low",
                        "category": "fact|preference|task|other"
                    }
                ]
            }
        """
        if not content or len(content.strip()) < 10:
            return None
        
        try:
            system_prompt = """你是一个记忆提炼专家。你的任务是从对话内容中提取关键信息。

提取规则：
1. 提取用户的重要偏好、习惯、需求
2. 提取重要的事实、数据、时间信息
3. 提取待办事项、任务、承诺
4. 忽略无关的闲聊、重复信息
5. 对每个关键点评估重要性：critical（关键）、high（高）、medium（中）、low（低）

输出格式（JSON）：
{
    "key_points": [
        {
            "content": "提取的关键信息（简洁明确）",
            "importance": "critical|high|medium|low",
            "category": "fact|preference|task|other"
        }
    ]
}"""
            
            user_prompt = f"""请从以下对话内容中提取关键信息：

内容：
{content}

元数据：
{metadata}

请返回 JSON 格式的关键点列表。"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            
            response = await self.llm_helper.call(
                messages=messages,
                temperature=0.3,  # 较低温度，确保输出稳定
            )
            
            # 解析 JSON 响应
            import json
            import re
            
            # 尝试提取 JSON 部分
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                return result
            else:
                # 如果无法解析，返回简单格式
                return {
                    "key_points": [
                        {
                            "content": response[:200],  # 截取前200字符
                            "importance": "medium",
                            "category": "other",
                        }
                    ]
                }
        except Exception as e:
            logger.error(f"LLM 提取关键点失败: {e}")
            return None

