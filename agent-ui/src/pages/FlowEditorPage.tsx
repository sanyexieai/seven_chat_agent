import React, { useState, useEffect, useCallback } from 'react';
import {
  Button,
  Input,
  Select,
  Space,
  Typography,
  Card,
  Row,
  Col,
  Divider,
  Tag,
  Popconfirm,
  Drawer,
  Tabs,
  Checkbox,
  Modal,
  Form,
  message
} from 'antd';
import {
  PlusOutlined,
  SaveOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  DeleteOutlined,
  RobotOutlined,
  BranchesOutlined,
  ThunderboltOutlined,
  ImportOutlined,
  ExportOutlined
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
import axios from 'axios';

const { Title, Paragraph } = Typography;
const { Option } = Select;
const { TabPane } = Tabs;

interface FlowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: {
    label: string;
    nodeType: string;
    config: any;
  };
}

interface FlowEdge {
  id: string;
  source: string;
  target: string;
  type: string;
}

interface FlowConfig {
  nodes: FlowNode[];
  edges: FlowEdge[];
  metadata: {
    name: string;
    description: string;
    version: string;
  };
}

interface Agent {
  id: number;
  name: string;
  display_name: string;
  agent_type: string;
  is_active: boolean;
}

// 自定义节点组件
const AgentNode = ({ data, id }: { data: any; id: string }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#f0f8ff', position: 'relative' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <RobotOutlined style={{ fontSize: '20px', color: '#1890ff' }} />
      <div style={{ fontWeight: 'bold' }}>{data.label}</div>
      <div style={{ fontSize: '12px', color: '#666' }}>{data.nodeType}</div>
    </div>
    <Handle type="source" position={Position.Bottom} />
    <Button
      type="text"
      size="small"
      danger
      icon={<DeleteOutlined />}
      style={{
        position: 'absolute',
        top: '-8px',
        right: '-8px',
        minWidth: '20px',
        height: '20px',
        padding: '0',
        borderRadius: '50%',
        background: '#fff',
        border: '1px solid #ff4d4f',
        zIndex: 10
      }}
      onClick={(e) => {
        e.stopPropagation();
        // 这里需要通过props传递deleteNode函数
        if (data.onDelete) {
          data.onDelete(id);
        }
      }}
    />
  </div>
);

const ConditionNode = ({ data, id }: { data: any; id: string }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#fff7e6', position: 'relative' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <BranchesOutlined style={{ fontSize: '20px', color: '#fa8c16' }} />
      <div style={{ fontWeight: 'bold' }}>{data.label}</div>
      <div style={{ fontSize: '12px', color: '#666' }}>{data.nodeType}</div>
    </div>
    <Handle type="source" position={Position.Bottom} />
    <Button
      type="text"
      size="small"
      danger
      icon={<DeleteOutlined />}
      style={{
        position: 'absolute',
        top: '-8px',
        right: '-8px',
        minWidth: '20px',
        height: '20px',
        padding: '0',
        borderRadius: '50%',
        background: '#fff',
        border: '1px solid #ff4d4f',
        zIndex: 10
      }}
      onClick={(e) => {
        e.stopPropagation();
        if (data.onDelete) {
          data.onDelete(id);
        }
      }}
    />
  </div>
);

const ActionNode = ({ data, id }: { data: any; id: string }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#f6ffed', position: 'relative' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <ThunderboltOutlined style={{ fontSize: '20px', color: '#52c41a' }} />
      <div style={{ fontWeight: 'bold' }}>{data.label}</div>
      <div style={{ fontSize: '12px', color: '#666' }}>{data.nodeType}</div>
    </div>
    <Handle type="source" position={Position.Bottom} />
    <Button
      type="text"
      size="small"
      danger
      icon={<DeleteOutlined />}
      style={{
        position: 'absolute',
        top: '-8px',
        right: '-8px',
        minWidth: '20px',
        height: '20px',
        padding: '0',
        borderRadius: '50%',
        background: '#fff',
        border: '1px solid #ff4d4f',
        zIndex: 10
      }}
      onClick={(e) => {
        e.stopPropagation();
        if (data.onDelete) {
          data.onDelete(id);
        }
      }}
    />
  </div>
);

