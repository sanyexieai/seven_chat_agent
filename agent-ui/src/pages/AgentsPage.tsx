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
  BranchesOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { TextArea } = Input;
const { Option } = Select;
const { Title, Paragraph, Text } = Typography;

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

  useEffect(() => {
    fetchAgents();
    fetchAvailableTools();
    fetchMCPServers();
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
      case 'chat':
        return <MessageOutlined />;
      case 'search':
        return <SearchOutlined />;
      case 'report':
        return <FileTextOutlined />;
      case 'prompt_driven':
        return <RobotOutlined />;
      case 'tool_driven':
        return <ToolOutlined />;
      case 'flow_driven':
        return <BranchesOutlined />;
      default:
        return <RobotOutlined />;
    }
  };

  const getAgentTypeLabel = (agentType: string) => {
    switch (agentType) {
      case 'chat':
        return '聊天智能体';
      case 'search':
        return '搜索智能体';
      case 'report':
        return '报告智能体';
      case 'prompt_driven':
        return '提示词驱动';
      case 'tool_driven':
        return '工具驱动';
      case 'flow_driven':
        return '流程图驱动';
      default:
        return agentType;
    }
  };

  const getAgentTypeColor = (agentType: string) => {
    switch (agentType) {
      case 'chat':
        return 'blue';
      case 'search':
        return 'green';
      case 'report':
        return 'orange';
      case 'prompt_driven':
        return 'cyan';
      case 'tool_driven':
        return 'purple';
      case 'flow_driven':
        return 'magenta';
      default:
        return 'default';
    }
  };

  const handleCreateAgent = async (values: AgentFormData) => {
    try {
      // 如果是工具驱动智能体，需要转换树选择的值
      if (values.agent_type === 'tool_driven' && values.bound_tools) {
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
      // 如果是工具驱动智能体，需要转换树选择的值
      if (values.agent_type === 'tool_driven' && values.bound_tools) {
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
    setSelectedAgent(agent);
    
    // 如果是工具驱动智能体，需要转换工具名称为树选择的值
    let boundTools = agent.bound_tools;
    if (agent.agent_type === 'tool_driven' && agent.bound_tools) {
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
      flow_config: agent.flow_config
    });
    setEditModalVisible(true);
  };

  const renderAgentForm = (formInstance: any, isEdit = false) => (
    <Form
      form={formInstance}
      layout="vertical"
      onFinish={isEdit ? handleEditAgent : handleCreateAgent}
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
        <Select placeholder="选择智能体类型">
          <Option value="chat">聊天智能体</Option>
          <Option value="search">搜索智能体</Option>
          <Option value="report">报告智能体</Option>
          <Option value="prompt_driven">提示词驱动</Option>
          <Option value="tool_driven">工具驱动</Option>
          <Option value="flow_driven">流程图驱动</Option>
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
        noStyle
        shouldUpdate={(prevValues, currentValues) => prevValues.agent_type !== currentValues.agent_type}
      >
        {({ getFieldValue }) => {
          const agentType = getFieldValue('agent_type');

          return (
            <>
              {agentType === 'prompt_driven' && (
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
              )}

              {agentType === 'tool_driven' && (
                <Form.Item
                  name="bound_tools"
                  label="绑定工具"
                  rules={[{ required: true, message: '请选择要绑定的工具' }]}
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
              )}

              {agentType === 'flow_driven' && (
                <Form.Item
                  name="flow_config"
                  label="流程图配置"
                >
                  <TextArea
                    rows={6}
                    placeholder="流程图配置（JSON格式）..."
                  />
                </Form.Item>
              )}
            </>
          );
        }}
      </Form.Item>
    </Form>
  );

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <Title level={2}>智能体管理</Title>
          <Paragraph>
            管理和配置各种AI智能体，支持不同类型的智能体创建和配置。
          </Paragraph>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setCreateModalVisible(true)}
        >
          创建智能体
        </Button>
      </div>

      <Row gutter={[24, 24]}>
        {agents.map((agent) => (
          <Col xs={24} sm={12} lg={8} key={agent.id}>
            <Card
              hoverable
              actions={[
                <Button
                  type="link"
                  icon={<EditOutlined />}
                  onClick={() => handleEditClick(agent)}
                >
                  编辑
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
                description={agent.description}
              />
              <div style={{ marginTop: 16 }}>
                <Text type="secondary">名称: {agent.name}</Text>
                <br />
                <Text type="secondary">创建时间: {new Date(agent.created_at).toLocaleString()}</Text>
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
        {renderAgentForm(form)}
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
        {renderAgentForm(editForm, true)}
      </Modal>
    </div>
  );
};

export default AgentsPage; 