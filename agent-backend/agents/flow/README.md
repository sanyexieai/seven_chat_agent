# 流程图节点系统设计

## 设计理念

新的节点系统采用**类别-实现分离**的设计，使得节点类型更通用、可扩展：

1. **节点类别（NodeCategory）**：定义节点的执行模式，是抽象的类别
   - `PROCESSOR`: 处理器节点（处理数据）
   - `ROUTER`: 路由节点（条件分支）
   - `LOOP`: 循环节点（迭代执行）
   - `AGGREGATOR`: 聚合节点（合并结果）
   - 等等...

2. **节点实现（NodeImplementation）**：定义具体的执行方式
   - `llm`: LLM调用
   - `tool`: 工具调用
   - `router_condition`: 条件路由
   - 等等...

3. **节点注册表（NodeRegistry）**：管理所有可用的节点实现，支持动态注册

## 优势

### 1. 更通用
- 节点类别不绑定具体实现，同一个类别可以有多种实现方式
- 例如：`PROCESSOR` 类别可以使用 `llm`、`tool`、`agent` 等多种实现

### 2. 可扩展
- 通过注册机制，可以轻松添加新的节点实现
- 不需要修改核心代码，只需注册新的实现类或工厂函数

### 3. 灵活配置
- 节点配置中通过 `implementation` 字段指定具体实现
- 支持自定义实现（`custom`）

## 默认节点实现

所有内置节点都位于 `agents/flow/nodes/` 目录下，每个节点类型拥有独立文件，方便维护与扩展：

- `llm_node.py`：LLM 调用节点
- `tool_node.py`：工具调用节点
- `start_node.py`：流程入口节点
- `router_node.py`：条件路由节点
- `end_node.py`：流程出口节点

## 使用示例

### 1. 注册节点实现

```python
from agents.flow import BaseFlowNode, NodeCategory, NodeRegistry

# 方式1：注册节点类
class LLMNode(BaseFlowNode):
    async def execute(self, user_id, message, context, agent_name=None):
        # LLM调用逻辑
        pass
    
    async def execute_stream(self, user_id, message, context, agent_name=None):
        # 流式LLM调用逻辑
        pass

NodeRegistry.register("llm", LLMNode)

# 方式2：注册工厂函数
def create_tool_node(node_id, category, name, config, position):
    return ToolNode(node_id, category, "tool", name, config, position)

NodeRegistry.register_factory("tool", create_tool_node)
```

### 2. 创建节点

```python
from agents.flow import NodeRegistry, NodeCategory

# 通过注册表创建
node = NodeRegistry.create_node(
    node_id="node_1",
    category=NodeCategory.PROCESSOR,
    implementation="llm",
    name="LLM处理",
    config={"system_prompt": "你是一个助手"}
)

# 或从配置创建（兼容旧格式）
node_config = {
    "id": "node_1",
    "type": "llm",  # 旧格式，会自动推断为 PROCESSOR + llm
    "data": {
        "label": "LLM处理",
        "config": {"system_prompt": "你是一个助手"}
    }
}
node = BaseFlowNode.from_config(node_config)

# 新格式
node_config = {
    "id": "node_1",
    "category": "processor",
    "implementation": "llm",
    "data": {
        "label": "LLM处理",
        "config": {"system_prompt": "你是一个助手"}
    }
}
node = BaseFlowNode.from_config(node_config)
```

### 3. 节点配置示例

```json
{
  "nodes": [
    {
      "id": "start",
      "category": "start",
      "data": {"label": "开始"}
    },
    {
      "id": "llm_process",
      "category": "processor",
      "implementation": "llm",
      "data": {
        "label": "LLM处理",
        "config": {
          "system_prompt": "你是一个助手",
          "user_prompt": "{{message}}",
          "save_as": "llm_result"
        }
      }
    },
    {
      "id": "router",
      "category": "router",
      "implementation": "router_condition",
      "data": {
        "label": "条件判断",
        "config": {
          "field": "llm_result",
          "condition": "contains",
          "value": "需要工具",
          "true_branch": "tool_node",
          "false_branch": "end"
        }
      }
    },
    {
      "id": "tool_node",
      "category": "processor",
      "implementation": "tool",
      "data": {
        "label": "工具调用",
        "config": {
          "server": "ddg",
          "tool": "search",
          "params": {"query": "{{llm_result}}"}
        }
      }
    }
  ]
}
```

## 扩展新节点实现

### 1. 创建节点类

```python
from agents.flow import BaseFlowNode, NodeCategory

class CustomNode(BaseFlowNode):
    def __init__(self, node_id, category, implementation, name, config, position):
        super().__init__(node_id, category, implementation, name, config, position)
        # 自定义初始化
    
    async def execute(self, user_id, message, context, agent_name=None):
        # 实现同步执行逻辑
        result = self._do_something()
        return self._create_agent_message(result, agent_name)
    
    async def execute_stream(self, user_id, message, context, agent_name=None):
        # 实现流式执行逻辑
        async for chunk in self._do_something_stream():
            yield self._create_stream_chunk("content", chunk)
```

### 2. 注册节点