const InputNode = ({ data, id }: { data: any; id: string }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#e6f7ff', position: 'relative' }}>
    <div style={{ textAlign: 'center' }}>
      <ImportOutlined style={{ fontSize: '20px', color: '#1890ff' }} />
      <div style={{ fontWeight: 'bold' }}>{data.label}</div>
      <div style={{ fontSize: '12px', color: '#666' }}>{data.nodeType}</div>
    </div>
    <Handle type="source" position={Position.Bottom} />
    <Button
      type="text"
      size="small"
      danger
      icon={<DeleteOutlined />}
      style={{
        position: 'absolute',
        top: '-8px',
        right: '-8px',
        minWidth: '20px',
        height: '20px',
        padding: '0',
        borderRadius: '50%',
        background: '#fff',
        border: '1px solid #ff4d4f',
        zIndex: 10
      }}
      onClick={(e) => {
        e.stopPropagation();
        if (data.onDelete) {
          data.onDelete(id);
        }
      }}
    />
  </div>
);

const OutputNode = ({ data, id }: { data: any; id: string }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#fff2e8', position: 'relative' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <ExportOutlined style={{ fontSize: '20px', color: '#fa541c' }} />
      <div style={{ fontWeight: 'bold' }}>{data.label}</div>
      <div style={{ fontSize: '12px', color: '#666' }}>{data.nodeType}</div>
    </div>
    <Button
      type="text"
      size="small"
      danger
      icon={<DeleteOutlined />}
      style={{
        position: 'absolute',
        top: '-8px',
        right: '-8px',
        minWidth: '20px',
        height: '20px',
        padding: '0',
        borderRadius: '50%',
        background: '#fff',
        border: '1px solid #ff4d4f',
        zIndex: 10
      }}
      onClick={(e) => {
        e.stopPropagation();
        if (data.onDelete) {
          data.onDelete(id);
        }
      }}
    />
  </div>
);

const nodeTypes: NodeTypes = {
  agent: AgentNode,
  condition: ConditionNode,
  action: ActionNode
};

