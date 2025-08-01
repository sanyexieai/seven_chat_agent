import React, { useState, useEffect } from 'react';
import {
  Card, Row, Col, Typography, Tag, Button, Modal, Descriptions, Space,
  Form, Input, Select, Switch, message, Popconfirm, Divider, Tabs
} from 'antd';
import {
  RobotOutlined, MessageOutlined, SearchOutlined, FileTextOutlined,
  PlusOutlined, EditOutlined, DeleteOutlined, SettingOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;
const { Option } = Select;
const { TabPane } = Tabs;

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

  useEffect(() => {
    fetchAgents();
    fetchAvailableTools();
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

  const getAgentIcon = (agentType: string) => {
    switch (agentType) {
      case 'chat':
        return <MessageOutlined />;
      case 'search':
        return <SearchOutlined />;
      case 'report':
        return <FileTextOutlined />;
      case 'prompt_driven':
        return <RobotOutlined style={{ color: '#1890ff' }} />;
      case 'tool_driven':
        return <SettingOutlined style={{ color: '#52c41a' }} />;
      case 'flow_driven':
        return <RobotOutlined style={{ color: '#722ed1' }} />;
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
    editForm.setFieldsValue({
      name: agent.name,
      display_name: agent.display_name,
      description: agent.description,
      agent_type: agent.agent_type,
      is_active: agent.is_active,
      system_prompt: agent.system_prompt,
      bound_tools: agent.bound_tools,
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
                  <Select
                    mode="multiple"
                    placeholder="选择要绑定的工具"
                    options={availableTools.map(tool => ({ label: tool, value: tool }))}
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
    <div>
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

      <Row gutter={[16, 16]}>
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