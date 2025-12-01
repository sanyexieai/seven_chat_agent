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
        
        # 运行提示词模板表迁移
        run_prompt_template_migrations()
        
        # 运行知识图谱相关表迁移
        run_knowledge_graph_migrations()
        
        # 运行临时工具表迁移
        run_temporary_tools_migrations()
        
        # 运行工具配置表迁移
        run_tool_config_migrations()
            
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
                if not check_column_exists('mcp_tools', 'raw_data'):
                    missing_tool_columns.append('raw_data')
                if not check_column_exists('mcp_tools', 'tool_metadata'):
                    missing_tool_columns.append('tool_metadata')
                
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
                        elif column == 'raw_data':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN raw_data JSON;"))
                            logger.info("添加 raw_data 字段")
                        elif column == 'tool_metadata':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN tool_metadata JSON;"))
                            logger.info("添加 tool_metadata 字段")
                        elif column == 'container_type':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN container_type VARCHAR(50) DEFAULT 'none';"))
                            logger.info("添加 container_type 字段")
                        elif column == 'container_config':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN container_config JSON;"))
                            logger.info("添加 container_config 字段")
                    
                    logger.info("MCP工具表迁移完成")
                else:
                    logger.info("MCP工具表结构已是最新版本")
                    
                    # 检查容器相关字段
                    if not check_column_exists('mcp_tools', 'container_type'):
                        logger.info("添加 container_type 字段到 mcp_tools 表...")
                        conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN container_type VARCHAR(50) DEFAULT 'none';"))
                        logger.info("成功添加 container_type 字段")
                    if not check_column_exists('mcp_tools', 'container_config'):
                        logger.info("添加 container_config 字段到 mcp_tools 表...")
                        conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN container_config JSON;"))
                        logger.info("成功添加 container_config 字段")
                    if not check_column_exists('mcp_tools', 'raw_data'):
                        logger.info("添加 raw_data 字段到 mcp_tools 表...")
                        conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN raw_data JSON;"))
                        logger.info("成功添加 raw_data 字段")
                    if not check_column_exists('mcp_tools', 'tool_metadata'):
                        logger.info("添加 tool_metadata 字段到 mcp_tools 表...")
                        conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN tool_metadata JSON;"))
                        logger.info("成功添加 tool_metadata 字段")
            
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
            # 新增：领域/策略/摘要相关字段
            if not check_column_exists('document_chunks', 'domain'):
                missing_chunk_columns.append('domain')
            if not check_column_exists('document_chunks', 'domain_confidence'):
                missing_chunk_columns.append('domain_confidence')
            if not check_column_exists('document_chunks', 'chunk_strategy'):
                missing_chunk_columns.append('chunk_strategy')
            if not check_column_exists('document_chunks', 'strategy_variant'):
                missing_chunk_columns.append('strategy_variant')
            if not check_column_exists('document_chunks', 'is_summary'):
                missing_chunk_columns.append('is_summary')
            if not check_column_exists('document_chunks', 'summary_parent_chunk_id'):
                missing_chunk_columns.append('summary_parent_chunk_id')
            if not check_column_exists('document_chunks', 'section_title'):
                missing_chunk_columns.append('section_title')
            if not check_column_exists('document_chunks', 'chunk_type'):
                missing_chunk_columns.append('chunk_type')
            if not check_column_exists('document_chunks', 'source_query'):
                missing_chunk_columns.append('source_query')
            if not check_column_exists('document_chunks', 'parent_chunk_ids'):
                missing_chunk_columns.append('parent_chunk_ids')
            
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
                    elif column == 'domain':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN domain VARCHAR(100);"))
                        logger.info("添加 domain 字段")
                    elif column == 'domain_confidence':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN domain_confidence FLOAT DEFAULT 0;"))
                        logger.info("添加 domain_confidence 字段")
                    elif column == 'chunk_strategy':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN chunk_strategy VARCHAR(50);"))
                        logger.info("添加 chunk_strategy 字段")
                    elif column == 'strategy_variant':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN strategy_variant VARCHAR(50);"))
                        logger.info("添加 strategy_variant 字段")
                    elif column == 'is_summary':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN is_summary BOOLEAN DEFAULT 0;"))
                        logger.info("添加 is_summary 字段")
                    elif column == 'summary_parent_chunk_id':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN summary_parent_chunk_id INTEGER REFERENCES document_chunks(id);"))
                        logger.info("添加 summary_parent_chunk_id 字段")
                    elif column == 'section_title':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN section_title VARCHAR(500);"))
                        logger.info("添加 section_title 字段")
                    elif column == 'chunk_type':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN chunk_type VARCHAR(50) DEFAULT '原文';"))
                        logger.info("添加 chunk_type 字段")
                    elif column == 'source_query':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN source_query VARCHAR(1000);"))
                        logger.info("添加 source_query 字段")
                    elif column == 'parent_chunk_ids':
                        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN parent_chunk_ids JSON;"))
                        logger.info("添加 parent_chunk_ids 字段")
                
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

