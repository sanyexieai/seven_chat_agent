# -*- coding: utf-8 -*-
"""
使用 LLM 整理和提取 MCP 工具信息的辅助模块
"""
import json
from typing import Dict, Any, Optional
from utils.llm_helper import get_llm_helper
from utils.log_helper import get_logger

logger = get_logger("tool_info_llm")


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
        
        system_prompt = (
            "你是一个工具信息分析专家。请根据提供的工具原始数据，"
            "提取和整理出有用的元数据信息，包括参数说明、使用场景、注意事项等。"
            "请以 JSON 格式输出，确保信息准确、有用。"
        )
        
        user_prompt = f"""请分析以下 MCP 工具的信息，并提取有用的元数据：

工具名称：{tool_name}
工具描述：{tool_description}
参数信息：{json.dumps(tool_args, ensure_ascii=False, indent=2) if tool_args else '无'}
输入 Schema：{json.dumps(input_schema, ensure_ascii=False, indent=2) if input_schema else '无'}
示例：{json.dumps(examples, ensure_ascii=False, indent=2) if examples else '无'}

请提取以下信息并以 JSON 格式输出：
{{
  "args_description": "参数的详细说明（如果有）",
  "usage_scenarios": ["使用场景1", "使用场景2"],
  "notes": "注意事项或限制",
  "best_practices": "最佳实践建议",
  "related_tools": ["相关工具名称"],
  "category": "工具类别（如：search, file, network, utility等）",
  "tags": ["标签1", "标签2"]
}}

请确保输出是有效的 JSON 格式。"""

        # 调用 LLM
        response = await llm_helper.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3  # 使用较低的温度以确保输出稳定
        )
        
        # 解析响应
        content = response.get('content', '{}')
        
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

