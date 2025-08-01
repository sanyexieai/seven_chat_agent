import React, { useState, useEffect } from 'react';
import { Layout, Menu, List, Avatar, Typography, Button, Modal, Form, Input, Select, Divider } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  MessageOutlined,
  RobotOutlined,
  PlusOutlined,
  UserOutlined,
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
  const [selectedAgent, setSelectedAgent] = useState<number | null>(null);
  const [selectedSession, setSelectedSession] = useState<number | null>(null);
  const [isCreateSessionModalVisible, setIsCreateSessionModalVisible] = useState(false);
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

  const handleAgentSelect = (agentId: number) => {
    setSelectedAgent(agentId);
    setSelectedSession(null);
  };

  const handleSessionSelect = (sessionId: number) => {
    setSelectedSession(sessionId);
    // 这里可以触发消息加载
    navigate(`/chat/${sessionId}`);
  };

  const handleCreateSession = async (values: any) => {
    try {
      const agentId = selectedAgent || (agents.length > 0 ? agents[0].id : null);
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

  return (
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

      {/* 导航菜单 */}
      <Menu
        mode="inline"
        style={{ background: '#001529', border: 'none' }}
        selectedKeys={[location.pathname]}
        onClick={({ key }) => navigate(key)}
      >
        <Menu.Item key="/" icon={<MessageOutlined />}>
          <Text style={{ color: 'white' }}>聊天</Text>
        </Menu.Item>
        <Menu.Item key="/mcp" icon={<RobotOutlined />}>
          <Text style={{ color: 'white' }}>MCP配置</Text>
        </Menu.Item>
      </Menu>

      <Divider style={{ margin: '16px', borderColor: '#303030' }} />

      {/* 智能体列表 - 只在聊天页面显示 */}
      {(location.pathname === '/' || location.pathname.startsWith('/chat')) && (
        <div style={{ padding: '0 16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <Text style={{ color: 'white', fontSize: '14px', fontWeight: 'bold' }}>
              智能体
            </Text>
          </div>
          <List
            size="small"
            dataSource={agents}
            renderItem={(agent) => (
              <List.Item
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  backgroundColor: selectedAgent === agent.id ? '#1890ff' : 'transparent',
                  borderRadius: '4px',
                  marginBottom: '4px',
                }}
                onClick={() => handleAgentSelect(agent.id)}
              >
                <List.Item.Meta
                  avatar={<Avatar icon={<RobotOutlined />} size="small" />}
                  title={
                    <Text style={{ color: 'white', fontSize: '12px' }}>
                      {agent.display_name}
                    </Text>
                  }
                  description={
                    <Text style={{ color: '#ccc', fontSize: '10px' }}>
                      {agent.description}
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        </div>
      )}

      <Divider style={{ margin: '16px', borderColor: '#303030' }} />

      {/* 会话列表 - 只在聊天页面显示 */}
      {(location.pathname === '/' || location.pathname.startsWith('/chat')) && (
        <div style={{ padding: '0 16px' }}>
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
      )}

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
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              创建会话
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </Sider>
  );
};

export default Sidebar; 