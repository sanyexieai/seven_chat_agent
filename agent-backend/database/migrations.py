"""
数据库迁移管理器
自动检查和执行数据库迁移
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from database.database import engine, SessionLocal
from models.database_models import Base
from utils.log_helper import get_logger

logger = get_logger("migrations")

def check_table_exists(table_name: str) -> bool:
    """检查表是否存在"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def check_column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col['name'] == column_name for col in columns)

def run_migrations():
    """运行所有数据库迁移"""
    logger.info("开始检查数据库迁移...")
    
    try:
        # 检查所有必需的表是否存在
        required_tables = ['agents']
        missing_tables = []
        
        for table in required_tables:
            if not check_table_exists(table):
                missing_tables.append(table)
        
        if missing_tables:
            logger.info(f"发现缺失的表: {missing_tables}")
            logger.info("创建所有缺失的表...")
            Base.metadata.create_all(bind=engine)
            logger.info("所有表创建完成")
            return
        
        # 检查agents表的新字段是否存在
        missing_columns = []
        
        if not check_column_exists('agents', 'system_prompt'):
            missing_columns.append('system_prompt')
        
        if not check_column_exists('agents', 'bound_tools'):
            missing_columns.append('bound_tools')
        
        if not check_column_exists('agents', 'bound_knowledge_bases'):
            missing_columns.append('bound_knowledge_bases')
        
        if not check_column_exists('agents', 'flow_config'):
            missing_columns.append('flow_config')
        
        if missing_columns:
            logger.info(f"发现缺失字段: {missing_columns}")
            
            with engine.connect() as conn:
                # 添加缺失的字段
                for column in missing_columns:
                    if column == 'system_prompt':
                        conn.execute(text("ALTER TABLE agents ADD COLUMN system_prompt TEXT;"))
                        logger.info("添加 system_prompt 字段")
                    elif column == 'bound_tools':
                        conn.execute(text("ALTER TABLE agents ADD COLUMN bound_tools JSON;"))
                        logger.info("添加 bound_tools 字段")
                    elif column == 'bound_knowledge_bases':
                        conn.execute(text("ALTER TABLE agents ADD COLUMN bound_knowledge_bases JSON;"))
                        logger.info("添加 bound_knowledge_bases 字段")
                    elif column == 'flow_config':
                        conn.execute(text("ALTER TABLE agents ADD COLUMN flow_config JSON;"))
                        logger.info("添加 flow_config 字段")
                
                conn.commit()
                logger.info("agents表迁移完成")
        else:
            logger.info("agents表结构已是最新版本")
        
        # 运行MCP服务器表迁移
        run_mcp_migrations()
        
        # 运行流程图表迁移
        run_flow_migrations()
        
        # 运行智能体LLM配置迁移
        run_agent_llm_config_migration()
        
        # 运行聊天相关表迁移
        run_chat_migrations()
        
        # 运行知识库相关表迁移
        run_knowledge_base_migrations()
        
        # 运行知识图谱相关表迁移
        run_knowledge_graph_migrations()
            
    except Exception as e:
        logger.error(f"数据库迁移失败: {str(e)}")
        raise

