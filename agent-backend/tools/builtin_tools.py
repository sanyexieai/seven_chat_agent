# -*- coding: utf-8 -*-
"""
内置工具包装器
将内置工具包装成BaseTool接口
"""
from typing import Dict, Any, List, Optional
from tools.base_tool import BaseTool
from utils.log_helper import get_logger
import json

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
            # 动态导入，确保依赖可用
            try:
                from tools.deepsearch import DeepSearch
            except ImportError:
                try:
                    from genie_tool.tool.deepsearch import DeepSearch
                except ImportError:
                    raise RuntimeError("深度搜索工具不可用：缺少依赖 json-repair，请运行 'pip install json-repair' 安装")
            self._search_instance = DeepSearch()
        return self._search_instance
    
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """执行深度搜索"""
        # 动态检查工具是否可用，而不是依赖模块级别的标志
        # 这样即使服务器在安装依赖前启动，也能在依赖安装后正常工作
        try:
            from tools.deepsearch import DeepSearch
        except ImportError:
            try:
                from genie_tool.tool.deepsearch import DeepSearch
            except ImportError:
                raise RuntimeError("深度搜索工具不可用：缺少依赖 json-repair，请运行 'pip install json-repair' 安装")
        
        query = parameters.get("query", "")
        request_id = parameters.get("request_id", "")
        max_loop = parameters.get("max_loop", 1)
        stream = parameters.get("stream", False)
        
        search_instance = self._get_search_instance()
        
        results = []
        final_answer = ""
        all_docs = []
        
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
            
            # 尝试解析 JSON 并提取答案
            try:
                chunk_data = json.loads(chunk)
                if chunk_data.get("messageType") == "report" and chunk_data.get("answer"):
                    final_answer += chunk_data.get("answer", "")
                # 收集搜索结果
                search_result = chunk_data.get("searchResult", {})
                if search_result.get("docs"):
                    for docs_list in search_result.get("docs", []):
                        all_docs.extend(docs_list)
            except (json.JSONDecodeError, TypeError):
                # 如果不是 JSON，可能是纯文本答案
                if chunk and not chunk.startswith("{"):
                    final_answer += chunk
        
        # 如果 stream=False，解析所有结果
        if not stream:
            combined_result = "".join(results)
            try:
                # 尝试解析最后一个 JSON（通常是最终答案）
                lines = combined_result.strip().split("\n")
                for line in reversed(lines):
                    if line.strip().startswith("{"):
                        try:
                            data = json.loads(line)
                            if data.get("messageType") == "report" and data.get("answer"):
                                final_answer = data.get("answer", "")
                                break
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass
        
        # 如果有最终答案，返回答案；否则返回格式化的搜索结果
        if final_answer:
            return final_answer
        elif all_docs:
            # 格式化搜索结果
            formatted_results = [f"关于 '{query}' 的搜索结果：\n"]
            for i, doc in enumerate(all_docs[:10], 1):
                if isinstance(doc, dict):
                    title = doc.get("title", "无标题") or "无标题"
                    content = doc.get("content", "") or ""
                    link = doc.get("link", "") or ""
                else:
                    title = getattr(doc, 'title', '无标题') or '无标题'
                    content = getattr(doc, 'content', '') or ''
                    link = getattr(doc, 'link', '') or ''
                
                formatted_results.append(f"{i}. {title}")
                if content:
                    content_preview = content[:200] + "..." if len(content) > 200 else content
                    formatted_results.append(f"   内容: {content_preview}")
                if link:
                    formatted_results.append(f"   链接: {link}")
                formatted_results.append("")
            
            formatted_results.append(f"共找到 {len(all_docs)} 个相关结果")
            return "\n".join(formatted_results)
        else:
            # 如果没有结果，返回原始 JSON（用于调试）
            if stream:
                return results
            else:
                return combined_result if results else f"未找到关于 '{query}' 的搜索结果"
    
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

