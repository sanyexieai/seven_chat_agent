#!/usr/bin/env python3
"""
知识库功能测试脚本
"""

import asyncio
import json
import requests
from typing import Dict, Any

# 测试配置
BASE_URL = "http://localhost:8000"
TEST_USER_ID = "test_user_001"

def test_create_knowledge_base():
    """测试创建知识库"""
    print("=== 测试创建知识库 ===")
    
    kb_data = {
        "name": "test_kb_001",
        "display_name": "测试知识库",
        "description": "这是一个测试知识库",
        "owner_id": TEST_USER_ID,
        "is_public": True,
        "config": {
            "chunk_size": 1000,
            "overlap": 200
        }
    }
    
    response = requests.post(f"{BASE_URL}/api/knowledge-base/", json=kb_data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    
    if response.status_code == 200:
        return response.json()["id"]
    return None

def test_create_document(kb_id: int):
    """测试创建文档"""
    print(f"\n=== 测试创建文档 (知识库ID: {kb_id}) ===")
    
    # 测试文档内容
    test_content = """
人工智能（Artificial Intelligence，AI）是计算机科学的一个分支，它企图了解智能的实质，
并生产出一种新的能以人类智能相似的方式做出反应的智能机器。该领域的研究包括机器人、
语言识别、图像识别、自然语言处理和专家系统等。

人工智能从诞生以来，理论和技术日益成熟，应用领域也不断扩大，可以设想，
未来人工智能带来的科技产品，将会是人类智慧的"容器"。人工智能可以对人的意识、
思维的信息过程的模拟。人工智能不是人的智能，但能像人那样思考、也可能超过人的智能。

人工智能是一门极富挑战性的科学，从事人工智能工作的人必须懂得计算机知识，
心理学和哲学。人工智能是包括十分广泛的科学，它由不同的领域组成，如机器学习，
计算机视觉等等，总的说来，人工智能研究的一个主要目标是使机器能够胜任一些通常需要人类智能才能完成的复杂工作。
    """
    
    doc_data = {
        "knowledge_base_id": kb_id,
        "name": "AI介绍文档",
        "file_type": "txt",
        "content": test_content,
        "metadata": {
            "author": "测试用户",
            "category": "技术文档"
        }
    }
    
    response = requests.post(
        f"{BASE_URL}/api/knowledge-base/{kb_id}/documents",
        data={
            "name": doc_data["name"],
            "file_type": doc_data["file_type"],
            "content": doc_data["content"],
            "metadata": json.dumps(doc_data["metadata"])
        }
    )
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    
    if response.status_code == 200:
        return response.json()["id"]
    return None

def test_query_knowledge_base(kb_id: int):
    """测试查询知识库"""
    print(f"\n=== 测试查询知识库 (知识库ID: {kb_id}) ===")
    
    query_data = {
        "knowledge_base_id": kb_id,
        "query": "什么是人工智能？",
        "user_id": TEST_USER_ID,
        "max_results": 3
    }
    
    response = requests.post(f"{BASE_URL}/api/knowledge-base/{kb_id}/query", json=query_data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

def test_get_knowledge_bases():
    """测试获取知识库列表"""
    print("\n=== 测试获取知识库列表 ===")
    
    response = requests.get(f"{BASE_URL}/api/knowledge-base/?owner_id={TEST_USER_ID}")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

def test_get_documents(kb_id: int):
    """测试获取文档列表"""
    print(f"\n=== 测试获取文档列表 (知识库ID: {kb_id}) ===")
    
    response = requests.get(f"{BASE_URL}/api/knowledge-base/{kb_id}/documents")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

def test_chat_with_knowledge_base(kb_id: int):
    """测试通过聊天接口查询知识库"""
    print(f"\n=== 测试聊天接口查询知识库 (知识库ID: {kb_id}) ===")
    
    chat_data = {
        "user_id": TEST_USER_ID,
        "message": "请告诉我人工智能的定义和应用领域",
        "agent_name": "knowledge_base_agent",
        "context": {
            "knowledge_base_id": kb_id
        }
    }
    
    response = requests.post(f"{BASE_URL}/api/chat", json=chat_data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

def main():
    """主测试函数"""
    print("开始知识库功能测试...")
    
    try:
        # 1. 创建知识库
        kb_id = test_create_knowledge_base()
        if not kb_id:
            print("创建知识库失败，退出测试")
            return
        
        # 2. 创建文档
        doc_id = test_create_document(kb_id)
        if not doc_id:
            print("创建文档失败，退出测试")
            return
        
        # 等待文档处理完成
        print("等待文档处理完成...")
        import time
        time.sleep(3)
        
        # 3. 查询知识库
        test_query_knowledge_base(kb_id)
        
        # 4. 获取知识库列表
        test_get_knowledge_bases()
        
        # 5. 获取文档列表
        test_get_documents(kb_id)
        
        # 6. 测试聊天接口
        test_chat_with_knowledge_base(kb_id)
        
        print("\n=== 知识库功能测试完成 ===")
        
    except Exception as e:
        print(f"测试过程中出现错误: {str(e)}")

if __name__ == "__main__":
    main() 