def run_mcp_migrations():
    """运行MCP相关的数据库迁移"""
    logger.info("开始检查MCP相关表迁移...")
    
    try:
        with engine.connect() as conn:
            # 检查mcp_servers表是否存在
            inspector = inspect(engine)
            if 'mcp_servers' not in inspector.get_table_names():
                logger.info("mcp_servers表不存在，创建所有MCP表...")
                Base.metadata.create_all(bind=engine)
                logger.info("所有MCP表创建完成")
                return
            
            # 检查config字段是否存在
            if not check_column_exists('mcp_servers', 'config'):
                logger.info("添加config字段到mcp_servers表...")
                conn.execute(text("""
                    ALTER TABLE mcp_servers 
                    ADD COLUMN config JSON;
                """))
                logger.info("成功添加config字段到mcp_servers表")
            else:
                logger.info("config字段已存在，跳过添加")
            
            # 检查其他可能缺失的字段
            missing_server_columns = []
            
            if not check_column_exists('mcp_servers', 'args'):
                missing_server_columns.append('args')
            
            if not check_column_exists('mcp_servers', 'env'):
                missing_server_columns.append('env')
            
            if missing_server_columns:
                logger.info(f"发现缺失字段: {missing_server_columns}")
                for column in missing_server_columns:
                    if column == 'args':
                        conn.execute(text("ALTER TABLE mcp_servers ADD COLUMN args JSON;"))
                        logger.info("添加 args 字段")
                    elif column == 'env':
                        conn.execute(text("ALTER TABLE mcp_servers ADD COLUMN env JSON;"))
                        logger.info("添加 env 字段")
                
                logger.info("MCP服务器表迁移完成")
            else:
                logger.info("MCP服务器表结构已是最新版本")
            
            # 检查mcp_tools表
            if 'mcp_tools' not in inspector.get_table_names():
                logger.info("mcp_tools表不存在，创建所有MCP表...")
                Base.metadata.create_all(bind=engine)
                logger.info("所有MCP表创建完成")
            else:
                # 检查mcp_tools表的字段
                missing_tool_columns = []
                
                if not check_column_exists('mcp_tools', 'tool_type'):
                    missing_tool_columns.append('tool_type')
                if not check_column_exists('mcp_tools', 'input_schema'):
                    missing_tool_columns.append('input_schema')
                if not check_column_exists('mcp_tools', 'output_schema'):
                    missing_tool_columns.append('output_schema')
                if not check_column_exists('mcp_tools', 'examples'):
                    missing_tool_columns.append('examples')
                if not check_column_exists('mcp_tools', 'tool_schema'):
                    missing_tool_columns.append('tool_schema')
                
                if missing_tool_columns:
                    logger.info(f"发现缺失字段: {missing_tool_columns}")
                    for column in missing_tool_columns:
                        if column == 'tool_type':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN tool_type VARCHAR(50);"))
                            logger.info("添加 tool_type 字段")
                        elif column == 'input_schema':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN input_schema JSON;"))
                            logger.info("添加 input_schema 字段")
                        elif column == 'output_schema':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN output_schema JSON;"))
                            logger.info("添加 output_schema 字段")
                        elif column == 'examples':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN examples JSON;"))
                            logger.info("添加 examples 字段")
                        elif column == 'tool_schema':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN tool_schema JSON;"))
                            logger.info("添加 tool_schema 字段")
                    
                    logger.info("MCP工具表迁移完成")
                else:
                    logger.info("MCP工具表结构已是最新版本")
            
            conn.commit()
                
    except Exception as e:
        logger.error(f"MCP相关表迁移失败: {str(e)}")
        raise

def run_flow_migrations():
    """运行流程图相关的数据库迁移"""
    logger.info("开始检查流程图表迁移...")
    
    try:
        with engine.connect() as conn:
            # 检查flows表是否存在
            inspector = inspect(engine)
            if 'flows' not in inspector.get_table_names():
                logger.info("flows表不存在，创建所有流程图表...")
                Base.metadata.create_all(bind=engine)
                logger.info("所有流程图表创建完成")
                return
            
            # 检查flow_config字段是否存在
            if not check_column_exists('flows', 'flow_config'):
                logger.info("添加flow_config字段到flows表...")
                conn.execute(text("""
                    ALTER TABLE flows 
                    ADD COLUMN flow_config JSON;
                """))
                logger.info("成功添加flow_config字段到flows表")
            else:
                logger.info("flow_config字段已存在，跳过添加")
            
            # 检查其他可能缺失的字段
            missing_flow_columns = []
            
            if not check_column_exists('flows', 'name'):
                missing_flow_columns.append('name')
            
            if not check_column_exists('flows', 'description'):
                missing_flow_columns.append('description')
            
            if not check_column_exists('flows', 'nodes'):
                missing_flow_columns.append('nodes')
            
            if not check_column_exists('flows', 'edges'):
                missing_flow_columns.append('edges')
            
            if not check_column_exists('flows', 'flow_schema'):
                missing_flow_columns.append('flow_schema')
            
            if missing_flow_columns:
                logger.info(f"发现缺失字段: {missing_flow_columns}")
                for column in missing_flow_columns:
                    if column == 'name':
                        conn.execute(text("ALTER TABLE flows ADD COLUMN name VARCHAR(255);"))
                        logger.info("添加 name 字段")
                    elif column == 'description':
                        conn.execute(text("ALTER TABLE flows ADD COLUMN description TEXT;"))
                        logger.info("添加 description 字段")
                    elif column == 'nodes':
                        conn.execute(text("ALTER TABLE flows ADD COLUMN nodes JSON;"))
                        logger.info("添加 nodes 字段")
                    elif column == 'edges':
                        conn.execute(text("ALTER TABLE flows ADD COLUMN edges JSON;"))
                        logger.info("添加 edges 字段")
                    elif column == 'flow_schema':
                        conn.execute(text("ALTER TABLE flows ADD COLUMN flow_schema JSON;"))
                        logger.info("添加 flow_schema 字段")
                
                logger.info("流程图表迁移完成")
            else:
                logger.info("流程图表结构已是最新版本")
            
            conn.commit()
                
    except Exception as e:
        logger.error(f"流程图表迁移失败: {str(e)}")
        raise

