import React, { useState, useEffect } from 'react';
import {
  Card,
  Button,
  Table,
  Tag,
  Space,
  Typography,
  Input,
  Select,
  Popconfirm,
  message,
  Badge,
  Modal,
  Form,
  Divider
} from 'antd';
import {
  RobotOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  PlayCircleOutlined,
  SearchOutlined,
  BranchesOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Title } = Typography;
const { Search } = Input;
const { Option } = Select;
const { TextArea } = Input;

interface Agent {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  agent_type: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const AgentListPage: React.FC = () => {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchText, setSearchText] = useState('');
  const [filterType, setFilterType] = useState<string>('all');
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [createForm] = Form.useForm();
  const [selectedAgentType, setSelectedAgentType] = useState<string>('');

  useEffect(() => {
    fetchAgents();
  }, []);

  const fetchAgents = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/agents');
      if (response.ok) {
        const data = await response.json();
        setAgents(data);
      } else {
        message.error('获取智能体列表失败');
      }
    } catch (error) {
      console.error('获取智能体列表失败:', error);
      message.error('获取智能体列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (agentId: number) => {
    try {
      const response = await fetch(`/api/agents/${agentId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        message.success('智能体删除成功');
        fetchAgents();
      } else {
        const error = await response.json();
        message.error(`删除失败: ${error.detail || '未知错误'}`);
      }
    } catch (error) {
      console.error('删除智能体失败:', error);
      message.error('删除智能体失败');
    }
  };

  const handleCreateAgent = async (values: any) => {
    try {
      // 处理工具绑定字段
      if (values.bound_tools && typeof values.bound_tools === 'string') {
        values.bound_tools = values.bound_tools.split(',').map((tool: string) => tool.trim()).filter(Boolean);
      }

      // 生成智能体名称
      const timestamp = Date.now();
      values.name = `${values.agent_type}_agent_${timestamp}`;

      const response = await fetch('/api/agents', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(values),
      });

      if (response.ok) {
        message.success('智能体创建成功');
        setCreateModalVisible(false);
        createForm.resetFields();
        setSelectedAgentType('');
        fetchAgents();
      } else {
        const error = await response.json();
        message.error(`创建失败: ${error.detail || '未知错误'}`);
      }
    } catch (error) {
      console.error('创建智能体失败:', error);
      message.error('创建智能体失败');
    }
  };

  const handleAgentTypeChange = (value: string) => {
    setSelectedAgentType(value);
    // 清空相关字段
    if (value !== 'prompt_driven') {
      createForm.setFieldsValue({ system_prompt: '' });
    }
    if (value !== 'tool_driven') {
      createForm.setFieldsValue({ bound_tools: '' });
    }
  };

  const getAgentTypeLabel = (type: string) => {
    const typeMap: { [key: string]: string } = {
      'chat': '聊天智能体',
      'search': '搜索智能体',
      'report': '报告智能体',
      'prompt_driven': '提示词驱动',
      'tool_driven': '工具驱动',
      'flow_driven': '流程图驱动'
    };
    return typeMap[type] || type;
  };

  const getAgentTypeColor = (type: string) => {
    const colorMap: { [key: string]: string } = {
      'chat': 'blue',
      'search': 'green',
      'report': 'orange',
      'prompt_driven': 'purple',
      'tool_driven': 'cyan',
      'flow_driven': 'magenta'
    };
    return colorMap[type] || 'default';
  };

  const agentTypes = [
    { value: 'chat', label: '聊天智能体', description: '通用对话智能体' },
    { value: 'search', label: '搜索智能体', description: '信息搜索和检索' },
    { value: 'report', label: '报告智能体', description: '生成报告和分析' },
    { value: 'prompt_driven', label: '提示词驱动', description: '基于自定义提示词' },
    { value: 'tool_driven', label: '工具驱动', description: '基于工具调用' },
  ];

  const filteredAgents = agents.filter(agent => {
    const matchesSearch = agent.display_name.toLowerCase().includes(searchText.toLowerCase()) ||
                         agent.description?.toLowerCase().includes(searchText.toLowerCase());
    const matchesType = filterType === 'all' || agent.agent_type === filterType;
    return matchesSearch && matchesType;
  });

  const columns = [
    {
      title: '智能体',
      key: 'agent',
      render: (text: string, record: Agent) => (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <RobotOutlined style={{ fontSize: '20px', marginRight: '8px', color: '#1890ff' }} />
          <div>
            <div style={{ fontWeight: 'bold' }}>{record.display_name}</div>
            <div style={{ fontSize: '12px', color: '#666' }}>{record.name}</div>
          </div>
        </div>
      ),
    },
    {
      title: '类型',
      dataIndex: 'agent_type',
      key: 'agent_type',
      render: (type: string) => (
        <Tag color={getAgentTypeColor(type)}>
          {getAgentTypeLabel(type)}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (isActive: boolean) => (
        <Badge 
          status={isActive ? 'success' : 'error'} 
          text={isActive ? '激活' : '停用'} 
        />
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      render: (description: string) => (
        <div style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {description || '暂无描述'}
        </div>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date: string) => new Date(date).toLocaleDateString(),
    },
    {
      title: '操作',
      key: 'action',
      render: (text: string, record: Agent) => (
        <Space>
          <Button 
            type="link" 
            icon={<EyeOutlined />} 
            onClick={() => navigate(`/agents/${record.id}`)}
          >
            查看
          </Button>
          <Button 
            type="link" 
            icon={<PlayCircleOutlined />} 
            onClick={() => navigate(`/agent-test?agent_id=${record.id}`)}
          >
            测试
          </Button>
          <Popconfirm
            title="确定要删除这个智能体吗？"
            description="删除后无法恢复"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <Title level={2} style={{ margin: 0 }}>
          <RobotOutlined style={{ marginRight: '8px' }} />
          智能体管理
        </Title>
        <Space>
          <Button 
            icon={<PlusOutlined />} 
            onClick={() => setCreateModalVisible(true)}
          >
            创建智能体
          </Button>
          <Button 
            type="primary" 
            icon={<BranchesOutlined />} 
            onClick={() => navigate('/flow-editor')}
          >
            创建流程图智能体
          </Button>
        </Space>
      </div>

      <Card>
        <div style={{ marginBottom: '16px' }}>
          <Space>
            <Search
              placeholder="搜索智能体名称或描述"
              allowClear
              style={{ width: 300 }}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
            />
            <Select
              placeholder="筛选类型"
              style={{ width: 150 }}
              value={filterType}
              onChange={setFilterType}
            >
              <Option value="all">全部类型</Option>
              <Option value="chat">聊天智能体</Option>
              <Option value="search">搜索智能体</Option>
              <Option value="report">报告智能体</Option>
              <Option value="prompt_driven">提示词驱动</Option>
              <Option value="tool_driven">工具驱动</Option>
              <Option value="flow_driven">流程图驱动</Option>
            </Select>
          </Space>
        </div>

        <Table
          columns={columns}
          dataSource={filteredAgents}
          rowKey="id"
          loading={loading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total, range) => `第 ${range[0]}-${range[1]} 条，共 ${total} 条`,
          }}
        />
      </Card>

      {/* 创建智能体模态框 */}
      <Modal
        title="创建智能体"
        open={createModalVisible}
        onOk={() => createForm.submit()}
        onCancel={() => {
          setCreateModalVisible(false);
          createForm.resetFields();
          setSelectedAgentType('');
        }}
        width={600}
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreateAgent}>
          <Form.Item
            name="display_name"
            label="显示名称"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="请输入智能体显示名称" />
          </Form.Item>
          
          <Form.Item
            name="agent_type"
            label="智能体类型"
            rules={[{ required: true, message: '请选择智能体类型' }]}
          >
            <Select placeholder="请选择智能体类型" value={selectedAgentType} onChange={handleAgentTypeChange}>
              {agentTypes.map(type => (
                <Option key={type.value} value={type.value}>
                  <div>
                    <div>{type.label}</div>
                    <div style={{ fontSize: '12px', color: '#666' }}>{type.description}</div>
                  </div>
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="description"
            label="描述"
          >
            <TextArea rows={4} placeholder="请输入智能体描述" />
          </Form.Item>

          {selectedAgentType === 'prompt_driven' && (
            <Form.Item
              name="system_prompt"
              label="系统提示词"
              extra="仅对提示词驱动智能体有效"
            >
              <TextArea rows={4} placeholder="请输入系统提示词" />
            </Form.Item>
          )}

          {selectedAgentType === 'tool_driven' && (
            <Form.Item
              name="bound_tools"
              label="绑定工具"
              extra="仅对工具驱动智能体有效，多个工具用逗号分隔"
            >
              <Input placeholder="例如: web_search,file_search" />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default AgentListPage; 