def run_temporary_tools_migrations():
    """运行临时工具表的数据库迁移"""
    logger.info("开始检查临时工具表迁移...")
    
    try:
        with engine.connect() as conn:
            # 检查temporary_tools表是否存在
            inspector = inspect(engine)
            if 'temporary_tools' not in inspector.get_table_names():
                logger.info("temporary_tools表不存在，创建临时工具表...")
                Base.metadata.create_all(bind=engine)
                logger.info("临时工具表创建完成")
                return
            
            logger.info("临时工具表已存在，检查字段...")
            
            # 检查字段是否存在
            missing_columns = []
            
            if not check_column_exists('temporary_tools', 'code'):
                missing_columns.append('code')
            if not check_column_exists('temporary_tools', 'input_schema'):
                missing_columns.append('input_schema')
            if not check_column_exists('temporary_tools', 'output_schema'):
                missing_columns.append('output_schema')
            if not check_column_exists('temporary_tools', 'examples'):
                missing_columns.append('examples')
            if not check_column_exists('temporary_tools', 'is_temporary'):
                missing_columns.append('is_temporary')
            if not check_column_exists('temporary_tools', 'container_type'):
                missing_columns.append('container_type')
            if not check_column_exists('temporary_tools', 'container_config'):
                missing_columns.append('container_config')
            
            if missing_columns:
                logger.info(f"发现缺失字段: {missing_columns}")
                for column in missing_columns:
                    if column == 'code':
                        conn.execute(text("ALTER TABLE temporary_tools ADD COLUMN code TEXT;"))
                        logger.info("添加 code 字段")
                    elif column == 'input_schema':
                        conn.execute(text("ALTER TABLE temporary_tools ADD COLUMN input_schema JSON;"))
                        logger.info("添加 input_schema 字段")
                    elif column == 'output_schema':
                        conn.execute(text("ALTER TABLE temporary_tools ADD COLUMN output_schema JSON;"))
                        logger.info("添加 output_schema 字段")
                    elif column == 'examples':
                        conn.execute(text("ALTER TABLE temporary_tools ADD COLUMN examples JSON;"))
                        logger.info("添加 examples 字段")
                    elif column == 'is_temporary':
                        conn.execute(text("ALTER TABLE temporary_tools ADD COLUMN is_temporary BOOLEAN DEFAULT 1;"))
                        logger.info("添加 is_temporary 字段")
                    elif column == 'container_type':
                        conn.execute(text("ALTER TABLE temporary_tools ADD COLUMN container_type VARCHAR(50) DEFAULT 'none';"))
                        logger.info("添加 container_type 字段")
                    elif column == 'container_config':
                        conn.execute(text("ALTER TABLE temporary_tools ADD COLUMN container_config JSON;"))
                        logger.info("添加 container_config 字段")
                
                logger.info("临时工具表迁移完成")
            else:
                logger.info("临时工具表结构已是最新版本")
            
            conn.commit()
            logger.info("临时工具表迁移完成")
                
    except Exception as e:
        logger.error(f"临时工具表迁移失败: {str(e)}")
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
                "flow_config": {
                    "nodes": [
                        {
                            "id": "start_node",
                            "type": "start",
                            "category": "start",
                            "implementation": "start",
                            "position": {
                                "x": 286.25650822501484,
                                "y": -42.71187021735619
                            },
                            "data": {
                                "label": "开始",
                                "nodeType": "start",
                                "config": {},
                                "isStartNode": True,
                                "isEndNode": False
                            }
                        },
                        {
                            "id": "node_1764068082424",
                            "type": "planner",
                            "category": "processor",
                            "implementation": "planner",
                            "position": {
                                "x": -326.98345782300225,
                                "y": 112.89646375781717
                            },
                            "data": {
                                "label": "规划节点",
                                "nodeType": "planner",
                                "config": {},
                                "isStartNode": False,
                                "isEndNode": False
                            }
                        },
                        {
                            "id": "end_node",
                            "type": "end",
                            "category": "end",
                            "implementation": "end",
                            "position": {
                                "x": 202.70784356173795,
                                "y": 501.109235622072
                            },
                            "data": {
                                "label": "结束",
                                "nodeType": "end",
                                "config": {},
                                "isStartNode": False,
                                "isEndNode": True
                            }
                        }
                    ],
                    "edges": [
                        {
                            "id": "edge_1764068086456",
                            "source": "start_node",
                            "target": "node_1764068082424",
                            "type": "default"
                        },
                        {
                            "id": "edge_1764068146739",
                            "source": "node_1764068082424",
                            "target": "end_node",
                            "type": "default"
                        }
                    ],
                    "metadata": {
                        "name": "测试",
                        "description": "",
                        "version": "1.0.0"
                    }
                },
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

