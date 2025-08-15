import React, { useState, useEffect } from 'react';
import { API_PATHS } from '../config/api';
import { 
  Layout, 
  Menu, 
  List, 
  Avatar, 
  Typography, 
  Button, 
  Modal, 
  Form, 
  Input, 
  Select, 
  Divider, 
  Drawer
} from 'antd';
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
  ApiOutlined,
  ToolOutlined,
  BranchesOutlined,
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
  title?: string;
  session_name?: string;  // 添加session_name字段
  // 移除强制绑定的智能体
  agent?: Agent;
  created_at: string;
}

const Sidebar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSession, setSelectedSession] = useState<number | null>(null);
  const [isSettingsDrawerVisible, setIsSettingsDrawerVisible] = useState(false);

  // 获取智能体列表
  useEffect(() => {
    fetchAgents();
  }, []);

  // 获取用户会话
  useEffect(() => {
    fetchSessions();
  }, []);

  // 监听URL变化，更新选中的会话
  useEffect(() => {
    const pathSegments = location.pathname.split('/');
    if (pathSegments.length > 2 && pathSegments[1] === 'chat') {
      const sessionId = parseInt(pathSegments[2]);
      if (!isNaN(sessionId)) {
        setSelectedSession(sessionId);
      }
    }
  }, [location.pathname]);

  const fetchAgents = async () => {
    try {
      const response = await fetch(API_PATHS.AGENTS);
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
              // 使用正确的URL格式：/api/sessions?user_id=default_user
        const url = agentId 
          ? `${API_PATHS.GET_USER_SESSIONS('default_user')}&agent_id=${agentId}`
          : API_PATHS.GET_USER_SESSIONS('default_user');
      const response = await fetch(url);
      const data = await response.json();
      
      console.log('获取会话列表响应:', data);
      
      // 处理新的API响应格式
      if (data.success && Array.isArray(data.sessions)) {
        setSessions(data.sessions);
        // 自动选择第一条会话（最新的）
        if (data.sessions.length > 0) {
          setSelectedSession(data.sessions[0].id);
        }
      } else if (Array.isArray(data)) {
        // 兼容旧格式
        setSessions(data);
        // 自动选择第一条会话（最新的）
        if (data.length > 0) {
          setSelectedSession(data[0].id);
        }
      } else {
        console.warn('会话数据格式不正确:', data);
        setSessions([]);
        setSelectedSession(null);
      }
    } catch (error) {
      console.error('获取会话失败:', error);
      setSessions([]);
    }
  };



  const handleSessionSelect = (sessionId: number) => {
    setSelectedSession(sessionId);
    // 跳转到聊天页面
    navigate(`/chat/${sessionId}`);
  };

  const handleCreateSessionDirect = async () => {
    try {
      // 直接创建新会话，标题为默认值
      const response = await fetch(API_PATHS.CREATE_SESSION, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: 'default_user',
          session_name: '新对话'
        }),
      });
      
      if (response.ok) {
        const sessionData = await response.json();
        fetchSessions();
        // 创建成功后跳转到聊天页面，使用数字ID
        navigate(`/chat/${sessionData.id}`);
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
          overflow: 'hidden',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          zIndex: 1000,
        }}
      >
        <div style={{ 
          height: '100vh', 
          display: 'flex', 
          flexDirection: 'column',
          overflow: 'hidden'
        }}>
          <div style={{ padding: '16px', textAlign: 'center' }}>
            <h2 style={{ color: 'white', margin: 0 }}>AI Agent</h2>
          </div>

          <Divider style={{ margin: '16px', borderColor: '#303030' }} />

                    {/* 会话列表 */}
          <div style={{ 
            padding: '0 16px', 
            flex: 1, 
            overflow: 'auto',
            marginBottom: '60px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <Text style={{ color: 'white', fontSize: '14px', fontWeight: 'bold' }}>
                会话
              </Text>
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
                  onClick={() => handleSessionSelect(session.id || parseInt(session.session_id))}
                >
                  <List.Item.Meta
                    avatar={<Avatar icon={<MessageOutlined />} size="small" />}
                    title={
                      <Text style={{ color: 'white', fontSize: '12px' }}>
                        {session.title || session.session_name || '新对话'}
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%' }}>
              <Button
                type="text"
                icon={<PlusOutlined />}
                style={{ 
                  color: 'white', 
                  width: '100%',
                  textAlign: 'left',
                  height: '40px',
                  border: '1px solid #303030',
                  borderRadius: '4px'
                }}
                onClick={handleCreateSessionDirect}
              >
                新建会话
              </Button>
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
          </div>
        </div>


      </Sider>

      {/* 设置抽屉 */}
      <Drawer
        title="设置"
        placement="right"
        onClose={() => setIsSettingsDrawerVisible(false)}
        open={isSettingsDrawerVisible}
        width={300}
      >
        <Menu
          mode="inline"
          onClick={({ key }) => handleSettingsMenuClick(key)}
          selectedKeys={[location.pathname]}
        >
          <Menu.Item key="/agent-management" icon={<SettingOutlined />}>
            智能体管理
          </Menu.Item>
          <Menu.Item key="/agent-test" icon={<ExperimentOutlined />}>
            智能体测试
          </Menu.Item>
          <Menu.Item key="/mcp" icon={<RobotOutlined />}>
            MCP配置
          </Menu.Item>
          <Menu.Item key="/llm-config" icon={<ApiOutlined />}>
            LLM配置
          </Menu.Item>
          <Menu.Item key="/knowledge-base" icon={<BookOutlined />}>
            知识库管理
          </Menu.Item>
          <Menu.Item key="/knowledge-query" icon={<SearchOutlined />}>
            知识库查询
          </Menu.Item>

          <Menu.Item key="/flow-editor" icon={<BranchesOutlined />}>
            流程图编辑器
          </Menu.Item>
        </Menu>
      </Drawer>
    </>
  );
};

export default Sidebar; 