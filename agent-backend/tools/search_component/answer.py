# -*- coding: utf-8 -*-
# =====================
# 
# 
# Author: liumin.423
# Date:   2025/7/9
# =====================
import os
import time

try:
    from genie_tool.util.log_util import timer
    from genie_tool.util.prompt_util import get_prompt
except ImportError:
    # 使用适配层
    from tools.genie_tool_adapter.util.log_util import timer
    from tools.genie_tool_adapter.util.prompt_util import get_prompt

from utils.llm_helper import get_llm_helper


@timer()
async def answer_question(query: str, search_content: str):
    prompt_template = get_prompt("deepsearch")["answer_prompt"]

    model = os.getenv("SEARCH_ANSWER_MODEL", "gpt-4.1")
    answer_length = os.getenv("SEARCH_ANSWER_LENGTH", "10000")

    prompt = prompt_template.format(
        query=query,
        sub_qa=search_content,
        current_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        response_length=answer_length
    )
    
    # 使用全局统一的 llm_helper
    # 不传入配置，让它自动从数据库获取默认配置
    llm_helper = get_llm_helper()
    
    async for chunk in llm_helper.call_stream(messages=prompt):
        if chunk:
            yield chunk


if __name__ == "__main__":
    pass
