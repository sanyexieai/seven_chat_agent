from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from models.database_models import UserSession, Message, SessionCreate, SessionResponse, MessageCreate, MessageResponse
from utils.log_helper import get_logger
import uuid
from datetime import datetime

logger = get_logger("session_service")

class SessionService:
    """会话服务"""
    
    @staticmethod
    def get_user_sessions(db: Session, user_id: str) -> List[SessionResponse]:
        """获取用户的所有会话"""
        sessions = db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.is_active == True
        ).all()
        return [SessionResponse.model_validate(session) for session in sessions]
    
    @staticmethod
    def get_session_by_id(db: Session, session_id: int) -> Optional[SessionResponse]:
        """根据ID获取会话"""
        session = db.query(UserSession).filter(UserSession.id == session_id).first()
        return SessionResponse.model_validate(session) if session else None
    
    @staticmethod
    def create_session(db: Session, session_data: SessionCreate) -> SessionResponse:
        """创建会话"""
        session = UserSession(
            session_id=str(uuid.uuid4()),
            user_id=session_data.user_id,
            agent_id=session_data.agent_id,
            title=session_data.title or f"新会话 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info(f"创建会话: {session.session_id}")
        return SessionResponse.model_validate(session)
    
    @staticmethod
    def update_session_title(db: Session, session_id: int, title: str) -> Optional[SessionResponse]:
        """更新会话标题"""
        session = db.query(UserSession).filter(UserSession.id == session_id).first()
        if not session:
            return None
        
        session.title = title
        db.commit()
        db.refresh(session)
        logger.info(f"更新会话标题: {session.session_id}")
        return SessionResponse.model_validate(session)
    
    @staticmethod
    def delete_session(db: Session, session_id: int) -> bool:
        """删除会话"""
        session = db.query(UserSession).filter(UserSession.id == session_id).first()
        if not session:
            return False
        
        session.is_active = False
        db.commit()
        logger.info(f"删除会话: {session.session_id}")
        return True

class MessageService:
    """消息服务"""
    
    @staticmethod
    def get_session_messages(db: Session, session_id: int, limit: int = 100) -> List[MessageResponse]:
        """获取会话消息"""
        messages = db.query(Message).filter(
            Message.session_id == session_id
        ).order_by(Message.created_at.asc()).limit(limit).all()
        return [MessageResponse.model_validate(message) for message in messages]
    
    @staticmethod
    def create_message(db: Session, message_data: MessageCreate) -> MessageResponse:
        """创建消息"""
        message = Message(
            message_id=str(uuid.uuid4()),
            session_id=message_data.session_id,
            type=message_data.type,
            content=message_data.content,
            agent_name=message_data.agent_name,
            message_metadata=message_data.metadata or {}
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        logger.info(f"创建消息: {message.message_id}")
        return MessageResponse.model_validate(message)
    
    @staticmethod
    def get_message_by_id(db: Session, message_id: str) -> Optional[MessageResponse]:
        """根据ID获取消息"""
        message = db.query(Message).filter(Message.message_id == message_id).first()
        return MessageResponse.model_validate(message) if message else None
    
    @staticmethod
    def delete_message(db: Session, message_id: str) -> bool:
        """删除消息"""
        message = db.query(Message).filter(Message.message_id == message_id).first()
        if not message:
            return False
        
        db.delete(message)
        db.commit()
        logger.info(f"删除消息: {message_id}")
        return True 