# 知识图谱增强RAG系统

## 概述

本项目实现了一个完整的知识图谱系统来增强RAG（检索增强生成）能力。知识图谱通过提取文档中的实体和关系，构建结构化的知识网络，提供更精确的语义检索和推理能力。

## 架构设计

### 1. 数据模型

知识图谱使用三元组（Subject-Predicate-Object）表示实体关系：

- **Subject（主语）**：实体，如人名、地名、机构、概念等
- **Predicate（关系）**：实体间的关系，如动作、属性、位置、时间等
- **Object（宾语）**：实体或属性值

### 2. 核心组件

#### KnowledgeGraphService（知识图谱服务）

位置：`agent-backend/services/knowledge_graph_service.py`

主要功能：
- **实体和关系提取**：使用LLM从文本中提取三元组
- **实体链接**：将相似的实体链接到规范化实体
- **图谱查询**：支持实体查询、多跳查询、路径查询
- **RAG增强**：使用知识图谱增强检索上下文

#### 主要方法

1. `extract_entities_and_relations()` - 从文本提取实体和关系
2. `store_triples()` - 存储三元组到数据库
3. `query_entities()` - 查询与实体相关的三元组
4. `query_relation_path()` - 查询两个实体之间的路径
5. `multi_hop_query()` - 多跳查询，发现间接关系
6. `enhance_rag_context()` - 使用知识图谱增强RAG上下文

## 工作流程

### 文档处理流程

```
文档上传 → 文本分块 → 向量化 → 三元组提取 → 存储到知识图谱
```

1. **文档上传**：用户上传文档到知识库
2. **文本分块**：将文档分割成多个文本块
3. **向量化**：为每个文本块生成嵌入向量
4. **三元组提取**：使用LLM从每个文本块提取实体和关系
5. **实体链接**：规范化实体名称，链接相似实体
6. **存储**：将三元组存储到数据库

### 查询流程

```
用户查询 → 向量检索 → 知识图谱增强 → 重排序 → LLM生成答案
```

1. **向量检索**：使用查询向量检索相关文档块
2. **知识图谱增强**：
   - 从查询和检索结果中提取实体
   - 查询相关三元组
   - 构建图谱上下文
3. **重排序**：使用CrossEncoder对结果重排序
4. **答案生成**：LLM基于增强的上下文生成答案

## 配置参数

### 环境变量

```bash
# 启用知识图谱提取
KG_EXTRACT_ENABLED=true

# 启用实体链接
KG_ENTITY_LINKING_ENABLED=true

# 最大跳数（多跳查询）
KG_MAX_HOPS=3

# 最多返回的实体数量
KG_TOP_ENTITIES=10

# 启用三元组提取（在文档处理时）
EXTRACT_TRIPLES_ENABLED=true

# 启用知识图谱查询（在RAG查询时）
KNOWLEDGE_GRAPH_ENABLED=true
```

## API接口

### 1. 获取知识图谱统计

```http
GET /api/knowledge-base/{kb_id}/graph/stats
```

返回：
```json
{
  "total_triples": 1000,
  "unique_subjects": 500,
  "unique_objects": 600,
  "unique_entities": 1100,
  "top_relations": [
    {"predicate": "位于", "count": 50},
    {"predicate": "属于", "count": 30}
  ]
}
```

### 2. 查询实体

```http
GET /api/knowledge-base/{kb_id}/graph/entities/{entity_name}?limit=20
```

返回：
```json
{
  "entity": "北京",
  "triples": [
    {
      "subject": "北京",
      "predicate": "位于",
      "object": "中国",
      "confidence": 0.9,
      "source_text": "...",
      "chunk_id": 123,
      "document_id": 45
    }
  ],
  "count": 1
}
```

### 3. 查询关系路径

```http
GET /api/knowledge-base/{kb_id}/graph/path?start_entity=张三&end_entity=公司A&max_hops=3
```

返回：
```json
{
  "start_entity": "张三",
  "end_entity": "公司A",
  "paths": [
    [
      {"subject": "张三", "predicate": "工作于", "object": "部门B"},
      {"subject": "部门B", "predicate": "属于", "object": "公司A"}
    ]
  ],
  "path_count": 1
}
```

## 使用示例

### 1. 启用知识图谱

在文档处理时自动提取三元组：

```python
# 设置环境变量
export EXTRACT_TRIPLES_ENABLED=true
export KNOWLEDGE_GRAPH_ENABLED=true
```

### 2. 查询知识库（自动使用知识图谱增强）

```python
# 查询会自动使用知识图谱增强上下文
result = kb_service.query_knowledge_base(
    db=db,
    kb_id=1,
    query="张三在哪里工作？",
    user_id="user123",
    max_results=5
)

# result 中包含：
# - sources: 向量检索结果
# - response: LLM生成的答案（基于增强的上下文）
# - metadata: 包含 graph_results_count 等信息
```

### 3. 直接使用知识图谱服务

```python
from services.knowledge_graph_service import KnowledgeGraphService

kg_service = KnowledgeGraphService()

# 提取三元组
triples = kg_service.extract_entities_and_relations(
    text="张三在北京工作，他是一名软件工程师。",
    kb_id=1,
    doc_id=1,
    chunk_id=1
)

# 存储三元组
stored_count = kg_service.store_triples(db, triples)

# 查询实体
entity_triples = kg_service.query_entities(db, kb_id=1, entity_name="张三")

# 多跳查询
related_triples = kg_service.multi_hop_query(
    db=db,
    kb_id=1,
    query="张三的工作",
    max_hops=2
)
```

## 优势

### 1. 更精确的语义理解

- 知识图谱捕获实体间的显式关系
- 支持多跳推理，发现间接关系
- 提供结构化的知识表示

### 2. 增强的检索能力

- 向量检索 + 知识图谱双重检索
- 实体级别的精确匹配
- 关系路径查询

### 3. 更好的答案质量

- LLM可以基于结构化知识生成更准确的答案
- 支持复杂推理问题
- 提供可解释的答案来源

## 性能优化

1. **批量处理**：三元组批量存储，减少数据库操作
2. **缓存机制**：实体链接结果缓存
3. **限制查询范围**：多跳查询限制跳数和结果数量
4. **异步处理**：三元组提取使用异步LLM调用

## 未来改进

1. **NER模型集成**：使用专门的命名实体识别模型提高提取精度
2. **关系分类**：自动分类关系类型
3. **实体消歧**：更智能的实体消歧算法
4. **图谱可视化**：提供图谱可视化界面
5. **增量更新**：支持知识图谱的增量更新
