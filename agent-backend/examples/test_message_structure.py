"""
测试脚本：演示新的消息数据结构
"""

import json
from datetime import datetime

def create_test_message_data():
    """创建测试消息数据"""
    
    # 示例1：用户消息（只有content，没有nodes）
    user_message = {
        "id": 1,
        "message_id": "user_1756178459453_abc123",
        "session_id": "session_uuid_123",
        "user_id": "user_123",
        "message_type": "user",
        "content": "你好，请帮我分析一下这个数据",
        "agent_name": None,
        "metadata": {},
        "created_at": "2025-01-26T10:30:00"
    }
    
    # 示例2：智能体消息（有content，没有nodes）
    agent_message_simple = {
        "id": 2,
        "message_id": "agent_1756178459453_def456",
        "session_id": "session_uuid_123",
        "user_id": "user_123",
        "message_type": "agent",
        "content": "您好！我很乐意帮您分析数据。请告诉我您需要分析什么样的数据？",
        "agent_name": "data_analysis_agent",
        "metadata": {},
        "created_at": "2025-01-26T10:31:00"
    }
    
    # 示例3：智能体消息（没有content，有nodes）
    agent_message_with_nodes = {
        "id": 3,
        "message_id": "agent_1756178459453_ghi789",
        "session_id": "session_uuid_123",
        "user_id": "user_123",
        "message_type": "agent",
        "content": None,
        "agent_name": "data_analysis_agent",
        "metadata": {},
        "created_at": "2025-01-26T10:32:00",
        "nodes": [
            {
                "id": 1,
                "node_id": "start_llm",
                "node_type": "llm",
                "node_name": "开始分析",
                "node_label": "开始分析",
                "content": "正在分析您提供的数据...",
                "node_metadata": {},
                "created_at": "2025-01-26T10:32:00"
            },
            {
                "id": 2,
                "node_id": "data_processing",
                "node_type": "tool",
                "node_name": "数据处理",
                "node_label": "数据处理",
                "content": "数据预处理完成，发现3个异常值",
                "node_metadata": {"tool_name": "data_cleaner"},
                "created_at": "2025-01-26T10:32:30"
            },
            {
                "id": 3,
                "node_id": "result_summary",
                "node_type": "llm",
                "node_name": "结果总结",
                "node_label": "结果总结",
                "content": "分析完成！您的数据总体质量良好，有3个异常值需要关注。",
                "node_metadata": {},
                "created_at": "2025-01-26T10:33:00"
            }
        ]
    }
    
    # 示例4：智能体消息（既有content，又有nodes）
    agent_message_mixed = {
        "id": 4,
        "message_id": "agent_1756178459453_jkl012",
        "session_id": "session_uuid_123",
        "user_id": "user_123",
        "message_type": "agent",
        "content": "我已经完成了数据分析，以下是详细结果：",
        "agent_name": "data_analysis_agent",
        "metadata": {},
        "created_at": "2025-01-26T10:34:00",
        "nodes": [
            {
                "id": 4,
                "node_id": "detailed_analysis",
                "node_type": "llm",
                "node_name": "详细分析",
                "node_label": "详细分析",
                "content": "数据分布：正态分布，均值=100，标准差=15",
                "node_metadata": {},
                "created_at": "2025-01-26T10:34:00"
            }
        ]
    }
    
    test_data = [
        user_message,
        agent_message_simple,
        agent_message_with_nodes,
        agent_message_mixed
    ]
    
    return test_data

def print_message_structure(messages):
    """打印消息结构分析"""
    print("=== 消息数据结构分析 ===\n")
    
    for i, msg in enumerate(messages, 1):
        print(f"消息 {i}: {msg['message_type'].upper()} 类型")
        print(f"  ID: {msg['id']}")
        print(f"  消息ID: {msg['message_id']}")
        print(f"  类型: {msg['message_type']}")
        print(f"  智能体: {msg['agent_name'] or 'N/A'}")
        
        # 检查消息级别内容
        if msg['content']:
            print(f"  ✅ 消息级别有内容: {msg['content'][:50]}{'...' if len(msg['content']) > 50 else ''}")
        else:
            print(f"  ❌ 消息级别无内容")
        
        # 检查节点信息
        if 'nodes' in msg and msg['nodes']:
            print(f"  ✅ 有节点信息，共 {len(msg['nodes'])} 个节点")
            for j, node in enumerate(msg['nodes'], 1):
                node_content = node.get('content', '无内容')
                print(f"    节点 {j}: {node['node_name']} ({node['node_type']})")
                print(f"      内容: {node_content[:30]}{'...' if len(str(node_content)) > 30 else ''}")
        else:
            print(f"  ❌ 无节点信息")
        
        print()

def main():
    """主函数"""
    print("🚀 测试新的消息数据结构")
    print("=" * 50)
    
    # 创建测试数据
    test_messages = create_test_message_data()
    
    # 分析消息结构
    print_message_structure(test_messages)
    
    # 保存到JSON文件
    with open('test_message_structure.json', 'w', encoding='utf-8') as f:
        json.dump(test_messages, f, ensure_ascii=False, indent=2)
    
    print("✅ 测试数据已保存到 test_message_structure.json")
    print("\n📋 数据结构说明:")
    print("1. 用户消息：只有 content，没有 nodes")
    print("2. 简单智能体消息：有 content，没有 nodes")
    print("3. 复杂智能体消息：没有 content，有 nodes")
    print("4. 混合智能体消息：既有 content，又有 nodes")

if __name__ == "__main__":
    main() 