def run_agent_llm_config_migration():
    """运行智能体LLM配置迁移"""
    logger.info("开始检查智能体LLM配置迁移...")
    
    try:
        with engine.connect() as conn:
            # 检查llm_config_id字段是否存在
            if not check_column_exists('agents', 'llm_config_id'):
                logger.info("添加llm_config_id字段到agents表...")
                conn.execute(text("""
                    ALTER TABLE agents 
                    ADD COLUMN llm_config_id INTEGER REFERENCES llm_configs(id);
                """))
                logger.info("成功添加llm_config_id字段到agents表")
            else:
                logger.info("llm_config_id字段已存在，跳过添加")
            
            conn.commit()
            logger.info("智能体LLM配置迁移完成")
                
    except Exception as e:
        logger.error(f"智能体LLM配置迁移失败: {str(e)}")
        raise

def run_chat_migrations():
    """运行聊天相关表的数据库迁移"""
    logger.info("开始检查聊天相关表迁移...")
    
    try:
        with engine.connect() as conn:
            # 检查chat_messages表是否存在
            inspector = inspect(engine)
            if 'chat_messages' not in inspector.get_table_names():
                logger.info("chat_messages表不存在，创建所有聊天相关表...")
                Base.metadata.create_all(bind=engine)
                logger.info("所有聊天相关表创建完成")
                return
            
            # 检查message_nodes表是否存在
            if 'message_nodes' not in inspector.get_table_names():
                logger.info("message_nodes表不存在，创建message_nodes表...")
                Base.metadata.create_all(bind=engine)
                logger.info("message_nodes表创建完成")
                return
            
            # 检查chat_messages表的字段
            missing_chat_columns = []
            
            if not check_column_exists('chat_messages', 'message_metadata'):
                missing_chat_columns.append('message_metadata')
            
            if not check_column_exists('chat_messages', 'agent_name'):
                missing_chat_columns.append('agent_name')
            
            # 检查是否需要移除content字段（迁移到message_nodes表）
            if check_column_exists('chat_messages', 'content'):
                logger.info("发现chat_messages表存在content字段，需要迁移到message_nodes表...")
                # 注意：这里只是标记，实际的数据迁移需要更复杂的逻辑
                # 暂时保留字段，避免数据丢失
                logger.warning("chat_messages表的content字段暂时保留，建议手动迁移数据后删除")
            
            if missing_chat_columns:
                logger.info(f"发现缺失字段: {missing_chat_columns}")
                for column in missing_chat_columns:
                    if column == 'message_metadata':
                        conn.execute(text("ALTER TABLE chat_messages ADD COLUMN message_metadata JSON;"))
                        logger.info("添加 message_metadata 字段")
                    elif column == 'agent_name':
                        conn.execute(text("ALTER TABLE chat_messages ADD COLUMN agent_name VARCHAR(100);"))
                        logger.info("添加 agent_name 字段")
                
                logger.info("chat_messages表迁移完成")
            else:
                logger.info("chat_messages表结构已是最新版本")
            
            # 检查message_nodes表的字段
            missing_node_columns = []
            
            if not check_column_exists('message_nodes', 'node_metadata'):
                missing_node_columns.append('node_metadata')
            
            if not check_column_exists('message_nodes', 'node_label'):
                missing_node_columns.append('node_label')
            
            if not check_column_exists('message_nodes', 'content'):
                missing_node_columns.append('content')
            
            if missing_node_columns:
                logger.info(f"发现缺失字段: {missing_node_columns}")
                for column in missing_node_columns:
                    if column == 'node_metadata':
                        conn.execute(text("ALTER TABLE message_nodes ADD COLUMN node_metadata JSON;"))
                        logger.info("添加 node_metadata 字段")
                    elif column == 'node_label':
                        conn.execute(text("ALTER TABLE message_nodes ADD COLUMN node_label VARCHAR(200);"))
                        logger.info("添加 node_label 字段")
                    elif column == 'content':
                        conn.execute(text("ALTER TABLE message_nodes ADD COLUMN content TEXT;"))
                        logger.info("添加 content 字段")
                
                logger.info("message_nodes表迁移完成")
            else:
                logger.info("message_nodes表结构已是最新版本")
            
            conn.commit()
                
    except Exception as e:
        logger.error(f"聊天相关表迁移失败: {str(e)}")
        raise

