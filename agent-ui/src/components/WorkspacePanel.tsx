import React, { useEffect, useRef, useState } from 'react';
import { Tabs, Empty, Typography, Card, Button, Space } from 'antd';
import ReactFlow, {
  Node,
  Edge,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  NodeTypes,
  Handle,
  Position
} from 'reactflow';
import 'reactflow/dist/style.css';
import { RobotOutlined, SettingOutlined, BranchesOutlined, ThunderboltOutlined } from '@ant-design/icons';
import FlowContextPanel, { PipelineData } from './FlowContextPanel';

const { Text } = Typography;

// 根据节点状态获取颜色
const getNodeColors = (status?: 'pending' | 'running' | 'completed' | 'failed', defaultBorder?: string, defaultBg?: string) => {
  // 如果状态为 undefined、null 或空字符串，默认使用 pending（灰色）
  const nodeStatus = status || 'pending';
  
  switch (nodeStatus) {
    case 'pending':
      return {
        border: '#d9d9d9', // 灰色
        background: '#f5f5f5',
        iconColor: '#bfbfbf'
      };
    case 'running':
      return {
        border: '#faad14', // 黄色
        background: '#fffbe6',
        iconColor: '#faad14'
      };
    case 'completed':
      return {
        border: '#52c41a', // 绿色
        background: '#f6ffed',
        iconColor: '#52c41a'
      };
    case 'failed':
      return {
        border: '#ff4d4f', // 红色
        background: '#fff1f0',
        iconColor: '#ff4d4f'
      };
    default:
      // 默认情况也使用灰色（pending 状态）
      return {
        border: '#d9d9d9',
        background: '#f5f5f5',
        iconColor: '#bfbfbf'
      };
  }
};

// 自定义节点组件 - 参考FlowEditorPage
const StartNode = ({ data }: { data: any }) => {
  const colors = getNodeColors(data.status, '#389e0d', '#f6ffed');
  return (
    <div style={{ padding: '10px', border: `2px solid ${colors.border}`, borderRadius: '8px', background: colors.background, minWidth: '80px' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '16px', color: colors.iconColor, marginBottom: '4px', fontWeight: 'bold' }}>▶</div>
        <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
      </div>
      <Handle type="source" position={Position.Bottom} id="source-0" />
      <Handle type="source" position={Position.Bottom} id="source-1" style={{ left: '30%' }} />
      <Handle type="source" position={Position.Bottom} id="source-2" style={{ left: '70%' }} />
    </div>
  );
};

