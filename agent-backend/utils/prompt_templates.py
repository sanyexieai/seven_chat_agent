# -*- coding: utf-8 -*-
"""
提示词模板统一管理
用于避免在多个地方重复定义相同的提示词
支持从数据库读取，如果数据库中没有则使用硬编码的默认值
"""
from typing import Dict, Any, Optional
from database.database import SessionLocal
from models.database_models import PromptTemplate
from utils.log_helper import get_logger

logger = get_logger("prompt_templates")

# 提示词模板占位（真实内容由数据库中的 auto_infer_* 管理）
# 兜底内容只在 extract_prompts_to_db.py 中维护
_DEFAULT_SYSTEM_PROMPT = ""
_DEFAULT_USER_PROMPT_TEMPLATE = ""
_DEFAULT_USER_PROMPT_SIMPLE_TEMPLATE = ""


class PromptTemplates:
    """提示词模板管理器"""
    
    _cache: Dict[str, str] = {}  # 缓存从数据库读取的模板
    
    @staticmethod
    def _get_template_from_db(name: str, template_type: str, default: str) -> str:
        """
        从数据库获取提示词模板，如果不存在则返回默认值
        
        Args:
            name: 模板名称
            template_type: 模板类型（system/user）
            default: 默认值（硬编码）
        
        Returns:
            模板内容
        """
        cache_key = f"{name}_{template_type}"
        
        # 检查缓存
        if cache_key in PromptTemplates._cache:
            return PromptTemplates._cache[cache_key]
        
        db = SessionLocal()
        try:
            template = db.query(PromptTemplate).filter(
                PromptTemplate.name == name,
                PromptTemplate.template_type == template_type,
                PromptTemplate.is_active == True
            ).first()
            
            if template:
                content = template.content
                PromptTemplates._cache[cache_key] = content
                return content
            else:
                logger.warning(f"未找到提示词模板 {name} ({template_type})，使用默认值")
                return default
        except Exception as e:
            logger.error(f"从数据库读取提示词模板失败: {str(e)}，使用默认值")
            return default
        finally:
            db.close()
    
    @staticmethod
    def clear_cache():
        """清除缓存，强制重新从数据库读取"""
        PromptTemplates._cache.clear()
    
    @staticmethod
    def get_auto_infer_system_prompt() -> str:
        """获取自动推理工具参数的系统提示词"""
        return PromptTemplates._get_template_from_db(
            "auto_infer_system",
            "system",
            _DEFAULT_SYSTEM_PROMPT
        )
    
    @staticmethod
    def get_auto_infer_user_prompt(
        tool_name: str = "",
        tool_type: Optional[str] = None,
        server: Optional[str] = None,
        schema_json: str = "{}",
        message: str = "",
        previous_output: Optional[str] = None,
        required_fields_text: str = "",
        use_simple: bool = False
    ) -> str:
        """
        获取自动推理工具参数的用户提示词
        
        Args:
            tool_name: 工具名称
            tool_type: 工具类型
            server: 服务器名称
            schema_json: 参数 Schema 的 JSON 字符串
            message: 用户输入
            previous_output: 上一节点输出
            required_fields_text: 必填字段文本（如果提供，会使用完整模板）
            use_simple: 是否使用简化模板（不包含 required_fields_text）
        
        Returns:
            格式化后的用户提示词
        """
        # 从数据库获取模板
        template_name = "auto_infer_user_simple" if use_simple else "auto_infer_user_full"
        default_template = _DEFAULT_USER_PROMPT_SIMPLE_TEMPLATE if use_simple else _DEFAULT_USER_PROMPT_TEMPLATE
        
        template = PromptTemplates._get_template_from_db(
            template_name,
            "user",
            default_template
        )
        
        return template.format(
            tool_name=tool_name or "",
            tool_type=tool_type or "",
            server=server or "",
            schema_json=schema_json,
            message=message or "",
            previous_output=previous_output or "",
            required_fields_text=required_fields_text or ""
        )
    
    @staticmethod
    def get_auto_infer_prompts(
        tool_name: str = "",
        tool_type: Optional[str] = None,
        server: Optional[str] = None,
        schema_json: str = "{}",
        message: str = "",
        previous_output: Optional[str] = None,
        required_fields_text: str = "",
        use_simple: bool = False
    ) -> Dict[str, str]:
        """
        获取自动推理工具参数的系统提示词和用户提示词
        
        Returns:
            包含 'system' 和 'user' 键的字典
        """
        return {
            "system": PromptTemplates.get_auto_infer_system_prompt(),
            "user": PromptTemplates.get_auto_infer_user_prompt(
                tool_name=tool_name,
                tool_type=tool_type,
                server=server,
                schema_json=schema_json,
                message=message,
                previous_output=previous_output,
                required_fields_text=required_fields_text,
                use_simple=use_simple
            )
        }