def run_knowledge_base_migrations():
    """运行知识库相关表的数据库迁移"""
    logger.info("开始检查知识库相关表迁移...")
    
    try:
        with engine.connect() as conn:
            # 检查knowledge_bases表是否存在
            inspector = inspect(engine)
            if 'knowledge_bases' not in inspector.get_table_names():
                logger.info("knowledge_bases表不存在，创建所有知识库相关表...")
                Base.metadata.create_all(bind=engine)
                logger.info("所有知识库相关表创建完成")
                return
            
            # 检查并移除name字段的唯一约束（支持软删除）
            try:
                # 检查是否存在唯一索引
                indexes = inspector.get_indexes('knowledge_bases')
                name_unique_index = None
                for index in indexes:
                    if index['unique'] and 'name' in index['column_names']:
                        name_unique_index = index['name']
                        break
                
                if name_unique_index:
                    logger.info(f"发现name字段的唯一索引: {name_unique_index}，准备移除...")
                    conn.execute(text(f"DROP INDEX IF EXISTS {name_unique_index}"))
                    logger.info("成功移除name字段的唯一索引")
                else:
                    logger.info("name字段没有唯一索引，跳过移除")
            except Exception as e:
                logger.warning(f"检查或移除name字段唯一索引时出错: {str(e)}")
                # 继续执行其他迁移，不中断流程
            
            # 检查documents表是否存在
            if 'documents' not in inspector.get_table_names():
                logger.info("documents表不存在，创建documents表...")
                Base.metadata.create_all(bind=engine)
                logger.info("documents表创建完成")
                return
            
            # 检查document_chunks表是否存在
            if 'document_chunks' not in inspector.get_table_names():
                logger.info("document_chunks表不存在，创建document_chunks表...")
                Base.metadata.create_all(bind=engine)
                logger.info("document_chunks表创建完成")
                return
            
            # 检查knowledge_base_queries表是否存在
            if 'knowledge_base_queries' not in inspector.get_table_names():
                logger.info("knowledge_base_queries表不存在，创建knowledge_base_queries表...")
                Base.metadata.create_all(bind=engine)
                logger.info("knowledge_base_queries表创建完成")
                return
            
            # 检查knowledge_bases表的字段
            missing_kb_columns = []
            
            if not check_column_exists('knowledge_bases', 'owner_id'):
                missing_kb_columns.append('owner_id')
            
            if not check_column_exists('knowledge_bases', 'is_public'):
                missing_kb_columns.append('is_public')
            
            if not check_column_exists('knowledge_bases', 'is_active'):
                missing_kb_columns.append('is_active')
            
            if missing_kb_columns:
                logger.info(f"发现缺失字段: {missing_kb_columns}")
                for column in missing_kb_columns:
                    if column == 'owner_id':
                        conn.execute(text("ALTER TABLE knowledge_bases ADD COLUMN owner_id VARCHAR(100);"))
                        logger.info("添加 owner_id 字段")
                    elif column == 'is_public':
                        conn.execute(text("ALTER TABLE knowledge_bases ADD COLUMN is_public BOOLEAN DEFAULT 0;"))
                        logger.info("添加 is_public 字段")
                    elif column == 'is_active':
                        conn.execute(text("ALTER TABLE knowledge_bases ADD COLUMN is_active BOOLEAN DEFAULT 1;"))
                        logger.info("添加 is_active 字段")
                
                logger.info("knowledge_bases表迁移完成")
            else:
                logger.info("knowledge_bases表结构已是最新版本")
            
            # 检查documents表的字段
            missing_doc_columns = []
            
            if not check_column_exists('documents', 'file_type'):
                missing_doc_columns.append('file_type')
            
            if not check_column_exists('documents', 'content'):
                missing_doc_columns.append('content')
            
            if not check_column_exists('documents', 'document_metadata'):
                missing_doc_columns.append('document_metadata')
            
            if not check_column_exists('documents', 'status'):
                missing_doc_columns.append('status')
            
            if not check_column_exists('documents', 'is_active'):
                missing_doc_columns.append('is_active')
            
            if missing_doc_columns:
                logger.info(f"发现缺失字段: {missing_doc_columns}")
                for column in missing_doc_columns:
                    if column == 'file_type':
                        conn.execute(text("ALTER TABLE documents ADD COLUMN file_type VARCHAR(50);"))
                        logger.info("添加 file_type 字段")
                    elif column == 'content':
                        conn.execute(text("ALTER TABLE documents ADD COLUMN content TEXT;"))
                        logger.info("添加 content 字段")
                    elif column == 'document_metadata':
                        conn.execute(text("ALTER TABLE documents ADD COLUMN document_metadata JSON;"))
                        logger.info("添加 document_metadata 字段")
                    elif column == 'status':
                        conn.execute(text("ALTER TABLE documents ADD COLUMN status VARCHAR(50) DEFAULT 'pending';"))
                        logger.info("添加 status 字段")
                    elif column == 'is_active':
                        conn.execute(text("ALTER TABLE documents ADD COLUMN is_active BOOLEAN DEFAULT 1;"))
                        logger.info("添加 is_active 字段")
                
                logger.info("documents表迁移完成")
            else:
                logger.info("documents表结构已是最新版本")
            
            # 检查document_chunks表的字段
            missing_chunk_columns = []
            
            if not check_column_exists('document_chunks', 'knowledge_base_id'):
                missing_chunk_columns.append('knowledge_base_id')
            
            if not check_column_exists('document_chunks', 'content'):
                missing_chunk_columns.append('content')
            
            if not check_column_exists('document_chunks', 'chunk_index'):
                missing_chunk_columns.append('chunk_index')
            
            if not check_column_exists('document_chunks', 'embedding'):
                missing_chunk_columns.append('embedding')
            
            if not check_column_exists('document_chunks', 'chunk_metadata'):
                missing_chunk_columns.append('chunk_metadata')
            
            if not check_column_exists('document_chunks', 'is_active'):
                missing_chunk_columns.append('is_active')
            
            if missing_chunk_columns:
                logger.info(f"发现缺失字段: {missing_chunk_columns}")
                for column in missing_chunk_columns:
                    if column == 'knowledge_base_id':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN knowledge_base_id INTEGER REFERENCES knowledge_bases(id);"))
                        logger.info("添加 knowledge_base_id 字段")
                    elif column == 'content':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN content TEXT;"))
                        logger.info("添加 content 字段")
                    elif column == 'chunk_index':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN chunk_index INTEGER;"))
                        logger.info("添加 chunk_index 字段")
                    elif column == 'embedding':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN embedding JSON;"))
                        logger.info("添加 embedding 字段")
                    elif column == 'chunk_metadata':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN chunk_metadata JSON;"))
                        logger.info("添加 chunk_metadata 字段")
                    elif column == 'is_active':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN is_active BOOLEAN DEFAULT 1;"))
                        logger.info("添加 is_active 字段")
                
                logger.info("document_chunks表迁移完成")
            else:
                logger.info("document_chunks表结构已是最新版本")
            
            conn.commit()
            logger.info("知识库相关表迁移完成")
                
    except Exception as e:
        logger.error(f"知识库相关表迁移失败: {str(e)}")
        raise

