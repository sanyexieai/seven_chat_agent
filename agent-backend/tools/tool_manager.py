from typing import Dict, List, Optional, Any
from tools.base_tool import BaseTool
from tools.search_tools import WebSearchTool, DocumentSearchTool
from tools.report_tools import DataAnalysisTool, ReportGeneratorTool
from tools.file_tools import FileReaderTool, FileWriterTool
from tools.builtin_tools import get_builtin_tools
from utils.log_helper import get_logger
from database.database import get_db, SessionLocal
from models.database_models import MCPTool, TemporaryTool
from agents.agent_manager import AgentManager

# 获取logger实例
logger = get_logger("tool_manager")
import asyncio
import importlib
import sys
import tempfile
import os


class MCPToolWrapper(BaseTool):
    """MCP工具包装器"""
    
    def __init__(self, mcp_tool: MCPTool, agent_manager: Optional[AgentManager] = None):
        # 优先使用数据库中存储的容器配置
        container_type = mcp_tool.container_type or BaseTool.CONTAINER_TYPE_NONE
        container_config = mcp_tool.container_config or {}
        
        # 如果数据库中没有配置，则根据工具名称推断容器类型
        if container_type == BaseTool.CONTAINER_TYPE_NONE or not container_config:
            tool_name_lower = mcp_tool.name.lower()
            if any(keyword in tool_name_lower for keyword in ['search', 'browser', 'web', 'crawl']):
                container_type = BaseTool.CONTAINER_TYPE_BROWSER
                container_config = {"browser_type": "headless", "timeout": 30}
            # 如果工具名称包含file、write、read等关键词，绑定文件容器
            elif any(keyword in tool_name_lower for keyword in ['file', 'write', 'read', 'save', 'report']):
                container_type = BaseTool.CONTAINER_TYPE_FILE
                container_config = {"workspace_dir": "mcp_tools"}
        
        super().__init__(
            name=f"mcp_{mcp_tool.server_id}_{mcp_tool.name}",
            description=mcp_tool.description or mcp_tool.display_name,
            container_type=container_type,
            container_config=container_config
        )
        self.mcp_tool = mcp_tool
        self.agent_manager = agent_manager
    
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """执行MCP工具"""
        if not self.agent_manager or not self.agent_manager.mcp_helper:
            raise RuntimeError("MCP助手未初始化")
        
        # 获取服务器名称
        db = SessionLocal()
        try:
            from models.database_models import MCPServer
            server = db.query(MCPServer).filter(MCPServer.id == self.mcp_tool.server_id).first()
            if not server:
                raise ValueError(f"MCP服务器 {self.mcp_tool.server_id} 不存在")
            server_name = server.name
        finally:
            db.close()
        
        # 调用MCP工具
        result = await self.agent_manager.mcp_helper.call_tool(
            server_name=server_name,
            tool_name=self.mcp_tool.name,
            **parameters
        )
        return result
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        if self.mcp_tool.input_schema:
            return self.mcp_tool.input_schema
        elif self.mcp_tool.tool_schema:
            return self.mcp_tool.tool_schema.get("input", {})
        else:
            return {
                "type": "object",
                "properties": {},
                "required": []
            }


class TemporaryToolWrapper(BaseTool):
    """临时工具包装器"""
    
    def __init__(self, temp_tool: TemporaryTool):
        # 优先使用数据库中存储的容器配置
        container_type = temp_tool.container_type or BaseTool.CONTAINER_TYPE_NONE
        container_config = temp_tool.container_config or {}
        
        # 如果数据库中没有配置，则根据工具名称和描述推断容器类型
        if container_type == BaseTool.CONTAINER_TYPE_NONE or not container_config:
            tool_name_lower = temp_tool.name.lower()
            description_lower = (temp_tool.description or "").lower()
            combined = f"{tool_name_lower} {description_lower}"
            
            # 如果工具名称或描述包含search、browser等关键词，绑定浏览容器
            if any(keyword in combined for keyword in ['search', 'browser', 'web', 'crawl']):
                container_type = BaseTool.CONTAINER_TYPE_BROWSER
                container_config = {"browser_type": "headless", "timeout": 30}
            # 如果工具名称或描述包含file、write、read、code等关键词，绑定文件容器
            elif any(keyword in combined for keyword in ['file', 'write', 'read', 'save', 'report', 'code', 'python']):
                container_type = BaseTool.CONTAINER_TYPE_FILE
                container_config = {"workspace_dir": "temp_tools"}
        
        super().__init__(
            name=f"temp_{temp_tool.name}",
            description=temp_tool.description or temp_tool.display_name,
            container_type=container_type,
            container_config=container_config
        )
        self.temp_tool = temp_tool
        self._compiled_code = None
        self._module = None
    
    def _compile_code(self):
        """编译工具代码"""
        if self._compiled_code is None:
            try:
                self._compiled_code = compile(self.temp_tool.code, f"<tool_{self.temp_tool.name}>", "exec")
            except SyntaxError as e:
                raise ValueError(f"工具代码语法错误: {e}")
    
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """执行临时工具"""
        self._compile_code()
        
        # 创建执行环境
        exec_globals = {
            "__name__": f"tool_{self.temp_tool.name}",
            "__builtins__": __builtins__,
        }
        exec_locals = {
            "parameters": parameters,
            "result": None
        }
        
        try:
            # 执行代码
            exec(self._compiled_code, exec_globals, exec_locals)
            
            # 获取结果
            result = exec_locals.get("result")
            if result is None:
                # 如果没有设置result，尝试从exec_locals中获取
                exec_locals.pop("parameters", None)
                exec_locals.pop("__name__", None)
                if len(exec_locals) == 1:
                    result = list(exec_locals.values())[0]
                else:
                    result = exec_locals
            
            return result
        except Exception as e:
            logger.error(f"执行临时工具 {self.temp_tool.name} 失败: {e}")
            raise RuntimeError(f"工具执行失败: {str(e)}")
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        if self.temp_tool.input_schema:
            return self.temp_tool.input_schema
        else:
            return {
                "type": "object",
                "properties": {},
                "required": []
            }