```python
from agents.flow import NodeRegistry

NodeRegistry.register("custom_implementation", CustomNode)
```

### 3. 使用

```json
{
  "id": "custom_node",
  "category": "processor",
  "implementation": "custom_implementation",
  "data": {
    "label": "自定义节点",
    "config": {"param1": "value1"}
  }
}
```

## 迁移指南

### 从旧格式迁移

旧格式使用 `type` 字段：
```json
{
  "id": "node_1",
  "type": "llm",
  "data": {"label": "LLM", "config": {}}
}
```

新格式使用 `category` + `implementation`：
```json
{
  "id": "node_1",
  "category": "processor",
  "implementation": "llm",
  "data": {"label": "LLM", "config": {}}
}
```

**兼容性**：系统会自动识别旧格式并转换为新格式，无需立即修改现有配置。

## 标准上下文与历史数据（中间件式）

节点可从上下文 `flow_state` 读取历史节点数据，并以“节点ID为命名空间”的方式存取数据。

- `set_node_value(context, key, value, node_id=None)`: 写入指定节点（默认当前节点）的 `data[key]`
- `get_node_value(context, key, default=None, node_id=None)`: 读取指定节点的 `data[key]`
- `append_node_output(context, output, node_id=None)`: 追加一条输出到指定节点的 `outputs`，并更新全局 `last_output`
- `get_node_outputs(context, node_id=None)`: 读取指定节点的所有输出
- `get_last_output_of_node(context, node_id=None, default=None)`: 读取指定节点的最后一次输出

在流程中，任意节点都可以通过以上方法访问历史节点的数据，实现“中间件式”的上下文共享。

## 标准输入与输出

为统一节点间协作，基类提供了标准的输入与输出辅助：

- `prepare_inputs(message, context) -> dict`
  - 基础输入包含：
    - `message`: 当前用户消息
    - `last_output`: 全局最后输出
    - `flow_state`: 全部流程状态（供高级模板引用）
  - 若配置中包含 `config.input`（dict），其中的值支持 `{{var}}` 模板，变量来自基础输入与 `flow_state`
- `save_output(context, output)`
  - 追加到当前节点的历史输出并更新全局 `last_output`
  - 若配置包含 `config.save_as`，则同时写入 `flow_state[save_as]`

节点实现通常写法：

```python
inputs = self.prepare_inputs(message, context)
# ... 执行逻辑，基于 inputs ...
self.save_output(context, result_text)
return self._create_agent_message(result_text, agent_name)
```

## 可选的挂载容器（例如浏览器节点）

对于需要外部运行环境的节点（如无头浏览器），可以在节点 `config` 中声明挂载容器规范：

```json
{
  "id": "browser_node",
  "category": "processor",
  "implementation": "custom_browser",
  "data": {
    "label": "浏览器渲染",
    "config": {
      "mount": {
        "type": "docker",
        "image": "my/browser:latest",
        "options": {"shm_size": "2g"}
      }
    }
  }
}
```

基类支持：
- `get_mount_spec() -> dict | None`
- `requires_mount() -> bool`

上层调度器可据此选择性地为节点准备容器环境（例如拉起/复用Docker），从而实现浏览器等可视化/隔离运行的需求。

## 工作流引擎（FlowEngine）

引擎负责构建和执行由节点组成的有向图，支持同步与流式执行、上下文传递、事件输出及挂载容器。

### 图配置格式

```json
{
  "nodes": [
    {
      "id": "start",
      "category": "start",
      "data": {"label": "开始"}
    },
    {
      "id": "llm_process",
      "category": "processor",
      "implementation": "llm",
      "data": {
        "label": "LLM处理",
        "config": {
          "user_prompt": "{{message}}",
          "save_as": "llm_result"
        }
      }
    },
    {
      "id": "end",
      "category": "end",
      "data": {"label": "结束"}
    }
  ],
  "edges": [
    {"source": "start", "target": "llm_process", "sourceIndex": 0},
    {"source": "llm_process", "target": "end", "sourceIndex": 0}
  ]
}
```

说明：
- 若未提供 `edges`，引擎会读取节点实例上的 `connections`。
- 起点优先顺序：显式传入 -> `category=start` -> 入度为0的节点 -> 任意一个节点。

### 使用示例

```python
from agents.flow.engine import FlowEngine
from agents.flow.base_node import NodeCategory

graph = {...}  # 上述格式
engine = FlowEngine()
engine.build_from_config(graph)

# 同步执行
messages = await engine.run(
    user_id="u1",
    message="你好",
    context={},
    start_node_id=None,
    agent_name="FlowAgent"
)

# 流式执行
async for chunk in engine.run_stream(
    user_id="u1",
    message="你好",
    context={},
    start_node_id=None,
    agent_name="FlowAgent"
):
    print(chunk.type, chunk.content)
```

### 挂载容器

创建引擎时可注入 `mount_provider` 钩子，用于根据节点 `config.mount` 准备外部环境（如Docker）：

```python
def mount_provider(mount_spec: dict):
    # 准备容器，返回可选的 handler（如容器ID/客户端对象）
    return {"container_id": "abc123"}

engine = FlowEngine(mount_provider=mount_provider)
```

