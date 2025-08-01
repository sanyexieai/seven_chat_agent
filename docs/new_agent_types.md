# 新智能体类型说明

本文档介绍了系统中新增的三种智能体类型，它们通过不同的方式来实现AI功能。

## 智能体类型概览

### 1. 纯提示词驱动 (Prompt-Driven)

**特点：**
- 完全依赖系统提示词定义行为
- 不需要特定的工具支持
- 可以通过修改提示词快速调整功能
- 适合对话、问答等场景

**使用场景：**
- 翻译助手
- 代码助手
- 写作助手
- 客服机器人
- 知识问答

**配置示例：**
```json
{
  "name": "translator",
  "display_name": "翻译助手",
  "agent_type": "prompt_driven",
  "system_prompt": "你是一个专业的翻译助手。请将用户输入的内容翻译成中文，保持原文的意思和风格。"
}
```

### 2. 纯工具驱动 (Tool-Driven)

**特点：**
- 根据绑定的工具自动生成系统提示词
- 专注于工具的使用和调用
- 支持多种MCP工具集成
- 适合搜索、数据处理等场景

**使用场景：**
- 搜索助手
- 数据分析助手
- 文件处理助手
- 网络爬虫助手

**配置示例：**
```json
{
  "name": "search_assistant",
  "display_name": "搜索助手",
  "agent_type": "tool_driven",
  "bound_tools": ["search", "news_search", "web_search"]
}
```

### 3. 流程图驱动 (Flow-Driven)

**特点：**
- 支持复杂的业务流程定义
- 每个节点可以绑定不同的提示词和工具
- 支持条件分支和循环
- 适合复杂的业务场景

**使用场景：**
- 客户服务流程
- 数据处理流程
- 报告生成流程
- 自动化工作流

**配置示例：**
```json
{
  "name": "customer_service",
  "display_name": "客服助手",
  "agent_type": "flow_driven",
  "flow_config": {
    "nodes": [
      {
        "id": "greeting",
        "type": "prompt",
        "content": "欢迎用户，询问需求"
      },
      {
        "id": "classify",
        "type": "condition",
        "condition": "用户需求类型"
      },
      {
        "id": "search",
        "type": "tool",
        "tool": "search",
        "condition": "需要搜索信息"
      }
    ]
  }
}
```

## 数据库结构

新的智能体类型需要在数据库中添加以下字段：

```sql
ALTER TABLE agents ADD COLUMN system_prompt TEXT;
ALTER TABLE agents ADD COLUMN bound_tools JSON;
ALTER TABLE agents ADD COLUMN flow_config JSON;
```

## API接口

### 创建智能体
```http
POST /api/agents
Content-Type: application/json

{
  "name": "my_agent",
  "display_name": "我的智能体",
  "description": "智能体描述",
  "agent_type": "prompt_driven",
  "system_prompt": "系统提示词",
  "bound_tools": ["tool1", "tool2"],
  "flow_config": {...}
}
```

### 更新智能体
```http
PUT /api/agents/{agent_id}
Content-Type: application/json

{
  "display_name": "新的显示名称",
  "system_prompt": "新的系统提示词",
  "bound_tools": ["new_tool1", "new_tool2"]
}
```

### 获取智能体列表
```http
GET /api/agents
```

## 前端界面

### 智能体管理页面
- 位置：`/agents`
- 功能：创建、编辑、删除智能体
- 支持所有智能体类型的配置

### 智能体测试页面
- 位置：`/agent-test`
- 功能：测试不同智能体的功能
- 支持实时聊天和流式响应

## 使用示例

### 创建翻译助手
1. 访问智能体管理页面
2. 点击"创建智能体"
3. 选择"提示词驱动"类型
4. 输入系统提示词："你是一个专业的翻译助手..."
5. 保存并测试

### 创建搜索助手
1. 访问智能体管理页面
2. 点击"创建智能体"
3. 选择"工具驱动"类型
4. 绑定搜索相关工具
5. 保存并测试

## 开发指南

### 添加新的智能体类型

1. 在 `models/chat_models.py` 中添加新的类型枚举
2. 在 `agents/` 目录下创建新的智能体类
3. 在 `agents/agent_manager.py` 中添加类型处理逻辑
4. 更新前端界面支持新类型

### 自定义工具集成

1. 实现MCP工具
2. 在数据库中注册工具
3. 在工具驱动智能体中绑定工具
4. 测试工具功能

## 注意事项

1. **数据库迁移**：首次使用需要运行数据库迁移脚本
2. **MCP配置**：工具驱动智能体需要正确的MCP配置
3. **提示词优化**：提示词驱动智能体的效果很大程度上取决于提示词质量
4. **工具权限**：确保工具驱动智能体有权限访问绑定的工具

## 故障排除

### 常见问题

1. **智能体无法加载**
   - 检查数据库连接
   - 验证智能体配置是否正确

2. **工具无法使用**
   - 检查MCP服务器状态
   - 验证工具权限配置

3. **提示词效果不佳**
   - 优化系统提示词
   - 添加更多上下文信息

### 日志查看

```bash
# 查看智能体管理器日志
tail -f logs/agent_manager.log

# 查看特定智能体日志
tail -f logs/prompt_driven_agent.log
tail -f logs/tool_driven_agent.log
```

## 未来计划

1. **流程图编辑器**：可视化流程图配置界面
2. **智能体模板**：预定义的智能体模板
3. **性能优化**：智能体响应速度优化
4. **更多工具集成**：支持更多MCP工具
5. **智能体训练**：基于用户反馈的智能体优化 