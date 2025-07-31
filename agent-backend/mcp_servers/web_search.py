#!/usr/bin/env python3
"""
MCP搜索服务器 - 使用LangChain工具格式
"""

import asyncio
import json
import sys
from typing import Any, Dict, List
import requests
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

class SearchInput(BaseModel):
    query: str = Field(description="Search query")

class WebSearchTool(BaseTool):
    name = "search"
    description = "Search the web for information"
    args_schema = SearchInput
    
    async def _arun(self, query: str) -> str:
        """执行网络搜索"""
        try:
            # 使用DuckDuckGo API进行搜索
            url = "https://api.duckduckgo.com/"
            params = {
                'q': query,
                'format': 'json',
                'no_html': '1',
                'skip_disambig': '1'
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            # 提取搜索结果
            results = []
            if 'Abstract' in data and data['Abstract']:
                results.append(f"摘要: {data['Abstract']}")
            
            if 'RelatedTopics' in data:
                for topic in data['RelatedTopics'][:3]:
                    if 'Text' in topic:
                        results.append(f"- {topic['Text']}")
            
            if results:
                return "\n".join(results)
            else:
                return f"搜索'{query}'没有找到相关结果。"
                
        except Exception as e:
            return f"搜索失败: {str(e)}"
    
    def _run(self, query: str) -> str:
        """同步执行搜索"""
        try:
            # 使用DuckDuckGo API进行搜索
            url = "https://api.duckduckgo.com/"
            params = {
                'q': query,
                'format': 'json',
                'no_html': '1',
                'skip_disambig': '1'
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            # 提取搜索结果
            results = []
            if 'Abstract' in data and data['Abstract']:
                results.append(f"摘要: {data['Abstract']}")
            
            if 'RelatedTopics' in data:
                for topic in data['RelatedTopics'][:3]:
                    if 'Text' in topic:
                        results.append(f"- {topic['Text']}")
            
            if results:
                return "\n".join(results)
            else:
                return f"搜索'{query}'没有找到相关结果。"
                
        except Exception as e:
            return f"搜索失败: {str(e)}"

# 创建工具实例
search_tool = WebSearchTool()

if __name__ == '__main__':
    # 测试工具
    result = search_tool.run("Python programming")
    print(result) 