# -*- coding: utf-8 -*-
"""
提示词工具适配
"""
import os
import json
from typing import Dict, Any
from pathlib import Path


# 默认提示词模板
DEFAULT_PROMPTS = {
    "code_interpreter": {
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
    },
    "deepsearch": {
        "query_decompose_think_prompt": "请思考如何分解以下查询：{task}\n检索到的内容：{retrieval_str}",
        "query_decompose_prompt": "当前日期：{current_date}\n请将查询分解为最多{max_queries}个子查询，每行一个，格式：- 子查询内容",
        "answer_prompt": "查询：{query}\n搜索结果：{sub_qa}\n当前时间：{current_time}\n请根据搜索结果回答问题，回答长度约{response_length}字。",
        "reasoning_prompt": "查询：{query}\n历史查询：{sub_queries}\n内容：{content}\n日期：{date}\n请判断是否需要继续搜索。"
    },
    "report": {
        "markdown_prompt": "请根据以下内容生成Markdown格式的报告。\n任务：{task}\n文件：{files}\n当前时间：{current_time}",
        "html_prompt": "请根据以下内容生成HTML格式的报告。",
        "html_task": "任务：{task}\n关键文件：{key_files}\n其他文件：{files}\n日期：{date}",
        "ppt_prompt": "请根据以下内容生成PPT格式的报告。\n任务：{task}\n文件：{files}\n日期：{date}"
    }
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
    if prompt_name in DEFAULT_PROMPTS:
        return DEFAULT_PROMPTS[prompt_name]
    
    # 如果不存在，返回空字典
    return {}

