from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database.database import get_db
from services.llm_config_service import LLMConfigService
from models.database_models import LLMConfigCreate, LLMConfigUpdate, LLMConfigResponse
from utils.log_helper import get_logger

logger = get_logger("llm_config_api")
router = APIRouter(prefix="/api/llm-config", tags=["llm-config"])

@router.get("", response_model=List[LLMConfigResponse])
async def get_llm_configs_no_slash(db: Session = Depends(get_db)):
    """获取所有LLM配置（不带斜杠）"""
    return await get_llm_configs(db)

@router.get("/", response_model=List[LLMConfigResponse])
async def get_llm_configs(db: Session = Depends(get_db)):
    """获取所有LLM配置"""
    try:
        configs = LLMConfigService.get_all_configs(db)
        return configs
    except Exception as e:
        logger.error(f"获取LLM配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取LLM配置失败")

@router.get("/{config_id}", response_model=LLMConfigResponse)
async def get_llm_config(
    config_id: int,
    db: Session = Depends(get_db)
):
    """根据ID获取LLM配置"""
    try:
        config = LLMConfigService.get_config_by_id(db, config_id)
        if not config:
            raise HTTPException(status_code=404, detail="LLM配置不存在")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取LLM配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取LLM配置失败")

@router.get("/default", response_model=LLMConfigResponse)
async def get_default_llm_config(db: Session = Depends(get_db)):
    """获取默认LLM配置"""
    try:
        config = LLMConfigService.get_default_config(db)
        if not config:
            raise HTTPException(status_code=404, detail="默认LLM配置不存在")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取默认LLM配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取默认LLM配置失败")

@router.post("/", response_model=LLMConfigResponse)
async def create_llm_config(
    config_data: LLMConfigCreate,
    db: Session = Depends(get_db)
):
    """创建LLM配置"""
    try:
        config = LLMConfigService.create_config(db, config_data)
        return config
    except Exception as e:
        logger.error(f"创建LLM配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="创建LLM配置失败")

@router.put("/{config_id}", response_model=LLMConfigResponse)
async def update_llm_config(
    config_id: int,
    update_data: LLMConfigUpdate,
    db: Session = Depends(get_db)
):
    """更新LLM配置"""
    try:
        config = LLMConfigService.update_config(db, config_id, update_data)
        if not config:
            raise HTTPException(status_code=404, detail="LLM配置不存在")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新LLM配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="更新LLM配置失败")

@router.delete("/{config_id}")
async def delete_llm_config(
    config_id: int,
    db: Session = Depends(get_db)
):
    """删除LLM配置"""
    try:
        success = LLMConfigService.delete_config(db, config_id)
        if not success:
            raise HTTPException(status_code=404, detail="LLM配置不存在")
        return {"message": "LLM配置删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除LLM配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除LLM配置失败")

@router.post("/{config_id}/set-default")
async def set_default_llm_config(
    config_id: int,
    db: Session = Depends(get_db)
):
    """设置默认LLM配置"""
    try:
        success = LLMConfigService.set_default_config(db, config_id)
        if not success:
            raise HTTPException(status_code=404, detail="LLM配置不存在")
        return {"message": "默认LLM配置设置成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置默认LLM配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="设置默认LLM配置失败")

@router.get("/provider/{provider}", response_model=LLMConfigResponse)
async def get_llm_config_by_provider(
    provider: str,
    db: Session = Depends(get_db)
):
    """根据提供商获取LLM配置"""
    try:
        config = LLMConfigService.get_config_for_provider(db, provider)
        if not config:
            raise HTTPException(status_code=404, detail=f"提供商 {provider} 的LLM配置不存在")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取提供商LLM配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取提供商LLM配置失败")

@router.post("/refresh")
async def refresh_llm_config():
    """刷新LLM配置缓存"""
    try:
        from config.llm_config_manager import llm_config_manager
        from utils.llm_helper import get_llm_helper
        
        # 刷新配置管理器
        llm_config_manager.refresh_config()
        
        # 刷新LLM助手配置
        llm_helper = get_llm_helper()
        llm_helper.refresh_config()
        
        logger.info("LLM配置刷新成功")
        return {"message": "LLM配置刷新成功"}
    except Exception as e:
        logger.error(f"刷新LLM配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="刷新LLM配置失败")

@router.post("/reload")
async def reload_llm_config():
    """重新加载LLM配置（完全重新初始化）"""
    try:
        from config.llm_config_manager import llm_config_manager
        from utils.llm_helper import get_llm_helper
        # 重新初始化配置管理器
        llm_config_manager._initialized = False
        llm_config_manager.initialize()
        
        # 重新初始化LLM助手
        llm_helper = get_llm_helper()
        llm_helper._initialized = False
        llm_helper.setup()
        
        # 重新初始化所有智能体的LLM助手
        try:
            from main import agent_manager
            if agent_manager:
                await agent_manager.reload_agents_llm()
        except ImportError:
            logger.warning("无法导入agent_manager，跳过智能体LLM重新加载")
        
        logger.info("LLM配置重新加载成功")
        return {"message": "LLM配置重新加载成功"}
    except Exception as e:
        logger.error(f"重新加载LLM配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="重新加载LLM配置失败") 