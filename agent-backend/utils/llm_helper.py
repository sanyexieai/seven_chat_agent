# -*- coding: utf-8 -*-
import os
import asyncio
from typing import Optional, Dict, Any, AsyncGenerator, List
import json
import httpx
import openai
import anthropic
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

from config.env import MODEL, MODEL_PROVIDER, TEMPERATURE, BASE_URL, API_KEY
from config.llm_config_manager import llm_config_manager
from utils.log_helper import get_logger

# 获取logger实例
logger = get_logger("llm_helper")

class LLMHelper:
    """大模型助手单例类，支持多模型配置、动态切换、便捷调用。"""
    _instance: Optional['LLMHelper'] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._config = {}
            self._openai_client = None
            self._anthropic_client = None
            self._ollama_base_url = None
            self._initialized = True

    def setup(self, llm_config: Optional[Dict[str, Any]] = None, **kwargs) -> 'LLMHelper':
        """
        配置并初始化大模型
        
        Args:
            llm_config: 可选的LLM配置字典，包含provider, model_name, api_key, api_base等
            **kwargs: 其他配置参数
        """
        if llm_config:
            # 使用传入的LLM配置
            self._config = {
                'model': llm_config.get('model_name', ''),
                'model_provider': llm_config.get('provider', ''),
                'temperature': llm_config.get('config', {}).get('temperature', 0.7),
                'base_url': llm_config.get('api_base', ''),
                'api_key': llm_config.get('api_key', '')
            }
            logger.info(f"使用传入的LLM配置: {llm_config.get('provider')} - {llm_config.get('model_name')}")
        else:
            # 从数据库配置管理器获取配置
            db_config = llm_config_manager.get_default_config()
            
            if db_config:
                # 使用数据库配置
                self._config = {
                    'model': db_config.model_name,
                    'model_provider': db_config.provider,
                    'temperature': db_config.config.get('temperature', 0.7) if db_config.config else 0.7,
                    'base_url': db_config.api_base,
                    'api_key': db_config.api_key
                }
                logger.info(f"使用数据库LLM配置: {db_config.display_name}")
            else:
                # 使用环境变量配置作为fallback
                self._config = dict(
                    model=MODEL, 
                    model_provider=MODEL_PROVIDER, 
                    temperature=TEMPERATURE, 
                    base_url=BASE_URL, 
                    api_key=API_KEY
                )
                logger.info("使用环境变量LLM配置")
        
        self._config.update(kwargs)
        
        # 初始化客户端
        self._init_clients()
        
        return self

    def _init_clients(self):
        """初始化LLM客户端"""
        try:
            provider = self._config.get('model_provider')
            
            if provider == 'openai':
                self._openai_client = AsyncOpenAI(
                    api_key=self._config.get('api_key'),
                    base_url=self._config.get('base_url')
                )
                logger.info("OpenAI客户端初始化成功")
            elif provider == 'anthropic':
                self._anthropic_client = AsyncAnthropic(
                    api_key=self._config.get('api_key')
                )
                logger.info("Anthropic客户端初始化成功")
            elif provider == 'ollama':
                self._ollama_base_url = self._config.get('base_url', 'http://localhost:11434')
                logger.info(f"Ollama客户端初始化成功，基础URL: {self._ollama_base_url}")
            elif provider == 'deepseek':
                self._deepseek_base_url = self._config.get('base_url', 'https://api.deepseek.com')
                self._deepseek_api_key = self._config.get('api_key', '')
                logger.info(f"DeepSeek客户端初始化成功，基础URL: {self._deepseek_base_url}")
            else:
                raise Exception(f"不支持的模型提供商: {provider}")
                
        except Exception as e:
            logger.error(f"LLM客户端初始化失败: {str(e)}")
            raise

    async def call(self, messages, **kwargs):
        """
        异步调用大模型
        :param messages: 聊天消息（list/dict/str）
        :param kwargs: 其他参数
        :return: 大模型输出
        """
        try:
            # 处理不同类型的输入
            if isinstance(messages, str):
                # 字符串输入，转换为消息格式
                messages = [{"role": "user", "content": messages}]
            elif isinstance(messages, list):
                # 确保消息格式正确
                formatted_messages = []
                for msg in messages:
                    if isinstance(msg, dict):
                        formatted_messages.append(msg)
                    elif isinstance(msg, str):
                        formatted_messages.append({"role": "user", "content": msg})
                    else:
                        formatted_messages.append({"role": "user", "content": str(msg)})
                messages = formatted_messages
            
            # 记录对话内容到日志
            logger.info(f"LLM调用 - 模型: {self._config.get('model_provider')}/{self._config.get('model')}")
            logger.info(f"LLM输入消息: {json.dumps(messages, ensure_ascii=False, indent=2)}")
            
            # 调用对应的LLM
            provider = self._config.get('model_provider')
            if provider == 'openai':
                response = await self._call_openai(messages, **kwargs)
            elif provider == 'anthropic':
                response = await self._call_anthropic(messages, **kwargs)
            elif provider == 'ollama':
                response = await self._call_ollama(messages, **kwargs)
            elif provider == 'deepseek':
                response = await self._call_deepseek(messages, **kwargs)
            else:
                raise Exception(f"不支持的模型提供商: {provider}")
            
            # 记录响应到日志
            logger.info(f"LLM响应: {response}")
            
            return response
                
        except Exception as e:
            logger.error(f"LLM调用失败: {str(e)}")
            raise

    async def _call_openai(self, messages: List[Dict], **kwargs) -> str:
        """调用OpenAI API"""
        try:
            if not self._openai_client:
                raise Exception("OpenAI客户端未初始化")
            
            # 优先从数据库配置获取token值，然后是kwargs参数，最后是默认值
            db_max_tokens = self._config.get('config', {}).get('max_tokens')
            max_tokens = kwargs.get('max_tokens') or db_max_tokens or 1000
            
            # 合并配置参数
            params = {
                "model": self._config.get('model', 'gpt-3.5-turbo'),
                "messages": messages,
                "temperature": self._config.get('temperature', 0.7),
                "max_tokens": max_tokens,
                **kwargs
            }
            
            response = await self._openai_client.chat.completions.create(**params)
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI调用失败: {str(e)}")
            raise

    async def _call_anthropic(self, messages: List[Dict], **kwargs) -> str:
        """调用Anthropic API"""
        try:
            if not self._anthropic_client:
                raise Exception("Anthropic客户端未初始化")
            
            # 转换消息格式
            system_message = ""
            user_messages = []
            
            for msg in messages:
                if msg.get('role') == 'system':
                    system_message = msg.get('content', '')
                elif msg.get('role') == 'user':
                    user_messages.append(msg.get('content', ''))
                elif msg.get('role') == 'assistant':
                    # Anthropic不支持assistant消息，跳过
                    continue
            
            # 合并用户消息
            user_content = "\n".join(user_messages)
            
            # 优先从数据库配置获取token值，然后是kwargs参数，最后是默认值
            db_max_tokens = self._config.get('config', {}).get('max_tokens')
            max_tokens = kwargs.get('max_tokens') or db_max_tokens or 1000
            
            # 调用API
            params = {
                "model": self._config.get('model', 'claude-3-sonnet-20240229'),
                "max_tokens": max_tokens,
                "temperature": self._config.get('temperature', 0.7),
                **kwargs
            }
            
            if system_message:
                params["system"] = system_message
            
            response = await self._anthropic_client.messages.create(
                messages=[{"role": "user", "content": user_content}],
                **params
            )
            
            return response.content[0].text
            
        except Exception as e:
            logger.error(f"Anthropic调用失败: {str(e)}")
            raise

    async def _call_ollama(self, messages: List[Dict], **kwargs) -> str:
        """调用Ollama API"""
        try:
            if not self._ollama_base_url:
                raise Exception("Ollama客户端未初始化")
            
            # 优先从数据库配置获取token值，然后是kwargs参数，最后是默认值
            db_max_tokens = self._config.get('config', {}).get('max_tokens')
            max_tokens = kwargs.get('max_tokens') or db_max_tokens or 512
            max_tokens = max(64, min(int(max_tokens), 512))
            data = {
                "model": self._config.get('model', 'qwen3:8b'),
                "messages": messages,
                "stream": False,
                "keep_alive": "5m",
                "options": {
                    "temperature": self._config.get('temperature', 0.7),
                    "num_predict": max_tokens,
                    **kwargs.get('options', {})
                }
            }
            
            logger.info(f"Ollama请求URL: {self._ollama_base_url}/api/chat")
            safe_preview = json.dumps({**data, 'messages': '[omitted for brevity]'}, ensure_ascii=False)
            logger.info(f"Ollama请求数据(简要): {safe_preview}")
            logger.info(f"Ollama配置: {self._config}")
            
            # 直接使用同步requests库，避免异步问题
            import time
            import requests
            start_time = time.time()
            
            logger.info("使用同步requests发送Ollama请求...")
            
            try:
                response = requests.post(
                    f"{self._ollama_base_url}/api/chat",
                    json=data,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                
                end_time = time.time()
                logger.info(f"请求完成时间: {end_time}")
                logger.info(f"请求耗时: {end_time - start_time:.2f}秒")
                logger.info(f"Ollama响应状态码: {response.status_code}")
                logger.info(f"Ollama响应头: {dict(response.headers)}")
                
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"Ollama响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
                
                content = result.get('message', {}).get('content', '')
                logger.info(f"提取的内容: {content}")
                return content
                
            except requests.exceptions.Timeout:
                logger.error("同步请求超时")
                raise
            except requests.exceptions.RequestException as e:
                logger.error(f"同步请求失败: {str(e)}")
                raise
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama HTTP错误: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Ollama请求错误: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Ollama响应JSON解析错误: {str(e)}")
            logger.error(f"响应内容: {response.text if 'response' in locals() else 'N/A'}")
            raise
        except Exception as e:
            logger.error(f"Ollama调用失败: {str(e)}")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误详情: {str(e)}")
            
            # 同步请求已经失败，记录错误
            logger.error("同步请求失败，无法获取Ollama响应")

    async def call_stream(self, messages, **kwargs) -> AsyncGenerator[str, None]:
        """
        流式调用大模型
        :param messages: 聊天消息
        :param kwargs: 其他参数
        :yield: 流式响应片段
        """
        try:
            # 处理不同类型的输入
            if isinstance(messages, str):
                messages = [{"role": "user", "content": messages}]
            elif isinstance(messages, list):
                formatted_messages = []
                for msg in messages:
                    if isinstance(msg, dict):
                        formatted_messages.append(msg)
                    elif isinstance(msg, str):
                        formatted_messages.append({"role": "user", "content": msg})
                    else:
                        formatted_messages.append({"role": "user", "content": str(msg)})
                messages = formatted_messages
            
            # 记录流式对话内容到日志
            logger.info(f"LLM流式调用 - 模型: {self._config.get('model_provider')}/{self._config.get('model')}")
            logger.info(f"LLM流式输入消息: {json.dumps(messages, ensure_ascii=False, indent=2)}")
            
            # 调用对应的流式LLM
            provider = self._config.get('model_provider')
            full_response = ""
            
            if provider == 'openai':
                async for chunk in self._call_openai_stream(messages, **kwargs):
                    full_response += chunk
                    yield chunk
            elif provider == 'anthropic':
                async for chunk in self._call_anthropic_stream(messages, **kwargs):
                    full_response += chunk
                    yield chunk
            elif provider == 'ollama':
                async for chunk in self._call_ollama_stream(messages, **kwargs):
                    full_response += chunk
                    yield chunk
            elif provider == 'deepseek':
                async for chunk in self._call_deepseek_stream(messages, **kwargs):
                    full_response += chunk
                    yield chunk
            else:
                raise Exception(f"不支持的模型提供商: {provider}")
            
            # 记录完整响应到日志
            logger.info(f"LLM流式响应完整内容: {full_response}")
                    
        except Exception as e:
            logger.error(f"LLM流式调用失败: {str(e)}")
            raise

    async def _call_openai_stream(self, messages: List[Dict], **kwargs) -> AsyncGenerator[str, None]:
        """流式调用OpenAI API"""
        try:
            if not self._openai_client:
                raise Exception("OpenAI客户端未初始化")
            
            # 优先从数据库配置获取token值，然后是kwargs参数，最后是默认值
            db_max_tokens = self._config.get('config', {}).get('max_tokens')
            max_tokens = kwargs.get('max_tokens') or db_max_tokens or 1000
            
            params = {
                "model": self._config.get('model', 'gpt-3.5-turbo'),
                "messages": messages,
                "temperature": self._config.get('temperature', 0.7),
                "max_tokens": max_tokens,
                "stream": True,
                **kwargs
            }
            
            stream = await self._openai_client.chat.completions.create(**params)
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"OpenAI流式调用失败: {str(e)}")
            raise

    async def _call_anthropic_stream(self, messages: List[Dict], **kwargs) -> AsyncGenerator[str, None]:
        """流式调用Anthropic API"""
        try:
            if not self._anthropic_client:
                raise Exception("Anthropic客户端未初始化")
            
            # 转换消息格式
            system_message = ""
            user_messages = []
            
            for msg in messages:
                if msg.get('role') == 'system':
                    system_message = msg.get('content', '')
                elif msg.get('role') == 'user':
                    user_messages.append(msg.get('content', ''))
                elif msg.get('role') == 'assistant':
                    continue
            
            user_content = "\n".join(user_messages)
            
            # 优先从数据库配置获取token值，然后是kwargs参数，最后是默认值
            db_max_tokens = self._config.get('config', {}).get('max_tokens')
            max_tokens = kwargs.get('max_tokens') or db_max_tokens or 1000
            
            params = {
                "model": self._config.get('model', 'claude-3-sonnet-20240229'),
                "max_tokens": max_tokens,
                "temperature": self._config.get('temperature', 0.7),
                **kwargs
            }
            
            if system_message:
                params["system"] = system_message
            
            stream = await self._anthropic_client.messages.create(
                messages=[{"role": "user", "content": user_content}],
                stream=True,
                **params
            )
            
            async for chunk in stream:
                if chunk.type == "content_block_delta":
                    yield chunk.delta.text
                    
        except Exception as e:
            logger.error(f"Anthropic流式调用失败: {str(e)}")
            raise

    async def _call_ollama_stream(self, messages: List[Dict], **kwargs) -> AsyncGenerator[str, None]:
        """流式调用Ollama API"""
        try:
            if not self._ollama_base_url:
                raise Exception("Ollama客户端未初始化")
            
            # 优先从数据库配置获取token值，然后是kwargs参数，最后是默认值
            db_max_tokens = self._config.get('config', {}).get('max_tokens')
            max_tokens = kwargs.get('max_tokens') or db_max_tokens or 512
            max_tokens = max(64, min(int(max_tokens), 512))
            data = {
                "model": self._config.get('model', 'qwen3:8b'),
                "messages": messages,
                "stream": True,
                "keep_alive": "5m",
                "options": {
                    "temperature": self._config.get('temperature', 0.7),
                    "num_predict": max_tokens,
                    **kwargs.get('options', {})
                }
            }
            
            logger.info(f"Ollama流式请求URL: {self._ollama_base_url}/api/chat")
            safe_preview = json.dumps({**data, 'messages': '[omitted for brevity]'}, ensure_ascii=False)
            logger.info(f"Ollama流式请求数据(简要): {safe_preview}")
            
            # 使用同步requests进行流式请求，避免异步问题
            import requests
            logger.info("使用同步requests发送Ollama流式请求...")
            
            try:
                response = requests.post(
                    f"{self._ollama_base_url}/api/chat",
                    json=data,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                    stream=True
                )
                
                logger.info(f"Ollama流式响应状态码: {response.status_code}")
                logger.info(f"Ollama流式响应头: {dict(response.headers)}")
                
                response.raise_for_status()
                
                # 处理流式响应
                for line in response.iter_lines():
                    if line:
                        try:
                            line_text = line.decode('utf-8').strip()
                            if line_text:
                                logger.debug(f"收到流式数据行: {line_text}")
                                chunk_data = json.loads(line_text)
                                if 'message' in chunk_data and 'content' in chunk_data['message']:
                                    content = chunk_data['message']['content']
                                    logger.debug(f"流式内容片段: {content}")
                                    yield content
                        except json.JSONDecodeError as e:
                            logger.warning(f"流式数据JSON解析失败: {str(e)}, 数据行: {line_text}")
                            continue
                        except Exception as e:
                            logger.warning(f"处理流式数据失败: {str(e)}")
                            continue
                            
            except requests.exceptions.Timeout:
                logger.error("同步流式请求超时")
                raise
            except requests.exceptions.RequestException as e:
                logger.error(f"同步流式请求失败: {str(e)}")
                raise
                                
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama流式HTTP错误: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Ollama流式请求错误: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Ollama流式调用失败: {str(e)}")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误详情: {str(e)}")
            raise

    async def _call_deepseek(self, messages: List[Dict], **kwargs) -> str:
        """调用DeepSeek API"""
        try:
            if not self._deepseek_base_url or not self._deepseek_api_key:
                raise Exception("DeepSeek客户端未初始化")
            
            # 构建请求数据
            data = {
                "model": self._config.get('model', 'deepseek-chat'),
                "messages": messages,
                "temperature": self._config.get('temperature', 0.7),
                "max_tokens": kwargs.get('max_tokens', 1000),
                **kwargs
            }
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._deepseek_base_url}/v1/chat/completions",
                    json=data,
                    headers={
                        "Authorization": f"Bearer {self._deepseek_api_key}",
                        "Content-Type": "application/json"
                    },
                    timeout=60
                )
                response.raise_for_status()
                
                result = response.json()
                return result.get('choices', [{}])[0].get('message', {}).get('content', '')
                
        except Exception as e:
            logger.error(f"DeepSeek调用失败: {str(e)}")
            raise

    async def _call_deepseek_stream(self, messages: List[Dict], **kwargs) -> AsyncGenerator[str, None]:
        """流式调用DeepSeek API"""
        try:
            if not self._deepseek_base_url or not self._deepseek_api_key:
                raise Exception("DeepSeek客户端未初始化")
            
            # 构建请求数据
            data = {
                "model": self._config.get('model', 'deepseek-chat'),
                "messages": messages,
                "temperature": self._config.get('temperature', 0.7),
                "max_tokens": kwargs.get('max_tokens', 1000),
                "stream": True,
                **kwargs
            }
            
            # 发送流式请求
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{self._deepseek_base_url}/v1/chat/completions",
                    json=data,
                    headers={
                        "Authorization": f"Bearer {self._deepseek_api_key}",
                        "Content-Type": "application/json"
                    },
                    timeout=60
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.strip() and line.startswith('data: '):
                            try:
                                chunk_data = json.loads(line[6:])  # 移除 'data: ' 前缀
                                if chunk_data.get('choices') and chunk_data['choices'][0].get('delta', {}).get('content'):
                                    yield chunk_data['choices'][0]['delta']['content']
                            except json.JSONDecodeError:
                                continue
                                
        except Exception as e:
            logger.error(f"DeepSeek流式调用失败: {str(e)}")
            raise

    def switch_model(self, model: str, **kwargs):
        """
        动态切换模型
        """
        cfg = self._config.copy()
        cfg.update(model=model)
        cfg.update(kwargs)
        self._config = cfg
        self._init_clients()
        return self
    
    def switch_config(self, config_name: str):
        """
        切换到指定的LLM配置
        """
        config = llm_config_manager.get_config(config_name)
        if config:
            self._config = {
                'model': config.model_name,
                'model_provider': config.provider,
                'temperature': config.config.get('temperature', 0.7) if config.config else 0.7,
                'base_url': config.api_base,
                'api_key': config.api_key
            }
            self._init_clients()
            logger.info(f"切换到LLM配置: {config.display_name}")
        else:
            logger.error(f"未找到LLM配置: {config_name}")
    
    def refresh_config(self):
        """
        刷新配置（从数据库重新加载）
        """
        llm_config_manager.refresh_config()
        self.setup()

    def get_config(self) -> dict:
        """获取当前模型配置"""
        return self._config.copy()

    def filter_think_content(self, text: str) -> str:
        """过滤掉<think>标签内的思考内容"""
        import re
        # 移除<think>...</think>标签及其内容
        filtered_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # 移除多余的空白字符
        filtered_text = re.sub(r'\s+', ' ', filtered_text).strip()
        return filtered_text