const LlmNode = ({ data }: { data: any }) => {
  const colors = getNodeColors(data.status, '#096dd9', '#e6f7ff');
  return (
    <div style={{ padding: '10px', border: `2px solid ${colors.border}`, borderRadius: '8px', background: colors.background, minWidth: '80px' }}>
      <Handle type="target" position={Position.Top} />
      <div style={{ textAlign: 'center' }}>
        <RobotOutlined style={{ fontSize: '16px', color: colors.iconColor, marginBottom: '4px' }} />
        <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

const ToolNode = ({ data }: { data: any }) => {
  const colors = getNodeColors(data.status, '#d46b08', '#fff7e6');
  return (
    <div style={{ padding: '10px', border: `2px solid ${colors.border}`, borderRadius: '8px', background: colors.background, minWidth: '80px' }}>
      <Handle type="target" position={Position.Top} />
      <div style={{ textAlign: 'center' }}>
        <SettingOutlined style={{ fontSize: '16px', color: colors.iconColor, marginBottom: '4px' }} />
        <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

const AgentNode = ({ data }: { data: any }) => {
  const colors = getNodeColors(data.status, '#08979c', '#e6fffb');
  return (
    <div style={{ padding: '10px', border: `2px solid ${colors.border}`, borderRadius: '8px', background: colors.background, minWidth: '80px' }}>
      <Handle type="target" position={Position.Top} />
      <div style={{ textAlign: 'center' }}>
        <RobotOutlined style={{ fontSize: '16px', color: colors.iconColor, marginBottom: '4px' }} />
        <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

const EndNode = ({ data }: { data: any }) => {
  const colors = getNodeColors(data.status, '#531dab', '#f9f0ff');
  return (
    <div style={{ padding: '10px', border: `2px solid ${colors.border}`, borderRadius: '8px', background: colors.background, minWidth: '80px' }}>
      <Handle type="target" position={Position.Top} />
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '16px', color: colors.iconColor, marginBottom: '4px', fontWeight: 'bold' }}>●</div>
        <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
      </div>
    </div>
  );
};

const RouterNode = ({ data }: { data: any }) => {
  const colors = getNodeColors(data.status, '#fa8c16', '#fff7e6');
  return (
    <div style={{ padding: '10px', border: `2px solid ${colors.border}`, borderRadius: '8px', background: colors.background, minWidth: '80px' }}>
      <Handle type="target" position={Position.Top} />
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '16px', color: colors.iconColor, marginBottom: '4px', fontWeight: 'bold' }}>🔄</div>
        <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
      </div>
      <Handle type="source" position={Position.Bottom} id="source-true" style={{ left: '30%' }} />
      <Handle type="source" position={Position.Bottom} id="source-false" style={{ left: '70%' }} />
    </div>
  );
};

// Info 节点组件（用于显示提示信息）
const InfoNode = ({ data }: { data: any }) => {
  const colors = getNodeColors(data.status, '#1890ff', '#e6f7ff');
  return (
    <div style={{ padding: '10px', border: `2px solid ${colors.border}`, borderRadius: '8px', background: colors.background, minWidth: '80px' }}>
      <Handle type="target" position={Position.Top} />
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '16px', color: colors.iconColor, marginBottom: '4px' }}>ℹ️</div>
        <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

// 节点类型映射
const nodeTypes: NodeTypes = {
  start: StartNode,
  llm: LlmNode,
  tool: ToolNode,
  agent: AgentNode,
  end: EndNode,
  router: RouterNode,
  info: InfoNode, // 添加 info 节点类型
  default: LlmNode // 默认使用LLM节点样式
};

export interface WorkspaceTabItem {
	key: string;
	title: string;
	toolName?: string;
	content: string;
	createdAt: Date;
	closable?: boolean;
}

// 流程图执行状态接口
interface FlowExecutionState {
  isRunning: boolean;
  isPaused: boolean;
  currentNodeId: string | null;
  completedNodes: string[];
  failedNodes: string[];
  skippedNodes: string[];
  totalNodes: number;
  startTime: number | null;
  endTime: number | null;
  executionLog: Array<{
    timestamp: number;
    nodeId: string;
    action: string;
    message: string;
    level: 'info' | 'warning' | 'error' | 'success';
  }>;
  nodeStatuses: Array<{
    nodeId: string;
    status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
    label: string;
    nodeType: string;
  }>;
}

interface WorkspacePanelProps {
	tabs: WorkspaceTabItem[];
	activeKey?: string;
	onChange?: (key: string) => void;
	onClose?: (key: string) => void;
	onClear?: () => void;
	onCollapse?: () => void;
	// 新增：流程图相关属性
	flowData?: {
		nodes: Array<{
			id: string;
			label: string;
			nodeType: string;
			status?: 'pending' | 'running' | 'completed' | 'failed';
			position?: { x: number; y: number };
		}>;
		edges: Array<{
			id: string;
			source: string;
			target: string;
		}>;
		executionState?: {
			isRunning: boolean;
			currentNodeId?: string;
			completedNodes: string[];
			failedNodes: string[];
		};
	};
	// 新增：Pipeline 上下文数据
	pipelineContext?: PipelineData | null;
}

const WorkspacePanel: React.FC<WorkspacePanelProps> = ({
	tabs,
	activeKey,
	onChange,
	onClose,
	onClear,
	onCollapse,
	flowData,
	pipelineContext
}) => {
	const bodyRef = useRef<HTMLDivElement>(null);

	// 流程图状态管理
	const [flowNodes, setFlowNodes, onFlowNodesChange] = useNodesState([]);
	const [flowEdges, setFlowEdges, onFlowEdgesChange] = useEdgesState([]);
	const [flowExecutionState, setFlowExecutionState] = useState<FlowExecutionState>({
		isRunning: false,
		isPaused: false,
		currentNodeId: null,
		completedNodes: [],
		failedNodes: [],
		skippedNodes: [],
		totalNodes: 0,
		startTime: null,
		endTime: null,
		executionLog: [],
		nodeStatuses: []
	});



	// 智能布局算法 - 支持分支结构
	const calculateNodePositions = (nodes: any[], edges: any[]) => {
		const nodeMap = new Map();
		const inDegree = new Map();
		const outDegree = new Map();
		const levels = new Map();
		
		// 初始化节点信息
		nodes.forEach(node => {
			nodeMap.set(node.id, node);
			inDegree.set(node.id, 0);
			outDegree.set(node.id, 0);
		});
		
		// 计算入度和出度
		edges.forEach(edge => {
			inDegree.set(edge.target, inDegree.get(edge.target) + 1);
			outDegree.set(edge.source, inDegree.get(edge.source) + 1);
		});
		
		// 拓扑排序计算层级
		const queue: string[] = [];
		nodes.forEach(node => {
			if (inDegree.get(node.id) === 0) {
				levels.set(node.id, 0);
				queue.push(node.id);
			}
		});
		
		while (queue.length > 0) {
			const currentId = queue.shift()!;
			const currentLevel = levels.get(currentId);
			
			edges.forEach(edge => {
				if (edge.source === currentId) {
					const targetLevel = Math.max(levels.get(edge.target) || 0, currentLevel + 1);
					levels.set(edge.target, targetLevel);
					
					inDegree.set(edge.target, inDegree.get(edge.target) - 1);
					if (inDegree.get(edge.target) === 0) {
						queue.push(edge.target);
					}
				}
			});
		}
		
		// 按层级分组节点
		const levelGroups = new Map();
		levels.forEach((level, nodeId) => {
			if (!levelGroups.has(level)) {
				levelGroups.set(level, []);
			}
			levelGroups.get(level).push(nodeId);
		});
		
		// 计算节点位置 - 智能布局避免重叠
		const positions = new Map();
		const levelHeight = 200; // 增加层级间距
		const nodeWidth = 120; // 节点宽度
		const minNodeSpacing = 180; // 最小节点间距
		const containerWidth = 1400; // 增加容器宽度
		
		levelGroups.forEach((nodeIds, level) => {
			const y = 80 + level * levelHeight;
			
			// 智能计算间距：根据节点数量动态调整
			let spacing = minNodeSpacing;
			if (nodeIds.length > 3) {
				spacing = Math.max(minNodeSpacing, (containerWidth - nodeWidth) / (nodeIds.length - 1));
			}
			
			// 计算这层需要的总宽度
			const totalWidth = (nodeIds.length - 1) * spacing + nodeWidth;
			const startX = Math.max(100, (containerWidth - totalWidth) / 2); // 居中对齐
			
			nodeIds.forEach((nodeId: string, index: number) => {
				const x = startX + index * spacing;
				positions.set(nodeId, { x, y });
			});
		});
		
		return positions;
	};

	// 创建节点 - 使用自定义节点类型
	const createNode = (node: any, position: { x: number; y: number }) => {
		// 确保状态总是被设置，默认为 pending（灰色）
		const nodeStatus = node.status || 'pending';
		
		return {
			id: node.id,
			type: node.nodeType || 'default', // 直接使用nodeType作为ReactFlow的type
			position,
			data: { 
				label: node.label, 
				nodeType: node.nodeType,
				status: nodeStatus // 传递状态信息，确保总是有值
			}
		};
	};

	// 根据边的状态获取颜色
	const getEdgeColor = (sourceStatus?: 'pending' | 'running' | 'completed' | 'failed', targetStatus?: 'pending' | 'running' | 'completed' | 'failed', sourceHandle?: string) => {
		// 路由节点的分支使用特殊颜色
		if (sourceHandle === 'source-true') {
			// 真值分支：根据目标节点状态
			switch (targetStatus) {
				case 'pending': return '#d9d9d9'; // 灰色
				case 'running': return '#faad14'; // 黄色
				case 'completed': return '#52c41a'; // 绿色
				case 'failed': return '#ff4d4f'; // 红色
				default: return '#52c41a'; // 默认绿色
			}
		} else if (sourceHandle === 'source-false') {
			// 假值分支：根据目标节点状态
			switch (targetStatus) {
				case 'pending': return '#d9d9d9'; // 灰色
				case 'running': return '#faad14'; // 黄色
				case 'completed': return '#52c41a'; // 绿色
				case 'failed': return '#ff4d4f'; // 红色
				default: return '#fa8c16'; // 默认橙色
			}
		}
		
		// 普通边：根据源节点和目标节点的状态
		// 优先使用目标节点状态（因为边表示数据流向）
		const status = targetStatus || sourceStatus;
		switch (status) {
			case 'pending': return '#d9d9d9'; // 灰色
			case 'running': return '#faad14'; // 黄色
			case 'completed': return '#52c41a'; // 绿色
			case 'failed': return '#ff4d4f'; // 红色
			default: return '#d9d9d9'; // 默认灰色
		}
	};

	// 创建连接线 - 根据节点状态设置颜色
	const createEdge = (edge: any, index: number, nodeStatusMap: Map<string, 'pending' | 'running' | 'completed' | 'failed'>) => {
		const sourceStatus = nodeStatusMap.get(edge.source);
		const targetStatus = nodeStatusMap.get(edge.target);
		const color = getEdgeColor(sourceStatus, targetStatus, edge.sourceHandle);
		
		// 根据状态设置样式
		let edgeStyle = { 
			stroke: color, 
			strokeWidth: 2
		};
		
		// 路由节点的分支使用更粗的线
		if (edge.sourceHandle === 'source-true' || edge.sourceHandle === 'source-false') {
			edgeStyle.strokeWidth = 3;
		}
		
		// 如果目标节点正在运行，添加动画效果
		const animated = targetStatus === 'running';
		
		return {
			id: edge.id,
			source: edge.source,
			target: edge.target,
			sourceHandle: edge.sourceHandle, // 关键：保留sourceHandle
			targetHandle: edge.targetHandle, // 保留targetHandle
			style: edgeStyle,
			animated: animated
		} as Edge;
	};

	// 显示智能体预定义流程图
	useEffect(() => {
		console.log('🔍 WorkspacePanel 收到 flowData:', flowData);
		
		if (!flowData?.nodes || flowData.nodes.length === 0) {
			console.log('🔍 flowData 为空或没有节点');
			return;
		}

		console.log('🔍 节点数量:', flowData.nodes.length);
		console.log('🔍 连线数量:', flowData.edges.length);
		console.log('🔍 节点详情:', flowData.nodes);
		console.log('🔍 连线详情:', flowData.edges);

		// 计算节点位置
		const positions = calculateNodePositions(flowData.nodes, flowData.edges);
		
		// 创建节点状态映射
		const nodeStatusMap = new Map<string, 'pending' | 'running' | 'completed' | 'failed'>();
		flowData.nodes.forEach(node => {
			nodeStatusMap.set(node.id, node.status || 'pending');
		});
		
		const nodes: Node[] = flowData.nodes.map(node => {
			const position = positions.get(node.id) || { x: 200, y: 100 };
			return createNode(node, position);
		});
		const edges: Edge[] = flowData.edges.map((edge, index) => createEdge(edge, index, nodeStatusMap));

		console.log('🔍 创建的 ReactFlow 节点:', nodes);
		console.log('🔍 创建的 ReactFlow 连线:', edges);

		setFlowNodes(nodes);
		setFlowEdges(edges);
		setFlowExecutionState(prev => ({
			...prev,
			totalNodes: nodes.length,
			nodeStatuses: nodes.map(node => ({
				nodeId: node.id,
				status: (node.data.status || 'pending') as 'pending' | 'running' | 'completed' | 'failed',
				label: node.data.label,
				nodeType: node.data.nodeType || 'default'
			}))
		}));
	}, [flowData]);

	// 处理连接
	const onConnect = (connection: Connection) => {
		setFlowEdges(prev => addEdge(connection, prev));
	};




	if (!tabs || tabs.length === 0) {
		return (
			<div className="workspace-panel">
				<div className="workspace-header">
					<Text strong>工作空间</Text>
					<div style={{ display: 'flex', gap: 8 }}>
						<Button size="small" onClick={onCollapse}>收起</Button>
					</div>
				</div>
				<div className="workspace-body" ref={bodyRef}>
					<Empty description="工具执行结果会显示在这里" />
				</div>
			</div>
		);
	}

	return (
		<div className="workspace-panel">
			<div className="workspace-header">
				<Text strong>工作空间</Text>
				<div style={{ display: 'flex', gap: 8 }}>
					<Button size="small" onClick={onClear}>清空</Button>
					<Button size="small" onClick={onCollapse}>收起</Button>
				</div>
			</div>
			<div className="workspace-body" ref={bodyRef}>
				<Tabs
					type="editable-card"
					hideAdd
					activeKey={activeKey}
					onChange={(key) => onChange && onChange(key)}
					onEdit={(targetKey, action) => {
						if (action === 'remove' && onClose) {
							onClose(targetKey as string);
						}
					}}
				>
					{tabs.map((tab) => (
						<Tabs.TabPane
							key={tab.key}
							tab={tab.title}
							closable={tab.closable}
						>
							<div style={{ height: '100%', padding: '16px' }}>
								{tab.key === 'live_follow' ? (
									// 实时跟随流程图显示
									<div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
										{/* 流程图显示 */}
										<Card 
											title={
												<Space>
													<span>智能体流程图</span>
													{flowNodes.length > 0 && (
														<Text type="secondary" style={{ fontSize: '12px' }}>
															{flowNodes.length} 个节点, {flowEdges.length} 条连接
														</Text>
													)}
												</Space>
											}
											size="small" 
											style={{ flex: 1, minHeight: '500px' }}
											bodyStyle={{ height: 'calc(100% - 57px)', padding: '8px' }}
										>
											{flowNodes.length === 0 ? (
												<div style={{ 
													height: '450px', 
													display: 'flex', 
													flexDirection: 'column',
													alignItems: 'center',
													justifyContent: 'center',
													color: '#999'
												}}>
													<Text>暂无流程图数据</Text>
												</div>
											) : (
												<div style={{ height: '450px', position: 'relative' }}>
													<ReactFlow
														nodes={flowNodes}
														edges={flowEdges}
														onNodesChange={onFlowNodesChange}
														onEdgesChange={onFlowEdgesChange}
														onConnect={onConnect}
														fitView
														fitViewOptions={{ padding: 0.3, includeHiddenNodes: false }}
														minZoom={0.3}
														maxZoom={2}
														proOptions={{ hideAttribution: true }}
														style={{ background: '#fafafa', minHeight: '600px' }}
														nodeTypes={nodeTypes}
														nodesDraggable={false}
														nodesConnectable={false}
														elementsSelectable={false}
														selectNodesOnDrag={false}
														attributionPosition="bottom-left"
													>
														<Controls position="top-right" />
														<Background color="#aaa" gap={16} />
														<MiniMap 
															style={{
																background: 'rgba(255, 255, 255, 0.9)',
																border: '1px solid #ccc',
																borderRadius: '4px'
															}}
															nodeColor="#1890ff"
															maskColor="rgba(0, 0, 0, 0.1)"
														/>
													</ReactFlow>
												</div>
											)}
										</Card>
									</div>
								) : tab.key === 'context' ? (
									// 上下文容器
									<div style={{ height: '100%' }}>
										<FlowContextPanel
											contextData={pipelineContext || undefined}
											onRefresh={() => {
												// 可以在这里实现刷新逻辑
												console.log('刷新上下文数据');
											}}
										/>
									</div>
								) : (
									// 其他标签页的原有内容
									tab.content && tab.content.trim().startsWith('<') ? (
										<div dangerouslySetInnerHTML={{ __html: tab.content }} />
									) : (
										<pre className="workspace-pre">{tab.content}</pre>
									)
								)}
							</div>
						</Tabs.TabPane>
					))}
				</Tabs>
			</div>


		</div>
	);
};

export default WorkspacePanel; 