def run_knowledge_graph_migrations():
    """运行知识图谱相关表的数据库迁移"""
    logger.info("开始检查知识图谱相关表迁移...")
    
    try:
        with engine.connect() as conn:
            # 检查knowledge_triples表是否存在
            inspector = inspect(engine)
            if 'knowledge_triples' not in inspector.get_table_names():
                logger.info("knowledge_triples表不存在，创建知识图谱相关表...")
                Base.metadata.create_all(bind=engine)
                logger.info("知识图谱相关表创建完成")
                return
            
            conn.commit()
            logger.info("知识图谱相关表迁移完成")
                
    except Exception as e:
        logger.error(f"知识图谱相关表迁移失败: {str(e)}")
        raise

def create_default_agents():
    """创建默认智能体"""
    logger.info("检查默认智能体...")
    
    db = SessionLocal()
    try:
        from models.database_models import Agent
        
        # 检查是否已有智能体
        existing_agents = db.query(Agent).count()
        if existing_agents > 0:
            logger.info(f"数据库中已有 {existing_agents} 个智能体，跳过创建默认智能体")
            return
        
        # 创建默认智能体
        default_agents = [
            {
                "name": "general_agent",
                "display_name": "通用智能体",
                "description": "可配置提示词、工具和LLM的通用智能体",
                "agent_type": "general",
                "system_prompt": "你是一个智能AI助手，能够帮助用户解答问题、进行对话交流。请用简洁、准确、友好的方式回应用户的问题。",
                "is_active": True
            },
            {
                "name": "flow_agent",
                "display_name": "流程图智能体",
                "description": "可配置各种节点的流程图智能体",
                "agent_type": "flow_driven",
                "flow_config": {},
                "is_active": True
            }
        ]
        
        for agent_data in default_agents:
            agent = Agent(**agent_data)
            db.add(agent)
        
        db.commit()
        logger.info(f"创建了 {len(default_agents)} 个默认智能体")
        
    except Exception as e:
        logger.error(f"创建默认智能体失败: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

def create_default_mcp_servers():
    """创建默认MCP服务器"""
    logger.info("检查默认MCP服务器...")
    
    db = SessionLocal()
    try:
        from models.database_models import MCPServer
        
        # 检查是否已有MCP服务器
        existing_servers = db.query(MCPServer).count()
        if existing_servers > 0:
            logger.info(f"数据库中已有 {existing_servers} 个MCP服务器，跳过创建默认MCP服务器")
            return
        
        # 创建默认的ddg MCP服务器
        default_servers = [
            {
                "name": "ddg",
                "display_name": "DuckDuckGo搜索服务",
                "description": "提供网络搜索功能的MCP服务器",
                "transport": "stdio",
                "command": "uvx",
                "args": ["duckduckgo-mcp-server"],
                "env": {},
                "is_active": True,
                "config": {
                    "command": "uvx",
                    "args": ["duckduckgo-mcp-server"],
                    "env": {}
                }
            }
        ]
        
        for server_data in default_servers:
            server = MCPServer(**server_data)
            db.add(server)
        
        db.commit()
        logger.info(f"创建了 {len(default_servers)} 个默认MCP服务器")
        
    except Exception as e:
        logger.error(f"创建默认MCP服务器失败: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

def init_database():
    """初始化数据库"""
    logger.info("开始初始化数据库...")
    
    # 运行迁移
    run_migrations()
    
    # 创建默认智能体
    create_default_agents()
    
    # 创建默认MCP服务器
    create_default_mcp_servers()
    
    # 创建默认LLM配置
    from database.database import create_default_llm_configs
    create_default_llm_configs()
    
    logger.info("数据库初始化完成")

if __name__ == "__main__":
    init_database() 