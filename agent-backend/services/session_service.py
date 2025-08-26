from sqlalchemy.orm import Session
from typing import List, Optional
from models.database_models import UserSession, ChatMessage, SessionCreate, SessionResponse, MessageCreate, MessageResponse, MessageNode
from utils.log_helper import get_logger
import uuid
from datetime import datetime

logger = get_logger("session_service")

class SessionService:
    """会话服务"""
    
    @staticmethod
    def create_session(db: Session, session_data: SessionCreate) -> UserSession:
        """创建会话"""
        session_id = str(uuid.uuid4())
        session = UserSession(
            session_id=session_id,
            user_id=session_data.user_id,
            session_name=session_data.session_name,
            agent_id=session_data.agent_id,  # 现在可以为None
            is_active=True
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info(f"创建会话: {session_id}, 智能体: {session_data.agent_id or '未选择'}")
        return session
    
    @staticmethod
    def get_session_by_id(db: Session, session_id: int) -> Optional[UserSession]:
        """根据ID获取会话"""
        return db.query(UserSession).filter(
            UserSession.id == session_id,
            UserSession.is_active == True
        ).first()
    
    @staticmethod
    def get_user_sessions(db: Session, user_id: str) -> List[UserSession]:
        """获取用户的所有会话，按创建时间降序排列（最新的在最上面）"""
        return db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.is_active == True
        ).order_by(UserSession.created_at.desc()).all()
    
    @staticmethod
    def update_session_title(db: Session, session_id: int, title: str) -> Optional[UserSession]:
        """更新会话标题"""
        session = db.query(UserSession).filter(UserSession.id == session_id).first()
        if session:
            session.session_name = title  # 使用session_name字段
            db.commit()
            db.refresh(session)
            logger.info(f"更新会话标题: {session_id}")
            return session
        return None
    
    @staticmethod
    def delete_session(db: Session, session_id: int) -> bool:
        """删除会话"""
        session = db.query(UserSession).filter(UserSession.id == session_id).first()
        if session:
            session.is_active = False
            db.commit()
            logger.info(f"删除会话: {session_id}")
            return True
        return False

