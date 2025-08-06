import React, { useState, useEffect } from 'react';
import {
  Card,
  Button,
  Descriptions,
  Tag,
  Space,
  Typography,
  Divider,
  Alert,
  Modal,
  Form,
  Input,
  message
} from 'antd';
import {
  RobotOutlined,
  EditOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  EyeOutlined,
  SettingOutlined
} from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';

const { Title, Paragraph } = Typography;
const { TextArea } = Input;

interface Agent {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  agent_type: string;
  is_active: boolean;
  flow_config?: any;
  created_at: string;
  updated_at: string;
}

const AgentDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editForm] = Form.useForm();

  useEffect(() => {
    if (id) {
      fetchAgent();
    }
  }, [id]);

  const fetchAgent = async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/agents/${id}`);
      if (response.ok) {
        const data = await response.json();
        setAgent(data);
      } else {
        message.error('获取智能体信息失败');
      }
    } catch (error) {
      console.error('获取智能体失败:', error);
      message.error('获取智能体失败');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = () => {
    if (agent) {
      editForm.setFieldsValue({
        display_name: agent.display_name,
        description: agent.description
      });
      setEditModalVisible(true);
    }
  };

  const handleEditSubmit = async (values: any) => {
    try {
      const response = await fetch(`/api/agents/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(values),
      });

      if (response.ok) {
        message.success('智能体更新成功');
        setEditModalVisible(false);
        fetchAgent();
      } else {
        const error = await response.json();
        message.error(`更新失败: ${error.detail || '未知错误'}`);
      }
    } catch (error) {
      console.error('更新智能体失败:', error);
      message.error('更新智能体失败');
    }
  };

  const handleDelete = async () => {
    try {
      const response = await fetch(`/api/agents/${id}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        message.success('智能体删除成功');
        navigate('/agents');
      } else {
        const error = await response.json();
        message.error(`删除失败: ${error.detail || '未知错误'}`);
      }
    } catch (error) {
      console.error('删除智能体失败:', error);
      message.error('删除智能体失败');
    }
  };

  const handleTest = () => {
    navigate(`/agent-test?agent_id=${id}`);
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

  if (loading) {
    return <div>加载中...</div>;
  }

  if (!agent) {
    return <div>智能体不存在</div>;
  }

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <Title level={2} style={{ margin: 0 }}>
            <RobotOutlined style={{ marginRight: '8px' }} />
            {agent.display_name}
          </Title>
          <Space>
            <Button icon={<PlayCircleOutlined />} onClick={handleTest}>
              测试
            </Button>
            <Button icon={<EditOutlined />} onClick={handleEdit}>
              编辑
            </Button>
            <Button icon={<DeleteOutlined />} danger onClick={handleDelete}>
              删除
            </Button>
          </Space>
        </div>

        <Descriptions bordered column={2}>
          <Descriptions.Item label="智能体名称" span={2}>
            {agent.display_name}
          </Descriptions.Item>
          <Descriptions.Item label="智能体类型">
            <Tag color={getAgentTypeColor(agent.agent_type)}>
              {getAgentTypeLabel(agent.agent_type)}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={agent.is_active ? 'green' : 'red'}>
              {agent.is_active ? '激活' : '停用'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>
            {agent.description || '暂无描述'}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {new Date(agent.created_at).toLocaleString()}
          </Descriptions.Item>
          <Descriptions.Item label="更新时间">
            {new Date(agent.updated_at).toLocaleString()}
          </Descriptions.Item>
        </Descriptions>

        {agent.agent_type === 'flow_driven' && agent.flow_config && (
          <>
            <Divider />
            <Title level={3}>流程图信息</Title>
            <Alert
              message="流程图驱动智能体"
              description="此智能体基于流程图创建，可以执行复杂的业务流程。"
              type="info"
              showIcon
              style={{ marginBottom: '16px' }}
            />
            <Card size="small" title="流程图配置">
              <pre style={{ fontSize: '12px', overflow: 'auto' }}>
                {JSON.stringify(agent.flow_config, null, 2)}
              </pre>
            </Card>
          </>
        )}
      </Card>

      <Modal
        title="编辑智能体"
        open={editModalVisible}
        onOk={() => editForm.submit()}
        onCancel={() => setEditModalVisible(false)}
        width={600}
      >
        <Form form={editForm} layout="vertical" onFinish={handleEditSubmit}>
          <Form.Item
            name="display_name"
            label="显示名称"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="请输入显示名称" />
          </Form.Item>
          <Form.Item
            name="description"
            label="描述"
          >
            <TextArea rows={4} placeholder="请输入描述" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default AgentDetailPage; 