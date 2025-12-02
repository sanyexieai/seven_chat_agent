# -*- coding: utf-8 -*-
"""
使用 LLM 整理和提取 MCP 工具信息的辅助模块
"""
import json
from typing import Dict, Any, Optional
from utils.llm_helper import get_llm_helper
from utils.log_helper import get_logger
from database.database import SessionLocal
from models.database_models import PromptTemplate

logger = get_logger("tool_info_llm")

# 工具信息分析提示词占位（真实内容由数据库中的 tool_info_analyzer_* 管理）
# 兜底内容只在 extract_prompts_to_db.py 中维护
_DEFAULT_TOOL_INFO_SYSTEM_PROMPT = ""
_DEFAULT_TOOL_INFO_USER_PROMPT = ""


def _get_tool_info_system_prompt() -> str:
    """从数据库获取工具信息分析系统提示词，不存在时回退到内置默认值"""
    db = SessionLocal()
    try:
        template = db.query(PromptTemplate).filter(
            PromptTemplate.name == "tool_info_analyzer_system",
            PromptTemplate.template_type == "system",
            PromptTemplate.is_active == True,
        ).first()
        
        if template:
            return template.content
        else:
            # 真正的兜底内容只在 extract_prompts_to_db.py 中维护，这里只给出技术性占位文本
            logger.warning("tool_info_analyzer_system 提示词未在数据库中配置，请在 prompt_templates 表中添加或通过提示词管理界面配置。")
            return _DEFAULT_TOOL_INFO_SYSTEM_PROMPT or "tool_info_analyzer_system 提示词未在数据库中配置。"
    except Exception as exc:
        logger.warning(f"从数据库获取 tool_info_analyzer_system 提示词失败: {exc}")
        return _DEFAULT_TOOL_INFO_SYSTEM_PROMPT or "tool_info_analyzer_system 提示词获取失败，请检查数据库配置。"
    finally:
        db.close()


def _get_tool_info_user_prompt(tool_name: str, tool_description: str, tool_args: str, input_schema: str, examples: str) -> str:
    """从数据库获取工具信息分析用户提示词模板，不存在时回退到内置默认值"""
    db = SessionLocal()
    try:
        template = db.query(PromptTemplate).filter(
            PromptTemplate.name == "tool_info_analyzer_user",
            PromptTemplate.template_type == "user",
            PromptTemplate.is_active == True,
        ).first()
        
        if template:
            return template.content.format(
                tool_name=tool_name,
                tool_description=tool_description,
                tool_args=tool_args,
                input_schema=input_schema,
                examples=examples
            )
        else:
            # 真正的兜底内容只在 extract_prompts_to_db.py 中维护，这里只给出技术性占位文本
            logger.warning("tool_info_analyzer_user 提示词未在数据库中配置，请在 prompt_templates 表中添加或通过提示词管理界面配置。")
            return _DEFAULT_TOOL_INFO_USER_PROMPT or "tool_info_analyzer_user 提示词未在数据库中配置。"
    except Exception as exc:
        logger.warning(f"从数据库获取 tool_info_analyzer_user 提示词失败: {exc}")
        return _DEFAULT_TOOL_INFO_USER_PROMPT or "tool_info_analyzer_user 提示词获取失败，请检查数据库配置。"
    finally:
        db.close()


async def extract_tool_metadata_with_llm(tool_raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    使用 LLM 从原始工具数据中提取和整理有效信息
    
    Args:
        tool_raw_data: 工具的原始数据（包含 name, description, args, inputSchema 等）
    
    Returns:
        整理后的元数据字典，包含：
        - args: 参数说明（如果有）
        - usage_scenarios: 使用场景
        - notes: 注意事项
        - best_practices: 最佳实践
        - related_tools: 相关工具
        - category: 工具类别
    """
    try:
        llm_helper = get_llm_helper()
        
        # 构建提示词
        tool_name = tool_raw_data.get('name', 'unknown')
        tool_description = tool_raw_data.get('description', '')
        tool_args = tool_raw_data.get('args', {})
        input_schema = tool_raw_data.get('inputSchema', {})
        examples = tool_raw_data.get('examples', [])
        
        # 从数据库获取提示词
        system_prompt = _get_tool_info_system_prompt()
        
        tool_args_str = json.dumps(tool_args, ensure_ascii=False, indent=2) if tool_args else '无'
        input_schema_str = json.dumps(input_schema, ensure_ascii=False, indent=2) if input_schema else '无'
        examples_str = json.dumps(examples, ensure_ascii=False, indent=2) if examples else '无'
        
        user_prompt = _get_tool_info_user_prompt(
            tool_name=tool_name,
            tool_description=tool_description,
            tool_args=tool_args_str,
            input_schema=input_schema_str,
            examples=examples_str
        )

        # 调用 LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        response = await llm_helper.call(
            messages=messages,
            temperature=0.3  # 使用较低的温度以确保输出稳定
        )
        
        # 解析响应 - call 方法直接返回字符串内容
        if isinstance(response, str):
            content = response
        elif isinstance(response, dict):
            content = response.get('content', str(response))
        else:
            content = str(response)
        
        # 尝试提取 JSON（可能被代码块包裹）
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            content = content.split('```')[1].split('```')[0].strip()
        
        try:
            metadata = json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"LLM 返回的 JSON 解析失败，使用默认值。内容: {content[:200]}")
            metadata = {
                "args_description": "",
                "usage_scenarios": [],
                "notes": "",
                "best_practices": "",
                "related_tools": [],
                "category": "utility",
                "tags": []
            }
        
        logger.info(f"成功提取工具 {tool_name} 的元数据")
        return metadata
        
    except Exception as e:
        logger.error(f"使用 LLM 提取工具元数据失败: {str(e)}")
        # 返回默认值
        return {
            "args_description": "",
            "usage_scenarios": [],
            "notes": "",
            "best_practices": "",
            "related_tools": [],
            "category": "utility",
            "tags": []
        }

