import React, { useState, useRef, useEffect } from 'react';
import { Layout, Input, Button, Avatar, Typography, Space, Card, Empty, Spin } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, SettingOutlined } from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
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
  id: number;
  session_id: string;
  title: string;
  agent: {
    id: number;
    name: string;
    display_name: string;
    description?: string;
  };
  created_at: string;
}

const ChatPage: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [inputValue, setInputValue] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sendMessage, isConnected } = useChat();

  // 加载会话信息
  useEffect(() => {
    if (sessionId) {
      loadSession();
      loadMessages();
    }
  }, [sessionId]);

  const loadSession = async () => {
    try {
      const response = await fetch(`/api/sessions/${sessionId}`);
      if (response.ok) {
        const session = await response.json();
        setCurrentSession(session);
      }
    } catch (error) {
      console.error('加载会话失败:', error);
    }
  };

  const loadMessages = async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/sessions/${sessionId}/messages`);
      if (response.ok) {
        const data = await response.json();
        const formattedMessages: Message[] = data.map((msg: any) => ({
          id: msg.message_id,
          content: msg.content,
          type: msg.type as 'user' | 'agent',
          timestamp: new Date(msg.created_at),
          agentName: msg.agent_name
        }));
        setMessages(formattedMessages);
      }
    } catch (error) {
      console.error('加载消息失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!inputValue.trim() || !sessionId) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      content: inputValue,
      type: 'user',
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');

    try {
      // 保存用户消息到数据库
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

  if (!sessionId) {
    return (
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '100vh' 
      }}>
        <Empty description="请选择一个会话开始聊天" />
      </div>
    );
  }

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
                {isConnected ? '在线' : '离线'}
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
                  height: '200px' 
                }}>
                  <Empty description="暂无消息，开始聊天吧！" />
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