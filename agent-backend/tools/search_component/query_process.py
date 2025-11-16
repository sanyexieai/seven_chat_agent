# -*- coding: utf-8 -*-
# =====================
# 
# 
# Author: liumin.423
# Date:   2025/7/9
# =====================
import os
import re
import time

from loguru import logger

try:
    from genie_tool.util.llm_util import ask_llm
    from genie_tool.util.prompt_util import get_prompt
    from genie_tool.model.context import RequestIdCtx
    from genie_tool.util.log_util import timer
except ImportError:
    # 使用适配层
    from tools.genie_tool_adapter.util.llm_util import ask_llm
    from tools.genie_tool_adapter.util.prompt_util import get_prompt
    from tools.genie_tool_adapter.model.context import RequestIdCtx
    from tools.genie_tool_adapter.util.log_util import timer


@timer()
async def query_decompose(
        query: str,
        **kwargs
):
    model = os.getenv("QUERY_DECOMPOSE_MODEL", "gpt-4.1")
    think_model = os.getenv("QUERY_DECOMPOSE_THINK_MODEL", "gpt-4.1")
    current_date = time.strftime("%Y-%m-%d", time.localtime())
    decompose_prompt = get_prompt("deepsearch")
    # think
    think_content = ""
    async for chunk in ask_llm(
            messages=decompose_prompt["query_decompose_think_prompt"].format(task=query, retrieval_str=""),
            model=think_model,
            stream=True,
            only_content=True,  # 只返回内容
    ):
        if chunk:
            think_content += chunk

    request_id = RequestIdCtx.get() or getattr(RequestIdCtx, 'request_id', '') or ""
    logger.info(f"{request_id} query_decompose think: {think_content}")

    # decompose
    messages = [
        {
            "role": "system",
            "content": decompose_prompt["query_decompose_prompt"].format(
                current_date=current_date, max_queries=os.getenv("QUERY_DECOMPOSE_MAX_SIZE", 5))},
        {"role": "user", "content": f"思考结果：{think_content}"},
    ]
    extend_queries = ""
    async for chunk in ask_llm(
            messages=messages,
            model=model,
            stream=True,
            only_content=True,  # 只返回内容
    ):
        if chunk:
            extend_queries += chunk

    request_id = RequestIdCtx.get() or RequestIdCtx.request_id or ""
    logger.info(f"{request_id} query_decompose queries: {extend_queries}")

    # 解析
    queries = re.findall(r"^- (.+)$", extend_queries, re.MULTILINE)
    return [match.strip() for match in queries]


if __name__ == "__main__":
    pass