def run_prompt_template_migrations():
    """运行提示词模板相关的数据库迁移"""
    logger.info("开始检查提示词模板相关表迁移...")
    
    try:
        if not check_table_exists('prompt_templates'):
            logger.info("创建 prompt_templates 表...")
            Base.metadata.create_all(bind=engine, tables=[Base.metadata.tables['prompt_templates']])
            logger.info("prompt_templates 表创建完成")
        else:
            logger.info("prompt_templates 表已存在")
            
            # 检查必要的字段
            missing_columns = []
            if not check_column_exists('prompt_templates', 'is_builtin'):
                missing_columns.append('is_builtin')
            if not check_column_exists('prompt_templates', 'version'):
                missing_columns.append('version')
            if not check_column_exists('prompt_templates', 'usage_count'):
                missing_columns.append('usage_count')
            if not check_column_exists('prompt_templates', 'source_file'):
                missing_columns.append('source_file')
            if not check_column_exists('prompt_templates', 'is_active'):
                missing_columns.append('is_active')
            if not check_column_exists('prompt_templates', 'variables'):
                missing_columns.append('variables')
            
            # 检查是否需要移除 is_default 字段（如果存在）
            if check_column_exists('prompt_templates', 'is_default'):
                logger.info("检测到旧字段 is_default，将在迁移中移除...")
                missing_columns.append('_remove_is_default')
            
            if missing_columns:
                logger.info(f"发现需要迁移的字段: {missing_columns}")
                with engine.connect() as conn:
                    for column in missing_columns:
                        if column == 'is_builtin':
                            conn.execute(text("ALTER TABLE prompt_templates ADD COLUMN is_builtin BOOLEAN DEFAULT 0;"))
                            logger.info("添加 is_builtin 字段")
                        elif column == 'version':
                            conn.execute(text("ALTER TABLE prompt_templates ADD COLUMN version VARCHAR(50);"))
                            logger.info("添加 version 字段")
                        elif column == 'usage_count':
                            conn.execute(text("ALTER TABLE prompt_templates ADD COLUMN usage_count INTEGER DEFAULT 0;"))
                            logger.info("添加 usage_count 字段")
                        elif column == 'source_file':
                            conn.execute(text("ALTER TABLE prompt_templates ADD COLUMN source_file VARCHAR(500);"))
                            logger.info("添加 source_file 字段")
                        elif column == 'is_active':
                            conn.execute(text("ALTER TABLE prompt_templates ADD COLUMN is_active BOOLEAN DEFAULT 1;"))
                            logger.info("添加 is_active 字段")
                        elif column == 'variables':
                            conn.execute(text("ALTER TABLE prompt_templates ADD COLUMN variables JSON;"))
                            logger.info("添加 variables 字段")
                        elif column == '_remove_is_default':
                            # SQLite 不支持直接删除列，需要重建表
                            logger.info("移除 is_default 字段（SQLite需要重建表）...")
                            try:
                                # 创建新表（不包含 is_default）
                                conn.execute(text("""
                                    CREATE TABLE prompt_templates_new (
                                        id INTEGER PRIMARY KEY,
                                        name VARCHAR(100) UNIQUE NOT NULL,
                                        display_name VARCHAR(200) NOT NULL,
                                        description TEXT,
                                        template_type VARCHAR(50) NOT NULL,
                                        content TEXT NOT NULL,
                                        variables JSON,
                                        is_builtin BOOLEAN DEFAULT 0,
                                        version VARCHAR(50),
                                        usage_count INTEGER DEFAULT 0,
                                        source_file VARCHAR(500),
                                        is_active BOOLEAN DEFAULT 1,
                                        created_at DATETIME,
                                        updated_at DATETIME
                                    );
                                """))
                                # 复制数据（排除 is_default）
                                conn.execute(text("""
                                    INSERT INTO prompt_templates_new 
                                    (id, name, display_name, description, template_type, content, variables, 
                                     is_builtin, version, usage_count, source_file, is_active, created_at, updated_at)
                                    SELECT id, name, display_name, description, template_type, content, variables,
                                           COALESCE(is_builtin, 0), COALESCE(version, '1.0.0'), 
                                           COALESCE(usage_count, 0), source_file, 
                                           COALESCE(is_active, 1), created_at, updated_at
                                    FROM prompt_templates;
                                """))
                                # 删除旧表
                                conn.execute(text("DROP TABLE prompt_templates;"))
                                # 重命名新表
                                conn.execute(text("ALTER TABLE prompt_templates_new RENAME TO prompt_templates;"))
                                logger.info("成功移除 is_default 字段")
                            except Exception as e:
                                logger.warning(f"移除 is_default 字段失败（可能已不存在）: {str(e)}")
                    conn.commit()
                    logger.info("prompt_templates 表迁移完成")
        
        # 初始化默认提示词模板
        create_default_prompt_templates()
        
    except Exception as e:
        logger.error(f"提示词模板表迁移失败: {str(e)}")
        raise


