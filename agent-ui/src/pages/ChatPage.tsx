import React, { useState, useRef, useEffect } from 'react';
import { Layout, Input, Button, Avatar, Typography, Space, Card, Empty, Spin, message, Select, Modal } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, SettingOutlined, PictureOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { useChat } from '../hooks/useChat';
import './ChatPage.css';

const { Header, Content, Sider } = Layout;
const { TextArea } = Input;
const { Title, Text } = Typography;

interface Message {
  id: string;
  content: string;
  type: 'user' | 'agent';
  timestamp: Date;
  agentName?: string;
}

interface Session {
  id?: number;
  session_id?: string;
  title: string;
  // 移除强制绑定的智能体，改为可选
  agent?: {
    id: number;
    name: string;
    display_name: string;
    description?: string;
  };
  created_at?: string;
}

const ChatPage: React.FC = () => {
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId?: string }>();
  const [inputValue, setInputValue] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(false);
  // 添加当前选择的智能体状态
  const [selectedAgent, setSelectedAgent] = useState<{
    id: number;
    name: string;
    display_name: string;
    description?: string;
  } | null>(null);
  // 智能体选择器显示状态
  const [agentSelectorVisible, setAgentSelectorVisible] = useState(false);
  // 智能体列表
  const [agents, setAgents] = useState<Array<{
    id: number;
    name: string;
    display_name: string;
    description?: string;
  }>>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sendMessage, isConnected } = useChat();
  // 在开发环境下绕过前端代理，直接连后端，避免SSE被代理缓存/缓冲
  const apiBase = (window.location.port === '3000') ? 'http://localhost:8000' : '';

  // 处理sessionId变化
  useEffect(() => {
    if (sessionId) {
      // 加载指定会话
      loadSession(parseInt(sessionId));
    } else {
      // 创建新会话
      createNewSession();
    }
  }, [sessionId]);

  // 获取智能体列表
  useEffect(() => {
    fetchAgents();
  }, []);

  // 获取智能体列表
  const fetchAgents = async () => {
    try {
      const response = await fetch('/api/agents/');
      if (response.ok) {
        const data = await response.json();
        const agentsList = Array.isArray(data) ? data : [];
        setAgents(agentsList);
        
        // 如果没有选中的智能体，设置第一个作为默认值
        if (agentsList.length > 0 && !selectedAgent) {
          setSelectedAgent(agentsList[0]);
        }
      }
    } catch (error) {
      console.error('获取智能体列表失败:', error);
    }
  };

  // 创建新会话
  const createNewSession = async () => {
    try {
      const response = await fetch(`${apiBase}/api/chat/sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: 'default_user', // 这里应该使用真实的用户ID
          session_name: '新对话'
          // 不再强制绑定智能体
        })
      });
      
      if (response.ok) {
        const sessionData = await response.json();
        const newSession = {
          id: sessionData.session_id,
          session_id: sessionData.session_id,
          title: sessionData.session_name
          // 不再设置默认智能体
        };
        setCurrentSession(newSession);
        setMessages([]);
        
        // 设置默认智能体（使用第一个可用的智能体）
        if (agents.length > 0) {
          setSelectedAgent(agents[0]);
        }
        
        // 更新URL，但不重新加载页面
        navigate(`/chat/${sessionData.session_id}`, { replace: true });
      } else {
        console.error('创建会话失败');
        message.error('创建会话失败');
      }
    } catch (error) {
      console.error('创建会话失败:', error);
      message.error('创建会话失败');
    }
  };

  // 加载会话信息
  const loadSession = async (sessionId: number) => {
    try {
      const response = await fetch(`/api/sessions/${sessionId}`);
      if (response.ok) {
        const session = await response.json();
        setCurrentSession(session);
        // 加载会话的历史消息
        loadSessionMessages(sessionId);
      } else {
        console.error('加载会话失败');
        message.error('加载会话失败');
      }
    } catch (error) {
      console.error('加载会话失败:', error);
      message.error('加载会话失败');
    }
  };

  // 加载会话消息
  const loadSessionMessages = async (sessionId: number) => {
    try {
      const response = await fetch(`/api/sessions/${sessionId}/messages`);
      if (response.ok) {
        const messages = await response.json();
        console.log('加载的消息:', messages); // 调试日志
        const formattedMessages = messages.map((msg: any) => ({
          id: msg.id,
          content: msg.content,
          type: msg.message_type === 'user' ? 'user' : 'agent',
          timestamp: new Date(msg.created_at),
          agentName: msg.agent_name
        }));
        setMessages(formattedMessages);
      } else {
        console.error('加载会话消息失败');
        setMessages([]);
      }
    } catch (error) {
      console.error('加载会话消息失败:', error);
      setMessages([]);
    }
  };

  // 从消息内容提取关键词作为会话标题
  const extractTitleFromMessage = (content: string): string => {
    // 移除特殊字符，保留中文、英文、数字
    const cleanContent = content.replace(/[^\u4e00-\u9fa5a-zA-Z0-9\s]/g, '');
    
    // 按空格分割，过滤空字符串
    const words = cleanContent.split(/\s+/).filter(word => word.length > 0);
    
    // 如果内容太短，直接返回
    if (words.length <= 3) {
      return words.join(' ') || '新对话';
    }
    
    // 取前3-5个词作为标题
    const titleWords = words.slice(0, Math.min(5, words.length));
    const title = titleWords.join(' ');
    
    // 如果标题太长，截断
    return title.length > 20 ? title.substring(0, 20) + '...' : title || '新对话';
  };



  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!inputValue.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      content: inputValue,
      type: 'user',
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');

    try {
      // 确保有当前会话
      if (!currentSession?.session_id) {
        message.error('请先创建会话');
        return;
      }

      // 如果是第一次发送消息，更新会话标题
      if (messages.length === 0) {
        const title = extractTitleFromMessage(inputValue);
        // 更新会话标题
        try {
          await fetch(`/api/sessions/${currentSession.id}/title?title=${encodeURIComponent(title)}`, {
            method: 'PUT',
          });
        } catch (error) {
          console.error('更新会话标题失败:', error);
        }
      }

      // 发送消息到智能体
      if (currentSession?.session_id && selectedAgent) {
        // 创建智能体消息占位符
        const agentMessageId = (Date.now() + 1).toString();
        const agentMessage: Message = {
          id: agentMessageId,
          content: '正在思考...',
          type: 'agent',
          timestamp: new Date(),
          agentName: selectedAgent.display_name
        };

        setMessages(prev => [...prev, agentMessage]);

        // 使用流式API获取响应
        const agentName = selectedAgent.name;
        try {
          const response = await fetch(`${apiBase}/api/chat/stream`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'text/event-stream',
              'Cache-Control': 'no-cache',
              'Pragma': 'no-cache'
            },
            body: JSON.stringify({
              user_id: 'default_user',
              message: inputValue,
              session_id: currentSession.session_id,
              agent_name: agentName,
              context: {}
            }),
          });

          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }

          const reader = response.body?.getReader();
          if (!reader) {
            throw new Error('无法获取响应流');
          }

          let fullContent = '';
          const decoder = new TextDecoder(undefined, { fatal: false });
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;
            
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            
            for (const line of lines) {
              if (line.trim() && line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.slice(6));
                  
                  if (data.type === 'content' && data.content) {
                    fullContent += data.content;
                    
                    setMessages(prev => prev.map(msg => 
                      msg.id === agentMessageId 
                        ? { ...msg, content: fullContent }
                        : msg
                    ));
                    
                    if (messagesEndRef.current) {
                      messagesEndRef.current.scrollIntoView({ behavior: 'auto' });
                    }
                    
                  } else if (data.type === 'done') {
                    // 流式响应完成
                  } else if (data.error) {
                    setMessages(prev => prev.map(msg => 
                      msg.id === agentMessageId 
                        ? { ...msg, content: `错误: ${data.error}` }
                        : msg
                    ));
                    console.error('流式响应错误:', data.error);
                  }
                } catch (e) {
                  console.error('解析流式数据失败:', e, line);
                }
              }
            }
          }
        } catch (error) {
          console.error('流式请求失败:', error);
          setMessages(prev => prev.map(msg => 
            msg.id === agentMessageId 
              ? { ...msg, content: '抱歉，处理您的消息时出现了问题，请稍后重试。' }
              : msg
          ));
        }
      }
    } catch (error) {
      console.error('发送消息失败:', error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: '抱歉，处理您的消息时出现了问题，请稍后重试。',
        type: 'agent',
        timestamp: new Date(),
        agentName: '系统'
      };
      setMessages(prev => [...prev, errorMessage]);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  
    



  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('zh-CN', { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  // 移除sessionId检查，现在可以直接聊天

  return (
    <div className="chat-layout">
      {/* 主聊天区域 */}
      <div className="chat-main">
        {/* 聊天头部 */}
        <div className="chat-header">
          <div className="header-left">
            <Avatar icon={<RobotOutlined />} />
            <div className="header-info">
              <Text strong>{selectedAgent?.display_name || 'AI助手'}</Text>
              <Text type="secondary" className="status-text">
                {currentSession?.title || '新对话'} • {isConnected ? '在线' : '离线'}
              </Text>
            </div>
          </div>
          <div className="header-right">
            <Button icon={<SettingOutlined />} type="text" />
          </div>
        </div>



        {/* 消息列表 */}
        <div className="messages-container">
          {loading ? (
            <div className="loading-container">
              <Spin size="large" />
            </div>
          ) : (
            <div className="messages-list">
              {messages.length === 0 ? (
                <div className="empty-container">
                  <RobotOutlined className="empty-icon" />
                  <Text type="secondary" className="empty-title">欢迎使用AI助手！</Text>
                  <Text type="secondary" className="empty-subtitle">直接输入消息开始聊天，系统会自动创建会话</Text>
                </div>
              ) : (
                messages.map((message) => (
                  <div
                    key={message.id}
                    className={`message-wrapper ${message.type === 'user' ? 'user' : 'agent'}`}
                  >
                    <div className="message-content">
                      <Avatar 
                        icon={message.type === 'user' 
                          ? <UserOutlined style={{ color: '#fff' }} /> 
                          : <RobotOutlined style={{ color: '#1890ff' }} />}
                        size={36}
                        className="message-avatar"
                        style={message.type === 'user' 
                          ? { backgroundColor: '#1890ff' }
                          : { backgroundColor: '#e6f7ff', border: '1px solid #91d5ff' }}
                      />
                      <div className="message-bubble">
                        <div className="message-header">
                          <Text className="message-name">
                            {message.agentName || (message.type === 'user' ? '我' : 'AI助手')}
                          </Text>
                        </div>
                        <div className="message-text">{message.content}</div>
                        <div className="message-time">
                          {formatTime(message.timestamp)}
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* 智能体选择器弹窗 */}
        <Modal
          title="选择智能体"
          open={agentSelectorVisible}
          onCancel={() => setAgentSelectorVisible(false)}
          footer={null}
          width={600}
          className="agent-selector-modal"
        >
          <div className="agent-grid">
            {agents.map((agent) => (
              <div 
                key={agent.id}
                className={`agent-card ${selectedAgent?.name === agent.name ? 'selected' : ''}`}
                onClick={() => {
                  setSelectedAgent({
                    id: agent.id,
                    name: agent.name,
                    display_name: agent.display_name,
                    description: agent.description
                  });
                  setAgentSelectorVisible(false);
                }}
              >
                <div className="agent-icon">
                  {agent.name === 'general_agent' ? '🤖' :
                   agent.name === 'code_agent' ? '💻' :
                   agent.name === 'writing_agent' ? '✍️' :
                   agent.name === 'finance_agent' ? '💰' : '🤖'}
                </div>
                <div className="agent-title">{agent.display_name}</div>
                <div className="agent-desc">{agent.description || '智能体'}</div>
              </div>
            ))}
          </div>
        </Modal>

        {/* 输入区域 */}
        <div className="input-container">
          <div className="input-wrapper">
            <div className="input-left-buttons">
              <Button 
                type="text" 
                icon={<RobotOutlined />}
                className="input-btn"
                onClick={() => setAgentSelectorVisible(true)}
              >
                @智能体
              </Button>
              <Button 
                type="text" 
                icon={<SettingOutlined />}
                className="input-btn"
              >
                #上下文
              </Button>
              <Button 
                type="text" 
                icon={<PictureOutlined />}
                className="input-btn"
              >
                图片
              </Button>
            </div>
            <TextArea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="输入消息..."
              autoSize={{ minRows: 1, maxRows: 4 }}
              className="message-input"
            />
            <div className="input-right-buttons">
              <Button
                type="text"
                className="auto-btn"
                style={{ marginRight: 8 }}
              >
                Auto
                <span className="auto-dot"></span>
              </Button>
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                disabled={!inputValue.trim()}
                className="send-button"
              >
                发送
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatPage; 