from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any
from models.database_models import Agent, AgentCreate, AgentUpdate, AgentResponse
from utils.log_helper import get_logger

logger = get_logger("agent_service")


def _normalize_bound_tools_for_storage(bound_tools: Optional[List[Any]]) -> Optional[List[Dict[str, Any]]]:
    """将传入的 bound_tools 统一为对象形式 [{ 'server_name': str, 'name': str }]
    - 接受 ['server_tool', ...] 或 [{...}] 两种形式
    - 跳过无效项
    """
    if not bound_tools:
        return bound_tools
    normalized: List[Dict[str, Any]] = []
    for item in bound_tools:
        if isinstance(item, str):
            if '_' in item:
                server_name, tool_name = item.split('_', 1)
                normalized.append({"server_name": server_name, "name": tool_name})
        elif isinstance(item, dict):
            server = item.get("server_name") or item.get("server")
            name = item.get("name") or item.get("tool_name")
            if server and name:
                normalized.append({"server_name": server, "name": name})
        # 其他格式忽略
    return normalized


def _map_bound_tools_for_response(bound_tools: Optional[List[Any]]) -> Optional[List[str]]:
    """将存储的对象形式映射为 ['server_tool', ...] 字符串数组，兼容旧前端"""
    if not bound_tools:
        return bound_tools
    result: List[str] = []
    for item in bound_tools:
        if isinstance(item, dict):
            server = item.get("server_name") or item.get("server")
            name = item.get("name") or item.get("tool_name")
            if server and name:
                result.append(f"{server}_{name}")
        elif isinstance(item, str):
            result.append(item)
    return result


class AgentService:
    """智能体服务"""
    
    @staticmethod
    def get_agents(db: Session, active_only: bool = True) -> List[AgentResponse]:
        """获取所有智能体"""
        query = db.query(Agent).options(joinedload(Agent.llm_config))
        if active_only:
            query = query.filter(Agent.is_active == True)
        
        agents = query.all()
        responses: List[AgentResponse] = []
        for agent in agents:
            resp = AgentResponse.model_validate(agent)
            # 映射 bound_tools 为字符串列表供前端显示
            try:
                mapped = _map_bound_tools_for_response(agent.bound_tools)
                object.__setattr__(resp, 'bound_tools', mapped)
            except Exception:
                pass
            responses.append(resp)
        return responses
    
    @staticmethod
    def get_agent_by_id(db: Session, agent_id: int) -> Optional[AgentResponse]:
        """根据ID获取智能体"""
        agent = db.query(Agent).options(joinedload(Agent.llm_config)).filter(Agent.id == agent_id).first()
        if not agent:
            return None
        resp = AgentResponse.model_validate(agent)
        try:
            mapped = _map_bound_tools_for_response(agent.bound_tools)
            object.__setattr__(resp, 'bound_tools', mapped)
        except Exception:
            pass
        return resp
    
    @staticmethod
    def get_agent_by_name(db: Session, name: str) -> Optional[AgentResponse]:
        """根据名称获取智能体"""
        agent = db.query(Agent).options(joinedload(Agent.llm_config)).filter(Agent.name == name).first()
        if not agent:
            return None
        resp = AgentResponse.model_validate(agent)
        try:
            mapped = _map_bound_tools_for_response(agent.bound_tools)
            object.__setattr__(resp, 'bound_tools', mapped)
        except Exception:
            pass
        return resp
    
    @staticmethod
    def create_agent(db: Session, agent_data: AgentCreate) -> AgentResponse:
        """创建智能体"""
        payload = agent_data.dict()
        # 规范化 bound_tools 为对象
        payload['bound_tools'] = _normalize_bound_tools_for_storage(payload.get('bound_tools'))
        agent = Agent(**payload)
        db.add(agent)
        db.commit()
        db.refresh(agent)
        logger.info(f"创建智能体: {agent.name}")
        resp = AgentResponse.model_validate(agent)
        try:
            mapped = _map_bound_tools_for_response(agent.bound_tools)
            object.__setattr__(resp, 'bound_tools', mapped)
        except Exception:
            pass
        return resp
    
    @staticmethod
    def update_agent(db: Session, agent_id: int, agent_data: AgentUpdate) -> Optional[AgentResponse]:
        """更新智能体"""
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return None
        update_data = agent_data.dict(exclude_unset=True)
        if 'bound_tools' in update_data:
            update_data['bound_tools'] = _normalize_bound_tools_for_storage(update_data.get('bound_tools'))
        for field, value in update_data.items():
            setattr(agent, field, value)
        db.commit()
        db.refresh(agent)
        logger.info(f"更新智能体: {agent.name}")
        resp = AgentResponse.model_validate(agent)
        try:
            mapped = _map_bound_tools_for_response(agent.bound_tools)
            object.__setattr__(resp, 'bound_tools', mapped)
        except Exception:
            pass
        return resp
    
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
    
    @staticmethod
    def get_agent_llm_config(db: Session, agent_id: int) -> Optional[Dict[str, Any]]:
        """获取智能体的LLM配置，如果没有配置则返回默认配置"""
        from services.llm_config_service import LLMConfigService
        
        # 获取智能体
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return None
        
        # 如果智能体有配置的LLM，使用该配置
        if agent.llm_config_id:
            llm_config = LLMConfigService.get_config_by_id(db, agent.llm_config_id)
            if llm_config:
                return {
                    "provider": llm_config.provider,
                    "model_name": llm_config.model_name,
                    "api_key": llm_config.api_key,
                    "api_base": llm_config.api_base,
                    "config": llm_config.config,
                    "source": "agent_specific"
                }
        
        # 如果没有配置，使用默认LLM配置
        default_config = LLMConfigService.get_default_config(db)
        if default_config:
            return {
                "provider": default_config.provider,
                "model_name": default_config.model_name,
                "api_key": default_config.api_key,
                "api_base": default_config.api_base,
                "config": default_config.config,
                "source": "default"
            }
        
        return None 