def create_default_prompt_templates():
    """创建默认提示词模板"""
    from models.database_models import PromptTemplate
    
    db = SessionLocal()
    try:
        # 检查是否已有提示词模板
        existing_count = db.query(PromptTemplate).count()
        
        # 总是调用提取脚本，因为它会检查并更新/创建缺失的提示词
        logger.info(f"当前数据库中有 {existing_count} 个提示词模板，开始同步所有提示词...")
        db.close()
        
        # 调用提取脚本，将所有提示词提取到数据库（会自动创建缺失的，更新已存在的）
        try:
            import sys
            import os
            # 确保可以导入 scripts 模块
            # 获取 agent-backend 目录路径
            backend_dir = os.path.dirname(os.path.dirname(__file__))
            scripts_path = os.path.join(backend_dir, 'scripts')
            # 将 scripts 目录添加到 sys.path
            if scripts_path not in sys.path:
                sys.path.insert(0, scripts_path)
            # 同时将 backend_dir 添加到 sys.path，确保可以导入其他模块
            if backend_dir not in sys.path:
                sys.path.insert(0, backend_dir)
            
            from extract_prompts_to_db import extract_prompts_to_database
            extract_prompts_to_database()
            logger.info("所有提示词已成功同步到数据库")
        except Exception as e:
            logger.error(f"提取提示词失败: {str(e)}", exc_info=True)
            if existing_count == 0:
                logger.info("回退到创建基础默认提示词模板...")
                # 如果提取失败且数据库为空，至少创建基础的3个默认模板
                _create_basic_default_prompt_templates()
            else:
                logger.warning("提取提示词失败，但数据库中已有部分提示词，跳过后备方案")
        
    except Exception as e:
        logger.error(f"创建默认提示词模板失败: {str(e)}")
        db.rollback()
        db.close()
        raise


