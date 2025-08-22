import React, { useState, useEffect, useCallback } from 'react';
import {
  Layout,
  Card,
  Space,
  Button,
  Typography,
  message,
  Divider,
  Row,
  Col,
  Alert,
  Tooltip
} from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  ReloadOutlined,
  SaveOutlined,
  ExportOutlined,
  ImportOutlined,
  SettingOutlined,
  EyeOutlined,
  CodeOutlined,
  RocketOutlined
} from '@ant-design/icons';
import ReactFlow, {
  addEdge,
  Connection,
  Edge,
  Node,
  useNodesState,
  useEdgesState,
  Controls,
  Background,
  MiniMap,
  NodeTypes,
  Handle,
  Position
} from 'reactflow';
import 'reactflow/dist/style.css';

import FlowExecutionTracker from '../components/FlowExecutionTracker';
import FlowExecutionEngine, { FlowConfig, FlowNode, FlowEdge } from '../services/FlowExecutionEngine';
import { FlowExecutionState } from '../components/FlowExecutionTracker';

const { Content } = Layout;
const { Title, Text, Paragraph } = Typography;


interface FlowExecutionPageProps {
  initialFlowConfig?: FlowConfig;
}

const FlowExecutionPage: React.FC<FlowExecutionPageProps> = ({ initialFlowConfig }) => {
  // 流程图状态
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [flowName, setFlowName] = useState('新流程图');
  const [flowDescription, setFlowDescription] = useState('');

  // 执行状态
  const [executionState, setExecutionState] = useState<FlowExecutionState>({
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

  // 执行引擎
  const [executionEngine, setExecutionEngine] = useState<FlowExecutionEngine | null>(null);
  const [isExecutionReady, setIsExecutionReady] = useState(false);

  // UI状态
  const [compactMode, setCompactMode] = useState(false);

  // 初始化流程图
  useEffect(() => {
    if (initialFlowConfig) {
      const reactFlowNodes: Node[] = initialFlowConfig.nodes.map(node => ({
        id: node.id,
        type: node.type || 'default',
        position: node.position,
        data: {
          label: node.data.label,
          nodeType: node.data.nodeType,
          config: node.data.config,
          isStartNode: node.data.isStartNode
        }
      }));
      setNodes(reactFlowNodes);
      setEdges(initialFlowConfig.edges);
      setFlowName(initialFlowConfig.metadata.name);
      setFlowDescription(initialFlowConfig.metadata.description);
    } else {
      // 创建默认的开始节点
      const defaultStartNode: Node = {
        id: 'start_1',
        type: 'default',
        position: { x: 250, y: 100 },
        data: {
          label: '开始',
          nodeType: 'llm',
          config: {},
          isStartNode: true
        }
      };
      setNodes([defaultStartNode]);
    }
  }, [initialFlowConfig]);

  // 初始化执行引擎
  useEffect(() => {
    if (nodes.length > 0) {
      const flowConfig: FlowConfig = {
        nodes: nodes.map(node => ({
          id: node.id,
          type: node.type || 'default',
          position: node.position,
          data: {
            label: (node.data as any).label || '未命名节点',
            nodeType: (node.data as any).nodeType || 'default',
            config: (node.data as any).config || {},
            isStartNode: (node.data as any).isStartNode || false
          }
        })),
        edges: edges.map(edge => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          type: edge.type || 'default'
        })),
        metadata: {
          name: flowName,
          description: flowDescription,
          version: '1.0.0'
        }
      };

      const engine = new FlowExecutionEngine(flowConfig);
      setExecutionEngine(engine);
      setIsExecutionReady(true);

      // 更新执行状态
      const engineState = engine.getExecutionState();
      setExecutionState(engineState);
    }
  }, [nodes, edges, flowName, flowDescription]);

  // 处理连接
  const onConnect = useCallback((connection: Connection) => {
    setEdges(prev => addEdge(connection, prev));
  }, [setEdges]);

  // 开始执行
  const handleStartExecution = useCallback(async () => {
    if (!executionEngine) {
      message.error('执行引擎未初始化');
      return;
    }

    try {
      await executionEngine.startExecution();
      
      // 开始状态更新循环
      const updateInterval = setInterval(() => {
        const state = executionEngine.getExecutionState();
        setExecutionState(state);
        
        if (!state.isRunning) {
          clearInterval(updateInterval);
        }
      }, 100);

      message.success('流程执行已开始');
    } catch (error) {
      message.error(`执行失败: ${error instanceof Error ? error.message : '未知错误'}`);
    }
  }, [executionEngine]);

  // 暂停执行
  const handlePauseExecution = useCallback(() => {
    if (executionEngine) {
      executionEngine.pauseExecution();
      const state = executionEngine.getExecutionState();
      setExecutionState(state);
      message.info('流程执行已暂停');
    }
  }, [executionEngine]);

  // 恢复执行
  const handleResumeExecution = useCallback(() => {
    if (executionEngine) {
      executionEngine.resumeExecution();
      const state = executionEngine.getExecutionState();
      setExecutionState(state);
      message.info('流程执行已恢复');
    }
  }, [executionEngine]);

  // 停止执行
  const handleStopExecution = useCallback(() => {
    if (executionEngine) {
      executionEngine.stopExecution();
      const state = executionEngine.getExecutionState();
      setExecutionState(state);
      message.info('流程执行已停止');
    }
  }, [executionEngine]);

  // 重置执行
  const handleResetExecution = useCallback(() => {
    if (executionEngine) {
      executionEngine.resetExecution();
      const state = executionEngine.getExecutionState();
      setExecutionState(state);
      message.info('流程执行已重置');
    }
  }, [executionEngine]);

  // 保存流程图
  const handleSaveFlow = useCallback(() => {
    const flowConfig: FlowConfig = {
      nodes: nodes.map(node => ({
        id: node.id,
        type: node.type || 'default',
        position: node.position,
        data: {
          label: (node.data as any).label || '未命名节点',
          nodeType: (node.data as any).nodeType || 'default',
          config: (node.data as any).config || {},
          isStartNode: (node.data as any).isStartNode || false
        }
      })),
      edges: edges.map(edge => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: edge.type || 'default'
      })),
      metadata: {
        name: flowName,
        description: flowDescription,
        version: '1.0.0'
      }
    };

    // 这里可以调用API保存到后端
    const jsonStr = JSON.stringify(flowConfig, null, 2);
    localStorage.setItem('saved_flow', jsonStr);
    message.success('流程图已保存到本地存储');
  }, [nodes, edges, flowName, flowDescription]);

  // 导出流程图
  const handleExportFlow = useCallback(() => {
    const flowConfig: FlowConfig = {
      nodes: nodes.map(node => ({
        id: node.id,
        type: node.type || 'default',
        position: node.position,
        data: {
          label: (node.data as any).label || '未命名节点',
          nodeType: (node.data as any).nodeType || 'default',
          config: (node.data as any).config || {},
          isStartNode: (node.data as any).isStartNode || false
        }
      })),
      edges: edges.map(edge => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: edge.type || 'default'
      })),
      metadata: {
        name: flowName,
        description: flowDescription,
        version: '1.0.0'
      }
    };

    const jsonStr = JSON.stringify(flowConfig, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const filename = `${flowName}_${Date.now()}.json`;
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    message.success('流程图已导出');
  }, [nodes, edges, flowName, flowDescription]);

  // 节点点击处理
  const handleNodeClick = useCallback((nodeId: string) => {
    // 可以在这里实现节点详情显示或其他交互
    console.log('点击节点:', nodeId);
  }, []);

  return (
    <Layout style={{ height: '100vh', padding: '16px' }}>
      <Content>
        {/* 页面标题和控制按钮 */}
        <Card style={{ marginBottom: '16px' }}>
          <Row justify="space-between" align="middle">
            <Col>
              <Title level={3} style={{ margin: 0 }}>
                <RocketOutlined style={{ marginRight: '8px', color: '#1890ff' }} />
                流程图执行器
              </Title>
              <Text type="secondary">{flowDescription || '设计、执行和监控智能体流程图'}</Text>
            </Col>
            <Col>
              <Space>
                <Button
                  icon={<SaveOutlined />}
                  onClick={handleSaveFlow}
                >
                  保存
                </Button>
                <Button
                  icon={<ExportOutlined />}
                  onClick={handleExportFlow}
                >
                  导出
                </Button>

                <Button
                  icon={<CodeOutlined />}
                  onClick={() => setCompactMode(!compactMode)}
                >
                  {compactMode ? '完整' : '紧凑'}模式
                </Button>
              </Space>
            </Col>
          </Row>
        </Card>

        {/* 主要内容区域 */}
        <Row gutter={16} style={{ height: 'calc(100vh - 140px)' }}>
          {/* 左侧：流程图设计器 */}
          <Col span={16}>
            <Card 
              title={
                <Space>
                  <span>流程图设计器</span>
                  {executionState.isRunning && (
                    <Alert
                      message="流程执行中"
                      type="info"
                      showIcon
                      style={{ fontSize: '12px' }}
                    />
                  )}
                </Space>
              }
              style={{ height: '100%' }}
              bodyStyle={{ height: 'calc(100% - 57px)', padding: '8px' }}
            >
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                fitView
                fitViewOptions={{ padding: 0.1 }}
                minZoom={0.1}
                maxZoom={2}
              >
                <Controls />
                <Background />
                <MiniMap />
              </ReactFlow>
            </Card>
          </Col>

          {/* 右侧：流程图执行器和进度显示 */}
          <Col span={8}>
            <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
              {/* 实时流程图显示 */}
              <Card 
                title="实时流程图"
                style={{ flex: 1, marginBottom: '16px' }}
                bodyStyle={{ height: 'calc(100% - 57px)', padding: '8px' }}
              >
                <div style={{ height: '100%', position: 'relative' }}>
                  <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    fitView
                    fitViewOptions={{ padding: 0.1 }}
                    minZoom={0.1}
                    maxZoom={1.5}
                    proOptions={{ hideAttribution: true }}
                    style={{ background: '#fafafa' }}
                  >
                    <Controls />
                    <Background />
                    <MiniMap 
                      style={{
                        background: 'rgba(255, 255, 255, 0.9)',
                        border: '1px solid #ccc',
                        borderRadius: '4px'
                      }}
                    />
                  </ReactFlow>
                </div>
              </Card>

              {/* 执行控制面板 */}
              <Card 
                title="执行控制面板"
                style={{ flex: 1 }}
                bodyStyle={{ height: 'calc(100% - 57px)', overflow: 'auto' }}
              >
                <FlowExecutionTracker
                  executionState={executionState}
                  onStartExecution={handleStartExecution}
                  onPauseExecution={handlePauseExecution}
                  onResumeExecution={handleResumeExecution}
                  onStopExecution={handleStopExecution}
                  onResetExecution={handleResetExecution}
                  onNodeClick={handleNodeClick}
                  showDetails={!compactMode}
                  compact={compactMode}
                />
              </Card>
            </div>
          </Col>
        </Row>

        {/* 底部状态栏 */}
        <Card size="small" style={{ marginTop: '16px' }}>
          <Row justify="space-between" align="middle">
            <Col>
              <Space>
                <Text type="secondary">状态:</Text>
                <Text strong>
                  {executionState.isRunning 
                    ? (executionState.isPaused ? '已暂停' : '运行中') 
                    : '已停止'
                  }
                </Text>
                {executionState.currentNodeId && (
                  <>
                    <Text type="secondary">|</Text>
                    <Text type="secondary">当前节点:</Text>
                    <Text strong>{executionState.currentNodeId}</Text>
                  </>
                )}
              </Space>
            </Col>
            <Col>
              <Space>
                <Text type="secondary">
                  节点: {executionState.completedNodes.length}/{executionState.totalNodes}
                </Text>
                <Text type="secondary">|</Text>
                <Text type="secondary">
                  执行时间: {executionState.startTime 
                    ? Math.round((Date.now() - executionState.startTime) / 1000)
                    : 0}s
                </Text>
              </Space>
            </Col>
          </Row>
        </Card>
      </Content>
    </Layout>
  );
};

export default FlowExecutionPage; 