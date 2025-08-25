# 路由节点架构设计

## 🎯 **设计理念**

**核心思想**：将判断逻辑和路由逻辑分离，实现更通用、更灵活的流程控制。

### 🔍 **传统架构的问题**

1. **硬编码判断逻辑**：条件节点和判断节点都在代码中硬编码了判断逻辑
2. **职责混乱**：节点既要生成结果，又要决定路由
3. **扩展性差**：新增判断类型需要修改代码
4. **维护困难**：判断逻辑分散在多个地方

### 💡 **新架构的优势**

1. **职责分离**：
   - LLM节点：负责生成判断结果（JSON）
   - 路由节点：负责根据结果进行分支选择
   
2. **更通用**：
   - 路由节点不关心结果是如何生成的
   - 前一个节点可以是LLM、工具、智能体等任何节点
   
3. **更灵活**：
   - 支持多种数据类型（布尔、数值、字符串）
   - 支持多种比较操作符
   - 完全可配置，无需修改代码

4. **更易维护**：
   - 减少硬编码
   - 判断逻辑集中在前置节点
   - 路由逻辑统一管理

## 🏗️ **架构组成**

### 1. **前置节点（生成结果）**

可以是任何类型的节点，负责生成路由决策所需的数据：

```json
{
  "type": "llm",
  "config": {
    "system_prompt": "你是一个智能判断器",
    "user_prompt": "请输出：{\"can_direct_answer\": true|false, \"domain\": \"技术|生活|工作\"}",
    "save_as": "judge_result"
  }
}
```

### 2. **路由节点（分支选择）**

根据前置节点的结果进行分支选择：

```json
{
  "type": "router",
  "config": {
    "routing_logic": {
      "field": "can_direct_answer",
      "true_branch": "direct_answer",
      "false_branch": "tool_required"
    }
  }
}
```

## 🔧 **路由节点配置**

### 基本配置

```json
{
  "routing_logic": {
    "field": "字段名",
    "true_branch": "真值分支",
    "false_branch": "假值分支"
  }
}
```

### 高级配置

#### 1. **精确值匹配**

```json
{
  "routing_logic": {
    "field": "status",
    "value": "success",
    "true_branch": "success_handler",
    "false_branch": "error_handler"
  }
}
```

#### 2. **数值比较**

```json
{
  "routing_logic": {
    "field": "retry_count",
    "operator": "<",
    "threshold": 3,
    "true_branch": "retry",
    "false_branch": "give_up"
  }
}
```

#### 3. **字符串模式匹配**

```json
{
  "routing_logic": {
    "field": "user_type",
    "pattern": "admin|moderator",
    "true_branch": "admin_panel",
    "false_branch": "user_panel"
  }
}
```

## 📋 **支持的数据类型**

### 1. **布尔值**

```json
{
  "field": "is_authenticated",
  "true_branch": "authenticated_flow",
  "false_branch": "login_flow"
}
```

### 2. **数值**

```json
{
  "field": "confidence",
  "operator": ">",
  "threshold": 0.8,
  "true_branch": "high_confidence",
  "false_branch": "low_confidence"
}
```

### 3. **字符串**

```json
{
  "field": "domain",
  "value": "技术",
  "true_branch": "tech_support",
  "false_branch": "general_support"
}
```

### 4. **数组/对象**

```json
{
  "field": "tools_available",
  "pattern": "search",
  "true_branch": "use_search",
  "false_branch": "manual_process"
}
```

## 🚀 **使用示例**

### 示例1：简单分支

```
[LLM判断] → [路由节点] → [分支A]
           ↓
           → [分支B]
```

**LLM节点配置：**
```json
{
  "system_prompt": "判断用户问题类型",
  "user_prompt": "输出：{\"is_technical\": true|false}",
  "save_as": "question_type"
}
```

**路由节点配置：**
```json
{
  "routing_logic": {
    "field": "is_technical",
    "true_branch": "tech_support",
    "false_branch": "general_support"
  }
}
```

### 示例2：多级路由

```
[LLM分析] → [路由1] → [技术处理] → [路由2] → [工具调用]
           ↓                    ↓
           → [通用处理] → [路由3] → [直接回答]
```

**路由1：问题类型判断**
```json
{
  "field": "is_technical",
  "true_branch": "tech_handler",
  "false_branch": "general_handler"
}
```

**路由2：是否需要工具**
```json
{
  "field": "requires_tool",
  "true_branch": "call_tool",
  "false_branch": "direct_answer"
}
```

## 🔄 **与传统节点的对比**

| 方面 | 传统架构 | 新架构 |
|------|----------|--------|
| **判断逻辑** | 硬编码在节点中 | 在前置节点中配置 |
| **路由逻辑** | 与判断逻辑混合 | 独立的路由节点 |
| **扩展性** | 需要修改代码 | 完全可配置 |
| **维护性** | 逻辑分散 | 逻辑集中 |
| **复用性** | 低 | 高 |
| **调试性** | 困难 | 容易 |

## 💭 **最佳实践**

1. **使用LLM节点生成判断结果**：
   - 复杂的语义判断
   - 需要理解自然语言的情况
   - 模糊的逻辑判断

2. **使用路由节点进行分支选择**：
   - 基于明确字段值的分支
   - 数值比较和范围判断
   - 字符串匹配和模式识别

3. **组合使用**：
   - LLM节点 + 路由节点
   - 工具节点 + 路由节点
   - 智能体节点 + 路由节点

4. **配置管理**：
   - 将路由逻辑配置化
   - 支持动态配置
   - 提供配置验证

## 🎉 **总结**

新的路由节点架构实现了：

- **职责分离**：判断逻辑和路由逻辑各司其职
- **高度通用**：支持各种类型的前置节点
- **完全可配置**：无需修改代码即可实现复杂的路由逻辑
- **易于维护**：逻辑集中，结构清晰
- **高度扩展**：支持各种数据类型和比较操作

这种架构让流程图更加灵活和强大，同时保持了代码的简洁性和可维护性。 