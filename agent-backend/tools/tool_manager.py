from typing import Dict, List, Optional, Any
from tools.base_tool import BaseTool
from tools.search_tools import WebSearchTool, DocumentSearchTool
from tools.report_tools import DataAnalysisTool, ReportGeneratorTool
from tools.file_tools import FileReaderTool, FileWriterTool
from utils.log_helper import get_logger

# 获取logger实例
logger = get_logger("tool_manager")
import asyncio

class ToolManager:
    """工具管理器"""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.tool_categories: Dict[str, List[str]] = {}
        
    async def initialize(self):
        """初始化工具管理器"""
        logger.info("初始化工具管理器...")
        
        # 注册默认工具
        await self._register_default_tools()
        
        # 按类别组织工具
        self._organize_tools_by_category()
        
        logger.info(f"工具管理器初始化完成，共 {len(self.tools)} 个工具")
    
    async def _register_default_tools(self):
        """注册默认工具"""
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
        self.register_tool(web_search)
        self.register_tool(doc_search)
        self.register_tool(data_analysis)
        self.register_tool(report_generator)
        self.register_tool(file_reader)
        self.register_tool(file_writer)
        
        logger.info("默认工具注册完成")
    
    def register_tool(self, tool: BaseTool):
        """注册工具"""
        self.tools[tool.name] = tool
        logger.info(f"注册工具: {tool.name}")
    
    def unregister_tool(self, tool_name: str):
        """注销工具"""
        if tool_name in self.tools:
            del self.tools[tool_name]
            logger.info(f"注销工具: {tool_name}")
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self.tools.get(tool_name)
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具列表"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.get_parameters_schema(),
                "category": self._get_tool_category(tool.name)
            }
            for tool in self.tools.values()
        ]
    
    def get_tools_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按类别获取工具"""
        tool_names = self.tool_categories.get(category, [])
        return [
            {
                "name": self.tools[name].name,
                "description": self.tools[name].description,
                "parameters": self.tools[name].get_parameters_schema()
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
                    "category": self._get_tool_category(tool.name)
                })
        
        return matching_tools
    
    def get_tool_statistics(self) -> Dict[str, Any]:
        """获取工具统计信息"""
        total_tools = len(self.tools)
        category_stats = {}
        
        for category, tool_names in self.tool_categories.items():
            category_stats[category] = len(tool_names)
        
        return {
            "total_tools": total_tools,
            "categories": category_stats,
            "categories_list": list(self.tool_categories.keys())
        } 