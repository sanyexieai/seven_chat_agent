"""流程图节点模块

提供流程图节点的基类和具体实现。

设计理念：
- 节点类别（NodeCategory）：定义节点的执行模式（如 PROCESSOR, ROUTER）
- 节点实现（NodeImplementation）：定义具体的执行方式（如 "llm", "tool"）
- 节点注册表（NodeRegistry）：管理所有可用的节点实现，支持动态扩展
"""

from .base_node import (
	BaseFlowNode,
	NodeCategory,
	NodeImplementation,
	NodeRegistry
)

# 导入节点实现并注册
from .nodes import (
	LLMNode,
	ToolNode,
	StartNode,
	EndNode,
	RouterNode,
	AutoParamNode
)
from .composite_node import CompositeNode

# 注册常用节点实现
NodeRegistry.register("llm", LLMNode)
NodeRegistry.register("tool", ToolNode)
NodeRegistry.register("start", StartNode)
NodeRegistry.register("end", EndNode)
NodeRegistry.register("router", RouterNode)
NodeRegistry.register("composite", CompositeNode)
NodeRegistry.register("auto_param", AutoParamNode)

__all__ = [
	'BaseFlowNode',
	'NodeCategory',
	'NodeImplementation',
	'NodeRegistry',
	'LLMNode',
	'ToolNode',
	'AutoParamNode',
	'StartNode',
	'EndNode',
	'RouterNode',
	'CompositeNode'
]
