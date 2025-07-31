from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database.database import get_db
from services.session_service import SessionService, MessageService
from models.database_models import SessionCreate, SessionResponse, MessageCreate, MessageResponse
from utils.log_helper import get_logger

logger = get_logger("sessions_api")
router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# 会话相关API
@router.get("/", response_model=List[SessionResponse])
async def get_user_sessions(
    user_id: str,
    db: Session = Depends(get_db)
):
    """获取用户的所有会话"""
    try:
        sessions = SessionService.get_user_sessions(db, user_id)
        return sessions
    except Exception as e:
        logger.error(f"获取用户会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取用户会话失败")

@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: int,
    db: Session = Depends(get_db)
):
    """根据ID获取会话"""
    try:
        session = SessionService.get_session_by_id(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取会话失败")

@router.post("/", response_model=SessionResponse)
async def create_session(
    session_data: SessionCreate,
    db: Session = Depends(get_db)
):
    """创建会话"""
    try:
        session = SessionService.create_session(db, session_data)
        return session
    except Exception as e:
        logger.error(f"创建会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail="创建会话失败")

@router.put("/{session_id}/title")
async def update_session_title(
    session_id: int,
    title: str,
    db: Session = Depends(get_db)
):
    """更新会话标题"""
    try:
        session = SessionService.update_session_title(db, session_id, title)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"message": "会话标题更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新会话标题失败: {str(e)}")
        raise HTTPException(status_code=500, detail="更新会话标题失败")

@router.delete("/{session_id}")
async def delete_session(
    session_id: int,
    db: Session = Depends(get_db)
):
    """删除会话"""
    try:
        success = SessionService.delete_session(db, session_id)
        if not success:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"message": "会话删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除会话失败")

# 消息相关API
@router.get("/{session_id}/messages", response_model=List[MessageResponse])
async def get_session_messages(
    session_id: int,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取会话消息"""
    try:
        messages = MessageService.get_session_messages(db, session_id, limit)
        return messages
    except Exception as e:
        logger.error(f"获取会话消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取会话消息失败")

@router.post("/{session_id}/messages", response_model=MessageResponse)
async def create_message(
    session_id: int,
    message_data: MessageCreate,
    db: Session = Depends(get_db)
):
    """创建消息"""
    try:
        # 确保session_id一致
        message_data.session_id = session_id
        message = MessageService.create_message(db, message_data)
        return message
    except Exception as e:
        logger.error(f"创建消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail="创建消息失败")

@router.get("/messages/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: str,
    db: Session = Depends(get_db)
):
    """根据ID获取消息"""
    try:
        message = MessageService.get_message_by_id(db, message_id)
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        return message
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取消息失败")

@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str,
    db: Session = Depends(get_db)
):
    """删除消息"""
    try:
        success = MessageService.delete_message(db, message_id)
        if not success:
            raise HTTPException(status_code=404, detail="消息不存在")
        return {"message": "消息删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除消息失败") 