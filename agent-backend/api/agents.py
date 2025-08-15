from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from database.database import get_db
from services.agent_service import AgentService
from models.database_models import AgentCreate, AgentUpdate, AgentResponse
from utils.log_helper import get_logger
import time
from models.database_models import Agent
from fastapi import status

logger = get_logger("agents_api")
router = APIRouter(prefix="/api/agents", tags=["agents"])

@router.get("", response_model=List[AgentResponse])
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
        
        # 重新加载智能体到agent_manager
        try:
            from main import agent_manager
            if agent_manager:
                # 根据智能体类型创建相应的智能体实例
                if agent_data.agent_type == "general":
                    from agents.general_agent import GeneralAgent
                    system_prompt = agent_data.system_prompt or ""
                    
                    # 获取智能体的LLM配置
                    llm_config = None
                    if agent_data.llm_config_id:
                        llm_config = AgentService.get_agent_llm_config(db, agent.id)
                        logger.info(f"智能体 {agent.name} 使用特定LLM配置: {llm_config.get('provider') if llm_config else 'None'}")
                    else:
                        logger.info(f"智能体 {agent.name} 使用默认LLM配置")
                    
                    prompt_agent = GeneralAgent(agent.name, agent.display_name, system_prompt, llm_config)
                    agent_manager.agents[agent.name] = prompt_agent
                elif agent_data.agent_type == "flow_driven":
                    from agents.flow_driven_agent import FlowDrivenAgent
                    flow_config = agent_data.flow_config or {}
                    flow_agent = FlowDrivenAgent(agent.name, agent.display_name, flow_config)
                    agent_manager.agents[agent.name] = flow_agent
                
                logger.info(f"智能体 {agent.name} 已加载到agent_manager")
        except Exception as e:
            logger.warning(f"重新加载智能体到agent_manager失败: {str(e)}")
        
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
        
        # 重新加载智能体到agent_manager
        try:
            from main import agent_manager
            if agent_manager:
                # 根据智能体类型创建相应的智能体实例
                if agent_data.agent_type == "general":
                    from agents.general_agent import GeneralAgent
                    system_prompt = agent_data.system_prompt or ""
                    
                    # 获取智能体的LLM配置
                    llm_config = None
                    if agent_data.llm_config_id:
                        llm_config = AgentService.get_agent_llm_config(db, agent.id)
                        logger.info(f"智能体 {agent.name} 使用特定LLM配置: {llm_config.get('provider') if llm_config else 'None'}")
                    else:
                        logger.info(f"智能体 {agent.name} 使用默认LLM配置")
                    
                    prompt_agent = GeneralAgent(agent.name, agent.display_name, system_prompt, llm_config)
                    agent_manager.agents[agent.name] = prompt_agent
                    logger.info(f"智能体 {agent.name} 已重新加载到agent_manager")
                elif agent_data.agent_type == "flow_driven":
                    from agents.flow_driven_agent import FlowDrivenAgent
                    flow_config = agent_data.flow_config or {}
                    flow_agent = FlowDrivenAgent(agent.name, agent.display_name, flow_config)
                    agent_manager.agents[agent.name] = flow_agent
                    logger.info(f"智能体 {agent.name} 已重新加载到agent_manager")
                
        except Exception as e:
            logger.warning(f"重新加载智能体到agent_manager失败: {str(e)}")
        
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

@router.get("/{agent_id}/tools")
async def get_agent_tools(
    agent_id: int,
    db: Session = Depends(get_db)
):
    """获取智能体绑定的工具"""
    try:
        agent = AgentService.get_agent_by_id(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")
        
        tools = agent.bound_tools or []
        return {"tools": tools}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能体工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取智能体工具失败")

@router.post("/{agent_id}/tools")
async def bind_tools_to_agent(
    agent_id: int,
    tools: List[str],
    db: Session = Depends(get_db)
):
    """绑定工具到智能体"""
    try:
        success = AgentService.bind_tools_to_agent(db, agent_id, tools)
        if not success:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"message": "工具绑定成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"绑定工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail="绑定工具失败")

@router.delete("/{agent_id}/tools")
async def unbind_tools_from_agent(
    agent_id: int,
    db: Session = Depends(get_db)
):
    """从智能体解绑工具"""
    try:
        success = AgentService.unbind_tools_from_agent(db, agent_id)
        if not success:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"message": "工具解绑成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解绑工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail="解绑工具失败")

@router.get("/{agent_id}/knowledge-bases")
async def get_agent_knowledge_bases(
    agent_id: int,
    db: Session = Depends(get_db)
):
    """获取智能体绑定的知识库"""
    try:
        agent = AgentService.get_agent_by_id(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")
        
        knowledge_bases = agent.bound_knowledge_bases or []
        return {"knowledge_bases": knowledge_bases}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能体知识库失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取智能体知识库失败")

@router.post("/{agent_id}/knowledge-bases")
async def bind_knowledge_bases_to_agent(
    agent_id: int,
    knowledge_bases: List[int],
    db: Session = Depends(get_db)
):
    """绑定知识库到智能体"""
    try:
        success = AgentService.bind_knowledge_bases_to_agent(db, agent_id, knowledge_bases)
        if not success:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"message": "知识库绑定成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"绑定知识库失败: {str(e)}")
        raise HTTPException(status_code=500, detail="绑定知识库失败")

@router.delete("/{agent_id}/knowledge-bases")
async def unbind_knowledge_bases_from_agent(
    agent_id: int,
    db: Session = Depends(get_db)
):
    """从智能体解绑知识库"""
    try:
        success = AgentService.unbind_knowledge_bases_from_agent(db, agent_id)
        if not success:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"message": "知识库解绑成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解绑知识库失败: {str(e)}")
        raise HTTPException(status_code=500, detail="解绑知识库失败") 
