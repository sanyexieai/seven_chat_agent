from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from models.database_models import LLMConfig, LLMConfigCreate, LLMConfigUpdate, LLMConfigResponse
from utils.log_helper import get_logger

logger = get_logger("llm_config_service")

class LLMConfigService:
    """LLM配置服务"""
    
    @staticmethod
    def get_all_configs(db: Session) -> List[LLMConfigResponse]:
        """获取所有LLM配置"""
        configs = db.query(LLMConfig).filter(LLMConfig.is_active == True).all()
        return [LLMConfigResponse.model_validate(config) for config in configs]
    
    @staticmethod
    def get_config_by_id(db: Session, config_id: int) -> Optional[LLMConfigResponse]:
        """根据ID获取LLM配置"""
        config = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        return LLMConfigResponse.model_validate(config) if config else None
    
    @staticmethod
    def get_config_by_name(db: Session, name: str) -> Optional[LLMConfigResponse]:
        """根据名称获取LLM配置"""
        config = db.query(LLMConfig).filter(LLMConfig.name == name).first()
        return LLMConfigResponse.model_validate(config) if config else None
    
    @staticmethod
    def get_default_config(db: Session) -> Optional[LLMConfigResponse]:
        """获取默认LLM配置"""
        config = db.query(LLMConfig).filter(
            LLMConfig.is_default == True,
            LLMConfig.is_active == True
        ).first()
        return LLMConfigResponse.model_validate(config) if config else None
    
    @staticmethod
    def create_config(db: Session, config_data: LLMConfigCreate) -> LLMConfigResponse:
        """创建LLM配置"""
        # 如果设置为默认配置，先取消其他默认配置
        if config_data.is_default:
            db.query(LLMConfig).filter(LLMConfig.is_default == True).update({"is_default": False})
        
        config = LLMConfig(**config_data.model_dump())
        db.add(config)
        db.commit()
        db.refresh(config)
        
        logger.info(f"创建LLM配置: {config.name}")
        return LLMConfigResponse.model_validate(config)
    
    @staticmethod
    def update_config(db: Session, config_id: int, update_data: LLMConfigUpdate) -> Optional[LLMConfigResponse]:
        """更新LLM配置"""
        config = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        if not config:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        
        # 如果设置为默认配置，先取消其他默认配置
        if update_dict.get("is_default", False):
            db.query(LLMConfig).filter(
                LLMConfig.is_default == True,
                LLMConfig.id != config_id
            ).update({"is_default": False})
        
        for field, value in update_dict.items():
            setattr(config, field, value)
        
        db.commit()
        db.refresh(config)
        
        logger.info(f"更新LLM配置: {config.name}")
        return LLMConfigResponse.model_validate(config)
    
    @staticmethod
    def delete_config(db: Session, config_id: int) -> bool:
        """删除LLM配置"""
        config = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        if not config:
            return False
        
        config.is_active = False
        db.commit()
        
        logger.info(f"删除LLM配置: {config.name}")
        return True
    
    @staticmethod
    def set_default_config(db: Session, config_id: int) -> bool:
        """设置默认LLM配置"""
        config = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        if not config:
            return False
        
        # 取消其他默认配置
        db.query(LLMConfig).filter(LLMConfig.is_default == True).update({"is_default": False})
        
        # 设置新的默认配置
        config.is_default = True
        db.commit()
        
        logger.info(f"设置默认LLM配置: {config.name}")
        return True
    
    @staticmethod
    def get_config_for_provider(db: Session, provider: str) -> Optional[LLMConfigResponse]:
        """根据提供商获取LLM配置"""
        config = db.query(LLMConfig).filter(
            LLMConfig.provider == provider,
            LLMConfig.is_active == True
        ).first()
        return LLMConfigResponse.model_validate(config) if config else None 