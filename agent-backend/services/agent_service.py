from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from models.database_models import Agent, AgentCreate, AgentUpdate, AgentResponse
from utils.log_helper import get_logger

logger = get_logger("agent_service")

class AgentService:
    """智能体服务"""
    
    @staticmethod
    def get_agents(db: Session, active_only: bool = True) -> List[AgentResponse]:
        """获取所有智能体"""
        query = db.query(Agent)
        if active_only:
            query = query.filter(Agent.is_active == True)
        
        agents = query.all()
        return [AgentResponse.model_validate(agent) for agent in agents]
    
    @staticmethod
    def get_agent_by_id(db: Session, agent_id: int) -> Optional[AgentResponse]:
        """根据ID获取智能体"""
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        return AgentResponse.model_validate(agent) if agent else None
    
    @staticmethod
    def get_agent_by_name(db: Session, name: str) -> Optional[AgentResponse]:
        """根据名称获取智能体"""
        agent = db.query(Agent).filter(Agent.name == name).first()
        return AgentResponse.model_validate(agent) if agent else None
    
    @staticmethod
    def create_agent(db: Session, agent_data: AgentCreate) -> AgentResponse:
        """创建智能体"""
        agent = Agent(**agent_data.dict())
        db.add(agent)
        db.commit()
        db.refresh(agent)
        logger.info(f"创建智能体: {agent.name}")
        return AgentResponse.model_validate(agent)
    
    @staticmethod
    def update_agent(db: Session, agent_id: int, agent_data: AgentUpdate) -> Optional[AgentResponse]:
        """更新智能体"""
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return None
        
        update_data = agent_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(agent, field, value)
        
        db.commit()
        db.refresh(agent)
        logger.info(f"更新智能体: {agent.name}")
        return AgentResponse.model_validate(agent)
    
    @staticmethod
    def delete_agent(db: Session, agent_id: int) -> bool:
        """删除智能体"""
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return False
        
        db.delete(agent)
        db.commit()
        logger.info(f"删除智能体: {agent.name}")
        return True
    
    @staticmethod
    def activate_agent(db: Session, agent_id: int) -> bool:
        """激活智能体"""
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return False
        
        agent.is_active = True
        db.commit()
        logger.info(f"激活智能体: {agent.name}")
        return True
    
    @staticmethod
    def deactivate_agent(db: Session, agent_id: int) -> bool:
        """停用智能体"""
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return False
        
        agent.is_active = False
        db.commit()
        logger.info(f"停用智能体: {agent.name}")
        return True 