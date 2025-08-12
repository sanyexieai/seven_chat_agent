import React, { useState, useEffect } from 'react';
import {
  Card,
  Button,
  Table,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  message,
  Space,
  Tag,
  Popconfirm,
  Typography,
  Tree,
  TreeSelect,
  Row,
  Col
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  RobotOutlined,
  SearchOutlined,
  FileTextOutlined,
  MessageOutlined,
  ToolOutlined,
  BranchesOutlined,
  SettingOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { TextArea } = Input;
const { Option } = Select;
const { Title, Paragraph, Text } = Typography;

interface LLMConfig {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  provider: string;
  model_name: string;
  api_key?: string;
  api_base?: string;
  config?: any;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface Agent {
  id: number;
  name: string;
  display_name: string;
  description: string;
  agent_type: string;
  is_active: boolean;
  system_prompt?: string;
  bound_tools?: string[];
  flow_config?: any;
  llm_config_id?: number;
  llm_config?: LLMConfig;
  created_at: string;
  updated_at: string;
}

interface AgentFormData {
  name: string;
  display_name: string;
  description: string;
  agent_type: string;
  is_active: boolean;
  system_prompt?: string;
  bound_tools?: string[];
  flow_config?: any;
  llm_config_id?: number;
}

interface MCPTool {
  id: number;
  server_id: number;
  name: string;
  display_name?: string;
  description?: string;
  tool_type: string;
  input_schema?: any;
  output_schema?: any;
  examples?: any[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface MCPServer {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  transport: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  tools?: MCPTool[];
}

const AgentsPage: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);

  const [editModalVisible, setEditModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const [availableTools, setAvailableTools] = useState<string[]>([]);
  const [mcpServers, setMcpServers] = useState<MCPServer[]>([]);
  const [toolTreeData, setToolTreeData] = useState<any[]>([]);
  const [llmConfigs, setLlmConfigs] = useState<LLMConfig[]>([]);

  useEffect(() => {
    fetchAgents();
    fetchAvailableTools();
    fetchMCPServers();
    fetchLLMConfigs();
  }, []);

  const fetchAgents = async () => {
    try {
      const response = await axios.get('/api/agents');
      setAgents(response.data || []);
    } catch (error) {
      console.error('获取智能体失败:', error);
      message.error('获取智能体失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchAvailableTools = async () => {
    try {
      const response = await axios.get('/api/mcp/tools');
      console.log('工具API响应:', response.data);
      // API直接返回工具数组，不需要.tools属性
      const tools = response.data || [];
      setAvailableTools(tools.map((tool: any) => tool.name));
    } catch (error) {
      console.error('获取工具列表失败:', error);
      // 如果API失败，使用默认工具列表
      setAvailableTools(['search', 'news_search', 'fetch_content']);
    }
  };

  const fetchMCPServers = async () => {
    try {
      const response = await axios.get('/api/mcp/servers');
      const servers = response.data || [];
      setMcpServers(servers);
      
      console.log('获取到的MCP服务器数据:', servers);
      
      // 构建工具树数据
      const treeData: any[] = [];
      for (const server of servers) {
        console.log(`处理服务器 ${server.name}:`, server);
        
        if (server.tools && server.tools.length > 0) {
          const serverNode = {
            title: server.display_name || server.name,
            key: `server_${server.id}`,
            value: `server_${server.id}`, // 添加value字段
            children: server.tools.map((tool: MCPTool) => ({
              title: tool.display_name || tool.name,
              key: `${server.name}_${tool.name}`,
              value: `${server.name}_${tool.name}`,
              isLeaf: true,
              tool: tool
            }))
          };
          treeData.push(serverNode);
          console.log(`服务器 ${server.name} 的工具:`, server.tools);
        } else {
          // 即使没有工具，也显示服务器节点
          const serverNode = {
            title: server.display_name || server.name,
            key: `server_${server.id}`,
            value: `server_${server.id}`,
            children: []
          };
          treeData.push(serverNode);
          console.log(`服务器 ${server.name} 没有工具`);
        }
      }
      
      console.log('构建的树数据:', treeData);
      setToolTreeData(treeData);
    } catch (error) {
      console.error('获取MCP服务器失败:', error);
    }
  };

  const fetchLLMConfigs = async () => {
    try {
      const response = await axios.get('/api/llm-config/');
      setLlmConfigs(response.data || []);
    } catch (error) {
      console.error('获取LLM配置失败:', error);
      message.error('获取LLM配置失败');
    }
  };

  // 将树选择的值转换为工具名称数组
  const convertTreeValuesToToolNames = (treeValues: string[]): string[] => {
    const toolNames: string[] = [];
    console.log('转换树选择值:', treeValues);
    
    for (const value of treeValues) {
      if (value.includes('_')) {
        const parts = value.split('_');
        if (parts.length >= 2) {
          const toolName = parts.slice(1).join('_'); // 处理工具名中可能包含下划线的情况
          toolNames.push(toolName);
        }
      }
    }
    
    console.log('转换后的工具名称:', toolNames);
    return toolNames;
  };

  // 将工具名称数组转换为树选择的值
  const convertToolNamesToTreeValues = (toolNames: string[]): string[] => {
    const treeValues: string[] = [];
    console.log('转换工具名称为树值:', toolNames);
    
    for (const server of mcpServers) {
      if (server.tools) {
        for (const tool of server.tools) {
          if (toolNames.includes(tool.name)) {
            treeValues.push(`${server.name}_${tool.name}`);
          }
        }
      }
    }
    
    console.log('转换后的树值:', treeValues);
    return treeValues;
  };

  const getAgentIcon = (agentType: string) => {
    switch (agentType) {
      case 'general':
        return <RobotOutlined />;
      case 'flow_driven':
        return <BranchesOutlined />;
      default:
        return <RobotOutlined />;
    }
  };

  const getAgentTypeLabel = (agentType: string) => {
    switch (agentType) {
      case 'general':
        return '通用智能体';
      case 'flow_driven':
        return '流程图智能体';
      default:
        return agentType;
    }
  };

  const getAgentTypeColor = (agentType: string) => {
    switch (agentType) {
      case 'general':
        return 'blue';
      case 'flow_driven':
        return 'purple';
      default:
        return 'default';
    }
  };

  const handleCreateAgent = async (values: AgentFormData) => {
    try {
      // 如果是通用智能体，需要转换树选择的值
      if (values.agent_type === 'general' && values.bound_tools) {
        values.bound_tools = convertTreeValuesToToolNames(values.bound_tools);
      }
      
      await axios.post('/api/agents', values);
      message.success('智能体创建成功');
      
      setCreateModalVisible(false);
      
      form.resetFields();
      fetchAgents();
    } catch (error) {
      console.error('创建智能体失败:', error);
      message.error('创建智能体失败');
    }
  };

  const handleEditAgent = async (values: AgentFormData) => {
    if (!selectedAgent) return;

    try {
      // 如果是通用智能体，需要转换树选择的值
      if (values.agent_type === 'general' && values.bound_tools) {
        values.bound_tools = convertTreeValuesToToolNames(values.bound_tools);
      }
      
      await axios.put(`/api/agents/${selectedAgent.id}`, values);
      message.success('智能体更新成功');
      setEditModalVisible(false);
      editForm.resetFields();
      fetchAgents();
    } catch (error) {
      console.error('更新智能体失败:', error);
      message.error('更新智能体失败');
    }
  };

  const handleDeleteAgent = async (agentId: number) => {
    try {
      await axios.delete(`/api/agents/${agentId}`);
      message.success('智能体删除成功');
      fetchAgents();
    } catch (error) {
      console.error('删除智能体失败:', error);
      message.error('删除智能体失败');
    }
  };

  const handleEditClick = (agent: Agent) => {
    // 如果是流程图智能体，直接跳转到流程图编辑器
    if (agent.agent_type === 'flow_driven') {
      // 将智能体信息编码到URL中，方便流程图编辑器加载
      const agentInfo = encodeURIComponent(JSON.stringify({
        id: agent.id,
        name: agent.name,
        display_name: agent.display_name,
        description: agent.description,
        flow_config: agent.flow_config,
        is_active: agent.is_active,
        llm_config_id: agent.llm_config_id
      }));
      window.location.href = `/flow-editor?mode=edit&agent_info=${agentInfo}`;
      return;
    }
    
    // 通用智能体的编辑逻辑
    setSelectedAgent(agent);
    
    // 如果是通用智能体，需要转换工具名称为树选择的值
    let boundTools = agent.bound_tools;
    if (agent.agent_type === 'general' && agent.bound_tools) {
      boundTools = convertToolNamesToTreeValues(agent.bound_tools);
    }
    
    editForm.setFieldsValue({
      name: agent.name,
      display_name: agent.display_name,
      description: agent.description,
      agent_type: agent.agent_type,
      is_active: agent.is_active,
      system_prompt: agent.system_prompt,
      bound_tools: boundTools,
      flow_config: agent.flow_config,
      llm_config_id: agent.llm_config_id
    });
    
    setEditModalVisible(true);
  };

  const renderGeneralAgentForm = (formInstance: any, isEdit = false) => (
    <Form
      form={formInstance}
      layout="vertical"
      onFinish={isEdit ? handleEditAgent : handleCreateAgent}
      initialValues={{ agent_type: 'general' }}
    >
      <Form.Item
        name="name"
        label="智能体名称"
        rules={[{ required: true, message: '请输入智能体名称' }]}
      >
        <Input placeholder="例如: my_agent" />
      </Form.Item>

      <Form.Item
        name="display_name"
        label="显示名称"
        rules={[{ required: true, message: '请输入显示名称' }]}
      >
        <Input placeholder="例如: 我的智能体" />
      </Form.Item>

      <Form.Item
        name="description"
        label="描述"
        rules={[{ required: true, message: '请输入描述' }]}
      >
        <TextArea rows={3} placeholder="智能体的功能描述" />
      </Form.Item>

      <Form.Item
        name="agent_type"
        label="智能体类型"
        rules={[{ required: true, message: '请选择智能体类型' }]}
      >
        <Select placeholder="选择智能体类型" disabled={isEdit}>
          <Option value="general">通用智能体</Option>
        </Select>
      </Form.Item>

      <Form.Item
        name="is_active"
        label="是否激活"
        valuePropName="checked"
      >
        <Switch />
      </Form.Item>

      <Form.Item
        name="llm_config_id"
        label="LLM配置"
        extra="选择智能体使用的LLM配置，如果不选择则使用全局默认配置"
      >
        <Select placeholder="选择LLM配置（可选）" allowClear>
          {llmConfigs.map(config => (
                          <Option key={config.id} value={config.id}>
                <Space>
                  {config.display_name}
                  <Tag color="blue">{config.provider}</Tag>
                  <Tag color="green">{config.model_name}</Tag>
                  {config.is_default && <Tag color="orange">默认</Tag>}
                </Space>
              </Option>
          ))}
        </Select>
      </Form.Item>

      <Form.Item
        name="system_prompt"
        label="系统提示词"
        rules={[{ required: true, message: '请输入系统提示词' }]}
      >
        <TextArea
          rows={6}
          placeholder="输入系统提示词，定义智能体的行为和能力..."
        />
      </Form.Item>

      <Form.Item
        name="bound_tools"
        label="绑定工具"
        extra="选择智能体可以使用的工具（可选）"
      >
        <TreeSelect
          treeData={toolTreeData}
          placeholder="选择要绑定的工具"
          treeCheckable={true}
          showCheckedStrategy={TreeSelect.SHOW_CHILD}
          allowClear={true}
          style={{ width: '100%' }}
          dropdownStyle={{ maxHeight: 400, overflow: 'auto' }}
          treeDefaultExpandAll={true}
          onChange={(value) => {
            console.log('TreeSelect onChange:', value);
          }}
        />
      </Form.Item>
    </Form>
  );



  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <Title level={2}>智能体管理</Title>
          <Paragraph>
            管理和配置AI智能体，支持通用智能体（可配置提示词、工具、LLM）和流程图智能体（可配置各种节点）。
          </Paragraph>
        </div>
        <Space>
          <Button
            icon={<SettingOutlined />}
            onClick={() => window.location.href = '/llm-config'}
          >
            LLM配置管理
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalVisible(true)}
          >
            创建普通智能体
          </Button>
          <Button
            type="primary"
            icon={<BranchesOutlined />}
            onClick={() => window.location.href = '/flow-editor?mode=create'}
          >
            创建流程图智能体
          </Button>
        </Space>
      </div>

      <Row gutter={[24, 24]} style={{ alignItems: 'stretch' }}>
        {agents.map((agent) => (
          <Col xs={24} sm={12} lg={8} key={agent.id}>
            <Card
              hoverable
              style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
              bodyStyle={{ flex: 1, display: 'flex', flexDirection: 'column' }}
              actions={[
                <Button
                  type="link"
                  icon={<EditOutlined />}
                  onClick={() => handleEditClick(agent)}
                >
                  {agent.agent_type === 'flow_driven' ? '编辑流程图' : '编辑'}
                </Button>,
                <Popconfirm
                  title="确定要删除这个智能体吗？"
                  onConfirm={() => handleDeleteAgent(agent.id)}
                  okText="确定"
                  cancelText="取消"
                >
                  <Button type="link" danger icon={<DeleteOutlined />}>
                    删除
                  </Button>
                </Popconfirm>
              ]}
            >
              <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                <Card.Meta
                  avatar={getAgentIcon(agent.agent_type)}
                  title={
                    <Space>
                      {agent.display_name}
                      <Tag color={getAgentTypeColor(agent.agent_type)}>
                        {getAgentTypeLabel(agent.agent_type)}
                      </Tag>
                      <Tag color={agent.is_active ? 'green' : 'red'}>
                        {agent.is_active ? '活跃' : '非活跃'}
                      </Tag>
                    </Space>
                  }
                  description={
                    <div style={{ minHeight: '40px' }}>
                      {agent.description || '暂无描述'}
                    </div>
                  }
                />
                <div style={{ marginTop: 16, flex: 1, display: 'flex', flexDirection: 'column' }}>
                  <div style={{ flex: 1 }}>
                    <Text type="secondary">名称: {agent.name}</Text>
                    <br />
                    {agent.llm_config && (
                      <>
                        <Text type="secondary">LLM: {agent.llm_config.display_name}</Text>
                        <br />
                        <Text type="secondary">模型: {agent.llm_config.provider}/{agent.llm_config.model_name}</Text>
                        <br />
                      </>
                    )}
                  </div>
                  <div style={{ marginTop: 'auto', paddingTop: 8 }}>
                    <Text type="secondary" style={{ fontSize: '12px' }}>
                      创建时间: {new Date(agent.created_at).toLocaleString()}
                    </Text>
                  </div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 创建智能体模态框 */}
      <Modal
        title="创建智能体"
        open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setCreateModalVisible(false)}>
            取消
          </Button>,
          <Button key="submit" type="primary" onClick={() => form.submit()}>
            创建
          </Button>
        ]}
        width={600}
      >
        {renderGeneralAgentForm(form)}
      </Modal>



      {/* 编辑智能体模态框 */}
      <Modal
        title="编辑智能体"
        open={editModalVisible}
        onCancel={() => setEditModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setEditModalVisible(false)}>
            取消
          </Button>,
          <Button key="submit" type="primary" onClick={() => editForm.submit()}>
            保存
          </Button>
        ]}
        width={600}
      >
        {renderGeneralAgentForm(editForm, true)}
      </Modal>
    </div>
  );
};

export default AgentsPage; 