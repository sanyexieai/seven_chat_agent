import asyncio
import os
import json
from typing import Dict, List, Any, Optional
from langchain_mcp_adapters.client import MultiServerMCPClient

class MCPHelper:
    """
    MCP 服务与工具管理助手，支持多服务配置、动态加载、工具/资源/提示查询。
    """
    _instance: Optional['MCPHelper'] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._client = None
            self._config = {}
            self._tools_cache = {}  # {server_name: [tools]}
            self._initialized = True

    @staticmethod
    def auto_infer_transport(mcp_config):
        """
        自动为 mcpServers 配置补全 transport 字段
        """
        servers = mcp_config.get("mcpServers", {})
        for name, server in servers.items():
            if "transport" not in server:
                # 推断 transport
                if "url" in server:
                    url = server["url"].lower()
                    if "sse" in url:
                        server["transport"] = "sse"
                    elif "ws" in url or "websocket" in url:
                        server["transport"] = "websocket"
                    elif "stream" in url:
                        server["transport"] = "streamable_http"
                    elif url.startswith("http"):
                        server["transport"] = "streamable_http"
                    else:
                        server["transport"] = "streamable_http"  # 默认
                elif "command" in server:
                    server["transport"] = "stdio"
                else:
                    raise ValueError(f"无法为 {name} 推断 transport，请手动指定")
        return mcp_config

    def setup(self, config: Dict = None, config_file: str = None) -> 'MCPHelper':
        """
        通过传入配置或配置文件加载 MCP 服务
        """
        if config_file:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        if not config:
            raise ValueError("必须传入 config 或 config_file")
        config = self.auto_infer_transport(config)
        self._config = config
        self._client = MultiServerMCPClient(config["mcpServers"])
        self._tools_cache.clear()
        return self

    def get_all_services(self) -> List[str]:
        """
        查询全部服务名
        """
        if not self._client:
            raise RuntimeError("MCPHelper 未初始化，请先 setup")
        return list(self._config["mcpServers"].keys())

    async def get_tools(self, server_name: str = None) -> List[Dict]:
        """
        查询全部工具/资源/提示（可通过服务名过滤）
        """
        if not self._client:
            raise RuntimeError("MCPHelper 未初始化，请先 setup")
        if server_name:
            if server_name in self._tools_cache:
                return self._tools_cache[server_name]
            tools = await self._client.get_tools(server_name=server_name)
            self._tools_cache[server_name] = tools
            return tools
        # 查询所有服务的全部工具
        all_tools = []
        for name in self.get_all_services():
            tools = await self.get_tools(server_name=name)
            all_tools.extend(tools)
        return all_tools

    async def get_tool_info(self, tool_name: str) -> Optional[Dict]:
        """
        通过工具名（支持 '服务名_工具名'）查询工具的描述信息/参数信息等
        """
        if not self._client:
            raise RuntimeError("MCPHelper 未初始化，请先 setup")
        # 支持 '服务名_工具名' 格式
        if '_' in tool_name:
            service, tname = tool_name.split('_', 1)
            tools = await self.get_tools(server_name=service)
            for tool in tools:
                name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)
                if name == tname:
                    return tool
        # 否则全局查找
        for name in self.get_all_services():
            tools = await self.get_tools(server_name=name)
            for tool in tools:
                tname = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)
                if tname == tool_name:
                    return tool
        return None

    async def call_tool(self, server_name: str, tool_name: str, **kwargs) -> Any:
        """
        调用指定服务器的指定工具
        """
        if not self._client:
            raise RuntimeError("MCPHelper 未初始化，请先 setup")
        
        try:
            # 获取工具列表
            tools = await self.get_tools(server_name)
            
            # 查找指定的工具
            target_tool = None
            for tool in tools:
                tool_name_attr = getattr(tool, 'name', None) or (tool.get('name') if isinstance(tool, dict) else None)
                if tool_name_attr == tool_name:
                    target_tool = tool
                    break
            
            if not target_tool:
                raise RuntimeError(f"未找到工具 {server_name}.{tool_name}")
            
            # 使用LangChain的工具调用机制
            if hasattr(target_tool, 'invoke'):
                result = await target_tool.ainvoke(kwargs)
            elif hasattr(target_tool, 'run'):
                result = await target_tool.arun(kwargs)
            else:
                # 尝试直接调用
                result = await target_tool(**kwargs)
            
            return result
            
        except Exception as e:
            raise RuntimeError(f"调用工具 {server_name}.{tool_name} 失败: {e}")

# 全局单例实例
mcp_helper = MCPHelper()

def get_mcp_helper(config: Dict = None, config_file: str = None) -> MCPHelper:
    """
    获取 MCPHelper 实例并初始化
    """
    if config or config_file:
        return mcp_helper.setup(config, config_file)
    return mcp_helper

if __name__ == "__main__":
    async def main():
        mcp_helper.setup(config_file="D:/code/ai/sevenminds/examples/mcp_servers.json")
        print(mcp_helper.get_all_services())
        print(await mcp_helper.get_tools())
        print(await mcp_helper.get_tool_info("ddg_search"))

    asyncio.run(main())