const FlowEditorPage: React.FC = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [nodeConfigModal, setNodeConfigModal] = useState(false);
  const [flowName, setFlowName] = useState('');
  const [flowDescription, setFlowDescription] = useState('');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentFlowId, setCurrentFlowId] = useState<number | null>(null);
  const [flows, setFlows] = useState<any[]>([]);
  const [configForm] = Form.useForm();
  const [isStartNode, setIsStartNode] = useState(false);
  const [configModalVisible, setConfigModalVisible] = useState(false);

  useEffect(() => {
    fetchAgents();
    fetchFlows(); // 组件加载时获取已保存的流程图
  }, []);

  const fetchAgents = async () => {
    try {
      const response = await axios.get('/api/agents');
      setAgents(response.data || []);
    } catch (error) {
      console.error('获取智能体失败:', error);
      message.error('获取智能体失败');
    }
  };

  const fetchFlows = async () => {
    try {
      const response = await axios.get('/api/flows');
      setFlows(response.data || []);
    } catch (error) {
      console.error('获取流程图失败:', error);
      message.error('获取流程图失败');
    }
  };

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds: Edge[]) => addEdge(params, eds)),
    [setEdges],
  );

  const addNode = (nodeType: string, position: { x: number; y: number }) => {
    const newNode: Node = {
      id: `node_${Date.now()}`,
      type: nodeType,
      position,
      data: {
        label: getNodeTypeLabel(nodeType),
        nodeType: nodeType,
        config: {},
        onDelete: deleteNode // 传递删除函数
      }
    };
    setNodes((nds) => [...nds, newNode]);
  };

  const getNodeTypeLabel = (nodeType: string) => {
    switch (nodeType) {
      case 'agent': return '智能体';
      case 'condition': return '条件';
      case 'action': return '动作';
      case 'input': return '输入';
      case 'output': return '输出';
      default: return '节点';
    }
  };

  const onNodeClick = (event: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
    configForm.setFieldsValue({
      label: node.data.label,
      isStartNode: node.data.isStartNode || false,
      agent_name: node.data.config?.agent_name || '',
      condition: node.data.config?.condition || '',
      action: node.data.config?.action || '',
      config: JSON.stringify(node.data.config || {}, null, 2)
    });
    setConfigModalVisible(true);
  };

  const saveNodeConfig = (values: any) => {
    if (!selectedNode) return;
    
    try {
      // 构建节点配置
      const config = {
        ...selectedNode.data.config,
        ...values
      };
      
      // 移除不需要的字段，但保留节点类型特定的配置
      delete config.label;
      delete config.isStartNode;
      delete config.config; // 高级配置字段
      
      // 根据节点类型保留相应的配置字段
      if (selectedNode.data.nodeType === 'agent') {
        // 保留智能体相关配置
        config.agent_name = values.agent_name;
      } else if (selectedNode.data.nodeType === 'condition') {
        // 保留条件相关配置
        config.condition = values.condition;
      } else if (selectedNode.data.nodeType === 'action') {
        // 保留动作相关配置
        config.action = values.action;
      }
      
      setNodes((nds) =>
        nds.map((node) =>
          node.id === selectedNode.id
            ? {
                ...node,
                data: {
                  ...node.data,
                  label: values.label,
                  isStartNode: values.isStartNode || false,
                  config: config
                }
              }
            : node
        )
      );
      
      setConfigModalVisible(false);
      setSelectedNode(null);
      message.success('节点配置已保存');
    } catch (error) {
      message.error('配置格式错误，请检查JSON格式');
    }
  };

  const deleteNode = (nodeId: string) => {
    setNodes((nds: Node[]) => nds.filter((node: Node) => node.id !== nodeId));
    setEdges((eds: Edge[]) => eds.filter((edge: Edge) => edge.source !== nodeId && edge.target !== nodeId));
    message.success('节点已删除');
  };

  const saveFlow = async () => {
    if (!flowName.trim()) {
      message.error('请输入流程图名称');
      return;
    }

    try {
      setLoading(true);
      const flowConfig = {
        nodes: nodes.map(node => ({
          id: node.id,
          type: node.data.nodeType,
          position: node.position,
          data: {
            ...node.data,
            isStartNode: node.data.isStartNode || false
          }
        })),
        edges: edges.map(edge => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          type: edge.type
        })),
        metadata: {
          name: flowName,
          description: flowDescription,
          version: '1.0.0'
        }
      };

      // 调用后端API保存流程图
      const response = await fetch('/api/flows', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: flowName,
          display_name: flowName,
          description: flowDescription,
          flow_config: flowConfig
        }),
      });

      if (response.ok) {
        const result = await response.json();
        setCurrentFlowId(result.id);
        message.success('流程图已保存');
        console.log('保存结果:', result);
      } else {
        const error = await response.json();
        message.error(`保存失败: ${error.detail || '未知错误'}`);
      }
    } catch (error) {
      console.error('保存流程图失败:', error);
      message.error('保存流程图失败');
    } finally {
      setLoading(false);
    }
  };

  const testFlow = async () => {
    if (!currentFlowId) {
      message.error('请先保存流程图');
      return;
    }

    try {
      setLoading(true);
      const testData = {
        input: "测试输入",
        context: {}
      };

      // 调用后端API测试流程图
      const response = await fetch(`/api/flows/${currentFlowId}/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(testData),
      });

      if (response.ok) {
        const result = await response.json();
        message.success('流程图测试成功');
        console.log('测试结果:', result);
      } else {
        const error = await response.json();
        message.error(`测试失败: ${error.detail || '未知错误'}`);
      }
    } catch (error) {
      console.error('测试流程图失败:', error);
      message.error('测试流程图失败');
    } finally {
      setLoading(false);
    }
  };

  const openSettings = () => {
    // 打开设置抽屉或模态框
    message.info('设置功能开发中...');
  };

  const deleteFlow = async (flowId: number) => {
    try {
      const response = await fetch(`/api/flows/${flowId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        message.success('流程图删除成功');
        // 重新获取流程图列表
        fetchFlows();
        // 如果删除的是当前加载的流程图，清空编辑器
        if (currentFlowId === flowId) {
          clearFlow();
        }
      } else {
        const error = await response.json();
        message.error(`删除失败: ${error.detail || '未知错误'}`);
      }
    } catch (error) {
      console.error('删除流程图失败:', error);
      message.error('删除流程图失败');
    }
  };

  const loadFlow = (flowConfig: FlowConfig) => {
    setFlowName(flowConfig.metadata.name);
    setFlowDescription(flowConfig.metadata.description);
    setNodes(flowConfig.nodes);
    setEdges(flowConfig.edges);
    message.success('流程图已加载');
  };

  const loadSavedFlow = async (flowId: number) => {
    try {
      const response = await fetch(`/api/flows/${flowId}`);
      if (response.ok) {
        const flow = await response.json();
        setFlowName(flow.display_name);
        setFlowDescription(flow.description || '');
        setCurrentFlowId(flow.id);
        
        // 加载流程图配置
        if (flow.flow_config) {
          const config = flow.flow_config;
          if (config.nodes) {
            // 为每个节点添加删除功能
            const nodesWithDelete = config.nodes.map((node: any) => ({
              ...node,
              data: {
                ...node.data,
                onDelete: deleteNode
              }
            }));
            setNodes(nodesWithDelete);
          }
          if (config.edges) {
            setEdges(config.edges);
          }
        }
        
        message.success('流程图已加载');
      } else {
        message.error('加载流程图失败');
      }
    } catch (error) {
      console.error('加载流程图失败:', error);
      message.error('加载流程图失败');
    }
  };

  const clearFlow = () => {
    setNodes([]);
    setEdges([]);
    setFlowName('');
    setFlowDescription('');
    setCurrentFlowId(null);
    message.success('流程图已清空');
  };

  const createAgentFromFlow = async () => {
    if (!currentFlowId) {
      message.error('请先保存流程图');
      return;
    }

    try {
      setLoading(true);
      const flowConfig = {
        nodes: nodes.map(node => ({
          id: node.id,
          type: node.data.nodeType,
          position: node.position,
          data: {
            ...node.data,
            isStartNode: node.data.isStartNode || false
          }
        })),
        edges: edges.map(edge => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          type: edge.type
        })),
        metadata: {
          name: flowName,
          description: flowDescription,
          version: '1.0.0'
        }
      };

      const response = await fetch('/api/agents/create_from_flow', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          flow_name: flowName,
          flow_description: flowDescription,
          flow_config: flowConfig
        }),
      });

      if (response.ok) {
        const result = await response.json();
        message.success('智能体创建成功');
        console.log('智能体创建结果:', result);
        
        // 重新加载智能体列表
        try {
          const reloadResponse = await fetch('/api/agents/reload', {
            method: 'POST',
          });
          if (reloadResponse.ok) {
            console.log('智能体重新加载成功');
          }
        } catch (error) {
          console.warn('重新加载智能体失败:', error);
        }
        
        // 跳转到智能体详情页
        window.location.href = `/agents/${result.id}`;
      } else {
        const error = await response.json();
        message.error(`智能体创建失败: ${error.detail || '未知错误'}`);
      }
    } catch (error) {
      console.error('创建智能体失败:', error);
      message.error('创建智能体失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* 工具栏 */}
      <div style={{ padding: '16px', borderBottom: '1px solid #f0f0f0', background: '#fff' }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Title level={3} style={{ margin: 0 }}>流程图编辑器</Title>
          </Col>
          <Col>
            <Space>
              <Input
                placeholder="流程图名称"
                value={flowName}
                onChange={(e) => setFlowName(e.target.value)}
                style={{ width: 200 }}
              />
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={saveFlow}
                loading={loading}
              >
                保存
              </Button>
              <Button icon={<PlayCircleOutlined />} onClick={testFlow}>
                测试
              </Button>
              <Button icon={<SettingOutlined />} onClick={openSettings}>
                设置
              </Button>
              {currentFlowId && (
                <Popconfirm
                  title="确定要删除当前流程图吗？"
                  description="删除后无法恢复"
                  onConfirm={() => deleteFlow(currentFlowId)}
                  okText="确定"
                  cancelText="取消"
                >
                  <Button icon={<DeleteOutlined />} danger>
                    删除
                  </Button>
                </Popconfirm>
              )}
              <Button icon={<DeleteOutlined />} onClick={clearFlow}>
                清空
              </Button>
              <Button 
                type="primary" 
                icon={<RobotOutlined />} 
                onClick={createAgentFromFlow}
                disabled={!currentFlowId || nodes.length === 0}
              >
                创建智能体
              </Button>
            </Space>
          </Col>
        </Row>
      </div>

      {/* 侧边栏 */}
      <div style={{ display: 'flex', flex: 1 }}>
        <div style={{ width: 250, borderRight: '1px solid #f0f0f0', background: '#fafafa', padding: '16px' }}>
          <Title level={4}>节点类型</Title>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Button
              icon={<RobotOutlined />}
              block
              onClick={() => addNode('agent', { x: 100, y: 100 })}
            >
              智能体节点
            </Button>
            <Button
              icon={<BranchesOutlined />}
              block
              onClick={() => addNode('condition', { x: 100, y: 200 })}
            >
              条件节点
            </Button>
            <Button
              icon={<ThunderboltOutlined />}
              block
              onClick={() => addNode('action', { x: 100, y: 300 })}
            >
              动作节点
            </Button>
          </Space>

          <Divider />

          <Title level={4}>已保存的流程图</Title>
          <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
            {flows.map((flow) => (
              <Card
                key={flow.id}
                size="small"
                style={{ marginBottom: '8px' }}
                actions={[
                  <Button
                    type="link"
                    size="small"
                    onClick={() => loadSavedFlow(flow.id)}
                  >
                    加载
                  </Button>,
                  <Popconfirm
                    title="确定要删除这个流程图吗？"
                    onConfirm={() => deleteFlow(flow.id)}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button type="link" size="small" danger>
                      删除
                    </Button>
                  </Popconfirm>
                ]}
              >
                <Card.Meta
                  title={flow.display_name}
                  description={flow.description || '暂无描述'}
                />
              </Card>
            ))}
          </div>

          <Divider />

          <Title level={4}>使用说明</Title>
          <div style={{ fontSize: '12px', color: '#666' }}>
            <p><strong>配置起始节点：</strong></p>
            <ol style={{ paddingLeft: '16px' }}>
              <li>点击任意节点打开配置对话框</li>
              <li>勾选"设为起始节点"选项</li>
              <li>点击确定保存配置</li>
            </ol>
            <p><strong>注意：</strong>每个流程图只能有一个起始节点</p>
          </div>
        </div>

        {/* 流程图画布 */}
        <div style={{ flex: 1, height: '100%' }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            nodeTypes={nodeTypes}
            fitView
          >
            <Controls />
            <Background />
            <MiniMap />
          </ReactFlow>
        </div>
      </div>

      {/* 节点配置模态框 */}
      <Modal
        title="节点配置"
        open={configModalVisible}
        onOk={() => configForm.submit()}
        onCancel={() => setConfigModalVisible(false)}
        width={600}
      >
        <Form form={configForm} layout="vertical" onFinish={saveNodeConfig}>
          <Form.Item
            name="label"
            label="节点名称"
            rules={[{ required: true, message: '请输入节点名称' }]}
          >
            <Input placeholder="请输入节点名称" />
          </Form.Item>
          
          <Form.Item
            name="isStartNode"
            label="起始节点"
            valuePropName="checked"
          >
            <Checkbox>设为起始节点</Checkbox>
          </Form.Item>

          {/* 根据节点类型显示不同的配置项 */}
          {selectedNode?.data.nodeType === 'agent' && (
            <Form.Item
              name="agent_name"
              label="选择智能体"
              rules={[{ required: true, message: '请选择智能体' }]}
            >
              <Select placeholder="请选择智能体">
                {agents.map((agent) => (
                  <Option key={agent.id} value={agent.name}>
                    {agent.display_name}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          )}

          {selectedNode?.data.nodeType === 'condition' && (
            <Form.Item
              name="condition"
              label="条件表达式"
              rules={[{ required: true, message: '请输入条件表达式' }]}
            >
              <Input.TextArea
                rows={3}
                placeholder="例如：用户消息包含'搜索'关键词"
              />
            </Form.Item>
          )}

          {selectedNode?.data.nodeType === 'action' && (
            <Form.Item
              name="action"
              label="动作描述"
              rules={[{ required: true, message: '请输入动作描述' }]}
            >
              <Input.TextArea
                rows={3}
                placeholder="例如：调用搜索API"
              />
            </Form.Item>
          )}

          <Form.Item
            name="config"
            label="高级配置"
          >
            <Input.TextArea rows={4} placeholder="请输入节点配置（JSON格式）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default FlowEditorPage; 