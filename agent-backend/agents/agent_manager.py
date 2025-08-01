from typing import Dict, Optional, AsyncGenerator, Any
from agents.base_agent import BaseAgent
from agents.chat_agent import ChatAgent
from agents.search_agent import SearchAgent
from agents.report_agent import ReportAgent
from agents.prompt_driven_agent import PromptDrivenAgent
from agents.tool_driven_agent import ToolDrivenAgent
from models.chat_models import AgentMessage, StreamChunk, AgentContext
from utils.log_helper import get_logger
from database.database import SessionLocal
from models.database_models import Agent as DBAgent, MCPServer, MCPTool as DBMCPTool
from utils.mcp_helper import get_mcp_helper

# 获取logger实例
logger = get_logger("agent_manager")
import asyncio
import uuid
import json

class AgentManager:
    """智能体管理器"""
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.user_sessions: Dict[str, str] = {}  # user_id -> session_id
        self.session_contexts: Dict[str, AgentContext] = {}  # session_id -> context
        self.mcp_configs: Dict[str, Dict] = {}  # MCP配置缓存
        self.mcp_helper = None  # MCP助手实例
        
    async def initialize(self):
        """初始化智能体管理器"""
        logger.info("初始化智能体管理器...")
        
        # 检查数据库表
        await self._check_database_tables()
        
        # 加载MCP配置
        await self._load_mcp_configs()
        
        # 创建默认智能体
        await self._create_default_agents()
        
        logger.info(f"智能体管理器初始化完成，共 {len(self.agents)} 个智能体，{len(self.mcp_configs)} 个MCP配置")
        logger.info(f"初始化完成后的MCP配置: {list(self.mcp_configs.keys())}")
        logger.info(f"初始化完成后的MCP配置详情: {self.mcp_configs}")
    
    async def _load_mcp_configs(self):
        """从数据库加载MCP配置"""
        db = SessionLocal()
        try:
            logger.info("开始从数据库加载MCP配置...")
            # 从数据库获取所有激活的MCP服务器
            db_mcp_servers = db.query(MCPServer).filter(MCPServer.is_active == True).all()
            logger.info(f"从数据库查询到 {len(db_mcp_servers)} 个MCP服务器")
            
            for db_server in db_mcp_servers:
                logger.info(f"处理服务器: {db_server.name} - 激活状态: {db_server.is_active}")
                
                # 构建服务器配置
                server_config = {
                    'transport': db_server.transport
                }
                
                if db_server.command:
                    server_config['command'] = db_server.command
                if db_server.args:
                    server_config['args'] = db_server.args
                if db_server.env:
                    server_config['env'] = db_server.env
                if db_server.url:
                    server_config['url'] = db_server.url
                
                logger.info(f"服务器 {db_server.name} 配置: {server_config}")
                
                self.mcp_configs[db_server.name] = {
                    'id': db_server.id,
                    'name': db_server.name,
                    'display_name': db_server.display_name,
                    'description': db_server.description,
                    'server_config': server_config,
                    'is_active': db_server.is_active,
                    'tools': []
                }
                logger.info(f"加载服务器配置: {db_server.name} -> {server_config}")
                
                # 加载该服务器的工具
                tools = db.query(DBMCPTool).filter(
                    DBMCPTool.server_id == db_server.id,
                    DBMCPTool.is_active == True
                ).all()
                
                for tool in tools:
                    self.mcp_configs[db_server.name]['tools'].append({
                        'id': tool.id,
                        'name': tool.name,
                        'display_name': tool.display_name,
                        'description': tool.description,
                        'tool_type': tool.tool_type,
                        'input_schema': tool.input_schema,
                        'output_schema': tool.output_schema,
                        'examples': tool.examples
                    })
                
                logger.info(f"加载MCP服务器: {db_server.name} ({db_server.display_name}) - {len(tools)} 个工具")
            
            # 初始化MCP助手
            if self.mcp_configs:
                logger.info(f"开始初始化MCP助手，配置数量: {len(self.mcp_configs)}")
                await self._initialize_mcp_helper()
            else:
                logger.warning("没有MCP配置，跳过MCP助手初始化")
                logger.info(f"从数据库加载了 {len(self.mcp_configs)} 个MCP服务器")
                logger.info(f"当前MCP配置: {list(self.mcp_configs.keys())}")
                logger.info(f"MCP配置详情: {self.mcp_configs}")
                
                # 检查每个服务器的配置
                for name, config in self.mcp_configs.items():
                    logger.info(f"服务器 {name} 配置: {config['server_config']}")
                
                # 检查是否所有服务器都被正确加载
                expected_servers = ['ddg', 'google', 'browser']
                missing_servers = [s for s in expected_servers if s not in self.mcp_configs]
                if missing_servers:
                    logger.error(f"缺少的服务器: {missing_servers}")
                else:
                    logger.info("所有服务器都已正确加载")
            
            # 如果没有加载到任何配置，创建默认配置
            if not self.mcp_configs:
                logger.info("数据库中没有MCP配置，创建默认配置...")
                await self._create_fallback_mcp_configs()
            
        except Exception as e:
            logger.error(f"从数据库加载MCP配置失败: {str(e)}")
            # 如果数据库加载失败，使用默认配置
            await self._create_fallback_mcp_configs()
        finally:
            db.close()
    
    async def _create_fallback_mcp_configs(self):
        """创建默认MCP配置（备用方案）"""
        try:
            # 读取默认配置文件
            import os
            from config.env import MCP_CONFIG_FILE
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), MCP_CONFIG_FILE)
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    default_config = json.load(f)
                
                # 将默认配置添加到数据库
                await self._save_default_mcp_configs(default_config)
                
                # 重新从数据库加载配置到内存
                await self._load_mcp_configs()
                
                logger.info("创建默认MCP配置完成")
            else:
                logger.warning("未找到默认MCP配置文件")
                
        except Exception as e:
            logger.error(f"创建默认MCP配置失败: {str(e)}")
    
    async def _check_database_tables(self):
        """检查数据库表是否存在"""
        db = SessionLocal()
        try:
            logger.info("检查数据库表...")
            
            # 检查MCPServer表
            try:
                server_count = db.query(MCPServer).count()
                logger.info(f"MCPServer表存在，有 {server_count} 条记录")
            except Exception as e:
                logger.error(f"MCPServer表不存在或查询失败: {str(e)}")
            
            # 检查MCPTool表
            try:
                tool_count = db.query(DBMCPTool).count()
                logger.info(f"MCPTool表存在，有 {tool_count} 条记录")
            except Exception as e:
                logger.error(f"MCPTool表不存在或查询失败: {str(e)}")
            
            # 检查Agent表
            try:
                agent_count = db.query(DBAgent).count()
                logger.info(f"Agent表存在，有 {agent_count} 条记录")
            except Exception as e:
                logger.error(f"Agent表不存在或查询失败: {str(e)}")
                
        except Exception as e:
            logger.error(f"检查数据库表失败: {str(e)}")
        finally:
            db.close()
    
    async def _save_default_mcp_configs(self, config: Dict):
        """保存默认MCP配置到数据库"""
        db = SessionLocal()
        try:
            for name, server_config in config.get('mcpServers', {}).items():
                # 检查是否已存在
                existing = db.query(MCPServer).filter(MCPServer.name == name).first()
                if not existing:
                    # 创建新的MCP服务器
                    mcp_server = MCPServer(
                        name=name,
                        display_name=f"{name.upper()} MCP服务器",
                        description=f"默认{name} MCP服务器配置",
                        transport=server_config.get('transport', 'stdio'),
                        command=server_config.get('command'),
                        args=server_config.get('args'),
                        env=server_config.get('env'),
                        url=server_config.get('url'),
                        is_active=True
                    )
                    db.add(mcp_server)
                    db.flush()  # 获取ID
                    
                    # 这里可以添加默认工具，但需要实际连接到MCP服务器获取工具列表
                    # 暂时跳过工具创建，等MCP助手初始化后再同步工具信息
            
            db.commit()
            logger.info("默认MCP服务器配置已保存到数据库")
            
        except Exception as e:
            logger.error(f"保存默认MCP配置失败: {str(e)}")
            db.rollback()
        finally:
            db.close()
    
    async def _initialize_mcp_helper(self):
        """初始化MCP助手"""
        try:
            if self.mcp_configs:
                logger.info(f"MCP配置详情: {self.mcp_configs}")
                
                # 构建MCP配置
                mcp_config = {
                    "mcpServers": {
                        name: config['server_config'] 
                        for name, config in self.mcp_configs.items()
                    }
                }
                
                logger.info(f"初始化MCP助手，配置: {list(mcp_config['mcpServers'].keys())}")
                logger.info(f"MCP配置内容: {mcp_config}")
                
                # 检查每个服务器的配置
                for name, server_config in mcp_config['mcpServers'].items():
                    logger.info(f"服务器 {name} 配置: {server_config}")
                
                # 初始化MCP助手
                self.mcp_helper = get_mcp_helper(config=mcp_config)
                logger.info("MCP助手初始化成功")
                
                # 检查可用的服务
                available_services = self.mcp_helper.get_all_services()
                logger.info(f"MCP助手初始化后，可用服务: {available_services}")
                
            else:
                logger.warning("没有可用的MCP配置")
                # 即使没有配置，也尝试初始化一个空的MCP助手
                try:
                    self.mcp_helper = get_mcp_helper(config={"mcpServers": {}})
                    logger.info("初始化空的MCP助手")
                except Exception as e:
                    logger.warning(f"初始化空MCP助手失败: {str(e)}")
                    self.mcp_helper = None
                
        except Exception as e:
            logger.error(f"MCP助手初始化失败: {str(e)}")
            logger.error(f"错误详情: {type(e).__name__}: {e}")
            self.mcp_helper = None
    
    async def _create_default_agents(self):
        """从数据库加载智能体"""
        db = SessionLocal()
        try:
            # 从数据库获取所有激活的智能体
            db_agents = db.query(DBAgent).filter(DBAgent.is_active == True).all()
            logger.info(f"从数据库查询到 {len(db_agents)} 个激活的智能体")
            for db_agent in db_agents:
                logger.info(f"数据库智能体: {db_agent.name} - {db_agent.display_name} - 类型: {db_agent.agent_type} - 激活: {db_agent.is_active}")
            logger.info(f"从数据库查询到 {len(db_agents)} 个激活的智能体")
            for db_agent in db_agents:
                logger.info(f"数据库智能体: {db_agent.name} - {db_agent.display_name} - 类型: {db_agent.agent_type} - 激活: {db_agent.is_active}")
            
            for db_agent in db_agents:
                # 根据智能体类型创建相应的智能体实例
                if db_agent.agent_type == "chat":
                    agent = ChatAgent(db_agent.name, db_agent.display_name)
                elif db_agent.agent_type == "search":
                    agent = SearchAgent(db_agent.name, db_agent.display_name)
                elif db_agent.agent_type == "report":
                    agent = ReportAgent(db_agent.name, db_agent.display_name)
                elif db_agent.agent_type == "prompt_driven":
                    # 纯提示词驱动智能体
                    system_prompt = db_agent.system_prompt
                    logger.info(f"加载提示词驱动智能体 {db_agent.name}，系统提示词: {system_prompt}")
                    agent = PromptDrivenAgent(db_agent.name, db_agent.display_name, system_prompt)
                elif db_agent.agent_type == "tool_driven":
                    # 纯工具驱动智能体
                    bound_tools = db_agent.bound_tools or []
                    logger.info(f"创建工具驱动智能体 {db_agent.name}，绑定工具: {bound_tools}")
                    agent = ToolDrivenAgent(db_agent.name, db_agent.display_name, bound_tools)
                elif db_agent.agent_type == "flow_driven":
                    # 流程图驱动智能体（暂时使用提示词驱动作为占位符）
                    logger.warning(f"流程图驱动智能体 {db_agent.name} 暂未实现，使用提示词驱动作为占位符")
                    system_prompt = db_agent.system_prompt or "你是一个流程图驱动的智能体，但目前功能还在开发中。"
                    agent = PromptDrivenAgent(db_agent.name, db_agent.display_name, system_prompt)
                else:
                    # 默认使用聊天智能体
                    agent = ChatAgent(db_agent.name, db_agent.display_name)
                
                # 设置智能体配置
                if db_agent.config:
                    agent.config = db_agent.config
                
                # 设置MCP助手（只对需要MCP的智能体）
                if self.mcp_helper:
                    if db_agent.agent_type == "tool_driven":
                        # 工具驱动智能体需要MCP助手
                        agent.mcp_helper = self.mcp_helper
                        logger.info(f"工具驱动智能体 {db_agent.name} 设置MCP助手")
                    elif db_agent.agent_type in ["chat", "search", "report"]:
                        # 传统智能体也需要MCP助手（向后兼容）
                        agent.mcp_helper = self.mcp_helper
                        logger.info(f"传统智能体 {db_agent.name} 设置MCP助手")
                    else:
                        # 提示词驱动智能体不需要MCP助手
                        logger.info(f"提示词驱动智能体 {db_agent.name} 不设置MCP助手")
                
                self.agents[db_agent.name] = agent
                logger.info(f"加载智能体: {db_agent.name} ({db_agent.display_name}) - 类型: {db_agent.agent_type}")
            
            logger.info(f"从数据库加载了 {len(self.agents)} 个智能体")
            
        except Exception as e:
            logger.error(f"从数据库加载智能体失败: {str(e)}")
            # 如果数据库加载失败，创建默认智能体
            await self._create_fallback_agents()
        finally:
            db.close()
    
    async def _create_fallback_agents(self):
        """创建默认智能体（备用方案）"""
        # 聊天智能体
        chat_agent = ChatAgent("chat_agent", "通用聊天智能体")
        if self.mcp_helper:
            chat_agent.mcp_helper = self.mcp_helper
        self.agents["chat_agent"] = chat_agent
        
        # 搜索智能体
        search_agent = SearchAgent("search_agent", "搜索和信息检索智能体")
        if self.mcp_helper:
            search_agent.mcp_helper = self.mcp_helper
        self.agents["search_agent"] = search_agent
        
        # 报告智能体
        report_agent = ReportAgent("report_agent", "报告生成智能体")
        if self.mcp_helper:
            report_agent.mcp_helper = self.mcp_helper
        self.agents["report_agent"] = report_agent
        
        # 提示词驱动智能体（不需要MCP助手）
        prompt_agent = PromptDrivenAgent("prompt_agent", "提示词驱动智能体")
        self.agents["prompt_agent"] = prompt_agent
        logger.info("创建提示词驱动智能体，不设置MCP助手")
        
        # 工具驱动智能体（需要MCP助手）
        tool_agent = ToolDrivenAgent("tool_agent", "工具驱动智能体", ["web_search", "file_search"])
        if self.mcp_helper:
            tool_agent.mcp_helper = self.mcp_helper
            logger.info("工具驱动智能体设置MCP助手")
        self.agents["tool_agent"] = tool_agent
        
        logger.info("创建默认智能体完成")
    
    def get_session_id(self, user_id: str) -> str:
        """获取或创建会话ID"""
        if user_id not in self.user_sessions:
            session_id = str(uuid.uuid4())
            self.user_sessions[user_id] = session_id
            self.session_contexts[session_id] = AgentContext(
                user_id=user_id,
                session_id=session_id
            )
        return self.user_sessions[user_id]
    
    def get_context(self, user_id: str) -> AgentContext:
        """获取用户上下文"""
        session_id = self.get_session_id(user_id)
        return self.session_contexts[session_id]
    
    def update_context(self, user_id: str, context: AgentContext):
        """更新用户上下文"""
        session_id = self.get_session_id(user_id)
        self.session_contexts[session_id] = context
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        try:
            # 获取或创建会话
            session_id = self.get_session_id(user_id)
            agent_context = self.get_context(user_id)
            
            # 如果上下文为空，创建一个新的
            if agent_context is None:
                agent_context = AgentContext(
                    user_id=user_id,
                    session_id=session_id,
                    messages=[],
                    metadata={}
                )
                self.update_context(user_id, agent_context)
            
            # 选择智能体（这里简化处理，实际可以根据消息内容智能选择）
            agent = self._select_agent(message)
            
            # 处理消息
            response = await agent.process_message(user_id, message, context)
            
            # 更新上下文
            agent_context.messages.append(response)
            self.update_context(user_id, agent_context)
            
            return response
            
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}")
            raise
    
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息"""
        try:
            # 获取或创建会话
            session_id = self.get_session_id(user_id)
            agent_context = self.get_context(user_id)
            
            # 选择智能体
            agent = self._select_agent(message)
            
            # 流式处理消息
            async for chunk in agent.process_message_stream(user_id, message, context):
                yield chunk
                
                # 如果是最终响应，更新上下文
                if chunk.type == "final":
                    # 这里可以添加消息到上下文
                    pass
                    
        except Exception as e:
            logger.error(f"流式处理消息失败: {str(e)}")
            yield StreamChunk(
                type="error",
                content=f"处理消息时出错: {str(e)}"
            )
    
    def _select_agent(self, message: str) -> BaseAgent:
        """选择智能体（简化版本）"""
        logger.info(f"选择智能体，用户消息: {message}")
        logger.info(f"当前可用智能体: {list(self.agents.keys())}")
        
        # 使用已经加载到内存中的智能体实例
        available_agents = list(self.agents.keys())
        
        # 根据消息内容选择最合适的智能体
        selected = None
        
        # 根据关键词匹配智能体
        if any(keyword in message.lower() for keyword in ["翻译", "translate"]):
            for name in available_agents:
                if "翻译" in name or "translate" in name.lower():
                    selected = self.agents[name]
                    break
        elif any(keyword in message.lower() for keyword in ["代码", "编程", "code", "program"]):
            for name in available_agents:
                if "代码" in name or "code" in name.lower():
                    selected = self.agents[name]
                    break
        elif any(keyword in message.lower() for keyword in ["写作", "write", "文章"]):
            for name in available_agents:
                if "写作" in name or "write" in name.lower():
                    selected = self.agents[name]
                    break
        elif any(keyword in message.lower() for keyword in ["搜索", "查找", "查询", "search", "find"]):
            for name in available_agents:
                if "搜索" in name or "search" in name.lower():
                    selected = self.agents[name]
                    break
        elif any(keyword in message.lower() for keyword in ["报告", "总结", "分析", "report", "summary"]):
            for name in available_agents:
                if "报告" in name or "report" in name.lower():
                    selected = self.agents[name]
                    break
        
        # 如果没有匹配的关键词，优先选择提示词驱动智能体
        if not selected:
            for name, agent in self.agents.items():
                if isinstance(agent, PromptDrivenAgent):
                    selected = agent
                    break
        
        # 如果还是没有，选择第一个可用的智能体
        if not selected:
            selected = list(self.agents.values())[0]
        
        logger.info(f"选择智能体: {selected.name}")
        return selected
    
    # MCP配置管理方法
    async def get_mcp_configs(self) -> Dict[str, Any]:
        """获取所有MCP配置"""
        return self.mcp_configs
    
    async def update_mcp_server(self, name: str, config: Dict[str, Any]) -> bool:
        """更新MCP服务器配置"""
        try:
            db = SessionLocal()
            db_server = db.query(MCPServer).filter(MCPServer.name == name).first()
            
            if db_server:
                # 更新现有配置
                for key, value in config.items():
                    if hasattr(db_server, key):
                        setattr(db_server, key, value)
                
                db.commit()
                
                # 重新加载配置
                await self._load_mcp_configs()
                
                logger.info(f"MCP服务器 {name} 更新成功")
                return True
            else:
                logger.error(f"MCP服务器 {name} 不存在")
                return False
                
        except Exception as e:
            logger.error(f"更新MCP服务器失败: {str(e)}")
            return False
        finally:
            db.close()
    
    async def create_mcp_server(self, config: Dict[str, Any]) -> bool:
        """创建新的MCP服务器"""
        try:
            db = SessionLocal()
            
            # 检查是否已存在
            existing = db.query(MCPServer).filter(MCPServer.name == config['name']).first()
            if existing:
                logger.error(f"MCP服务器 {config['name']} 已存在")
                return False
            
            # 创建新服务器
            mcp_server = MCPServer(
                name=config['name'],
                display_name=config['display_name'],
                description=config.get('description'),
                transport=config['transport'],
                command=config.get('command'),
                args=config.get('args'),
                env=config.get('env'),
                url=config.get('url'),
                is_active=config.get('is_active', True)
            )
            
            db.add(mcp_server)
            db.commit()
            
            # 重新加载配置
            await self._load_mcp_configs()
            
            logger.info(f"MCP服务器 {config['name']} 创建成功")
            return True
            
        except Exception as e:
            logger.error(f"创建MCP服务器失败: {str(e)}")
            return False
        finally:
            db.close()
    
    async def sync_mcp_tools(self, server_name: str) -> bool:
        """同步MCP服务器工具信息"""
        db = None
        try:
            logger.info(f"开始同步MCP工具，服务器: {server_name}")
            logger.info(f"当前MCP配置: {list(self.mcp_configs.keys())}")
            logger.info(f"MCP配置详情: {self.mcp_configs}")
            logger.info(f"MCP助手状态: {self.mcp_helper is not None}")
            
            # 检查服务器是否在配置中
            if server_name not in self.mcp_configs:
                logger.error(f"服务器 {server_name} 不在MCP配置中")
                logger.error(f"当前可用的服务器: {list(self.mcp_configs.keys())}")
                return False
            
            # 如果MCP助手未初始化，重新初始化
            if not self.mcp_helper:
                logger.info("MCP助手未初始化，重新初始化...")
                await self._initialize_mcp_helper()
                if not self.mcp_helper:
                    logger.error("MCP助手初始化失败")
                    return False
                else:
                    logger.info("MCP助手重新初始化成功")
            else:
                logger.info("MCP助手已初始化")
            
            # 获取服务器工具
            logger.info(f"尝试获取服务器 {server_name} 的工具...")
            try:
                tools = await self.mcp_helper.get_tools(server_name=server_name)
                logger.info(f"成功获取到 {len(tools)} 个工具")
            except Exception as e:
                logger.error(f"获取工具失败: {str(e)}")
                # 如果获取工具失败，返回空列表而不是失败
                tools = []
                logger.info("使用空工具列表继续执行")
            
            db = SessionLocal()
            db_server = db.query(MCPServer).filter(MCPServer.name == server_name).first()
            
            if not db_server:
                logger.error(f"MCP服务器 {server_name} 不存在")
                return False
            
            # 清除现有工具
            db.query(DBMCPTool).filter(DBMCPTool.server_id == db_server.id).delete()
            
            # 添加新工具
            for tool in tools:
                # 处理不同类型的工具对象
                tool_name = ''
                tool_display_name = ''
                tool_description = ''
                tool_type = 'tool'
                input_schema = {}
                output_schema = {}
                examples = []
                
                # 如果是字典类型
                if isinstance(tool, dict):
                    tool_name = tool.get('name', '')
                    tool_display_name = tool.get('displayName', '')
                    tool_description = tool.get('description', '')
                    tool_type = tool.get('type', 'tool')
                    input_schema = tool.get('inputSchema', {})
                    output_schema = tool.get('outputSchema', {})
                    examples = tool.get('examples', [])
                # 如果是StructuredTool对象
                elif hasattr(tool, 'name'):
                    tool_name = getattr(tool, 'name', '')
                    tool_display_name = getattr(tool, 'display_name', '')
                    tool_description = getattr(tool, 'description', '')
                    tool_type = getattr(tool, 'type', 'tool')
                    
                    # 处理input_schema和output_schema，确保它们是可序列化的
                    input_schema_raw = getattr(tool, 'input_schema', {})
                    output_schema_raw = getattr(tool, 'output_schema', {})
                    
                    # 如果是类对象，尝试获取其schema
                    if hasattr(input_schema_raw, 'schema'):
                        try:
                            input_schema = input_schema_raw.schema()
                        except:
                            input_schema = {}
                    else:
                        input_schema = input_schema_raw
                    
                    if hasattr(output_schema_raw, 'schema'):
                        try:
                            output_schema = output_schema_raw.schema()
                        except:
                            output_schema = {}
                    else:
                        output_schema = output_schema_raw
                    
                    examples = getattr(tool, 'examples', [])
                # 如果是其他对象，尝试获取属性
                else:
                    try:
                        tool_name = str(getattr(tool, 'name', ''))
                        tool_display_name = str(getattr(tool, 'display_name', ''))
                        tool_description = str(getattr(tool, 'description', ''))
                        tool_type = str(getattr(tool, 'type', 'tool'))
                        
                        # 处理input_schema和output_schema
                        input_schema_raw = getattr(tool, 'input_schema', {})
                        output_schema_raw = getattr(tool, 'output_schema', {})
                        
                        # 如果是类对象，尝试获取其schema
                        if hasattr(input_schema_raw, 'schema'):
                            try:
                                input_schema = input_schema_raw.schema()
                            except:
                                input_schema = {}
                        else:
                            input_schema = input_schema_raw
                        
                        if hasattr(output_schema_raw, 'schema'):
                            try:
                                output_schema = output_schema_raw.schema()
                            except:
                                output_schema = {}
                        else:
                            output_schema = output_schema_raw
                        
                        examples = getattr(tool, 'examples', [])
                    except Exception as e:
                        logger.warning(f"无法解析工具对象: {str(e)}")
                        continue
                
                # 跳过没有名称的工具
                if not tool_name:
                    logger.warning(f"跳过没有名称的工具: {tool}")
                    continue
                
                mcp_tool = DBMCPTool(
                    server_id=db_server.id,
                    name=tool_name,
                    display_name=tool_display_name,
                    description=tool_description,
                    tool_type=tool_type,
                    input_schema=input_schema,
                    output_schema=output_schema,
                    examples=examples,
                    is_active=True
                )
                db.add(mcp_tool)
            
            db.commit()
            logger.info(f"同步MCP服务器 {server_name} 工具成功，共 {len(tools)} 个工具")
            return True
            
        except Exception as e:
            logger.error(f"同步MCP工具失败: {str(e)}")
            return False
        finally:
            if db:
                db.close()