class ToolManager:
    """工具管理器 - 支持内置工具、MCP工具和临时工具"""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.tool_categories: Dict[str, List[str]] = {}
        self.tool_types: Dict[str, str] = {}  # 工具名称 -> 工具类型 (builtin, mcp, temporary)
        self.agent_manager: Optional[AgentManager] = None
        
    def set_agent_manager(self, agent_manager: AgentManager):
        """设置AgentManager引用"""
        self.agent_manager = agent_manager
        
    async def initialize(self):
        """初始化工具管理器"""
        logger.info("初始化工具管理器...")
        
        # 注册内置工具
        await self._register_builtin_tools()
        
        # 注册MCP工具
        await self._register_mcp_tools()
        
        # 注册临时工具
        await self._register_temporary_tools()
        
        # 注册默认工具（保持向后兼容）
        await self._register_default_tools()
        
        # 按类别组织工具
        self._organize_tools_by_category()
        
        logger.info(f"工具管理器初始化完成，共 {len(self.tools)} 个工具")
    
    async def _register_builtin_tools(self):
        """注册内置工具"""
        try:
            builtin_tools = get_builtin_tools()
            for tool in builtin_tools:
                self.register_tool(tool, tool_type="builtin")
            logger.info(f"注册了 {len(builtin_tools)} 个内置工具")
        except Exception as e:
            logger.error(f"注册内置工具失败: {e}")
    
    async def _register_mcp_tools(self):
        """从数据库注册MCP工具"""
        try:
            db = SessionLocal()
            try:
                mcp_tools = db.query(MCPTool).filter(MCPTool.is_active == True).all()
                for mcp_tool in mcp_tools:
                    tool = MCPToolWrapper(mcp_tool, self.agent_manager)
                    self.register_tool(tool, tool_type="mcp")
                logger.info(f"注册了 {len(mcp_tools)} 个MCP工具")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"注册MCP工具失败: {e}")
    
    async def _register_temporary_tools(self):
        """从数据库注册临时工具"""
        try:
            db = SessionLocal()
            try:
                temp_tools = db.query(TemporaryTool).filter(TemporaryTool.is_active == True).all()
                for temp_tool in temp_tools:
                    tool = TemporaryToolWrapper(temp_tool)
                    self.register_tool(tool, tool_type="temporary")
                logger.info(f"注册了 {len(temp_tools)} 个临时工具")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"注册临时工具失败: {e}")
    
    async def _register_default_tools(self):
        """注册默认工具（保持向后兼容）"""
        try:
            # 搜索工具
            web_search = WebSearchTool()
            doc_search = DocumentSearchTool()
            
            # 报告工具
            data_analysis = DataAnalysisTool()
            report_generator = ReportGeneratorTool()
            
            # 文件工具
            file_reader = FileReaderTool()
            file_writer = FileWriterTool()
            
            # 注册工具
            self.register_tool(web_search, tool_type="builtin")
            self.register_tool(doc_search, tool_type="builtin")
            self.register_tool(data_analysis, tool_type="builtin")
            self.register_tool(report_generator, tool_type="builtin")
            self.register_tool(file_reader, tool_type="builtin")
            self.register_tool(file_writer, tool_type="builtin")
            
            logger.info("默认工具注册完成")
        except Exception as e:
            logger.error(f"注册默认工具失败: {e}")
    
    def register_tool(self, tool: BaseTool, tool_type: str = "builtin"):
        """注册工具"""
        self.tools[tool.name] = tool
        self.tool_types[tool.name] = tool_type
        logger.info(f"注册工具: {tool.name} (类型: {tool_type})")
    
    def unregister_tool(self, tool_name: str):
        """注销工具"""
        if tool_name in self.tools:
            del self.tools[tool_name]
            logger.info(f"注销工具: {tool_name}")
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self.tools.get(tool_name)
    
    def get_available_tools(self, tool_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取可用工具列表"""
        tools_list = []
        for tool_name, tool in self.tools.items():
            if tool_type and self.tool_types.get(tool_name) != tool_type:
                continue
            tool_info = tool.get_info()
            tools_list.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.get_parameters_schema(),
                "category": self._get_tool_category(tool.name),
                "type": self.tool_types.get(tool_name, "unknown"),
                "container_type": tool.get_container_type(),  # 容器类型
                "container_config": tool.get_container_config()  # 容器配置
            })
        return tools_list
    
    def get_tools_by_type(self, tool_type: str) -> List[Dict[str, Any]]:
        """按类型获取工具"""
        return self.get_available_tools(tool_type=tool_type)
    
    def get_tools_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按类别获取工具"""
        tool_names = self.tool_categories.get(category, [])
        return [
            {
                "name": self.tools[name].name,
                "description": self.tools[name].description,
                "parameters": self.tools[name].get_parameters_schema(),
                "type": self.tool_types.get(name, "unknown"),
                "container_type": self.tools[name].get_container_type(),  # 容器类型
                "container_config": self.tools[name].get_container_config()  # 容器配置
            }
            for name in tool_names
            if name in self.tools
        ]
    
    def get_categories(self) -> List[str]:
        """获取所有工具类别"""
        return list(self.tool_categories.keys())
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """执行工具"""
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"工具 {tool_name} 不存在")
        
        try:
            result = await tool.execute_with_validation(parameters)
            logger.info(f"工具 {tool_name} 执行成功")
            return result
        except Exception as e:
            logger.error(f"工具 {tool_name} 执行失败: {str(e)}")
            raise
    
    async def execute_tools_chain(self, tool_chain: List[Dict[str, Any]]) -> List[Any]:
        """执行工具链"""
        results = []
        
        for tool_call in tool_chain:
            tool_name = tool_call["tool_name"]
            parameters = tool_call["parameters"]
            
            try:
                result = await self.execute_tool(tool_name, parameters)
                results.append({
                    "tool_name": tool_name,
                    "success": True,
                    "result": result
                })
            except Exception as e:
                results.append({
                    "tool_name": tool_name,
                    "success": False,
                    "error": str(e)
                })
        
        return results
    
    def _organize_tools_by_category(self):
        """按类别组织工具"""
        self.tool_categories = {
            "search": [],
            "report": [],
            "file": [],
            "utility": []
        }
        
        for tool_name, tool in self.tools.items():
            category = self._get_tool_category(tool_name)
            if category in self.tool_categories:
                self.tool_categories[category].append(tool_name)
    
    def _get_tool_category(self, tool_name: str) -> str:
        """获取工具类别"""
        if "search" in tool_name.lower():
            return "search"
        elif "report" in tool_name.lower() or "analysis" in tool_name.lower():
            return "report"
        elif "file" in tool_name.lower() or "read" in tool_name.lower() or "write" in tool_name.lower():
            return "file"
        else:
            return "utility"
    
    def search_tools(self, query: str) -> List[Dict[str, Any]]:
        """搜索工具"""
        matching_tools = []
        query_lower = query.lower()
        
        for tool in self.tools.values():
            if (query_lower in tool.name.lower() or 
                query_lower in tool.description.lower()):
                matching_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.get_parameters_schema(),
                    "category": self._get_tool_category(tool.name),
                    "type": self.tool_types.get(tool.name, "unknown"),
                    "container_type": tool.get_container_type(),  # 容器类型
                    "container_config": tool.get_container_config()  # 容器配置
                })
        
        return matching_tools
    
    def get_tool_statistics(self) -> Dict[str, Any]:
        """获取工具统计信息"""
        total_tools = len(self.tools)
        category_stats = {}
        type_stats = {}
        
        for category, tool_names in self.tool_categories.items():
            category_stats[category] = len(tool_names)
        
        for tool_type in self.tool_types.values():
            type_stats[tool_type] = type_stats.get(tool_type, 0) + 1
        
        return {
            "total_tools": total_tools,
            "categories": category_stats,
            "categories_list": list(self.tool_categories.keys()),
            "types": type_stats,
            "types_list": list(type_stats.keys())
        }
    
    async def reload_tools(self):
        """重新加载所有工具"""
        logger.info("重新加载工具...")
        self.tools.clear()
        self.tool_types.clear()
        await self.initialize()
    
    async def reload_mcp_tools(self):
        """重新加载MCP工具"""
        logger.info("重新加载MCP工具...")
        # 移除现有的MCP工具
        tools_to_remove = [name for name, tool_type in self.tool_types.items() if tool_type == "mcp"]
        for name in tools_to_remove:
            if name in self.tools:
                del self.tools[name]
                del self.tool_types[name]
        # 重新注册MCP工具
        await self._register_mcp_tools()
    
    async def reload_temporary_tools(self):
        """重新加载临时工具"""
        logger.info("重新加载临时工具...")
        # 移除现有的临时工具
        tools_to_remove = [name for name, tool_type in self.tool_types.items() if tool_type == "temporary"]
        for name in tools_to_remove:
            if name in self.tools:
                del self.tools[name]
                del self.tool_types[name]
        # 重新注册临时工具
        await self._register_temporary_tools() 