# 获取单例
def get_llm_helper(llm_config: Optional[Dict[str, Any]] = None):
    """获取LLM助手实例
    
    Args:
        llm_config: 可选的LLM配置字典
    """
    llm_helper = LLMHelper()
    llm_helper.setup(llm_config=llm_config)
    return llm_helper

def get_llm(model: str = None, **kwargs):
    """
    获取大模型实例的便捷函数
    :param model: 指定模型（可选）
    :param kwargs: 其他参数
    :return: 大模型实例
    """
    helper = get_llm_helper()
    if model:
        return helper.switch_model(model, **kwargs)
    return helper

def setup_llm(**kwargs) -> LLMHelper:
    """
    配置并初始化大模型的便捷函数
    :param kwargs: 配置参数
    :return: LLMHelper实例
    """
    #尝试从环境变量获取参数
    if "MODEL_PROVIDER" in os.environ:
        kwargs["model_provider"] = os.environ["MODEL_PROVIDER"]
    if "MODEL" in os.environ:
        kwargs["model"] = os.environ["MODEL"]
    if "TEMPERATURE" in os.environ:
        kwargs["temperature"] = float(os.environ["TEMPERATURE"])
    
    llm_helper = LLMHelper()
    return llm_helper.setup(**kwargs)

if __name__ == "__main__":
    async def test_llm_helper():
        """测试LLM助手"""
        print("🧪 测试LLM助手...")
        
        # 创建LLM助手
        llm_helper = get_llm_helper()
        
        # 测试调用
        test_prompts = [
            "你好",
            "请介绍一下你自己",
            "现在几点了？",
            "搜索人工智能信息"
        ]
        
        for prompt in test_prompts:
            print(f"\n📝 输入: {prompt}")
            try:
                response = await llm_helper.call(prompt)
                print(f"🤖 输出: {response}")
            except Exception as e:
                print(f"❌ 错误: {str(e)}")
        
        print("\n✅ LLM助手测试完成")

    asyncio.run(test_llm_helper())