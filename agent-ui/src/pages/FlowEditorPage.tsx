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
  message,
  TreeSelect
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
import { API_PATHS } from '../config/api';

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

const LlmNode = ({ data, id }: { data: any; id: string }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#e8f5e9', position: 'relative' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <RobotOutlined style={{ fontSize: '20px', color: '#389e0d' }} />
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

const ToolNode = ({ data, id }: { data: any; id: string }) => (
  <div style={{ padding: '10px', border: '1px solid #ccc', borderRadius: '8px', background: '#fffbe6', position: 'relative' }}>
    <Handle type="target" position={Position.Top} />
    <div style={{ textAlign: 'center' }}>
      <SettingOutlined style={{ fontSize: '20px', color: '#d48806' }} />
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
  action: ActionNode,
  llm: LlmNode,
  tool: ToolNode
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
  const [currentMode, setCurrentMode] = useState<'create' | 'edit'>('create');
  const [flows, setFlows] = useState<any[]>([]);
  const [configForm] = Form.useForm();
  const [isStartNode, setIsStartNode] = useState(false);
  const [configModalVisible, setConfigModalVisible] = useState(false);
  const [importModalVisible, setImportModalVisible] = useState(false);
  const [importJsonText, setImportJsonText] = useState('');
  const [currentAgentId, setCurrentAgentId] = useState<number | null>(null);
  
  const createStartNode = () => {
    const hasStart = nodes.some((n: any) => n?.data?.isStartNode);
    if (hasStart) return;
    const startNode: Node = {
      id: `start_${Date.now()}`,
      type: 'llm',
      position: { x: 120, y: 60 },
      data: {
        label: '开始',
        nodeType: 'llm',
        config: {},
        isStartNode: true,
        onDelete: deleteNode
      }
    } as any;
    setNodes((nds) => [startNode, ...nds]);
  };
  
  // 设置抽屉相关状态（参考通用智能体，除提示词外）
  const [settingsVisible, setSettingsVisible] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSubmitting, setSettingsSubmitting] = useState(false);
  const [settingsForm] = Form.useForm();
  const [llmConfigs, setLlmConfigs] = useState<any[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<any[]>([]);
  const [toolTreeData, setToolTreeData] = useState<any[]>([]);

  useEffect(() => {
    fetchAgents();
    fetchFlows(); // 组件加载时获取已保存的流程图
    
    // 检查URL参数，如果是编辑模式，加载智能体信息
    const urlParams = new URLSearchParams(window.location.search);
    const mode = urlParams.get('mode');
    const agentInfo = urlParams.get('agent_info');
    
    console.log('URL参数检查:', { mode, agentInfo });
    
    if (mode === 'edit' && agentInfo) {
      try {
        console.log('开始解析智能体信息...');
        const agent = JSON.parse(decodeURIComponent(agentInfo));
        console.log('解析后的智能体信息:', agent);
        setCurrentMode('edit');
        loadAgentInfo(agent);
      } catch (error) {
        console.error('解析智能体信息失败:', error);
        message.error('加载智能体信息失败');
      }
    } else if (mode === 'create') {
      console.log('设置为创建模式');
      setCurrentMode('create');
      // 创建默认开始节点
      setTimeout(() => createStartNode(), 0);
    } else {
      console.log('未找到有效的模式参数');
    }
  }, []);

  const fetchAgents = async () => {
    try {
      const response = await axios.get(API_PATHS.AGENTS);
      setAgents(response.data || []);
    } catch (error) {
      console.error('获取智能体失败:', error);
      message.error('获取智能体失败');
    }
  };

  const fetchFlows = async () => {
    try {
      const response = await axios.get(API_PATHS.FLOWS);
      setFlows(response.data || []);
    } catch (error) {
      console.error('获取流程图失败:', error);
      message.error('获取流程图失败');
    }
  };

  const exportFlowAsJSON = () => {
    try {
      const flowConfig = {
        nodes: nodes.map(node => ({
          id: node.id,
          type: node.data.nodeType,
          position: node.position,
          data: { ...node.data, isStartNode: node.data.isStartNode || false }
        })),
        edges: edges.map(edge => ({ id: edge.id, source: edge.source, target: edge.target, type: edge.type })),
        metadata: { name: flowName || '新流程', description: flowDescription || '', version: '1.0.0' }
      };
      const jsonStr = JSON.stringify(flowConfig, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const filename = `${(flowName || 'flow')}_${Date.now()}.json`;
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      message.success('流程JSON已导出');
    } catch (e) {
      console.error(e);
      message.error('导出失败');
    }
  };

  const loadAgentInfo = (agent: any) => {
    console.log('开始加载智能体信息:', agent);
    
    // 设置智能体基本信息
    setFlowName(agent.display_name || agent.name);
    setFlowDescription(agent.description || '');
    
    console.log('设置基本信息完成:', {
      name: agent.display_name || agent.name,
      description: agent.description || ''
    });
    
    // 规范化旧 bound_tools（对象 -> "server_tool" 字符串）
    const normalizedBoundTools = Array.isArray(agent.bound_tools)
      ? agent.bound_tools
          .map((t: any) => typeof t === 'string' ? t : (t && t.server && t.tool ? `${t.server}_${t.tool}` : null))
          .filter((v: any) => !!v)
      : [];
    settingsForm.setFieldsValue({
      llm_config_id: agent.llm_config_id || undefined,
      bound_tools: normalizedBoundTools,
      bound_knowledge_bases: Array.isArray(agent.bound_knowledge_bases) ? agent.bound_knowledge_bases : []
    });
    
    // 如果有流程图配置，加载节点和边
    if (agent.flow_config) {
      const config = agent.flow_config;
      console.log('发现流程图配置:', config);
      console.log('流程图配置类型:', typeof config);
      console.log('流程图配置内容:', JSON.stringify(config, null, 2));
      
      // 尝试不同的配置格式
      let nodes = null;
      let edges = null;
      
      // 检查是否是直接的配置对象
      if (config.nodes && Array.isArray(config.nodes)) {
        console.log('使用直接的节点配置');
        nodes = config.nodes;
        edges = config.edges;
      }
      // 检查是否在metadata中
      else if (config.metadata && config.metadata.nodes && Array.isArray(config.metadata.nodes)) {
        console.log('使用metadata中的节点配置');
        nodes = config.metadata.nodes;
        edges = config.metadata.edges;
      }
      // 检查是否是字符串格式（需要解析）
      else if (typeof config === 'string') {
        console.log('尝试解析字符串格式的配置');
        try {
          const parsedConfig = JSON.parse(config);
          console.log('解析后的配置:', parsedConfig);
          if (parsedConfig.nodes && Array.isArray(parsedConfig.nodes)) {
            nodes = parsedConfig.nodes;
            edges = parsedConfig.edges;
          }
        } catch (e) {
          console.error('解析流程图配置字符串失败:', e);
        }
      }
      
      // 加载节点
      if (nodes && Array.isArray(nodes)) {
        console.log('加载节点:', nodes);
        const nodesWithDelete = nodes.map((node: any) => ({
          ...node,
          data: {
            ...node.data,
            onDelete: (nodeId: string) => {
              setNodes((nds: Node[]) => nds.filter((node: Node) => node.id !== nodeId));
              setEdges((eds: Edge[]) => eds.filter((edge: Edge) => edge.source !== nodeId && edge.target !== nodeId));
              message.success('节点已删除');
            }
          }
        }));
        setNodes(nodesWithDelete);
        console.log('节点设置完成:', nodesWithDelete);
      } else {
        console.log('没有找到有效的节点配置');
        console.log('nodes变量:', nodes);
      }
      
      // 加载边
      if (edges && Array.isArray(edges)) {
        console.log('加载边:', edges);
        setEdges(edges);
        console.log('边设置完成');
      } else {
        console.log('没有找到有效的边配置');
        console.log('edges变量:', edges);
      }
    } else {
      console.log('该智能体没有流程图配置');
    }

    // 记录当前正在编辑的智能体ID
    if (agent && typeof agent.id !== 'undefined') {
      setCurrentAgentId(agent.id);
      console.log('设置当前智能体ID:', agent.id);
      message.success(`已加载智能体: ${agent.display_name || agent.name}`);
    }
  };

  // =========== 设置抽屉相关逻辑（除提示词外） ===========
  const fetchLlmConfigs = async () => {
    const res = await axios.get(API_PATHS.LLM_CONFIG);
    return res.data || [];
  };
  const fetchKnowledgeBases = async () => {
    const res = await axios.get(API_PATHS.KNOWLEDGE_BASE);
    return res.data || [];
  };
  const fetchMcpServers = async () => {
    const res = await axios.get(API_PATHS.MCP_SERVERS);
    return res.data || [];
  };

  const openSettings = async () => {
    try {
      setSettingsVisible(true);
      setSettingsLoading(true);
      const [llms, kbs, servers] = await Promise.all([
        fetchLlmConfigs(),
        fetchKnowledgeBases(),
        fetchMcpServers(),
      ]);
      setLlmConfigs(llms);
      setKnowledgeBases(kbs);
      // 基于服务器及其内嵌工具生成树形数据（与通用智能体一致）
      const treeData: any[] = (servers || []).map((srv: any) => ({
        title: srv.display_name || srv.name,
        key: `server_${srv.id}`,
        value: `server_${srv.id}`,
        children: (srv.tools || []).map((tool: any) => ({
          title: tool.display_name || tool.name,
          key: `${srv.name}_${tool.name}`,
          value: `${srv.name}_${tool.name}`,
          isLeaf: true,
        }))
      }));
      setToolTreeData(treeData);

      // 编辑模式下进一步获取最新的智能体配置
      if (currentAgentId) {
        try {
          const detail = await axios.get(API_PATHS.AGENT_BY_ID(currentAgentId));
          const ag = detail.data || {};
          console.log('从数据库获取的智能体配置:', ag);
          
          const normalizedBoundTools = Array.isArray(ag.bound_tools)
            ? ag.bound_tools
                .map((t: any) => typeof t === 'string' ? t : (t && t.server && t.tool ? `${t.server}_${t.tool}` : null))
                .filter((v: any) => !!v)
            : [];
          
          const formValues = {
            llm_config_id: ag.llm_config_id || undefined,
            bound_tools: normalizedBoundTools,
            bound_knowledge_bases: Array.isArray(ag.bound_knowledge_bases) ? ag.bound_knowledge_bases : []
          };
          
          console.log('设置表单值:', formValues);
          settingsForm.setFieldsValue(formValues);
        } catch (e) {
          console.error('获取智能体配置失败:', e);
        }
      } else {
        // 新建模式下，设置默认值
        settingsForm.setFieldsValue({
          llm_config_id: undefined,
          bound_tools: [],
          bound_knowledge_bases: []
        });
      }
    } catch (e) {
      console.error(e);
      message.error('加载设置失败');
    } finally {
      setSettingsLoading(false);
    }
  };

  const closeSettings = () => setSettingsVisible(false);

  // 保存智能体时一并带上设置（除提示词外）
  // 右侧按钮：保存/更新 智能体（flow_driven）
  const saveAgent = async () => {
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
          data: { ...node.data, isStartNode: node.data.isStartNode || false }
        })),
        edges: edges.map(edge => ({ id: edge.id, source: edge.source, target: edge.target, type: edge.type })),
        metadata: { name: flowName, description: flowDescription, version: '1.0.0' }
      };

      // 从设置表单获取配置
      const settings = await settingsForm.validateFields();
      console.log('获取到的设置数据:', settings);
      
      const payloadBase: any = {
        display_name: flowName,
        description: flowDescription,
        agent_type: 'flow_driven',
        flow_config: flowConfig,
      };
      
      // 添加设置配置到提交数据
      if (settings) {
        if (typeof settings.llm_config_id !== 'undefined') {
          payloadBase.llm_config_id = settings.llm_config_id;
          console.log('设置 LLM 配置 ID:', settings.llm_config_id);
        }
        if (Array.isArray(settings.bound_tools)) {
          payloadBase.bound_tools = settings.bound_tools;
          console.log('设置绑定工具:', settings.bound_tools);
        }
        if (Array.isArray(settings.bound_knowledge_bases)) {
          payloadBase.bound_knowledge_bases = settings.bound_knowledge_bases;
          console.log('设置绑定知识库:', settings.bound_knowledge_bases);
        }
      }
      
      console.log('最终提交的数据:', payloadBase);

      if (currentAgentId) {
        // 更新现有智能体
        const response = await fetch(API_PATHS.AGENT_BY_ID(currentAgentId), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payloadBase)
        });
        if (response.ok) {
          message.success('智能体已更新');
          // 重新加载智能体信息以确认更新
          try {
            const detail = await axios.get(API_PATHS.AGENT_BY_ID(currentAgentId));
            console.log('更新后的智能体数据:', detail.data);
          } catch (e) {
            console.log('重新加载智能体信息失败:', e);
          }
        } else {
          const error = await response.json();
          message.error(`更新智能体失败: ${error.detail || '未知错误'}`);
        }
      } else {
        // 创建新智能体
        const response = await fetch(API_PATHS.AGENTS, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: (flowName || 'agent') + '_' + Date.now(),
            ...payloadBase
          })
        });
        if (response.ok) {
          const result = await response.json();
          setCurrentAgentId(result.id);
          message.success('智能体已创建');
        } else {
          const error = await response.json();
          message.error(`创建智能体失败: ${error.detail || '未知错误'}`);
        }
      }
    } catch (e) {
      console.error('保存智能体失败:', e);
      message.error('保存智能体失败');
    } finally {
      setLoading(false);
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
      case 'llm': return 'LLM';
      case 'tool': return '工具';
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
      system_prompt: node.data.nodeType === 'llm' ? (node.data.config?.system_prompt || '') : undefined,
      user_prompt: node.data.nodeType === 'llm' ? (node.data.config?.user_prompt || '') : undefined,
      save_as: node.data.nodeType === 'llm' ? (node.data.config?.save_as || 'last_output') : (node.data.nodeType === 'tool' ? (node.data.config?.save_as || 'last_output') : undefined),
      server: node.data.nodeType === 'tool' ? (node.data.config?.server || '') : undefined,
      tool: node.data.nodeType === 'tool' ? (node.data.config?.tool || '') : undefined,
      params: node.data.nodeType === 'tool' ? (typeof node.data.config?.params === 'object' ? JSON.stringify(node.data.config?.params, null, 2) : (node.data.config?.params || '')) : undefined,
      append_to_output: node.data.nodeType === 'tool' ? (node.data.config?.append_to_output !== false) : undefined,
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
      } else if (selectedNode.data.nodeType === 'llm') {
        // LLM 节点配置
        config.system_prompt = values.system_prompt || '';
        config.user_prompt = values.user_prompt || '{{message}}';
        if (values.save_as) config.save_as = values.save_as;
      } else if (selectedNode.data.nodeType === 'tool') {
        // 工具 节点配置
        if (values.server) config.server = values.server;
        if (values.tool) config.tool = values.tool;
        if (typeof values.append_to_output !== 'undefined') config.append_to_output = !!values.append_to_output;
        if (values.save_as) config.save_as = values.save_as;
        if (typeof values.params !== 'undefined') {
          try {
            const parsed = JSON.parse(values.params);
            config.params = parsed;
          } catch (e) {
            config.params = values.params; // 允许简单字符串
          }
        }
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
    const target = nodes.find((n: any) => n.id === nodeId);
    if (target && target.data && target.data.isStartNode) {
      message.error('开始节点不可删除');
      return;
    }
    setNodes((nds: Node[]) => nds.filter((node: Node) => node.id !== nodeId));
    setEdges((eds: Edge[]) => eds.filter((edge: Edge) => edge.source !== nodeId && edge.target !== nodeId));
    message.success('节点已删除');
  };

  // 左侧保存：若已有 flowId 则更新流程；否则创建新流程
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
          data: { ...node.data, isStartNode: node.data.isStartNode || false }
        })),
        edges: edges.map(edge => ({ id: edge.id, source: edge.source, target: edge.target, type: edge.type })),
        metadata: { name: flowName, description: flowDescription, version: '1.0.0' }
      };

      // 左侧保存：若已有 flowId 则更新流程；否则创建新流程
      if (currentFlowId) {
        const response = await fetch(API_PATHS.FLOW_BY_ID(currentFlowId), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            display_name: flowName,
            description: flowDescription,
            flow_config: flowConfig
          })
        });
        if (response.ok) {
          const result = await response.json();
          message.success('流程图已更新');
          console.log('更新结果:', result);
          try { fetchFlows(); } catch (e) { /* noop */ }
        } else {
          const error = await response.json();
          message.error(`更新失败: ${error.detail || '未知错误'}`);
        }
      } else {
        const response = await fetch(API_PATHS.FLOWS, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: flowName || `flow_${Date.now()}`,
            display_name: flowName || '新流程',
            description: flowDescription || '',
            flow_config: flowConfig
          })
        });
        if (response.ok) {
          const result = await response.json();
          setCurrentFlowId(result.id);
          message.success('流程图已保存');
          console.log('保存结果:', result);
          try { fetchFlows(); } catch (e) { /* noop */ }
        } else {
          const error = await response.json();
          message.error(`保存失败: ${error.detail || '未知错误'}`);
        }
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
      const response = await fetch(API_PATHS.FLOW_TEST(currentFlowId), {
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

  const deleteFlow = async (flowId: number) => {
    try {
      const response = await fetch(API_PATHS.FLOW_BY_ID(flowId), {
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
      const response = await fetch(API_PATHS.FLOW_BY_ID(flowId));
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
    // 重新创建开始节点
    setTimeout(() => createStartNode(), 0);
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

      const response = await fetch(API_PATHS.AGENT_CREATE_FROM_FLOW, {
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
          const reloadResponse = await fetch(API_PATHS.AGENT_RELOAD, {
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
            <Title level={3} style={{ margin: 0 }}>
              {currentMode === 'edit' ? '编辑流程图智能体' : '流程图编辑器'}
            </Title>
            <Space style={{ marginTop: 8 }}>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={saveFlow}
                loading={loading}
              >
                保存流程图
              </Button>
              <Button
                icon={<SaveOutlined />}
                onClick={async () => {
                  // 强制走创建流程，而不是更新
                  try {
                    setLoading(true);
                    const flowConfig = {
                      nodes: nodes.map(node => ({
                        id: node.id,
                        type: node.data.nodeType,
                        position: node.position,
                        data: { ...node.data, isStartNode: node.data.isStartNode || false }
                      })),
                      edges: edges.map(edge => ({ id: edge.id, source: edge.source, target: edge.target, type: edge.type })),
                      metadata: { name: flowName || '新流程', description: flowDescription || '', version: '1.0.0' }
                    };
                    const response = await fetch(API_PATHS.FLOWS, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        name: (flowName || 'new_flow') + '_' + Date.now(),
                        display_name: flowName || '新流程',
                        description: flowDescription || '',
                        flow_config: flowConfig
                      }),
                    });
                    if (response.ok) {
                      const result = await response.json();
                      setCurrentFlowId(result.id);
                      setCurrentMode('create');
                      message.success('已另存为新流程图');
                      fetchFlows();
                    } else {
                      const error = await response.json();
                      message.error(`另存失败: ${error.detail || '未知错误'}`);
                    }
                  } catch (e) {
                    console.error(e);
                    message.error('另存失败');
                  } finally {
                    setLoading(false);
                  }
                }}
              >
                另存为新流程图
              </Button>
            </Space>
          </Col>
          <Col>
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
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
                onClick={saveAgent}
                loading={loading}
              >
                {currentAgentId ? '更新智能体' : '保存智能体'}
              </Button>
              </Space>
              <Input.TextArea
                placeholder="流程图描述（可选）"
                value={flowDescription}
                onChange={(e) => setFlowDescription(e.target.value)}
                style={{ width: 400 }}
                rows={2}
                maxLength={200}
                showCount
              />
            </Space>
          </Col>
          <Col>
            <Space>
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
              <Button icon={<ImportOutlined />} onClick={() => setImportModalVisible(true)}>
                导入JSON
              </Button>
              <Button icon={<ExportOutlined />} onClick={exportFlowAsJSON} disabled={nodes.length === 0}>
                导出JSON
              </Button>
              <Button 
                type="primary" 
                icon={<RobotOutlined />} 
                onClick={createAgentFromFlow}
                disabled={!currentFlowId || nodes.length === 0}
              >
                创建智能体
              </Button>
              <Button 
                icon={<SettingOutlined />} 
                onClick={() => {
                  console.log('当前状态:', {
                    flowName,
                    flowDescription,
                    currentFlowId,
                    currentMode,
                    nodes: nodes.length,
                    edges: edges.length
                  });
                }}
              >
                调试
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
              icon={<RobotOutlined />}
              block
              onClick={() => addNode('llm', { x: 100, y: 150 })}
            >
              LLM 节点
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
              icon={<SettingOutlined />}
              block
              onClick={() => addNode('tool', { x: 100, y: 350 })}
            >
              工具节点
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

          {selectedNode?.data.nodeType === 'llm' && (
            <>
              <Form.Item name="system_prompt" label="系统提示词">
                <Input.TextArea rows={3} placeholder="可选：系统提示词，支持 {{message}} 与 {{last_output}} 模板" />
              </Form.Item>
              <Form.Item name="user_prompt" label="用户提示词" rules={[{ required: true, message: '请输入用户提示词' }]}
              >
                <Input.TextArea rows={3} placeholder="必填：用户提示词，默认 {{message}}" />
              </Form.Item>
              <Form.Item name="save_as" label="保存变量名">
                <Input placeholder="默认 last_output" />
              </Form.Item>
            </>
          )}

          {selectedNode?.data.nodeType === 'tool' && (
            <>
              <Form.Item name="server" label="服务名">
                <Input placeholder="例如：ddg（可选，若工具名为 server_tool 可省略）" />
              </Form.Item>
              <Form.Item name="tool" label="工具名" rules={[{ required: true, message: '请输入工具名' }]}
              >
                <Input placeholder="例如：search 或 ddg_search" />
              </Form.Item>
              <Form.Item name="params" label="参数（JSON或字符串）">
                <Input.TextArea rows={3} placeholder='例如：{"query": "{{message}}"}' />
              </Form.Item>
              <Form.Item name="append_to_output" label="附加到输出" valuePropName="checked">
                <Checkbox defaultChecked>将结果附加到 last_output</Checkbox>
              </Form.Item>
              <Form.Item name="save_as" label="保存变量名">
                <Input placeholder="默认 last_output" />
              </Form.Item>
            </>
          )}

          <Form.Item
            name="config"
            label="高级配置"
          >
            <Input.TextArea rows={4} placeholder="请输入节点配置（JSON格式）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 设置抽屉（除提示词外） */}
      <Drawer
        title="智能体设置"
        placement="right"
        width={520}
        open={settingsVisible}
        onClose={closeSettings}
        destroyOnClose
      >
        <Form layout="vertical" form={settingsForm}>
          <Form.Item name="llm_config_id" label="LLM配置" extra="选择智能体使用的LLM配置（可选）">
            <Select placeholder="选择LLM配置（可选）" allowClear loading={settingsLoading}>
              {llmConfigs.map((cfg: any) => (
                <Select.Option key={cfg.id} value={cfg.id}>
                  <Space>
                    {cfg.display_name || cfg.name}
                    {cfg.provider && <Tag color="blue">{cfg.provider}</Tag>}
                    {cfg.model_name && <Tag color="green">{cfg.model_name}</Tag>}
                    {cfg.is_default && <Tag color="orange">默认</Tag>}
                  </Space>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="bound_tools" label="绑定工具" extra="选择智能体可用工具（可选，多选）">
            <TreeSelect
              treeData={toolTreeData}
              placeholder="选择要绑定的工具"
              treeCheckable
              showCheckedStrategy={TreeSelect.SHOW_CHILD}
              allowClear
              style={{ width: '100%' }}
              dropdownStyle={{ maxHeight: 400, overflow: 'auto' }}
              treeDefaultExpandAll
            />
          </Form.Item>

          <Form.Item name="bound_knowledge_bases" label="绑定知识库" extra="选择智能体可查询的知识库（可多选）">
            <Select
              mode="multiple"
              placeholder="选择知识库"
              allowClear
              loading={settingsLoading}
              options={(knowledgeBases || []).map((kb: any) => ({
                label: kb.display_name || kb.name,
                value: kb.id
              }))}
            />
          </Form.Item>

          <Divider />
          <Space>
            <Button onClick={closeSettings}>取消</Button>
            <Button type="primary" loading={settingsSubmitting} onClick={async () => {
              if (!currentAgentId) {
                message.warning('请先保存智能体后再更新设置');
                return;
              }
              try {
                setSettingsSubmitting(true);
                const values = await settingsForm.validateFields();
                const payload: any = {};
                if (typeof values.llm_config_id !== 'undefined') payload.llm_config_id = values.llm_config_id;
                if (Array.isArray(values.bound_tools)) payload.bound_tools = values.bound_tools;
                if (Array.isArray(values.bound_knowledge_bases)) payload.bound_knowledge_bases = values.bound_knowledge_bases;
                const resp = await fetch(API_PATHS.AGENT_BY_ID(currentAgentId), {
                  method: 'PUT',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify(payload)
                });
                if (resp.ok) {
                  message.success('设置已更新');
                  closeSettings();
                } else {
                  const err = await resp.json().catch(() => ({}));
                  message.error(`更新失败: ${err.detail || '未知错误'}`);
                }
              } catch (e) {
                console.error(e);
              } finally {
                setSettingsSubmitting(false);
              }
            }}>确定</Button>
          </Space>
        </Form>
      </Drawer>

      {/* 导入流程 JSON 模态框 */}
      <Modal
        title="导入流程JSON"
        open={importModalVisible}
        onOk={async () => {
          try {
            const parsed = JSON.parse(importJsonText);
            // 允许两种形态：完整 flow_config 或仅 nodes/edges
            const flowConfig = {
              nodes: parsed.nodes || (parsed.flow_config && parsed.flow_config.nodes) || [],
              edges: parsed.edges || (parsed.flow_config && parsed.flow_config.edges) || [],
              metadata: parsed.metadata || parsed.flow_config?.metadata || {}
            } as any;
            if (!Array.isArray(flowConfig.nodes) || !Array.isArray(flowConfig.edges)) {
              message.error('JSON 格式不正确：缺少 nodes/edges');
              return;
            }
            // 应用到编辑器
            if (flowConfig.metadata?.name) setFlowName(flowConfig.metadata.name);
            if (typeof flowConfig.metadata?.description === 'string') setFlowDescription(flowConfig.metadata.description);
            const nodesWithDelete = flowConfig.nodes.map((node: any) => ({
              ...node,
              data: {
                ...node.data,
                onDelete: deleteNode
              }
            }));
            setNodes(nodesWithDelete);
            setEdges(flowConfig.edges);
            setImportModalVisible(false);
            setImportJsonText('');
            message.success('流程JSON已导入');
          } catch (e) {
            console.error(e);
            message.error('解析JSON失败，请检查格式');
          }
        }}
        onCancel={() => setImportModalVisible(false)}
        width={700}
      >
        <Input.TextArea
          rows={12}
          value={importJsonText}
          onChange={(e) => setImportJsonText(e.target.value)}
          placeholder="粘贴 flow_config JSON（包含 nodes/edges/metadata）"
        />
      </Modal>
    </div>
  );
};

export default FlowEditorPage; 