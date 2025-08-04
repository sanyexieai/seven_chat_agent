import React, { useState, useEffect } from 'react';
import { Layout, Menu, List, Avatar, Typography, Button, Modal, Form, Input, Select, Divider, Drawer } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  MessageOutlined,
  RobotOutlined,
  PlusOutlined,
  UserOutlined,
  SettingOutlined,
  ExperimentOutlined,
  BookOutlined,
  SearchOutlined,
  MenuOutlined,
} from '@ant-design/icons';

const { Sider } = Layout;
const { Text } = Typography;

interface Agent {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  agent_type: string;
  is_active: boolean;
}

interface Session {
  id: number;
  session_id: string;
  title: string;
  agent: Agent;
  created_at: string;
}

const Sidebar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSession, setSelectedSession] = useState<number | null>(null);
  const [isCreateSessionModalVisible, setIsCreateSessionModalVisible] = useState(false);
  const [isSettingsDrawerVisible, setIsSettingsDrawerVisible] = useState(false);
  const [createSessionForm] = Form.useForm();

  // 获取智能体列表
  useEffect(() => {
    fetchAgents();
  }, []);

  // 获取用户会话
  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchAgents = async () => {
    try {
      const response = await fetch('/api/agents/');
      const data = await response.json();
      // 确保data是数组
      setAgents(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('获取智能体失败:', error);
      setAgents([]);
    }
  };

  const fetchSessions = async (agentId?: number) => {
    try {
      const url = agentId 
        ? `/api/sessions?user_id=default&agent_id=${agentId}`
        : '/api/sessions?user_id=default';
      const response = await fetch(url);
      const data = await response.json();
      // 确保data是数组
      setSessions(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('获取会话失败:', error);
      setSessions([]);
    }
  };



  const handleSessionSelect = (sessionId: number) => {
    setSelectedSession(sessionId);
    // 这里可以触发消息加载
    navigate(`/chat/${sessionId}`);
  };

  const handleCreateSession = async (values: any) => {
    try {
      const agentId = values.agent_id || (agents.length > 0 ? agents[0].id : null);
      if (!agentId) {
        console.error('没有可用的智能体');
        return;
      }
      
      const response = await fetch('/api/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: 'default',
          agent_id: agentId,
          title: values.title,
        }),
      });
      
      if (response.ok) {
        setIsCreateSessionModalVisible(false);
        createSessionForm.resetFields();
        fetchSessions();
      }
    } catch (error) {
      console.error('创建会话失败:', error);
    }
  };

  const handleSettingsMenuClick = (key: string) => {
    navigate(key);
    setIsSettingsDrawerVisible(false);
  };

  return (
    <>
      <Sider
        width={280}
        style={{
          background: '#001529',
          overflow: 'auto',
        }}
      >
        <div style={{ padding: '16px', textAlign: 'center' }}>
          <h2 style={{ color: 'white', margin: 0 }}>AI Agent</h2>
        </div>

        <Divider style={{ margin: '16px', borderColor: '#303030' }} />

        {/* 会话列表 */}
        <div style={{ padding: '0 16px', marginBottom: '60px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <Text style={{ color: 'white', fontSize: '14px', fontWeight: 'bold' }}>
              会话
            </Text>
            <Button
              type="text"
              icon={<PlusOutlined />}
              size="small"
              style={{ color: 'white' }}
              onClick={() => setIsCreateSessionModalVisible(true)}
            />
          </div>
          <List
            size="small"
            dataSource={sessions}
            renderItem={(session) => (
              <List.Item
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  backgroundColor: selectedSession === session.id ? '#1890ff' : 'transparent',
                  borderRadius: '4px',
                  marginBottom: '4px',
                }}
                onClick={() => handleSessionSelect(session.id)}
              >
                <List.Item.Meta
                  avatar={<Avatar icon={<MessageOutlined />} size="small" />}
                  title={
                    <Text style={{ color: 'white', fontSize: '12px' }}>
                      {session.title}
                    </Text>
                  }
                  description={
                    <Text style={{ color: '#ccc', fontSize: '10px' }}>
                      {new Date(session.created_at).toLocaleDateString()}
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        </div>

        {/* 设置按钮 - 固定在底部 */}
        <div style={{ 
          position: 'absolute', 
          bottom: '16px', 
          left: '16px', 
          right: '16px',
          backgroundColor: '#001529'
        }}>
          <Button
            type="text"
            icon={<SettingOutlined />}
            style={{ 
              color: 'white', 
              width: '100%',
              textAlign: 'left',
              height: '40px',
              border: '1px solid #303030',
              borderRadius: '4px'
            }}
            onClick={() => setIsSettingsDrawerVisible(true)}
          >
            设置
          </Button>
        </div>

        {/* 创建会话模态框 */}
        <Modal
          title="创建新会话"
          open={isCreateSessionModalVisible}
          onCancel={() => setIsCreateSessionModalVisible(false)}
          footer={null}
        >
          <Form
            form={createSessionForm}
            onFinish={handleCreateSession}
            layout="vertical"
          >
            <Form.Item
              name="title"
              label="会话标题"
              rules={[{ required: true, message: '请输入会话标题' }]}
            >
              <Input placeholder="请输入会话标题" />
            </Form.Item>
            <Form.Item
              name="agent_id"
              label="选择智能体"
              rules={[{ required: true, message: '请选择智能体' }]}
            >
              <Select placeholder="请选择智能体">
                {agents.map(agent => (
                  <Select.Option key={agent.id} value={agent.id}>
                    {agent.display_name}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" block>
                创建会话
              </Button>
            </Form.Item>
          </Form>
        </Modal>
      </Sider>

      {/* 设置抽屉 */}
      <Drawer
        title="设置"
        placement="left"
        onClose={() => setIsSettingsDrawerVisible(false)}
        open={isSettingsDrawerVisible}
        width={300}
      >
        <Menu
          mode="inline"
          onClick={({ key }) => handleSettingsMenuClick(key)}
          selectedKeys={[location.pathname]}
        >
          <Menu.Item key="/agents" icon={<SettingOutlined />}>
            智能体管理
          </Menu.Item>
          <Menu.Item key="/agent-test" icon={<ExperimentOutlined />}>
            智能体测试
          </Menu.Item>
          <Menu.Item key="/mcp" icon={<RobotOutlined />}>
            MCP配置
          </Menu.Item>
          <Menu.Item key="/knowledge-base" icon={<BookOutlined />}>
            知识库管理
          </Menu.Item>
          <Menu.Item key="/knowledge-query" icon={<SearchOutlined />}>
            知识库查询
          </Menu.Item>
        </Menu>
      </Drawer>
    </>
  );
};

export default Sidebar; 