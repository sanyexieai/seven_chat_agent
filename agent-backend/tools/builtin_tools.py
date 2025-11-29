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
        # 动态检查工具是否可用，而不是依赖模块级别的标志
        # 这样即使服务器在安装依赖前启动，也能在依赖安装后正常工作
        try:
            from tools.code_interpreter import code_interpreter_agent
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
        
        # 保存搜索结果到文件（如果启用了保存）
        save_to_file = parameters.get("save_to_file", True)  # 默认保存
        saved_file_path = None
        
        if save_to_file and (all_docs or final_answer):
            try:
                import os
                from datetime import datetime
                
                # 创建搜索结果目录
                search_results_dir = "search_results"
                os.makedirs(search_results_dir, exist_ok=True)
                
                # 生成文件名
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                # 从查询中提取关键词作为文件名（取前20个字符）
                query_slug = "".join(c for c in query[:20] if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
                if not query_slug:
                    query_slug = "search"
                
                file_path = os.path.join(search_results_dir, f"{query_slug}_{timestamp}_search_result.txt")
                
                # 准备文件内容
                file_content_parts = []
                file_content_parts.append(f"搜索查询: {query}\n")
                file_content_parts.append(f"搜索时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                file_content_parts.append(f"=" * 80 + "\n\n")
                
                if final_answer:
                    file_content_parts.append("【最终答案】\n")
                    file_content_parts.append(final_answer)
                    file_content_parts.append("\n\n")
                
                if all_docs:
                    file_content_parts.append(f"【搜索结果】共找到 {len(all_docs)} 个相关结果\n\n")
                    for i, doc in enumerate(all_docs, 1):
                        if isinstance(doc, dict):
                            title = doc.get("title", "无标题") or "无标题"
                            content = doc.get("content", "") or ""
                            link = doc.get("link", "") or ""
                        else:
                            title = getattr(doc, 'title', '无标题') or '无标题'
                            content = getattr(doc, 'content', '') or ''
                            link = getattr(doc, 'link', '') or ''
                        
                        file_content_parts.append(f"结果 {i}: {title}\n")
                        if link:
                            file_content_parts.append(f"链接: {link}\n")
                        if content:
                            file_content_parts.append(f"内容:\n{content}\n")
                        file_content_parts.append("-" * 80 + "\n\n")
                
                # 写入文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("".join(file_content_parts))
                
                # 计算相对路径（相对于项目根目录）
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                try:
                    rel_path = os.path.relpath(file_path, project_root)
                    rel_path = rel_path.replace("\\", "/")
                except ValueError:
                    rel_path = file_path.replace("\\", "/")
                
                saved_file_path = rel_path
                logger.info(f"搜索结果已保存到: {saved_file_path}")
                
            except Exception as e:
                logger.warning(f"保存搜索结果到文件失败: {str(e)}")
        
        # 如果有最终答案，返回答案；否则返回格式化的搜索结果
        if final_answer:
            result_text = final_answer
            if saved_file_path:
                result_text += f"\n\n[搜索结果已保存到文件: {saved_file_path}]"
            return result_text
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
            if saved_file_path:
                formatted_results.append(f"\n[搜索结果已保存到文件: {saved_file_path}]")
            
            # 返回结果和文件路径信息（JSON格式，方便后续节点使用）
            result_text = "\n".join(formatted_results)
            
            # 如果保存了文件，返回包含文件路径的结构化结果
            if saved_file_path:
                return {
                    "result": result_text,
                    "file_path": saved_file_path,
                    "file_name": saved_file_path,  # 兼容性：也提供 file_name
                    "doc_count": len(all_docs)
                }
            
            return result_text
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
                },
                "save_to_file": {
                    "type": "boolean",
                    "description": "是否保存搜索结果到文件（默认true，保存后可在后续节点中使用）",
                    "default": True
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
        # 动态检查工具是否可用，而不是依赖模块级别的标志
        # 这样即使服务器在安装依赖前启动，也能在依赖安装后正常工作
        try:
            from tools.report import report
        except ImportError:
            try:
                from genie_tool.tool.report import report
            except ImportError:
                raise RuntimeError(
                    "报告生成工具不可用：缺少依赖。"
                    "请确保已安装相关依赖，或安装 genie_tool 包。"
                )
        
        task = parameters.get("task", "")
        file_names = parameters.get("file_names", [])
        file_type = parameters.get("file_type", "markdown")
        output_path = parameters.get("output_path")  # 可选：指定输出路径
        
        # 过滤掉已废弃的 model 参数（如果存在）
        # model 参数已移除，现在从环境变量 REPORT_MODEL 获取
        
        results = []
        async for chunk in report(
            task=task,
            file_type=file_type,
            file_names=file_names if file_names else None
        ):
            results.append(chunk)
        
        # 合并所有结果
        report_content = "".join(results)
        
        # 保存到本地文件
        if report_content:
            try:
                import os
                from datetime import datetime
                
                # 如果没有指定输出路径，使用默认路径
                if not output_path:
                    # 使用配置的工作目录
                    workspace_dir = self.container_config.get("workspace_dir", "reports")
                    os.makedirs(workspace_dir, exist_ok=True)
                    
                    # 生成文件名：基于任务和时间戳
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    # 从任务中提取关键词作为文件名（取前20个字符）
                    task_slug = "".join(c for c in task[:20] if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
                    if not task_slug:
                        task_slug = "report"
                    
                    # 根据文件类型确定扩展名
                    ext_map = {
                        "markdown": ".md",
                        "html": ".html",
                        "ppt": ".pptx"
                    }
                    ext = ext_map.get(file_type, ".md")
                    
                    output_path = os.path.join(workspace_dir, f"{task_slug}_{timestamp}{ext}")
                
                # 确保目录存在
                output_dir = os.path.dirname(output_path)
                if output_dir:  # 只有当目录不为空时才创建
                    os.makedirs(output_dir, exist_ok=True)
                
                # 写入文件（根据文件类型选择写入模式）
                if file_type == "ppt":
                    # PPT 文件可能是二进制，但这里先按文本处理
                    # 如果后续需要支持真正的 PPT 二进制格式，需要额外处理
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(report_content)
                else:
                    # Markdown 和 HTML 文件使用文本模式
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(report_content)
                
                logger.info(f"报告已保存到: {output_path}")
                
                # 计算相对路径（相对于项目根目录）
                import os
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                try:
                    rel_path = os.path.relpath(output_path, project_root)
                    # 统一使用正斜杠作为路径分隔符（用于URL）
                    rel_path = rel_path.replace("\\", "/")
                except ValueError:
                    # 如果无法计算相对路径，使用绝对路径
                    rel_path = output_path.replace("\\", "/")
                
                # 生成下载URL
                download_url = f"/api/files/download/{rel_path}"
                
                # 返回结构化的结果，包含下载链接信息（JSON格式，方便前端解析）
                import json
                result_data = {
                    "message": "报告已生成并保存",
                    "file_path": output_path,
                    "file_name": os.path.basename(output_path),
                    "download_url": download_url,
                    "file_size": len(report_content),
                    "preview": report_content[:500] + "..." if len(report_content) > 500 else report_content,
                    "full_content": report_content  # 保留完整内容供后续使用
                }
                
                # 返回格式化的文本，包含可点击的下载链接标记
                return f"✅ 报告已生成并保存\n\n📄 文件名: {result_data['file_name']}\n📁 路径: {output_path}\n💾 大小: {len(report_content)} 字符\n\n🔗 [下载链接]({download_url})\n\n📝 内容预览:\n{result_data['preview']}\n\n<!-- REPORT_DOWNLOAD_INFO: {json.dumps(result_data, ensure_ascii=False)} -->"
            except Exception as e:
                logger.error(f"保存报告文件失败: {e}")
                # 即使保存失败，也返回报告内容
                return f"报告生成成功，但保存文件失败: {str(e)}\n\n报告内容:\n{report_content}"
        
        return report_content
    
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
                "file_type": {
                    "type": "string",
                    "enum": ["markdown", "html", "ppt"],
                    "description": "报告类型",
                    "default": "markdown"
                },
                "output_path": {
                    "type": "string",
                    "description": "输出文件路径（可选，如果不指定则自动生成）",
                    "default": None
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

