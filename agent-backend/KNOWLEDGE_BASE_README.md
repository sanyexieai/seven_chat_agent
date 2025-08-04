# 知识库功能说明

## 概述

知识库功能是AI Agent系统的重要组成部分，允许用户创建、管理和查询知识库，实现基于文档的智能问答。

## 功能特性

### 1. 知识库管理
- **创建知识库**: 用户可以创建个人或公开的知识库
- **知识库列表**: 查看所有可访问的知识库
- **知识库详情**: 获取知识库的详细信息
- **更新知识库**: 修改知识库的名称、描述等属性
- **删除知识库**: 软删除知识库（保留数据）

### 2. 文档管理
- **上传文档**: 支持文本文件上传
- **创建文档**: 通过API创建文档
- **文档列表**: 查看知识库中的所有文档
- **文档详情**: 获取文档的详细信息
- **更新文档**: 修改文档内容或元数据
- **删除文档**: 删除文档及其分块

### 3. 智能查询
- **语义搜索**: 基于向量相似度的文档检索
- **分块处理**: 自动将文档分割成小块进行索引
- **相似度排序**: 按相关性排序返回结果
- **来源追踪**: 显示查询结果的来源文档

### 4. 智能体集成
- **知识库智能体**: 专门用于查询知识库的智能体
- **聊天集成**: 通过聊天接口查询知识库
- **上下文理解**: 智能体能够理解查询意图

## 数据库设计

### 核心表结构

#### 1. knowledge_bases (知识库表)
```sql
- id: 主键
- name: 知识库名称（唯一）
- display_name: 显示名称
- description: 描述
- owner_id: 所有者ID
- is_public: 是否公开
- is_active: 是否激活
- config: 配置信息（JSON）
- created_at: 创建时间
- updated_at: 更新时间
```

#### 2. documents (文档表)
```sql
- id: 主键
- knowledge_base_id: 知识库ID（外键）
- name: 文档名称
- file_path: 文件路径
- file_type: 文件类型
- file_size: 文件大小
- content: 文档内容
- metadata: 元数据（JSON）
- status: 处理状态（pending/processing/completed/failed）
- is_active: 是否激活
- created_at: 创建时间
- updated_at: 更新时间
```

#### 3. document_chunks (文档分块表)
```sql
- id: 主键
- knowledge_base_id: 知识库ID（外键）
- document_id: 文档ID（外键）
- chunk_index: 分块索引
- content: 分块内容
- embedding: 向量嵌入（JSON）
- metadata: 分块元数据（JSON）
- created_at: 创建时间
```

#### 4. knowledge_base_queries (查询记录表)
```sql
- id: 主键
- knowledge_base_id: 知识库ID（外键）
- user_id: 用户ID
- query: 查询内容
- response: 响应内容
- sources: 来源文档（JSON）
- metadata: 查询元数据（JSON）
- created_at: 创建时间
```

## API接口

### 知识库管理接口

#### 1. 创建知识库
```http
POST /api/knowledge-base/
Content-Type: application/json

{
  "name": "my_kb",
  "display_name": "我的知识库",
  "description": "个人知识库",
  "owner_id": "user123",
  "is_public": false,
  "config": {
    "chunk_size": 1000,
    "overlap": 200
  }
}
```

#### 2. 获取知识库列表
```http
GET /api/knowledge-base/?owner_id=user123&include_public=true
```

#### 3. 获取知识库详情
```http
GET /api/knowledge-base/{kb_id}
```

#### 4. 更新知识库
```http
PUT /api/knowledge-base/{kb_id}
Content-Type: application/json

{
  "display_name": "更新后的名称",
  "description": "更新后的描述"
}
```

#### 5. 删除知识库
```http
DELETE /api/knowledge-base/{kb_id}
```

### 文档管理接口

#### 1. 创建文档
```http
POST /api/knowledge-base/{kb_id}/documents
Content-Type: multipart/form-data

name: 文档名称
file_type: txt
content: 文档内容
metadata: {"author": "张三", "category": "技术"}
```

#### 2. 上传文档文件
```http
POST /api/knowledge-base/{kb_id}/documents/upload
Content-Type: multipart/form-data

file: 文件
metadata: {"author": "张三"}
```

#### 3. 获取文档列表
```http
GET /api/knowledge-base/{kb_id}/documents
```

#### 4. 获取文档详情
```http
GET /api/knowledge-base/documents/{doc_id}
```

#### 5. 更新文档
```http
PUT /api/knowledge-base/documents/{doc_id}
Content-Type: application/json

{
  "name": "更新后的名称",
  "content": "更新后的内容"
}
```