class MessageService:
    """消息服务"""
    
    @staticmethod
    def create_message(db: Session, message_data: MessageCreate) -> 'MessageResponse':
        """创建消息"""
        message_id = str(uuid.uuid4())
        message = ChatMessage(
            message_id=message_id,
            session_id=message_data.session_id,
            user_id=message_data.user_id,
            message_type=message_data.message_type,
            content=message_data.content,  # 保存消息内容
            agent_name=message_data.agent_name,
            message_metadata=message_data.metadata
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        logger.info(f"创建消息: {message_id}")
        
        # 返回Pydantic模型而不是数据库模型
        from models.database_models import MessageResponse
        return MessageResponse(
            id=message.id,
            message_id=message.message_id,
            session_id=message.session_id,
            user_id=message.user_id,
            message_type=message.message_type,
            content=message_data.content,  # 使用传入的内容
            agent_name=message.agent_name,
            metadata=message.message_metadata,
            created_at=message.created_at
        )
    
    @staticmethod
    def get_session_messages(db: Session, session_id: int, limit: int = 100) -> List['MessageResponse']:
        """获取会话的最近消息（优先包含最新的workspace_summary等）"""
        logger.info(f"🔍 开始查询会话消息: session_id={session_id}, limit={limit}")
        
        # 先按时间倒序获取更多条数，再过滤软删，然后取前limit条并升序返回
        recent = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at.desc()).limit(limit * 2).all()
        
        logger.info(f"🔍 数据库查询结果: 找到 {len(recent)} 条消息")
        
        # 显示前几条消息的详细信息
        for i, msg in enumerate(recent[:3]):
            logger.info(f"  消息{i+1}: id={msg.id}, message_id={msg.message_id}, session_id={msg.session_id}, type={msg.message_type}, content_length={len(msg.content) if msg.content else 0}")
        
        filtered = [m for m in recent if not ((m.message_metadata or {}).get('deleted') is True)]
        messages = list(reversed(filtered[:limit]))
        
        logger.info(f"🔍 过滤后消息数量: {len(messages)}")
        
        # 转换为Pydantic模型
        from models.database_models import MessageResponse, MessageNodeResponse
        result = []
        for message in messages:
            # 查询该消息的节点信息
            nodes = db.query(MessageNode).filter(
                MessageNode.message_id == message.message_id
            ).order_by(MessageNode.created_at.asc()).all()
            
            # 转换为节点响应模型
            node_responses = []
            for node in nodes:
                node_responses.append(MessageNodeResponse(
                    id=node.id,
                    node_id=node.node_id,
                    node_type=node.node_type,
                    node_name=node.node_name,
                    node_label=node.node_label,
                    node_metadata=node.node_metadata,
                    content=node.content,
                    created_at=node.created_at
                ))
            
            # 获取消息内容：优先使用消息本身的content，如果没有则从节点中获取
            message_content = ""
            if message.content:
                # 如果消息本身有content，直接使用
                message_content = message.content
            else:
                # 否则从节点中获取内容
                for node in nodes:
                    if node.content:
                        message_content = node.content
                        break
            
            result.append(MessageResponse(
                id=message.id,
                message_id=message.message_id,
                session_id=message.session_id,
                user_id=message.user_id,
                message_type=message.message_type,
                content=message_content,  # 使用消息内容或节点内容
                agent_name=message.agent_name,
                metadata=message.message_metadata,
                created_at=message.created_at,
                nodes=node_responses  # 添加节点信息
            ))
        return result
    
    @staticmethod
    def get_message(db: Session, message_id: str) -> Optional[ChatMessage]:
        """获取消息"""
        return db.query(ChatMessage).filter(
            ChatMessage.message_id == message_id
        ).first()
    
    @staticmethod
    def delete_message(db: Session, message_id: str) -> bool:
        """删除消息"""
        message = db.query(ChatMessage).filter(ChatMessage.message_id == message_id).first()
        if message:
            try:
                # 软删：写入metadata标记
                meta = message.message_metadata or {}
                meta.update({"deleted": True, "deleted_at": datetime.utcnow().isoformat()})
                message.message_metadata = meta
                db.commit()
                logger.info(f"软删消息: {message_id}")
                return True
            except Exception:
                # 兜底物理删除
                db.delete(message)
                db.commit()
                logger.info(f"物理删除消息: {message_id}")
                return True
        return False

    @staticmethod
    def get_last_workspace_summary(db: Session, session_uuid: str) -> Optional['MessageResponse']:
        """获取会话最近一条 workspace_summary"""
        msgs = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_uuid,
            ChatMessage.message_type == "workspace_summary"
        ).order_by(ChatMessage.created_at.desc()).limit(50).all()
        msg = None
        for m in msgs:
            if not ((m.message_metadata or {}).get('deleted') is True):
                msg = m
                break
        if not msg:
            return None
        from models.database_models import MessageResponse
        return MessageResponse(
            id=msg.id,
            message_id=msg.message_id,
            session_id=msg.session_id,
            user_id=msg.user_id,
            message_type=msg.message_type,
            content=msg.content,
            agent_name=msg.agent_name,
            metadata=msg.message_metadata,
            created_at=msg.created_at
        )

    @staticmethod
    def upsert_workspace_summary(
        db: Session,
        session_uuid: str,
        user_id: str,
        content: str,
        agent_name: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> 'MessageResponse':
        """若存在最近一条未删除的 workspace_summary 则更新，否则创建"""
        existing = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_uuid,
            ChatMessage.message_type == "workspace_summary"
        ).order_by(ChatMessage.created_at.desc()).first()
        
        if existing and not ((existing.message_metadata or {}).get('deleted') is True):
            # 更新现有记录
            existing.content = content
            meta = existing.message_metadata or {}
            if metadata:
                meta.update(metadata)
            meta['updated_at'] = datetime.utcnow().isoformat()
            existing.message_metadata = meta
            if agent_name:
                existing.agent_name = agent_name
            db.commit()
            db.refresh(existing)
            from models.database_models import MessageResponse
            return MessageResponse(
                id=existing.id,
                message_id=existing.message_id,
                session_id=existing.session_id,
                user_id=existing.user_id,
                message_type=existing.message_type,
                content=existing.content,
                agent_name=existing.agent_name,
                metadata=existing.message_metadata,
                created_at=existing.created_at
            )
        else:
            # 创建新记录
            return MessageService.create_message(db, MessageCreate(
                session_id=session_uuid,
                user_id=user_id,
                message_type="workspace_summary",
                content=content,
                agent_name=agent_name,
                metadata=metadata
            )) 