#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM配置测试脚本
用于验证不同LLM提供商的配置是否正确
"""

import asyncio
import os
import sys
from typing import Dict, Any

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.llm_helper import get_llm_helper
from utils.log_helper import get_logger

# 获取logger实例
logger = get_logger("test_llm_config")

async def test_llm_config():
    """测试LLM配置"""
    print("🧪 LLM配置测试")
    print("=" * 50)
    
    # 获取配置信息
    provider = os.getenv("MODEL_PROVIDER", "openai")
    model = os.getenv("MODEL", "gpt-3.5-turbo")
    api_key = os.getenv("API_KEY", "")
    base_url = os.getenv("BASE_URL", "https://api.openai.com/v1")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    print(f"📋 当前配置:")
    print(f"   提供商: {provider}")
    print(f"   模型: {model}")
    print(f"   API密钥: {'已设置' if api_key else '未设置'}")
    print(f"   基础URL: {base_url}")
    if provider == "ollama":
        print(f"   Ollama URL: {ollama_url}")
    print()
    
    # 测试LLM初始化
    try:
        print("🔧 初始化LLM客户端...")
        llm_helper = get_llm_helper()
        print("✅ LLM客户端初始化成功")
        
        # 测试简单调用
        print("\n📝 测试简单调用...")
        test_message = "你好，请简单介绍一下你自己"
        response = await llm_helper.call(test_message)
        print(f"✅ 调用成功")
        print(f"📤 输入: {test_message}")
        print(f"📥 输出: {response[:200]}...")
        
        # 测试流式调用
        print("\n🌊 测试流式调用...")
        print("📤 输入: 请用一句话总结人工智能")
        print("📥 输出: ", end="", flush=True)
        
        async for chunk in llm_helper.call_stream("请用一句话总结人工智能"):
            print(chunk, end="", flush=True)
        print("\n✅ 流式调用成功")
        
        print("\n🎉 所有测试通过！LLM配置正确。")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        print("\n🔧 故障排除建议:")
        
        if provider == "openai":
            print("1. 检查API密钥是否正确设置")
            print("2. 确认API密钥有足够的配额")
            print("3. 检查网络连接是否正常")
            print("4. 验证模型名称是否正确")
            
        elif provider == "anthropic":
            print("1. 检查API密钥是否正确设置")
            print("2. 确认API密钥有足够的配额")
            print("3. 检查网络连接是否正常")
            print("4. 验证模型名称是否正确")
            
        elif provider == "ollama":
            print("1. 确保Ollama服务正在运行: ollama serve")
            print("2. 检查端口11434是否可访问")
            print("3. 验证模型是否已下载: ollama list")
            print("4. 测试模型: ollama run llama2 'Hello'")
            
        else:
            print("1. 检查MODEL_PROVIDER环境变量")
            print("2. 确保支持该提供商")
            
        return False
    
    return True

async def test_specific_provider(provider: str):
    """测试特定提供商"""
    print(f"\n🧪 测试 {provider} 配置")
    print("-" * 30)
    
    # 设置环境变量
    os.environ["MODEL_PROVIDER"] = provider
    
    if provider == "ollama":
        os.environ["MODEL"] = "llama2"
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
    elif provider == "openai":
        os.environ["MODEL"] = "gpt-3.5-turbo"
        os.environ["BASE_URL"] = "https://api.openai.com/v1"
    elif provider == "anthropic":
        os.environ["MODEL"] = "claude-3-sonnet-20240229"
    
    try:
        llm_helper = get_llm_helper()
        response = await llm_helper.call("你好")
        print(f"✅ {provider} 配置正确")
        print(f"   响应: {response[:100]}...")
        return True
    except Exception as e:
        print(f"❌ {provider} 配置错误: {str(e)}")
        return False

async def main():
    """主函数"""
    print("🚀 LLM配置测试工具")
    print("=" * 50)
    
    # 检查命令行参数
    if len(sys.argv) > 1:
        provider = sys.argv[1]
        if provider in ["openai", "anthropic", "ollama"]:
            await test_specific_provider(provider)
        else:
            print(f"❌ 不支持的提供商: {provider}")
            print("支持的提供商: openai, anthropic, ollama")
    else:
        # 测试当前配置
        success = await test_llm_config()
        
        if not success:
            print("\n💡 提示:")
            print("1. 检查 .env 文件配置")
            print("2. 确保环境变量正确设置")
            print("3. 参考 LLM_SETUP.md 文档")
            print("4. 运行 python test_llm_config.py <provider> 测试特定提供商")

if __name__ == "__main__":
    asyncio.run(main()) 