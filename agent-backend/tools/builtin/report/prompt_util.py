"""报告生成提示词工具"""
import os
import json
from typing import Dict, Any


# 默认提示词模板
DEFAULT_REPORT_PROMPTS = {
    "markdown_prompt": "请根据以下内容生成Markdown格式的报告。\n任务：{task}\n文件：{files}\n当前时间：{current_time}",
    "html_prompt": "请根据以下内容生成HTML格式的报告。",
    "html_task": "任务：{task}\n关键文件：{key_files}\n其他文件：{files}\n日期：{date}",
    "ppt_prompt": "请根据以下内容生成PPT格式的报告。\n任务：{task}\n文件：{files}\n日期：{date}"
}


def get_prompt(prompt_name: str) -> Dict[str, Any]:
    """获取提示词模板"""
    # 首先尝试从环境变量或配置文件加载
    prompt_file = os.getenv(f"{prompt_name.upper()}_PROMPT_FILE")
    if prompt_file and os.path.exists(prompt_file):
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    
    # 使用默认模板
    if prompt_name == "report":
        return DEFAULT_REPORT_PROMPTS
    
    # 如果不存在，返回空字典
    return {}

