from typing import Dict, Any, List
from tools.base_tool import BaseTool
import httpx
import asyncio
from bs4 import BeautifulSoup
import json
import os

# 导入真实的搜索引擎
try:
    from tools.search_component.search_engine import MixSearch
    from tools.genie_tool_adapter.model.document import Doc
except ImportError:
    try:
        from genie_tool.tool.search_component.search_engine import MixSearch
        from genie_tool.model.document import Doc
    except ImportError:
        MixSearch = None
        Doc = None

class WebSearchTool(BaseTool):
    """网络搜索工具"""
    
    def __init__(self):
        super().__init__(
            name="web_search",
            description="在网络上搜索信息",
            container_type=BaseTool.CONTAINER_TYPE_BROWSER,  # 绑定浏览容器
            container_config={
                "browser_type": "headless",
                "timeout": 30,
                "max_results": 10
            }
        )
        self._search_engine = None
    
    def _get_search_engine(self):
        """获取搜索引擎实例"""
        if self._search_engine is None and MixSearch:
            self._search_engine = MixSearch()
        return self._search_engine
    
    async def execute(self, parameters: Dict[str, Any]) -> str:
        """执行网络搜索"""
        query = parameters.get("query", "")
        keywords = parameters.get("keywords", [])
        
        if not query:
            return "搜索查询不能为空"
        
        try:
            # 尝试使用真实的搜索引擎
            search_engine = self._get_search_engine()
            if search_engine:
                # 使用真实的搜索引擎
                docs = await search_engine.search_and_dedup(query, request_id=None)
                
                if docs:
                    # 格式化搜索结果
                    results = [f"关于 '{query}' 的搜索结果：\n"]
                    for i, doc in enumerate(docs[:10], 1):  # 最多返回10个结果
                        # Doc 对象有 title, content, link 属性
                        title = getattr(doc, 'title', '无标题') or '无标题'
                        content = getattr(doc, 'content', '') or ''
                        link = getattr(doc, 'link', '') or ''
                        
                        results.append(f"{i}. {title}")
                        if content:
                            # 截取前200个字符
                            content_preview = content[:200] + "..." if len(content) > 200 else content
                            results.append(f"   内容: {content_preview}")
                        if link:
                            results.append(f"   链接: {link}")
                        results.append("")
                    
                    results.append(f"共找到 {len(docs)} 个相关结果")
                    return "\n".join(results)
                else:
                    return f"未找到关于 '{query}' 的搜索结果"
            else:
                # 如果没有搜索引擎，返回提示信息
                return f"搜索功能暂不可用：缺少搜索引擎配置。请配置 BING_SEARCH_URL 和 BING_SEARCH_API_KEY 环境变量。"
        except Exception as e:
            return f"搜索失败: {str(e)}"
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询"
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "关键词列表"
                }
            },
            "required": ["query"]
        }

class DocumentSearchTool(BaseTool):
    """文档搜索工具"""
    
    def __init__(self):
        super().__init__(
            name="document_search",
            description="在本地文档中搜索信息",
            container_type=BaseTool.CONTAINER_TYPE_FILE,  # 绑定文件容器
            container_config={
                "workspace_dir": "documents",
                "index_format": "vector"
            }
        )
        self.documents = {}  # 模拟文档存储
    
    async def execute(self, parameters: Dict[str, Any]) -> str:
        """执行文档搜索"""
        query = parameters.get("query", "")
        keywords = parameters.get("keywords", [])
        
        if not query:
            return "搜索查询不能为空"
        
        try:
            search_results = await self._search_documents(query, keywords)
            return search_results
        except Exception as e:
            return f"文档搜索失败: {str(e)}"
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询"
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "关键词列表"
                }
            },
            "required": ["query"]
        }
    
    async def _search_documents(self, query: str, keywords: List[str]) -> str:
        """搜索文档"""
        # 模拟文档搜索
        results = [
            f"在文档中搜索 '{query}' 的结果：",
            f"1. 找到 {len(keywords)} 个相关文档",
            f"2. 匹配的文档：document1.txt, document2.pdf",
            f"3. 相关内容：{query} 在文档中有详细说明",
            f"4. 建议：查看相关章节获取更多信息"
        ]
        
        return "\n".join(results)
    
    def add_document(self, doc_id: str, content: str):
        """添加文档"""
        self.documents[doc_id] = content
    
    def remove_document(self, doc_id: str):
        """移除文档"""
        if doc_id in self.documents:
            del self.documents[doc_id] 