def _create_basic_default_prompt_templates():
    """创建基础的默认提示词模板（作为后备方案）"""
    from models.database_models import PromptTemplate
    
    db = SessionLocal()
    try:
        # 默认系统提示词
        system_template = PromptTemplate(
            name="auto_infer_system",
            display_name="自动推理系统提示词",
            description="用于AI参数推理的系统提示词",
            template_type="system",
            content="你是一个工具参数推理助手。请根据用户输入和工具描述，生成满足工具 schema 的 JSON 参数。\n必须输出 JSON，对每个必填字段给出合理值。",
            variables=["tool_name", "tool_type", "server", "schema_json", "message", "previous_output"],
            is_builtin=True,
            version="1.0.0",
            usage_count=0,
            source_file="utils/prompt_templates.py",
            is_active=True
        )
        db.add(system_template)
        
        # 默认用户提示词（完整版）
        user_template_full = PromptTemplate(
            name="auto_infer_user_full",
            display_name="自动推理用户提示词（完整版）",
            description="用于AI参数推理的用户提示词，包含必填字段说明",
            template_type="user",
            content="工具名称：{tool_name}\n工具类型：{tool_type}\n服务器：{server}\n参数 Schema：\n{schema_json}\n{required_fields_text}\n用户输入：{message}\n如果需要上下文，可参考上一节点输出：{previous_output}\n\n请输出 JSON，严格遵守 schema 格式。\n重要：\n1. 必须包含所有必填字段（如果上面列出了必填字段）\n2. 根据字段类型和描述，为每个必填字段生成合理的值",
            variables=["tool_name", "tool_type", "server", "schema_json", "required_fields_text", "message", "previous_output"],
            is_builtin=True,
            version="1.0.0",
            usage_count=0,
            source_file="utils/prompt_templates.py",
            is_active=True
        )
        db.add(user_template_full)
        
        # 默认用户提示词（简化版）
        user_template_simple = PromptTemplate(
            name="auto_infer_user_simple",
            display_name="自动推理用户提示词（简化版）",
            description="用于AI参数推理的用户提示词，不包含必填字段说明（向后兼容）",
            template_type="user",
            content="工具名称：{tool_name}\n工具类型：{tool_type}\n服务器：{server}\n参数 Schema：\n{schema_json}\n\n用户输入：{message}\n如果需要上下文，可参考上一节点输出：{previous_output}\n\n请输出 JSON，严格遵守 schema 格式。",
            variables=["tool_name", "tool_type", "server", "schema_json", "message", "previous_output"],
            is_builtin=True,
            version="1.0.0",
            usage_count=0,
            source_file="utils/prompt_templates.py",
            is_active=True
        )
        db.add(user_template_simple)
        
        db.commit()
        logger.info("基础默认提示词模板创建完成（后备方案）")
        
    except Exception as e:
        logger.error(f"创建基础默认提示词模板失败: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


def run_tool_config_migrations():
    """运行工具配置表的数据库迁移"""
    logger.info("开始检查工具配置表迁移...")
    
    try:
        with engine.connect() as conn:
            # 检查tool_configs表是否存在
            inspector = inspect(engine)
            if 'tool_configs' not in inspector.get_table_names():
                logger.info("tool_configs表不存在，创建工具配置表...")
                Base.metadata.create_all(bind=engine)
                logger.info("工具配置表创建完成")
                return
            
            logger.info("工具配置表已存在，检查字段...")
            
            # 检查字段是否存在
            missing_columns = []
            
            if not check_column_exists('tool_configs', 'tool_name'):
                missing_columns.append('tool_name')
            if not check_column_exists('tool_configs', 'tool_type'):
                missing_columns.append('tool_type')
            if not check_column_exists('tool_configs', 'container_type'):
                missing_columns.append('container_type')
            if not check_column_exists('tool_configs', 'container_config'):
                missing_columns.append('container_config')
            
            if missing_columns:
                logger.info(f"发现缺失字段: {missing_columns}")
                for column in missing_columns:
                    if column == 'tool_name':
                        conn.execute(text("ALTER TABLE tool_configs ADD COLUMN tool_name VARCHAR(100) NOT NULL;"))
                        logger.info("添加 tool_name 字段")
                    elif column == 'tool_type':
                        conn.execute(text("ALTER TABLE tool_configs ADD COLUMN tool_type VARCHAR(50) NOT NULL;"))
                        logger.info("添加 tool_type 字段")
                    elif column == 'container_type':
                        conn.execute(text("ALTER TABLE tool_configs ADD COLUMN container_type VARCHAR(50) DEFAULT 'none';"))
                        logger.info("添加 container_type 字段")
                    elif column == 'container_config':
                        conn.execute(text("ALTER TABLE tool_configs ADD COLUMN container_config JSON;"))
                        logger.info("添加 container_config 字段")
                
                logger.info("工具配置表迁移完成")
            else:
                logger.info("工具配置表结构已是最新版本")
            
            conn.commit()
            logger.info("工具配置表迁移完成")
                
    except Exception as e:
        logger.error(f"工具配置表迁移失败: {str(e)}")
        raise

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


def migrate_tool_prompt_links_table():
    """创建或迁移工具-提示词关联表 tool_prompt_links"""
    logger.info("检查/迁移 tool_prompt_links 表结构...")
    try:
        inspector = inspect(engine)
        table_name = "tool_prompt_links"
        
        with engine.begin() as conn:
            if table_name not in inspector.get_table_names():
                logger.info("tool_prompt_links 表不存在，创建新表...")
                from models.database_models import Base  # type: ignore
                # 让 SQLAlchemy 知道只创建这一张表
                Base.metadata.tables[table_name].create(bind=engine, checkfirst=True)
                logger.info("tool_prompt_links 表创建完成")
            else:
                logger.info("tool_prompt_links 表已存在，目前不做字段级迁移")
    except Exception as e:
        logger.error(f"tool_prompt_links 表迁移失败: {str(e)}")
        raise

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
    
    # 创建默认提示词模板
    create_default_prompt_templates()
    
    # 创建/迁移工具-提示词关联表
    migrate_tool_prompt_links_table()
    
    logger.info("数据库初始化完成")

if __name__ == "__main__":
    init_database() 