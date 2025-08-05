import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Button,
  Modal,
  Form,
  Input,
  Select,
  message,
  Space,
  Typography,
  Row,
  Col,
  Divider,
  Tag,
  Popconfirm,
  Drawer,
  Tabs
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  SaveOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  NodeIndexOutlined,
  BranchesOutlined,
  RobotOutlined,
  CheckCircleOutlined,
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
const AgentNode = ({ data }: { data: any }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#f0f8ff' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <RobotOutlined style={{ fontSize: '20px', color: '#1890ff' }} />
      <div style={{ fontWeight: 'bold' }}>{data.label}</div>
      <div style={{ fontSize: '12px', color: '#666' }}>{data.nodeType}</div>
    </div>
    <Handle type="source" position={Position.Bottom} />
  </div>
);

const ConditionNode = ({ data }: { data: any }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#fff7e6' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <BranchesOutlined style={{ fontSize: '20px', color: '#fa8c16' }} />
      <div style={{ fontWeight: 'bold' }}>{data.label}</div>
      <div style={{ fontSize: '12px', color: '#666' }}>条件判断</div>
    </div>
    <Handle type="source" position={Position.Bottom} id="true" />
    <Handle type="source" position={Position.Right} id="false" />
  </div>
);

const ActionNode = ({ data }: { data: any }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#f6ffed' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <ThunderboltOutlined style={{ fontSize: '20px', color: '#52c41a' }} />
      <div style={{ fontWeight: 'bold' }}>{data.label}</div>
      <div style={{ fontSize: '12px', color: '#666' }}>动作执行</div>
    </div>
    <Handle type="source" position={Position.Bottom} />
  </div>
);

const InputNode = ({ data }: { data: any }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#fff0f6' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <ImportOutlined style={{ fontSize: '20px', color: '#eb2f96' }} />
      <div style={{ fontWeight: 'bold' }}>{data.label}</div>
      <div style={{ fontSize: '12px', color: '#666' }}>输入节点</div>
    </div>
    <Handle type="source" position={Position.Bottom} />
  </div>
);

const OutputNode = ({ data }: { data: any }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#f9f0ff' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <ExportOutlined style={{ fontSize: '20px', color: '#722ed1' }} />
      <div style={{ fontWeight: 'bold' }}>{data.label}</div>
      <div style={{ fontSize: '12px', color: '#666' }}>输出节点</div>
    </div>
  </div>
);

const nodeTypes: NodeTypes = {
  agent: AgentNode,
  condition: ConditionNode,
  action: ActionNode,
  input: InputNode,
  output: OutputNode,
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
  const [configForm] = Form.useForm();

  useEffect(() => {
    fetchAgents();
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
        label: `新${getNodeTypeLabel(nodeType)}`,
        nodeType,
        config: {}
      }
    };
    setNodes((nds: Node[]) => nds.concat(newNode));
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
    setNodeConfigModal(true);
    
    // 填充表单
    configForm.setFieldsValue({
      label: node.data.label,
      nodeType: node.data.nodeType,
      ...node.data.config
    });
  };

  const saveNodeConfig = () => {
    configForm.validateFields().then((values) => {
      if (selectedNode) {
        setNodes((nds: Node[]) =>
          nds.map((node: Node) =>
            node.id === selectedNode.id
              ? {
                  ...node,
                  data: {
                    ...node.data,
                    label: values.label,
                    config: {
                      ...node.data.config,
                      ...values
                    }
                  }
                }
              : node
          )
        );
        setNodeConfigModal(false);
        setSelectedNode(null);
        message.success('节点配置已保存');
      }
    });
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
          data: node.data
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

      // 这里可以保存到后端
      console.log('流程图配置:', flowConfig);
      message.success('流程图已保存');
    } catch (error) {
      console.error('保存流程图失败:', error);
      message.error('保存流程图失败');
    } finally {
      setLoading(false);
    }
  };

  const loadFlow = (flowConfig: FlowConfig) => {
    setFlowName(flowConfig.metadata.name);
    setFlowDescription(flowConfig.metadata.description);
    setNodes(flowConfig.nodes);
    setEdges(flowConfig.edges);
    message.success('流程图已加载');
  };

  const clearFlow = () => {
    setNodes([]);
    setEdges([]);
    setFlowName('');
    setFlowDescription('');
    message.success('流程图已清空');
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
              <Button icon={<PlayCircleOutlined />}>
                测试
              </Button>
              <Button icon={<SettingOutlined />}>
                设置
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
            <Button
              icon={<ImportOutlined />}
              block
              onClick={() => addNode('input', { x: 100, y: 400 })}
            >
              输入节点
            </Button>
            <Button
              icon={<ExportOutlined />}
              block
              onClick={() => addNode('output', { x: 100, y: 500 })}
            >
              输出节点
            </Button>
          </Space>

          <Divider />

          <Title level={4}>可用智能体</Title>
          <div style={{ maxHeight: 300, overflowY: 'auto' }}>
            {agents.map((agent) => (
              <div key={agent.id} style={{ marginBottom: '8px' }}>
                <Tag color="blue">{agent.display_name}</Tag>
              </div>
            ))}
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
        open={nodeConfigModal}
        onOk={saveNodeConfig}
        onCancel={() => {
          setNodeConfigModal(false);
          setSelectedNode(null);
        }}
        width={600}
      >
        <Form form={configForm} layout="vertical">
          <Form.Item
            name="label"
            label="节点名称"
            rules={[{ required: true, message: '请输入节点名称' }]}
          >
            <Input placeholder="请输入节点名称" />
          </Form.Item>

          <Form.Item
            name="nodeType"
            label="节点类型"
          >
            <Select disabled>
              <Option value="agent">智能体节点</Option>
              <Option value="condition">条件节点</Option>
              <Option value="action">动作节点</Option>
              <Option value="input">输入节点</Option>
              <Option value="output">输出节点</Option>
            </Select>
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

          {selectedNode?.data.nodeType === 'input' && (
            <Form.Item
              name="prompt"
              label="输入提示"
              rules={[{ required: true, message: '请输入输入提示' }]}
            >
              <Input.TextArea
                rows={3}
                placeholder="例如：请输入您的问题"
              />
            </Form.Item>
          )}

          {selectedNode?.data.nodeType === 'output' && (
            <Form.Item
              name="template"
              label="输出模板"
              rules={[{ required: true, message: '请输入输出模板' }]}
            >
              <Input.TextArea
                rows={3}
                placeholder="例如：处理结果：{message}"
              />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default FlowEditorPage; 