#### 6. 删除文档
```http
DELETE /api/knowledge-base/documents/{doc_id}
```

### 查询接口

#### 1. 查询知识库
```http
POST /api/knowledge-base/{kb_id}/query
Content-Type: application/json

{
  "knowledge_base_id": 1,
  "query": "什么是人工智能？",
  "user_id": "user123",
  "max_results": 5
}
```

#### 2. 获取文档分块
```http
GET /api/knowledge-base/{kb_id}/chunks?document_id=1
```

## 智能体集成

### 知识库智能体

知识库智能体专门用于查询知识库，可以通过聊天接口调用：

```http
POST /api/chat
Content-Type: application/json

{
  "user_id": "user123",
  "message": "请告诉我人工智能的定义",
  "agent_name": "knowledge_base_agent",
  "context": {
    "knowledge_base_id": 1
  }
}
```

### 智能体特性

1. **上下文理解**: 能够理解用户的查询意图
2. **知识库查询**: 自动查询指定的知识库
3. **结果格式化**: 将查询结果格式化为易读的回答
4. **来源追踪**: 显示回答的来源文档
5. **流式响应**: 支持流式返回查询结果

## 技术实现

### 1. 文本处理
- **文本清理**: 移除特殊字符，标准化格式
- **分块策略**: 基于句子的智能分块
- **重叠处理**: 保持分块间的上下文连贯性

### 2. 向量嵌入
- **嵌入生成**: 为每个文本块生成向量表示
- **相似度计算**: 使用余弦相似度计算文本相似性
- **检索优化**: 支持批量处理和缓存

### 3. 查询处理
- **查询解析**: 理解用户查询意图
- **向量检索**: 基于相似度的文档检索
- **结果排序**: 按相关性排序返回结果
- **响应生成**: 基于检索结果生成回答

## 使用示例

### 1. 创建知识库并上传文档

```python
import requests

# 创建知识库
kb_data = {
    "name": "ai_knowledge",
    "display_name": "AI知识库",
    "description": "人工智能相关知识",
    "owner_id": "user123",
    "is_public": True
}

response = requests.post("http://localhost:8000/api/knowledge-base/", json=kb_data)
kb_id = response.json()["id"]

# 上传文档
with open("ai_document.txt", "rb") as f:
    files = {"file": f}
    data = {"metadata": '{"category": "AI"}'}
    response = requests.post(
        f"http://localhost:8000/api/knowledge-base/{kb_id}/documents/upload",
        files=files,
        data=data
    )
```

### 2. 查询知识库

```python
# 直接查询
query_data = {
    "knowledge_base_id": kb_id,
    "query": "什么是机器学习？",
    "user_id": "user123"
}

response = requests.post(
    f"http://localhost:8000/api/knowledge-base/{kb_id}/query",
    json=query_data
)

# 通过智能体查询
chat_data = {
    "user_id": "user123",
    "message": "请解释深度学习的概念",
    "agent_name": "knowledge_base_agent",
    "context": {"knowledge_base_id": kb_id}
}

response = requests.post("http://localhost:8000/api/chat", json=chat_data)
```

## 测试

运行测试脚本验证功能：

```bash
cd agent-backend
python test_knowledge_base.py
```

## 扩展功能

### 1. 高级搜索
- 支持多字段搜索
- 支持布尔查询
- 支持范围查询

### 2. 文档处理
- 支持PDF、Word等格式
- 支持图片OCR
- 支持表格数据提取

### 3. 向量数据库
- 集成Chroma、Pinecone等向量数据库
- 支持大规模文档索引
- 支持实时更新

### 4. 智能问答
- 集成大语言模型
- 支持多轮对话
- 支持上下文记忆

## 注意事项

1. **文件大小限制**: 建议单个文档不超过10MB
2. **处理时间**: 大文档处理可能需要较长时间
3. **存储空间**: 向量嵌入会占用额外存储空间
4. **并发限制**: 避免同时处理大量文档
5. **数据备份**: 定期备份知识库数据

## 故障排除

### 常见问题

1. **文档处理失败**
   - 检查文件格式是否支持
   - 检查文件内容是否为空
   - 查看日志获取详细错误信息

2. **查询无结果**
   - 确认知识库中有文档
   - 检查文档是否处理完成
   - 尝试不同的查询关键词

3. **性能问题**
   - 减少文档大小
   - 调整分块参数
   - 优化向量计算

### 日志查看

```bash
tail -f logs/knowledge_base_service.log
tail -f logs/embedding_service.log
``` 