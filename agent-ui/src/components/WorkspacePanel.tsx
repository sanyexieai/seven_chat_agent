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

const { Text } = Typography;

// 自定义节点组件 - 参考FlowEditorPage
const StartNode = ({ data }: { data: any }) => (
  <div style={{ padding: '10px', border: '2px solid #389e0d', borderRadius: '8px', background: '#f6ffed', minWidth: '80px' }}>
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: '16px', color: '#52c41a', marginBottom: '4px', fontWeight: 'bold' }}>▶</div>
      <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
    </div>
    <Handle type="source" position={Position.Bottom} id="source-0" />
    <Handle type="source" position={Position.Bottom} id="source-1" style={{ left: '30%' }} />
    <Handle type="source" position={Position.Bottom} id="source-2" style={{ left: '70%' }} />
  </div>
);

const LlmNode = ({ data }: { data: any }) => (
  <div style={{ padding: '10px', border: '2px solid #096dd9', borderRadius: '8px', background: '#e6f7ff', minWidth: '80px' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <RobotOutlined style={{ fontSize: '16px', color: '#1890ff', marginBottom: '4px' }} />
      <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
    </div>
    <Handle type="source" position={Position.Bottom} />
  </div>
 );

const ToolNode = ({ data }: { data: any }) => (
  <div style={{ padding: '10px', border: '2px solid #d46b08', borderRadius: '8px', background: '#fff7e6', minWidth: '80px' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <SettingOutlined style={{ fontSize: '16px', color: '#fa8c16', marginBottom: '4px' }} />
      <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
    </div>
    <Handle type="source" position={Position.Bottom} />
  </div>
 );

const ConditionNode = ({ data }: { data: any }) => (
  <div style={{ padding: '10px', border: '2px solid #d48806', borderRadius: '8px', background: '#fffbe6', minWidth: '80px' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <BranchesOutlined style={{ fontSize: '16px', color: '#faad14', marginBottom: '4px' }} />
      <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
    </div>
    <Handle type="source" position={Position.Bottom} />
  </div>
 );

const AgentNode = ({ data }: { data: any }) => (
  <div style={{ padding: '10px', border: '2px solid #08979c', borderRadius: '8px', background: '#e6fffb', minWidth: '80px' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <RobotOutlined style={{ fontSize: '16px', color: '#13c2c2', marginBottom: '4px' }} />
      <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
    </div>
    <Handle type="source" position={Position.Bottom} />
  </div>
);

const EndNode = ({ data }: { data: any }) => (
  <div style={{ padding: '10px', border: '2px solid #531dab', borderRadius: '8px', background: '#f9f0ff', minWidth: '80px' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: '16px', color: '#722ed1', marginBottom: '4px', fontWeight: 'bold' }}>●</div>
      <div style={{ fontWeight: 'bold', fontSize: '12px' }}>{data.label}</div>
    </div>
  </div>
);

// 节点类型映射
const nodeTypes: NodeTypes = {
  start: StartNode,
  llm: LlmNode,
  tool: ToolNode,
  condition: ConditionNode,
  agent: AgentNode,
  end: EndNode,
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
}

const WorkspacePanel: React.FC<WorkspacePanelProps> = ({
	tabs,
	activeKey,
	onChange,
	onClose,
	onClear,
	onCollapse,
	flowData
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
		return {
			id: node.id,
			type: node.nodeType || 'default', // 直接使用nodeType作为ReactFlow的type
			position,
			data: { 
				label: node.label, 
				nodeType: node.nodeType 
			}
		};
	};

	// 创建连接线 - 简单直线，参考FlowEditorPage
	const createEdge = (edge: any, index: number) => {
		// 为不同的连接线使用不同颜色
		const colors = ['#1890ff', '#52c41a', '#fa8c16', '#722ed1', '#eb2f96', '#13c2c2'];
		const color = colors[index % colors.length];
		
		return {
			id: edge.id,
			source: edge.source,
			target: edge.target,
			style: { 
				stroke: color, 
				strokeWidth: 2
			},
			animated: false
		} as Edge;
	};

	// 显示智能体预定义流程图
	useEffect(() => {
		if (!flowData?.nodes || flowData.nodes.length === 0) return;

		// 计算节点位置
		const positions = calculateNodePositions(flowData.nodes, flowData.edges);
		
		const nodes: Node[] = flowData.nodes.map(node => {
			const position = positions.get(node.id) || { x: 200, y: 100 };
			return createNode(node, position);
		});
		const edges: Edge[] = flowData.edges.map((edge, index) => createEdge(edge, index));

		setFlowNodes(nodes);
		setFlowEdges(edges);
		setFlowExecutionState(prev => ({
			...prev,
			totalNodes: nodes.length,
			nodeStatuses: nodes.map(node => ({
				nodeId: node.id,
				status: 'pending',
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