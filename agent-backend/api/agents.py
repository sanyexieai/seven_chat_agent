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
        
        # 重新加载智能体到agent_manager
        try:
            from main import agent_manager
            if agent_manager:
                # 根据智能体类型创建相应的智能体实例
                if agent_data.agent_type == "general":
                    from agents.prompt_driven_agent import PromptDrivenAgent
                    system_prompt = agent_data.system_prompt or ""
                    
                    # 获取智能体的LLM配置
                    llm_config = None
                    if agent_data.llm_config_id:
                        from services.agent_service import AgentService
                        llm_config = AgentService.get_agent_llm_config(db, agent.id)
                        logger.info(f"智能体 {agent.name} 使用特定LLM配置: {llm_config.get('provider') if llm_config else 'None'}")
                    else:
                        logger.info(f"智能体 {agent.name} 使用默认LLM配置")
                    
                    prompt_agent = PromptDrivenAgent(agent.name, agent.display_name, system_prompt, llm_config)
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

@router.post("/create_from_flow", response_model=AgentResponse)
async def create_agent_from_flow(
    flow_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """从流程图创建智能体"""
    try:
        flow_name = flow_data.get('flow_name', '未命名流程图')
        flow_description = flow_data.get('flow_description', '')
        flow_config = flow_data.get('flow_config', {})

        # 生成智能体名称
        agent_name = f"flow_agent_{flow_name.lower().replace(' ', '_')}_{int(time.time())}"
        agent_display_name = f"{flow_name} 智能体"

        # 创建智能体
        agent = Agent(
            name=agent_name,
            display_name=agent_display_name,
            description=f"基于流程图 '{flow_name}' 创建的智能体。{flow_description}",
            agent_type="flow_driven",
            flow_config=flow_config,
            is_active=True
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        logger.info(f"从流程图创建智能体: {agent.name}")
        
        # 重新加载智能体到agent_manager
        try:
            from main import agent_manager
            if agent_manager:
                # 创建FlowDrivenAgent实例
                from agents.flow_driven_agent import FlowDrivenAgent
                flow_agent = FlowDrivenAgent(agent.name, agent.display_name, agent.flow_config)
                agent_manager.agents[agent.name] = flow_agent
                logger.info(f"智能体 {agent.name} 已加载到agent_manager")
        except Exception as e:
            logger.warning(f"重新加载智能体到agent_manager失败: {str(e)}")
        
        return agent
    except Exception as e:
        logger.error(f"从流程图创建智能体失败: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"从流程图创建智能体失败: {str(e)}"
        ) 

@router.post("/reload")
async def reload_agents():
    """重新加载所有智能体"""
    try:
        from main import agent_manager
        if agent_manager:
            await agent_manager._create_default_agents()
            logger.info("智能体重新加载完成")
            return {"message": "智能体重新加载完成"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="智能体管理器未初始化"
            )
    except Exception as e:
        logger.error(f"重新加载智能体失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新加载智能体失败: {str(e)}"
        )

@router.get("/{agent_id}/llm-config")
async def get_agent_llm_config(
    agent_id: int,
    db: Session = Depends(get_db)
):
    """获取智能体的LLM配置"""
    try:
        llm_config = AgentService.get_agent_llm_config(db, agent_id)
        if not llm_config:
            raise HTTPException(status_code=404, detail="智能体LLM配置不存在")
        return llm_config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能体LLM配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取智能体LLM配置失败") 