"""代码解释器提示词工具"""
import os
import json
from typing import Dict, Any


# 默认提示词模板
DEFAULT_CODE_INTERPRETER_PROMPTS = {
    "task_template": """
你是一个代码解释器助手。请根据用户的任务编写Python代码。

任务: {{task}}

{% if files %}
可用文件:
{% for file in files %}
- {{file.path}}: {{file.abstract}}
{% endfor %}
{% endif %}

输出目录: {{output_dir}}

请编写代码完成任务。
"""
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
    if prompt_name == "code_interpreter":
        return DEFAULT_CODE_INTERPRETER_PROMPTS
    
    # 如果不存在，返回空字典
    return {}

