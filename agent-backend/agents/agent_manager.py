from typing import Dict, Optional, AsyncGenerator, Any
from agents.base_agent import BaseAgent
from agents.general_agent import GeneralAgent
from agents.flow_driven_agent import FlowDrivenAgent
from models.chat_models import AgentMessage, StreamChunk, AgentContext
from utils.log_helper import get_logger
from database.database import SessionLocal
from models.database_models import Agent as DBAgent, MCPServer, MCPTool as DBMCPTool
from utils.mcp_helper import get_mcp_helper
from utils.tool_info_llm import extract_tool_metadata_with_llm
from sqlalchemy import text
import json

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
        self.tool_manager = None  # 工具管理器实例
        
    async def initialize(self):
        """初始化智能体管理器"""
        logger.info("初始化智能体管理器...")
        
        # 运行数据库迁移
        from database.database import init_db
        init_db()
        
        # 检查数据库表
        await self._check_database_tables()
        
        # 加载MCP配置
        await self._load_mcp_configs()
        
        # 初始化MCP助手
        await self._initialize_mcp_helper()
        
        # 创建默认智能体
        await self._create_default_agents()
        
        # 初始化工具管理器
        await self._initialize_tool_manager()
        
        logger.info(f"智能体管理器初始化完成，共 {len(self.agents)} 个智能体，{len(self.mcp_configs)} 个MCP配置")
        logger.info(f"初始化完成后的MCP配置: {list(self.mcp_configs.keys())}")
        logger.info(f"初始化完成后的MCP配置详情: {self.mcp_configs}")
    
    async def _initialize_tool_manager(self):
        """初始化工具管理器"""
        try:
            from tools.tool_manager import ToolManager
            self.tool_manager = ToolManager()
            self.tool_manager.set_agent_manager(self)
            await self.tool_manager.initialize()
            logger.info("工具管理器初始化完成")
        except Exception as e:
            logger.error(f"工具管理器初始化失败: {e}")
    
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
                
                logger.info(f"服务器 {db_server.name} 加载了 {len(tools)} 个工具")
                
        except Exception as e:
            logger.error(f"从数据库加载MCP配置失败: {str(e)}")
            # 如果数据库加载失败，创建默认MCP配置
            await self._create_fallback_mcp_configs()
        finally:
            db.close()
    
    async def _create_fallback_mcp_configs(self):
        """创建默认MCP配置（备用方案）"""
        logger.info("创建默认MCP配置...")
        
        # 默认MCP配置
        default_configs = {
            'web_search': {
                'id': 1,
                'name': 'web_search',
                'display_name': '网络搜索',
                'description': '网络搜索工具',
                'server_config': {
                    'transport': 'stdio',
                    'command': 'python',
                    'args': ['-m', 'mcp.server.web_search']
                },
                'is_active': True,
                'tools': [
                    {
                        'id': 1,
                        'name': 'web_search',
                        'display_name': '网络搜索',
                        'description': '搜索网络信息',
                        'tool_type': 'tool',
                        'input_schema': {'query': 'string'},
                        'output_schema': {'results': 'array'},
                        'examples': []
                    }
                ]
            },
            'file_search': {
                'id': 2,
                'name': 'file_search',
                'display_name': '文件搜索',
                'description': '本地文件搜索工具',
                'server_config': {
                    'transport': 'stdio',
                    'command': 'python',
                    'args': ['-m', 'mcp.server.file_search']
                },
                'is_active': True,
                'tools': [
                    {
                        'id': 2,
                        'name': 'file_search',
                        'display_name': '文件搜索',
                        'description': '搜索本地文件',
                        'tool_type': 'tool',
                        'input_schema': {'query': 'string'},
                        'output_schema': {'files': 'array'},
                        'examples': []
                    }
                ]
            }
        }
        
        self.mcp_configs.update(default_configs)
        logger.info(f"创建了 {len(default_configs)} 个默认MCP配置")
    
    async def _check_database_tables(self):
        """检查数据库表是否存在"""
        try:
            db = SessionLocal()
            # 尝试查询表是否存在
            db.execute(text("SELECT 1 FROM agents LIMIT 1"))
            db.execute(text("SELECT 1 FROM mcp_servers LIMIT 1"))
            db.execute(text("SELECT 1 FROM mcp_tools LIMIT 1"))
            db.close()
            logger.info("数据库表检查通过")
        except Exception as e:
            logger.warning(f"数据库表检查失败: {str(e)}")
            # 如果表不存在，创建默认数据
            await self._save_default_mcp_configs(self.mcp_configs)
    
    async def _save_default_mcp_configs(self, config: Dict):
        """保存默认MCP配置到数据库"""
        db = SessionLocal()
        try:
            # 检查是否已有MCP服务器
            existing_servers = db.query(MCPServer).count()
            if existing_servers > 0:
                logger.info("MCP服务器已存在，跳过创建")
                return
            
            # 创建默认MCP服务器
            for server_name, server_config in config.items():
                server = MCPServer(
                    name=server_config['name'],
                    display_name=server_config['display_name'],
                    description=server_config['description'],
                    transport=server_config['server_config']['transport'],
                    command=server_config['server_config'].get('command'),
                    args=server_config['server_config'].get('args'),
                    env=server_config['server_config'].get('env'),
                    url=server_config['server_config'].get('url'),
                    is_active=True
                )
                db.add(server)
                db.flush()  # 获取ID
                
                # 创建工具
                for tool_config in server_config['tools']:
                    tool = DBMCPTool(
                        server_id=server.id,
                        name=tool_config['name'],
                        display_name=tool_config['display_name'],
                        description=tool_config['description'],
                        tool_type=tool_config['tool_type'],
                        input_schema=tool_config['input_schema'],
                        output_schema=tool_config['output_schema'],
                        examples=tool_config['examples'],
                        is_active=True
                    )
                    db.add(tool)
            
            db.commit()
            logger.info("默认MCP配置保存成功")
            
        except Exception as e:
            logger.error(f"保存默认MCP配置失败: {str(e)}")
            db.rollback()
        finally:
            db.close()
    
    async def _initialize_mcp_helper(self):
        """初始化MCP助手"""
        try:
            # 如果当前没有任何MCP配置，尝试自动创建/同步默认MCP服务
            if not self.mcp_configs:
                logger.warning("没有MCP配置，尝试自动创建/同步默认MCP服务...")
                try:
                    from database.migrations import create_default_mcp_servers
                    create_default_mcp_servers()
                    logger.info("默认MCP服务器创建完成，重新加载配置...")
                    await self._load_mcp_configs()
                except Exception as e:
                    logger.warning(f"创建默认MCP服务器失败: {str(e)}")
                
                # 如果仍然没有配置，使用内置回退配置并尝试持久化
                if not self.mcp_configs:
                    logger.info("仍无MCP配置，使用回退配置并尝试保存到数据库...")
                    await self._create_fallback_mcp_configs()
                    try:
                        await self._save_default_mcp_configs(self.mcp_configs)
                        await self._load_mcp_configs()
                    except Exception as e:
                        logger.warning(f"保存回退MCP配置失败: {str(e)}")
            
            if self.mcp_configs:
                # 将配置转换为MCP助手需要的格式
                mcp_config = {
                    "mcpServers": {}
                }
                
                for server_name, server_config in self.mcp_configs.items():
                    mcp_config["mcpServers"][server_name] = server_config["server_config"]
                
                logger.info(f"MCP配置转换: {mcp_config}")
                logger.info(f"MCP配置中的服务器: {list(mcp_config['mcpServers'].keys())}")
                
                # 详细记录每个服务器的配置
                for server_name, server_config in mcp_config["mcpServers"].items():
                    logger.info(f"服务器 {server_name} 配置详情: {server_config}")
                
                self.mcp_helper = get_mcp_helper(config=mcp_config)
                logger.info("MCP助手初始化成功")
                
                # 测试连接和工具加载
                logger.info("开始测试MCP服务器连接...")
                try:
                    available_services = await self.mcp_helper.get_available_services()
                    logger.info(f"可用的MCP服务: {available_services}")
                    
                    # 为每个可用服务加载工具并更新内存
                    for service_name in available_services:
                        try:
                            logger.info(f"正在从服务器 {service_name} 加载工具...")
                            tools = await self.mcp_helper.get_tools(server_name=service_name)
                            logger.info(f"服务器 {service_name} 加载了 {len(tools)} 个工具")
                            
                            # 更新内存配置中的工具信息
                            if service_name in self.mcp_configs:
                                self.mcp_configs[service_name]['tools'] = []
                                for tool in tools:
                                    if isinstance(tool, dict):
                                        tool_info = {
                                            'name': tool.get('name', ''),
                                            'display_name': tool.get('displayName', ''),
                                            'description': tool.get('description', ''),
                                            'tool_type': tool.get('type', 'tool'),
                                            'input_schema': tool.get('inputSchema', {}),
                                            'output_schema': tool.get('outputSchema', {}),
                                            'examples': tool.get('examples', [])
                                        }
                                    else:
                                        tool_info = {
                                            'name': getattr(tool, 'name', ''),
                                            'display_name': getattr(tool, 'display_name', ''),
                                            'description': getattr(tool, 'description', ''),
                                            'tool_type': getattr(tool, 'type', 'tool'),
                                            'input_schema': getattr(tool, 'input_schema', {}),
                                            'output_schema': getattr(tool, 'output_schema', {}),
                                            'examples': getattr(tool, 'examples', [])
                                        }
                                    self.mcp_configs[service_name]['tools'].append(tool_info)
                                    logger.info(f"  工具: {tool_info['name']} - {tool_info['description']}")
                        except Exception as e:
                            logger.error(f"从服务器 {service_name} 加载工具失败: {str(e)}")
                            import traceback
                            logger.error(f"错误堆栈: {traceback.format_exc()}")
                            # 继续处理其他服务器，不中断整个流程
                            continue
                    
                    # 在内存更新后，执行一次数据库层的同步，确保工具持久化
                    for service_name in available_services:
                        try:
                            await self.sync_mcp_tools(service_name)
                            logger.info(f"已同步MCP服务器 {service_name} 的工具到数据库")
                        except Exception as e:
                            logger.warning(f"同步MCP服务器 {service_name} 工具到数据库失败: {str(e)}")
                except Exception as e:
                    logger.error(f"MCP服务连接测试失败: {str(e)}")
                    logger.warning("MCP工具加载失败，但系统将继续运行")
            else:
                logger.warning("没有MCP配置，跳过MCP助手初始化")
        except Exception as e:
            logger.error(f"MCP助手初始化失败: {str(e)}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
    
    async def _create_default_agents(self):
        """从数据库加载智能体"""
        db = SessionLocal()
        try:
            # 从数据库获取所有激活的智能体
            db_agents = db.query(DBAgent).filter(DBAgent.is_active == True).all()
            logger.info(f"从数据库查询到 {len(db_agents)} 个激活的智能体")
            
            for db_agent in db_agents:
                # 根据智能体类型创建相应的智能体实例
                if db_agent.agent_type == "general":
                    # 通用智能体（可配置提示词、工具、LLM）
                    system_prompt = db_agent.system_prompt
                    logger.info(f"加载通用智能体 {db_agent.name}，系统提示词: {system_prompt}")
                    
                    # 获取智能体的LLM配置
                    llm_config = None
                    if db_agent.llm_config_id:
                        from services.agent_service import AgentService
                        llm_config = AgentService.get_agent_llm_config(db, db_agent.id)
                        logger.info(f"智能体 {db_agent.name} 使用特定LLM配置: {llm_config.get('provider') if llm_config else 'None'}")
                    else:
                        logger.info(f"智能体 {db_agent.name} 使用默认LLM配置")
                    
                    agent = GeneralAgent(db_agent.name, db_agent.display_name, system_prompt, llm_config)
                elif db_agent.agent_type == "flow_driven":
                    # 流程图驱动智能体
                    logger.info(f"加载流程图驱动智能体 {db_agent.name}，流程图: {db_agent.flow_config}")
                    agent = FlowDrivenAgent(db_agent.name, db_agent.display_name, db_agent.flow_config)
                    # 注入绑定工具（server_tool 字符串数组）
                    try:
                        if db_agent.bound_tools and hasattr(agent, 'bound_tools'):
                            # 归一化为字符串
                            norm = []
                            for t in db_agent.bound_tools:
                                if isinstance(t, str):
                                    norm.append(t)
                                elif isinstance(t, dict) and t.get('server') and t.get('tool'):
                                    norm.append(f"{t['server']}_{t['tool']}")
                                elif isinstance(t, dict) and t.get('server_name') and t.get('name'):
                                    norm.append(f"{t['server_name']}_{t['name']}")
                            agent.bound_tools = norm
                            logger.info(f"流程图智能体 {db_agent.name} 注入绑定工具: {len(norm)} 个")
                    except Exception as e:
                        logger.warning(f"注入绑定工具失败: {str(e)}")
                elif db_agent.agent_type == "chat":
                    logger.info(f"加载聊天智能体 {db_agent.name}")
                    from agents.chat_agent import ChatAgent
                    agent = ChatAgent(db_agent.name, db_agent.display_name)
                else:
                    # 默认使用通用智能体
                    agent = GeneralAgent(db_agent.name, db_agent.display_name, "你是一个智能AI助手，能够帮助用户解答问题、进行对话交流。")
                
                # 设置智能体配置
                if db_agent.config:
                    agent.config = db_agent.config
                
                # 设置MCP助手（通用智能体可以绑定工具，需要MCP助手）
                if self.mcp_helper:
                    if db_agent.agent_type == "general" and db_agent.bound_tools:
                        # 通用智能体如果绑定了工具，需要MCP助手
                        agent.mcp_helper = self.mcp_helper
                        logger.info(f"通用智能体 {db_agent.name} 绑定了工具，设置MCP助手")
                    elif db_agent.agent_type == "flow_driven":
                        # 流程图智能体可能需要MCP助手
                        agent.mcp_helper = self.mcp_helper
                        logger.info(f"流程图智能体 {db_agent.name} 设置MCP助手")
                    else:
                        # 其他情况不设置MCP助手
                        logger.info(f"智能体 {db_agent.name} 不设置MCP助手")
                
                # 设置知识库绑定（通用智能体）
                if db_agent.bound_knowledge_bases:
                    try:
                        # 获取知识库详细信息
                        from services.knowledge_base_service import KnowledgeBaseService
                        kb_service = KnowledgeBaseService()
                        knowledge_bases = []
                        
                        for kb_info in db_agent.bound_knowledge_bases:
                            if isinstance(kb_info, dict):
                                kb_id = kb_info.get('id') or kb_info.get('knowledge_base_id')
                                if kb_id:
                                    kb = kb_service.get_knowledge_base(db, kb_id)
                                    if kb:
                                        knowledge_bases.append({
                                            'id': kb.id,
                                            'name': kb.name,
                                            'description': kb.description
                                        })
                            elif isinstance(kb_info, int):
                                # 如果只是ID
                                kb = kb_service.get_knowledge_base(db, kb_info)
                                if kb:
                                    knowledge_bases.append({
                                        'id': kb.id,
                                        'name': kb.name,
                                        'description': kb.description
                                    })
                        
                        if knowledge_bases:
                            agent.set_knowledge_bases(knowledge_bases)
                            logger.info(f"通用智能体 {db_agent.name} 绑定了 {len(knowledge_bases)} 个知识库")
                    except Exception as e:
                        logger.warning(f"绑定知识库失败: {str(e)}")
                
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
        # 通用智能体
        general_agent = GeneralAgent("general_agent", "通用智能体", "你是一个智能AI助手，能够帮助用户解答问题、进行对话交流。")
        if self.mcp_helper:
            general_agent.mcp_helper = self.mcp_helper
        self.agents["general_agent"] = general_agent
        
        # 流程图智能体
        flow_agent = FlowDrivenAgent("flow_agent", "流程图智能体", {})
        if self.mcp_helper:
            flow_agent.mcp_helper = self.mcp_helper
        self.agents["flow_agent"] = flow_agent
        
        logger.info("创建默认智能体完成")
        
        # 工具驱动智能体（需要MCP助手）
        tool_agent = GeneralAgent("tool_agent", "工具驱动智能体", "你是一个智能AI助手，能够帮助用户解答问题、进行对话交流。")
        if self.mcp_helper:
            tool_agent.mcp_helper = self.mcp_helper
            logger.info("工具驱动智能体设置MCP助手")
        self.agents["tool_agent"] = tool_agent
        
        # 移除重复的flow_agent创建
        # flow_agent = FlowDrivenAgent("flow_agent", "流程图驱动智能体")
        # self.agents["flow_agent"] = flow_agent
        # logger.info("创建流程图驱动智能体，不设置MCP助手")
        
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
            
            # 如果上下文为空，创建一个新的
            if agent_context is None:
                agent_context = AgentContext(
                    user_id=user_id,
                    session_id=session_id,
                    messages=[],
                    metadata={}
                )
                self.update_context(user_id, agent_context)
            
            # 选择智能体
            agent = self._select_agent(message)
            
            # 流式处理消息
            async for chunk in agent.process_message_stream(user_id, message, context):
                yield chunk
                
        except Exception as e:
            logger.error(f"流式处理消息失败: {str(e)}")
            yield StreamChunk(
                type="error",
                content=f"处理消息时出现错误: {str(e)}",
                agent_name="system"
            )
    
    def _select_agent(self, message: str) -> BaseAgent:
        """选择智能体（简化版本）"""
        # 这里可以实现更复杂的智能体选择逻辑
        # 目前简单返回第一个可用的智能体
        if not self.agents:
            raise Exception("没有可用的智能体")
        
        # 根据消息内容选择智能体
        message_lower = message.lower()
        
        if any(keyword in message_lower for keyword in ['搜索', '查找', '查询', 'search', 'find']):
            if 'web_search' in self.mcp_configs: # Changed from search_agent to web_search
                return GeneralAgent("web_search", "网络搜索", "你是一个网络搜索工具，能够帮助用户在互联网上查找信息。")
        elif any(keyword in message_lower for keyword in ['文件', '本地', 'file', 'local']):
            if 'file_search' in self.mcp_configs: # Changed from file_search to file_search
                return GeneralAgent("file_search", "文件搜索", "你是一个本地文件搜索工具，能够帮助用户在本地文件系统中查找文件。")
        elif any(keyword in message_lower for keyword in ['工具', '使用', 'tool', 'use']):
            if 'tool_agent' in self.agents:
                return self.agents['tool_agent']
        elif any(keyword in message_lower for keyword in ['提示', 'prompt']):
            if 'prompt_agent' in self.agents:
                return self.agents['prompt_agent']
        elif any(keyword in message_lower for keyword in ['流程图', 'flow', 'graph']):
            if 'flow_agent' in self.agents:
                return self.agents['flow_agent']
        
        # 默认返回通用智能体
        return self.agents.get('general_agent', list(self.agents.values())[0])
    
    def get_agent(self, agent_name: str) -> Optional[BaseAgent]:
        """根据名称获取智能体"""
        return self.agents.get(agent_name)
    
    def get_agent_by_id(self, agent_id: int) -> Optional[BaseAgent]:
        """根据ID获取智能体"""
        # 从数据库获取智能体信息
        db = SessionLocal()
        try:
            db_agent = db.query(DBAgent).filter(DBAgent.id == agent_id).first()
            if db_agent:
                return self.agents.get(db_agent.name)
            return None
        finally:
            db.close()
    
    async def get_mcp_configs(self) -> Dict[str, Any]:
        """获取MCP配置"""
        return self.mcp_configs
    
    async def update_mcp_server(self, name: str, config: Dict[str, Any]) -> bool:
        """更新MCP服务器配置"""
        db = SessionLocal()
        try:
            # 查找现有服务器
            server = db.query(MCPServer).filter(MCPServer.name == name).first()
            if not server:
                return False
            
            # 更新配置
            for key, value in config.items():
                if hasattr(server, key):
                    setattr(server, key, value)
            
            db.commit()
            
            # 更新内存中的配置
            if name in self.mcp_configs:
                self.mcp_configs[name].update(config)
            
            logger.info(f"更新MCP服务器配置: {name}")
            return True
            
        except Exception as e:
            logger.error(f"更新MCP服务器配置失败: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    async def create_mcp_server(self, config: Dict[str, Any]) -> bool:
        """创建MCP服务器"""
        db = SessionLocal()
        try:
            # 检查是否已存在
            existing = db.query(MCPServer).filter(MCPServer.name == config['name']).first()
            if existing:
                logger.warning(f"MCP服务器 {config['name']} 已存在")
                return False
            
            # 创建新服务器
            server = MCPServer(
                name=config['name'],
                display_name=config.get('display_name', config['name']),
                description=config.get('description', ''),
                transport=config['server_config']['transport'],
                command=config['server_config'].get('command'),
                args=config['server_config'].get('args'),
                env=config['server_config'].get('env'),
                url=config['server_config'].get('url'),
                is_active=True
            )
            db.add(server)
            db.commit()
            
            # 添加到内存配置
            self.mcp_configs[config['name']] = {
                'id': server.id,
                'name': server.name,
                'display_name': server.display_name,
                'description': server.description,
                'server_config': config['server_config'],
                'is_active': True,
                'tools': []
            }
            
            logger.info(f"创建MCP服务器: {config['name']}")
            return True
            
        except Exception as e:
            logger.error(f"创建MCP服务器失败: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    async def sync_mcp_tools(self, server_name: str) -> bool:
        """同步MCP工具"""
        db = SessionLocal()
        try:
            # 查找服务器
            db_server = db.query(MCPServer).filter(MCPServer.name == server_name).first()
            if not db_server:
                logger.error(f"MCP服务器 {server_name} 不存在")
                return False
            
            # 获取服务器配置
            server_config = self.mcp_configs.get(server_name)
            if not server_config:
                logger.warning(f"MCP服务器 {server_name} 配置不存在，尝试重新加载配置...")
                # 尝试重新加载配置
                await self._load_mcp_configs()
                server_config = self.mcp_configs.get(server_name)
                if not server_config:
                    logger.error(f"MCP服务器 {server_name} 配置重新加载后仍不存在")
                    return False
                # 重新初始化MCPHelper以包含新配置
                await self._ensure_mcp_helper_initialized()
            
            # 真正连接到MCP服务器获取工具
            if not self.mcp_helper:
                logger.error("MCP助手未初始化，尝试重新初始化...")
                await self._ensure_mcp_helper_initialized()
                if not self.mcp_helper:
                    logger.error("MCP助手重新初始化失败，无法同步工具")
                    return False
            
            try:
                logger.info(f"正在从MCP服务器 {server_name} 获取工具...")
                tools = await self.mcp_helper.get_tools(server_name=server_name)
                logger.info(f"从MCP服务器 {server_name} 获取到 {len(tools)} 个工具")
                
                # 更新内存配置
                self.mcp_configs[server_name]['tools'] = []
                for tool in tools:
                    if isinstance(tool, dict):
                        tool_info = {
                            'name': tool.get('name', ''),
                            'display_name': tool.get('displayName', ''),
                            'description': tool.get('description', ''),
                            'tool_type': tool.get('type', 'tool'),
                            'input_schema': tool.get('inputSchema', {}),
                            'output_schema': tool.get('outputSchema', {}),
                            'examples': tool.get('examples', [])
                        }
                    else:
                        tool_info = {
                            'name': getattr(tool, 'name', ''),
                            'display_name': getattr(tool, 'display_name', ''),
                            'description': getattr(tool, 'description', ''),
                            'tool_type': getattr(tool, 'type', 'tool'),
                            'input_schema': getattr(tool, 'input_schema', {}),
                            'output_schema': getattr(tool, 'output_schema', {}),
                            'examples': getattr(tool, 'examples', [])
                        }
                    self.mcp_configs[server_name]['tools'].append(tool_info)
                    logger.info(f"  工具: {tool_info['name']} - {tool_info['description']}")
                
            except Exception as e:
                logger.error(f"从MCP服务器 {server_name} 获取工具失败: {str(e)}")
                # 如果获取失败，使用配置中的工具作为备用
                tools = server_config.get('tools', [])
                logger.warning(f"使用备用工具配置，共 {len(tools)} 个工具")
            
            # 清除现有工具
            db.query(DBMCPTool).filter(DBMCPTool.server_id == db_server.id).delete()
            
            # 清理函数，用于移除不可序列化的对象
            def clean_for_json(obj):
                """递归清理对象，移除不可序列化的部分"""
                if isinstance(obj, dict):
                    result = {}
                    for k, v in obj.items():
                        # 跳过 Pydantic FieldInfo 等特殊对象
                        if hasattr(v, '__class__') and 'FieldInfo' in str(type(v)):
                            continue
                        if hasattr(v, '__class__') and 'ModelField' in str(type(v)):
                            continue
                        try:
                            # 尝试序列化以检查是否可序列化
                            json.dumps(v)
                            result[k] = clean_for_json(v)
                        except (TypeError, ValueError):
                            # 如果不可序列化，尝试转换为字符串
                            try:
                                result[k] = str(v)
                            except:
                                result[k] = f"<{type(v).__name__}>"
                    return result
                elif isinstance(obj, list):
                    return [clean_for_json(item) for item in obj]
                elif isinstance(obj, (str, int, float, bool, type(None))):
                    return obj
                else:
                    # 尝试序列化
                    try:
                        json.dumps(obj)
                        return obj
                    except (TypeError, ValueError):
                        # 如果不可序列化，转换为字符串
                        try:
                            return str(obj)
                        except:
                            return f"<{type(obj).__name__}>"
            
            # 添加新工具
            for tool in tools:
                # 处理不同类型的工具对象
                if isinstance(tool, dict):
                    tool_name = tool.get('name', '')
                    tool_display_name = tool.get('displayName', '')
                    tool_description = tool.get('description', '')
                    tool_type = tool.get('type', 'tool')
                    input_schema = clean_for_json(tool.get('inputSchema', {}))
                    output_schema = clean_for_json(tool.get('outputSchema', {}))
                    examples = clean_for_json(tool.get('examples', []))
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
                                input_schema = clean_for_json(input_schema_raw.schema())
                            except:
                                input_schema = {}
                        else:
                            input_schema = clean_for_json(input_schema_raw)
                        
                        if hasattr(output_schema_raw, 'schema'):
                            try:
                                output_schema = clean_for_json(output_schema_raw.schema())
                            except:
                                output_schema = {}
                        else:
                            output_schema = clean_for_json(output_schema_raw)
                        
                        examples = clean_for_json(getattr(tool, 'examples', []))
                    except Exception as e:
                        logger.warning(f"无法解析工具对象: {str(e)}")
                        continue
                
                # 跳过没有名称的工具
                if not tool_name:
                    logger.warning(f"跳过没有名称的工具: {tool}")
                    continue
                
                # 获取工具的原始数据，并清理不可序列化的对象
                if isinstance(tool, dict):
                    raw_data = clean_for_json(tool)
                else:
                    # 序列化工具对象
                    raw_data = {}
                    for attr in dir(tool):
                        if attr.startswith('_'):
                            continue
                        try:
                            value = getattr(tool, attr)
                            if callable(value):
                                continue
                            # 跳过 Pydantic FieldInfo 等特殊对象
                            if hasattr(value, '__class__') and 'FieldInfo' in str(type(value)):
                                continue
                            if hasattr(value, '__class__') and 'ModelField' in str(type(value)):
                                continue
                            raw_data[attr] = clean_for_json(value)
                        except:
                            continue
                
                # 使用 LLM 整理工具信息
                metadata = None
                try:
                    logger.info(f"使用 LLM 整理工具 {tool_name} 的信息...")
                    metadata = await extract_tool_metadata_with_llm(raw_data)
                    logger.info(f"工具 {tool_name} 的元数据整理完成")
                except Exception as e:
                    logger.warning(f"使用 LLM 整理工具 {tool_name} 信息失败: {str(e)}，将使用空元数据")
                    metadata = {}
                
                mcp_tool = DBMCPTool(
                    server_id=db_server.id,
                    name=tool_name,
                    display_name=tool_display_name,
                    description=tool_description,
                    tool_type=tool_type,
                    input_schema=input_schema,
                    output_schema=output_schema,
                    examples=examples,
                    raw_data=raw_data,  # 保存原始数据
                    tool_metadata=metadata,  # 保存 LLM 整理的元数据
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
    
    async def reload_agents_llm(self):
        """重新加载所有智能体的LLM配置"""
        logger.info("重新加载所有智能体的LLM配置...")
        
        for agent_name, agent in self.agents.items():
            if hasattr(agent, 'llm_helper'):
                try:
                    agent.llm_helper._initialized = False
                    agent.llm_helper.setup()
                    logger.info(f"重新初始化智能体 {agent_name} 的LLM助手")
                except Exception as e:
                    logger.error(f"重新初始化智能体 {agent_name} 的LLM助手失败: {str(e)}")
        
        logger.info("所有智能体的LLM配置重新加载完成")
    
    def get_agent_llm_config(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """获取智能体的LLM配置"""
        from services.agent_service import AgentService
        
        db = SessionLocal()
        try:
            # 获取智能体
            agent = self.get_agent_by_name(agent_name)
            if not agent:
                return None
            
            # 获取智能体的LLM配置
            llm_config = AgentService.get_agent_llm_config(db, agent.id)
            return llm_config
        except Exception as e:
            logger.error(f"获取智能体 {agent_name} 的LLM配置失败: {str(e)}")
            return None
        finally:
            db.close() 