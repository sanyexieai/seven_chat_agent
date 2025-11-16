# -*- coding: utf-8 -*-
"""
内置工具包装器
将内置工具包装成BaseTool接口
"""
from typing import Dict, Any, List, Optional
from tools.base_tool import BaseTool
from utils.log_helper import get_logger

logger = get_logger("builtin_tools")

# 导入内置工具
try:
    from tools.code_interpreter import code_interpreter_agent
    CODE_INTERPRETER_AVAILABLE = True
except ImportError:
    try:
        from genie_tool.tool.code_interpreter import code_interpreter_agent
        CODE_INTERPRETER_AVAILABLE = True
    except ImportError:
        CODE_INTERPRETER_AVAILABLE = False
        logger.warning("code_interpreter 工具不可用")

try:
    from tools.deepsearch import DeepSearch
    DEEPSEARCH_AVAILABLE = True
except ImportError:
    try:
        from genie_tool.tool.deepsearch import DeepSearch
        DEEPSEARCH_AVAILABLE = True
    except ImportError:
        DEEPSEARCH_AVAILABLE = False
        logger.warning("deepsearch 工具不可用")

try:
    from tools.report import report
    REPORT_AVAILABLE = True
except ImportError:
    try:
        from genie_tool.tool.report import report
        REPORT_AVAILABLE = True
    except ImportError:
        REPORT_AVAILABLE = False
        logger.warning("report 工具不可用")


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
        if not CODE_INTERPRETER_AVAILABLE:
            raise RuntimeError("代码解释器工具不可用")
        
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


class DeepSearchTool(BaseTool):
    """深度搜索工具"""
    
    def __init__(self):
        super().__init__(
            name="deepsearch",
            description="深度搜索工具，可以进行多轮搜索和推理",
            container_type=BaseTool.CONTAINER_TYPE_BROWSER,  # 绑定浏览容器
            container_config={
                "browser_type": "headless",
                "timeout": 30
            }
        )
        self._search_instance = None
    
    def _get_search_instance(self):
        """获取搜索实例"""
        if self._search_instance is None:
            self._search_instance = DeepSearch()
        return self._search_instance
    
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """执行深度搜索"""
        if not DEEPSEARCH_AVAILABLE:
            raise RuntimeError("深度搜索工具不可用")
        
        query = parameters.get("query", "")
        request_id = parameters.get("request_id", "")
        max_loop = parameters.get("max_loop", 1)
        stream = parameters.get("stream", False)
        
        search_instance = self._get_search_instance()
        
        results = []
        async for chunk in search_instance.run(
            query=query,
            request_id=request_id,
            max_loop=max_loop,
            stream=stream
        ):
            if stream:
                results.append(chunk)
            else:
                results.append(chunk)
        
        return results if stream else "".join(results)
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询"
                },
                "request_id": {
                    "type": "string",
                    "description": "请求ID",
                    "default": ""
                },
                "max_loop": {
                    "type": "integer",
                    "description": "最大搜索轮数",
                    "default": 1
                },
                "stream": {
                    "type": "boolean",
                    "description": "是否流式返回",
                    "default": False
                }
            },
            "required": ["query"]
        }


class ReportTool(BaseTool):
    """报告生成工具"""
    
    def __init__(self):
        super().__init__(
            name="report",
            description="报告生成工具，可以生成markdown、html或ppt格式的报告",
            container_type=BaseTool.CONTAINER_TYPE_FILE,  # 绑定文件容器
            container_config={
                "workspace_dir": "reports",
                "allowed_formats": ["markdown", "html", "ppt"]
            }
        )
    
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """执行报告生成"""
        if not REPORT_AVAILABLE:
            raise RuntimeError("报告生成工具不可用")
        
        task = parameters.get("task", "")
        file_names = parameters.get("file_names", [])
        model = parameters.get("model", "gpt-4.1")
        file_type = parameters.get("file_type", "markdown")
        
        results = []
        async for chunk in report(
            task=task,
            file_names=file_names,
            model=model,
            file_type=file_type
        ):
            results.append(chunk)
        
        return "".join(results)
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "报告生成任务描述"
                },
                "file_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要处理的文件名列表",
                    "default": []
                },
                "model": {
                    "type": "string",
                    "description": "使用的模型",
                    "default": "gpt-4.1"
                },
                "file_type": {
                    "type": "string",
                    "enum": ["markdown", "html", "ppt"],
                    "description": "报告类型",
                    "default": "markdown"
                }
            },
            "required": ["task"]
        }


# 内置工具列表
BUILTIN_TOOLS = [
    CodeInterpreterTool,
    DeepSearchTool,
    ReportTool,
]

def get_builtin_tools() -> List[BaseTool]:
    """获取所有可用的内置工具实例"""
    tools = []
    for tool_class in BUILTIN_TOOLS:
        try:
            tool = tool_class()
            tools.append(tool)
        except Exception as e:
            logger.warning(f"无法创建内置工具 {tool_class.__name__}: {e}")
    return tools

