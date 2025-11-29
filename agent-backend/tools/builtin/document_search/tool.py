# -*- coding: utf-8 -*-
"""
文档搜索工具
"""
from typing import Dict, Any, List
from tools.base_tool import BaseTool


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
