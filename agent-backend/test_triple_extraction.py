#!/usr/bin/env python3
"""
测试实体和关系提取功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.knowledge_base_service import KnowledgeBaseService

def test_triple_extraction():
    """测试三元组提取功能"""
    
    print("=== 测试实体和关系提取功能 ===\n")
    
    # 创建知识库服务实例
    kb_service = KnowledgeBaseService()
    
    # 测试文本1：包含多个实体和关系
    test_text_1 = """
    人工智能（AI）是计算机科学的一个分支，它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。
    该领域的研究包括机器人、语言识别、图像识别、自然语言处理和专家系统等。
    人工智能从诞生以来，理论和技术日益成熟，应用领域也不断扩大。
    深度学习是机器学习的一个重要分支，它使用多层神经网络来模拟人脑的工作方式。
    卷积神经网络（CNN）和循环神经网络（RNN）是深度学习的两个重要架构。
    """
    
    # 测试文本2：包含人物关系
    test_text_2 = """
    张三是一名软件工程师，在北京工作。他在阿里巴巴公司担任高级开发工程师。
    李四是张三的同事，负责机器学习项目。他们经常一起讨论技术问题。
    王五是项目经理，管理着整个技术团队。张三向王五汇报工作。
    """
    
    # 测试文本3：包含时间关系
    test_text_3 = """
    2020年，新冠疫情爆发，全球进入紧急状态。
    各国政府采取了封锁措施，限制人员流动。
    远程办公成为主流工作方式，视频会议软件需求激增。
    在线教育平台快速发展，学生在家学习。
    """
    
    test_cases = [
        ("AI技术文本", test_text_1),
        ("人物关系文本", test_text_2),
        ("时间关系文本", test_text_3)
    ]
    
    for i, (name, text) in enumerate(test_cases, 1):
        print(f"{i}. 测试 {name}:")
        print("-" * 50)
        print(f"原文: {text[:100]}...")
        print()
        
        try:
            # 提取三元组
            triples = kb_service._extract_triples_sync(text)
            
            print(f"提取到 {len(triples)} 个三元组:")
            for j, triple in enumerate(triples, 1):
                if len(triple) >= 3:
                    print(f"  {j}. {triple[0]} | {triple[1]} | {triple[2]}")
                else:
                    print(f"  {j}. 格式错误: {triple}")
            print()
            
        except Exception as e:
            print(f"提取失败: {str(e)}")
            print()
    
    print("=== 测试完成 ===")

if __name__ == "__main__":
    test_triple_extraction()
