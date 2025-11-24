import asyncio
import os
import json
import logging
from typing import Dict, List, Any, Optional

# 修复 httpx.TimeoutError 兼容性问题
try:
    import httpx
    # 在新版本的 httpx 中，TimeoutError 可能不存在
    # 如果不存在，创建一个别名或使用其他异常类型
    if not hasattr(httpx, 'TimeoutError'):
        # 使用 TimeoutException 或 RequestError 作为替代
        if hasattr(httpx, 'TimeoutException'):
            httpx.TimeoutError = httpx.TimeoutException
        elif hasattr(httpx, 'Timeout'):
            httpx.TimeoutError = httpx.Timeout
        else:
            # 如果都不存在，创建一个占位符类
            class TimeoutError(Exception):
                pass
            httpx.TimeoutError = TimeoutError
except ImportError:
    pass

from langchain_mcp_adapters.client import MultiServerMCPClient

# 获取logger
logger = logging.getLogger(__name__)

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
            logger.info(f"处理服务器 {name} 的传输配置: {server}")
            
            # 如果已经有transport字段，跳过
            if "transport" in server:
                logger.info(f"服务器 {name} 已有transport配置: {server['transport']}")
                continue
            
            # 检查是否有type字段，如果有则转换为transport
            if "type" in server:
                transport_type = server["type"]
                logger.info(f"服务器 {name} 使用type字段: {transport_type}")
                
                # 转换type为transport
                if transport_type == "streamable-http":
                    server["transport"] = "streamable_http"
                elif transport_type == "stdio":
                    server["transport"] = "stdio"
                elif transport_type == "sse":
                    server["transport"] = "sse"
                elif transport_type == "websocket":
                    server["transport"] = "websocket"
                else:
                    # 尝试直接使用type值
                    server["transport"] = transport_type
                
                # 删除type字段，避免冲突
                del server["type"]
                logger.info(f"服务器 {name} 转换后transport: {server['transport']}")
                continue
            
            # 如果没有transport和type字段，则根据其他字段推断
            if "url" in server:
                url = server["url"].lower()
                logger.info(f"服务器 {name} 根据URL推断传输类型: {url}")
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
                logger.info(f"服务器 {name} 推断结果: {server['transport']}")
            elif "command" in server:
                server["transport"] = "stdio"
                logger.info(f"服务器 {name} 使用stdio传输")
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
        
        logger.info(f"MCPHelper setup - 原始配置: {config}")
        config = self.auto_infer_transport(config)
        logger.info(f"MCPHelper setup - 处理后配置: {config}")
        
        self._config = config
        logger.info(f"创建MultiServerMCPClient，配置: {config['mcpServers']}")
        self._client = MultiServerMCPClient(config["mcpServers"])
        self._tools_cache.clear()
        
        logger.info(f"MCPHelper setup - 最终配置: {self._config}")
        return self

    def get_all_services(self) -> List[str]:
        """
        查询全部服务名
        """
        if not self._client:
            raise RuntimeError("MCPHelper 未初始化，请先 setup")
        services = list(self._config["mcpServers"].keys())
        logger.info(f"获取所有服务名: {services}")
        return services
    
    async def get_available_services(self) -> List[str]:
        """
        查询实际可用的服务名（通过测试连接）
        """
        if not self._client:
            raise RuntimeError("MCPHelper 未初始化，请先 setup")
        
        logger.info(f"配置中的所有服务: {list(self._config['mcpServers'].keys())}")
        
        available_services = []
        for service_name in self._config["mcpServers"].keys():
            try:
                logger.info(f"正在测试服务 {service_name} 的连接...")
                logger.info(f"服务 {service_name} 的配置: {self._config['mcpServers'][service_name]}")
                
                # 尝试获取工具来测试连接
                tools = await self._client.get_tools(server_name=service_name)
                available_services.append(service_name)
                logger.info(f"服务 {service_name} 连接成功，获取到 {len(tools)} 个工具")
                
                # 详细记录工具信息
                for i, tool in enumerate(tools):
                    if isinstance(tool, dict):
                        tool_name = tool.get('name', 'unknown')
                        tool_desc = tool.get('description', 'no description')
                    else:
                        tool_name = getattr(tool, 'name', 'unknown')
                        tool_desc = getattr(tool, 'description', 'no description')
                    logger.info(f"  工具 {i+1}: {tool_name} - {tool_desc}")
                    
            except Exception as e:
                # 连接失败，记录错误
                logger.error(f"服务 {service_name} 连接失败: {type(e).__name__}: {e}")
                logger.error(f"服务 {service_name} 错误详情: {str(e)}")
                import traceback
                logger.error(f"服务 {service_name} 错误堆栈: {traceback.format_exc()}")
                continue
        
        logger.info(f"最终可用的服务: {available_services}")
        return available_services

    async def get_tools(self, server_name: str = None) -> List[Dict]:
        """
        查询全部工具/资源/提示（可通过服务名过滤）
        """
        if not self._client:
            raise RuntimeError("MCPHelper 未初始化，请先 setup")
        
        if server_name:
            logger.info(f"尝试从服务器 {server_name} 获取工具...")
            if server_name in self._tools_cache:
                logger.info(f"从缓存获取服务器 {server_name} 的工具，共 {len(self._tools_cache[server_name])} 个")
                return self._tools_cache[server_name]
            
            try:
                logger.info(f"从服务器 {server_name} 获取工具，配置: {self._config['mcpServers'].get(server_name, 'not found')}")
                tools = await self._client.get_tools(server_name=server_name)
                logger.info(f"从服务器 {server_name} 获取到 {len(tools)} 个工具")
                
                # 详细记录工具信息
                for i, tool in enumerate(tools):
                    if isinstance(tool, dict):
                        tool_name = tool.get('name', 'unknown')
                        tool_desc = tool.get('description', 'no description')
                    else:
                        tool_name = getattr(tool, 'name', 'unknown')
                        tool_desc = getattr(tool, 'description', 'no description')
                    logger.info(f"  工具 {i+1}: {tool_name} - {tool_desc}")
                
                self._tools_cache[server_name] = tools
                return tools
            except Exception as e:
                logger.error(f"从服务器 {server_name} 获取工具失败: {type(e).__name__}: {e}")
                logger.error(f"错误详情: {str(e)}")
                import traceback
                logger.error(f"错误堆栈: {traceback.format_exc()}")
                return []
        
        # 查询所有服务的全部工具
        logger.info("获取所有服务器的工具...")
        all_tools = []
        for name in self.get_all_services():
            tools = await self.get_tools(server_name=name)
            all_tools.extend(tools)
        logger.info(f"总共获取到 {len(all_tools)} 个工具")
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
            try:
                if hasattr(target_tool, 'invoke'):
                    result = await target_tool.ainvoke(kwargs)
                elif hasattr(target_tool, 'run'):
                    result = await target_tool.arun(kwargs)
                else:
                    # 尝试直接调用
                    result = await target_tool(**kwargs)
                
                return result
            except AttributeError as e:
                # 处理 httpx.TimeoutError 属性不存在的问题
                error_msg = str(e)
                if "TimeoutError" in error_msg or "has no attribute 'TimeoutError'" in error_msg:
                    # httpx 新版本中 TimeoutError 可能不存在，使用通用超时错误
                    raise RuntimeError("搜索超时，请稍后重试")
                else:
                    raise e
            except Exception as e:
                # 捕获所有异常，包括 httpx 相关的超时异常
                error_type = type(e).__name__
                error_msg = str(e)
                
                # 检查是否是超时相关的错误
                timeout_keywords = ["timeout", "Timeout", "timed out", "TimedOut"]
                if any(keyword in error_msg or keyword in error_type for keyword in timeout_keywords):
                    raise RuntimeError("搜索超时，请稍后重试")
                
                # 检查是否是 httpx 相关的属性错误（httpx.TimeoutError 不存在）
                if "has no attribute" in error_msg and ("TimeoutError" in error_msg or "httpx" in error_msg.lower()):
                    logger.warning(f"httpx 版本兼容性问题: {error_msg}")
                    # 尝试修复：如果是 AttributeError 且与 httpx.TimeoutError 相关，转换为超时错误
                    if "TimeoutError" in error_msg:
                        raise RuntimeError("搜索超时，请稍后重试（httpx版本兼容性问题）")
                    else:
                        raise RuntimeError(f"搜索工具调用失败: {error_type} - {error_msg}")
                
                # 其他异常直接抛出
                raise e
            
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
        #使用ddg_search工具
        result = await mcp_helper.call_tool("ddg", "search", query="python")
        print(result)

    asyncio.run(main())