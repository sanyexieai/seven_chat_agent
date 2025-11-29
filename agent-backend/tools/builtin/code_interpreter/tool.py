# -*- coding: utf-8 -*-
"""
代码解释器工具
"""
from typing import Dict, Any
from tools.base_tool import BaseTool
from utils.log_helper import get_logger

logger = get_logger("code_interpreter_tool")


class CodeInterpreterTool(BaseTool):
    """代码解释器工具"""
    
    def __init__(self):
        super().__init__(
            name="code_interpreter",
            description="代码解释器工具，可以执行Python代码并处理文件",
            container_type=BaseTool.CONTAINER_TYPE_FILE,  # 绑定文件容器
            container_config={
                "workspace_dir": "code_output",
                "allowed_extensions": [".py", ".txt", ".md", ".csv", ".xlsx", ".json"]
            }
        )
    
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """执行代码解释器"""
        # 动态检查工具是否可用，而不是依赖模块级别的标志
        # 这样即使服务器在安装依赖前启动，也能在依赖安装后正常工作
        try:
            from tools.builtin.code_interpreter.code_interpreter_impl import code_interpreter_agent
        except ImportError:
            try:
                from genie_tool.tool.code_interpreter import code_interpreter_agent
            except ImportError:
                raise RuntimeError(
                    "代码解释器工具不可用：缺少依赖。"
                    "请确保已安装 smolagents 和相关依赖，或安装 genie_tool 包。"
                )
        
        task = parameters.get("task", "")
        file_names = parameters.get("file_names", [])
        max_file_abstract_size = parameters.get("max_file_abstract_size", 2000)
        max_tokens = parameters.get("max_tokens", 32000)
        request_id = parameters.get("request_id", "")
        stream = parameters.get("stream", False)
        
        results = []
        async for chunk in code_interpreter_agent(
            task=task,
            file_names=file_names,
            max_file_abstract_size=max_file_abstract_size,
            max_tokens=max_tokens,
            request_id=request_id,
            stream=stream
        ):
            if stream:
                results.append(chunk)
            else:
                results.append(chunk)
        
        return results if stream else (results[0] if results else None)
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "要执行的任务描述"
                },
                "file_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要处理的文件名列表",
                    "default": []
                },
                "max_file_abstract_size": {
                    "type": "integer",
                    "description": "文件摘要最大大小",
                    "default": 2000
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "最大token数",
                    "default": 32000
                },
                "request_id": {
                    "type": "string",
                    "description": "请求ID",
                    "default": ""
                },
                "stream": {
                    "type": "boolean",
                    "description": "是否流式返回",
                    "default": False
                }
            },
            "required": ["task"]
        }
