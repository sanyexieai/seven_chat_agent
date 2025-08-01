import React, { useState, useRef, useEffect } from 'react';
import { Layout, Input, Button, Avatar, Typography, Space, Card, Empty, Spin, message } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, SettingOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
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
  agent: {
    id: number;
    name: string;
    display_name: string;
    description?: string;
  };
  created_at?: string;
}

const ChatPage: React.FC = () => {
  const navigate = useNavigate();
  const [inputValue, setInputValue] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(false);
  const [sessionCreated, setSessionCreated] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sendMessage, isConnected } = useChat();

  // 初始化默认会话
  useEffect(() => {
    // 设置默认会话
    setCurrentSession({
      title: '新对话',
      agent: {
        id: 1,
        name: 'chat_agent',
        display_name: 'AI助手',
        description: '通用聊天智能体'
      }
    });
  }, []);

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

  const createSession = async (title: string) => {
    try {
      const response = await fetch('/api/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: title,
          agent_name: currentSession?.agent.name || 'chat_agent'
        }),
      });

      if (response.ok) {
        const session = await response.json();
        setCurrentSession(prev => prev ? {
          ...prev,
          id: session.id,
          session_id: session.session_id,
          created_at: session.created_at
        } : null);
        setSessionCreated(true);
        return session;
      }
    } catch (error) {
      console.error('创建会话失败:', error);
      message.error('创建会话失败');
    }
    return null;
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
      // 如果是第一次发送消息，创建会话
      let sessionId = currentSession?.session_id;
      if (!sessionCreated) {
        const title = extractTitleFromMessage(inputValue);
        const session = await createSession(title);
        sessionId = session?.session_id;
      }

      // 保存用户消息到数据库
      if (sessionId) {
        await fetch(`/api/sessions/${sessionId}/messages`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            session_id: parseInt(sessionId),
            type: 'user',
            content: inputValue,
          }),
        });
      }

      // 发送消息给智能体
      const response = await sendMessage(inputValue, currentSession?.agent.name || 'chat_agent');
      
      const agentMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: response.message,
        type: 'agent',
        timestamp: new Date(),
        agentName: currentSession?.agent.display_name
      };

      // 保存智能体消息到数据库
      if (sessionId) {
        await fetch(`/api/sessions/${sessionId}/messages`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            session_id: parseInt(sessionId),
            type: 'agent',
            content: response.message,
            agent_name: currentSession?.agent.name,
          }),
        });
      }

      setMessages(prev => [...prev, agentMessage]);
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
              <Text strong>{currentSession?.agent.display_name || 'AI助手'}</Text>
              <Text type="secondary" className="status-text">
                {currentSession?.title || '新对话'} • {isConnected ? '在线' : '离线'}
              </Text>
            </div>
          </div>
          <Button icon={<SettingOutlined />} type="text" />
        </div>

        {/* 消息列表 */}
        <div className="messages-container">
          {loading ? (
            <div style={{ 
              display: 'flex', 
              justifyContent: 'center', 
              alignItems: 'center', 
              height: '200px' 
            }}>
              <Spin size="large" />
            </div>
          ) : (
            <div className="messages-list">
              {messages.length === 0 ? (
                <div style={{ 
                  display: 'flex', 
                  justifyContent: 'center', 
                  alignItems: 'center', 
                  height: '200px',
                  flexDirection: 'column'
                }}>
                  <RobotOutlined style={{ fontSize: 48, color: '#d9d9d9', marginBottom: 16 }} />
                  <Text type="secondary" style={{ marginBottom: 8 }}>欢迎使用AI助手！</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>直接输入消息开始聊天，系统会自动创建会话</Text>
                </div>
              ) : (
                messages.map((message) => (
                  <div
                    key={message.id}
                    className={`message-wrapper ${message.type === 'user' ? 'user' : 'agent'}`}
                  >
                    <div className="message-content">
                      <Avatar 
                        icon={message.type === 'user' ? <UserOutlined /> : <RobotOutlined />}
                        size="small"
                        className="message-avatar"
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

        {/* 输入区域 */}
        <div className="input-container">
          <div className="input-wrapper">
            <TextArea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="输入消息..."
              autoSize={{ minRows: 1, maxRows: 4 }}
              className="message-input"
            />
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
  );
};

export default ChatPage; 