from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database.database import get_db
from services.agent_service import AgentService
from models.database_models import AgentCreate, AgentUpdate, AgentResponse
from utils.log_helper import get_logger

logger = get_logger("agents_api")
router = APIRouter(prefix="/api/agents", tags=["agents"])

@router.get("/", response_model=List[AgentResponse])
async def get_agents(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """获取所有智能体"""
    try:
        agents = AgentService.get_agents(db, active_only=active_only)
        return agents
    except Exception as e:
        logger.error(f"获取智能体失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取智能体失败")

@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    db: Session = Depends(get_db)
):
    """根据ID获取智能体"""
    try:
        agent = AgentService.get_agent_by_id(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return agent
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能体失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取智能体失败")

@router.post("/", response_model=AgentResponse)
async def create_agent(
    agent_data: AgentCreate,
    db: Session = Depends(get_db)
):
    """创建智能体"""
    try:
        agent = AgentService.create_agent(db, agent_data)
        return agent
    except Exception as e:
        logger.error(f"创建智能体失败: {str(e)}")
        raise HTTPException(status_code=500, detail="创建智能体失败")

@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: int,
    agent_data: AgentUpdate,
    db: Session = Depends(get_db)
):
    """更新智能体"""
    try:
        agent = AgentService.update_agent(db, agent_id, agent_data)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return agent
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新智能体失败: {str(e)}")
        raise HTTPException(status_code=500, detail="更新智能体失败")

@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int,
    db: Session = Depends(get_db)
):
    """删除智能体"""
    try:
        success = AgentService.delete_agent(db, agent_id)
        if not success:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"message": "智能体删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除智能体失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除智能体失败")

@router.post("/{agent_id}/activate")
async def activate_agent(
    agent_id: int,
    db: Session = Depends(get_db)
):
    """激活智能体"""
    try:
        success = AgentService.activate_agent(db, agent_id)
        if not success:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"message": "智能体激活成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"激活智能体失败: {str(e)}")
        raise HTTPException(status_code=500, detail="激活智能体失败")

@router.post("/{agent_id}/deactivate")
async def deactivate_agent(
    agent_id: int,
    db: Session = Depends(get_db)
):
    """停用智能体"""
    try:
        success = AgentService.deactivate_agent(db, agent_id)
        if not success:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"message": "智能体停用成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停用智能体失败: {str(e)}")
        raise HTTPException(status_code=500, detail="停用智能体失败") 