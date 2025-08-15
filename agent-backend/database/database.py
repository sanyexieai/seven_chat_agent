from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from typing import Generator
import os
from config.env import DATABASE_URL
from models.database_models import Base

# 创建数据库引擎
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 使用database_models中的Base
from models.database_models import Agent, UserSession, ChatMessage, MCPServer, MCPTool, LLMConfig, Flow

def get_db() -> Generator[Session, None, None]:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """初始化数据库"""
    import os
    
    # 确保数据目录存在
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    
    # 确保文档目录存在
    documents_dir = os.path.join(data_dir, "documents")
    os.makedirs(documents_dir, exist_ok=True)
    
    # 导入所有模型以确保表被创建
    from models.database_models import Agent, UserSession, MCPServer, MCPTool, LLMConfig, Flow, KnowledgeBase, Document, DocumentChunk, KnowledgeBaseQuery
    
    # 运行数据库迁移
    from database.migrations import init_database
    init_database()
    
    # 创建默认数据
    create_default_agents()
    create_default_llm_configs()


def create_default_agents():
    """创建默认智能体"""
    from models.database_models import Agent
    
    db = SessionLocal()
    try:
        # 检查是否已有智能体
        existing_agents = db.query(Agent).count()
        if existing_agents > 0:
            return
        
        # 创建默认智能体
        default_agents = [
            {
                "name": "general_agent",
                "display_name": "通用智能体",
                "description": "可配置提示词、工具和LLM的通用智能体",
                "agent_type": "general",
                "system_prompt": "你是一个智能AI助手，能够帮助用户解答问题、进行对话交流。请用简洁、准确、友好的方式回应用户的问题。",
                "config": {
                    "model": "qwen3:32b",
                    "temperature": 0.7,
                    "max_tokens": 2048
                }
            },
            {
                "name": "flow_agent",
                "display_name": "流程图智能体",
                "description": "可配置各种节点的流程图智能体",
                "agent_type": "flow_driven",
                "flow_config": {},
                "config": {
                    "model": "qwen3:32b",
                    "temperature": 0.5,
                    "max_tokens": 2048
                }
            }
        ]
        
        for agent_data in default_agents:
            agent = Agent(**agent_data)
            db.add(agent)
        
        db.commit()
        print("默认智能体创建完成")
        
    except Exception as e:
        db.rollback()
        print(f"创建默认智能体失败: {e}")
    finally:
        db.close()

def create_default_llm_configs():
    """创建默认LLM配置"""
    from services.llm_config_service import LLMConfigService
    from models.database_models import LLMConfigCreate
    import os
    
    db = SessionLocal()
    try:
        # 检查是否已有LLM配置
        existing_configs = LLMConfigService.get_all_configs(db)
        if existing_configs:
            print(f"已存在 {len(existing_configs)} 个LLM配置，跳过初始化")
            return
        
        # 默认LLM配置
        default_configs = [
            {
                "name": "openai_gpt4",
                "display_name": "OpenAI GPT-4",
                "description": "OpenAI GPT-4 模型配置",
                "provider": "openai",
                "model_name": "gpt-4",
                "api_key": os.getenv("OPENAI_API_KEY", ""),
                "api_base": "https://api.openai.com/v1",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            },
            {
                "name": "ollama_qwen",
                "display_name": "Ollama Qwen 模型",
                "description": "Ollama Qwen 模型配置(开发环境 不一定可用)",
                "provider": "ollama",
                "model_name": "qwen3:32b",
                "api_key": "",
                "api_base": "http://192.168.1.39:11434",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 10240
                },
                "is_default": False
            },
            {
                "name": "ollama_llama",
                "display_name": "Ollama Llama 模型",
                "description": "Ollama Llama 模型配置(服务器cpu环境)",
                "provider": "ollama",
                "model_name": "llama3.2:latest",
                "api_key": "",
                "api_base": "http://192.168.1.48:11434",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": True
            },
            {
                "name": "ollama_mistral",
                "display_name": "Ollama Mistral 模型",
                "description": "Ollama Mistral 模型配置",
                "provider": "ollama",
                "model_name": "mistral:7b",
                "api_key": "",
                "api_base": "http://localhost:11434",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            },
            {
                "name": "deepseek_chat",
                "display_name": "DeepSeek Chat",
                "description": "DeepSeek Chat 模型配置",
                "provider": "deepseek",
                "model_name": "deepseek-chat",
                "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
                "api_base": "https://api.deepseek.com",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            },
            {
                "name": "deepseek_coder",
                "display_name": "DeepSeek Coder",
                "description": "DeepSeek Coder 代码生成模型配置",
                "provider": "deepseek",
                "model_name": "deepseek-coder",
                "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
                "api_base": "https://api.deepseek.com",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            }
        ]
        
        for config_data in default_configs:
            try:
                config_create = LLMConfigCreate(**config_data)
                config = LLMConfigService.create_config(db, config_create)
                print(f"创建LLM配置: {config.display_name}")
            except Exception as e:
                print(f"创建LLM配置失败 {config_data['name']}: {str(e)}")
        
        print("默认LLM配置创建完成")
        
    except Exception as e:
        print(f"创建默认LLM配置失败: {str(e)}")
    finally:
        db.close()

 