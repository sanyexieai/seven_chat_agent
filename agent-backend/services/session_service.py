from sqlalchemy.orm import Session
from typing import List, Optional
from models.database_models import UserSession, ChatMessage, SessionCreate, SessionResponse, MessageCreate, MessageResponse
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
        """获取用户的所有会话"""
        return db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.is_active == True
        ).all()
    
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
            content=message_data.content,
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
            content=message.content,
            agent_name=message.agent_name,
            metadata=message.message_metadata,
            created_at=message.created_at
        )
    
    @staticmethod
    def get_session_messages(db: Session, session_id: int, limit: int = 100) -> List['MessageResponse']:
        """获取会话的所有消息"""
        messages = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at).limit(limit).all()
        
        # 转换为Pydantic模型
        from models.database_models import MessageResponse
        result = []
        for message in messages:
            result.append(MessageResponse(
                id=message.id,
                message_id=message.message_id,
                session_id=message.session_id,
                user_id=message.user_id,
                message_type=message.message_type,
                content=message.content,
                agent_name=message.agent_name,
                metadata=message.message_metadata,
                created_at=message.created_at
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
            db.delete(message)
            db.commit()
            logger.info(f"删除消息: {message_id}")
            return True
        return False 