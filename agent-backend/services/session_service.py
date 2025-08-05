from sqlalchemy.orm import Session
from typing import List, Optional
from models.database_models import UserSession, ChatMessage, SessionCreate, SessionResponse, MessageCreate, MessageResponse
from utils.log_helper import get_logger
import uuid
from datetime import datetime

logger = get_logger("session_service")

class SessionService:
    """会话服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_session(self, user_id: str, agent_id: int) -> UserSession:
        """创建会话"""
        session_id = str(uuid.uuid4())
        session = UserSession(
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            is_active=True
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        logger.info(f"创建会话: {session_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[UserSession]:
        """获取会话"""
        return self.db.query(UserSession).filter(
            UserSession.session_id == session_id,
            UserSession.is_active == True
        ).first()
    
    def get_user_sessions(self, user_id: str) -> List[UserSession]:
        """获取用户的所有会话"""
        return self.db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.is_active == True
        ).all()
    
    def deactivate_session(self, session_id: str) -> bool:
        """停用会话"""
        session = self.get_session(session_id)
        if session:
            session.is_active = False
            self.db.commit()
            logger.info(f"停用会话: {session_id}")
            return True
        return False

class MessageService:
    """消息服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_message(self, session_id: str, user_id: str, message_type: str, 
                      content: str, agent_name: Optional[str] = None, 
                      metadata: Optional[dict] = None) -> ChatMessage:
        """创建消息"""
        message_id = str(uuid.uuid4())
        message = ChatMessage(
            message_id=message_id,
            session_id=session_id,
            user_id=user_id,
            message_type=message_type,
            content=content,
            agent_name=agent_name,
            message_metadata=metadata
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        logger.info(f"创建消息: {message_id}")
        return message
    
    def get_session_messages(self, session_id: str) -> List[ChatMessage]:
        """获取会话的所有消息"""
        return self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at).all()
    
    def get_message(self, message_id: str) -> Optional[ChatMessage]:
        """获取消息"""
        return self.db.query(ChatMessage).filter(
            ChatMessage.message_id == message_id
        ).first() 