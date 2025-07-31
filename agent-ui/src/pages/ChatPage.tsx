import React, { useState, useRef, useEffect } from 'react';
import { Layout, Input, Button, Avatar, Typography, Space, Card } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, SettingOutlined } from '@ant-design/icons';
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

const ChatPage: React.FC = () => {
  const [inputValue, setInputValue] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      content: '你好！我是AI助手，有什么可以帮助你的吗？',
      type: 'agent',
      timestamp: new Date(),
      agentName: 'AI助手'
    }
  ]);
  const [selectedAgent, setSelectedAgent] = useState('chat_agent');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sendMessage, isConnected } = useChat();

  const agents = [
    { id: 'chat_agent', name: 'AI助手', description: '通用聊天助手' },
    { id: 'search_agent', name: '搜索助手', description: '信息搜索专家' },
    { id: 'report_agent', name: '报告助手', description: '数据分析专家' }
  ];

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
      const response = await sendMessage(inputValue, selectedAgent);
      const agentMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: response.message,
        type: 'agent',
        timestamp: new Date(),
        agentName: agents.find(a => a.id === selectedAgent)?.name
      };
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

  return (
    <div className="chat-layout">
      {/* 左侧智能体列表 */}
      <div className="sidebar">
        <div className="sidebar-header">
          <Title level={4} className="sidebar-title">
            <RobotOutlined /> AI智能体
          </Title>
        </div>
        <div className="agent-list">
          {agents.map(agent => (
            <div
              key={agent.id}
              className={`agent-item ${selectedAgent === agent.id ? 'selected' : ''}`}
              onClick={() => setSelectedAgent(agent.id)}
            >
              <Avatar icon={<RobotOutlined />} size="small" />
              <div className="agent-info">
                <Text strong>{agent.name}</Text>
                <Text type="secondary" className="agent-description">
                  {agent.description}
                </Text>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 主聊天区域 */}
      <div className="chat-main">
        {/* 聊天头部 */}
        <div className="chat-header">
          <div className="header-left">
            <Avatar icon={<RobotOutlined />} />
            <div className="header-info">
              <Text strong>{agents.find(a => a.id === selectedAgent)?.name}</Text>
              <Text type="secondary" className="status-text">
                {isConnected ? '在线' : '离线'}
              </Text>
            </div>
          </div>
          <Button icon={<SettingOutlined />} type="text" />
        </div>

        {/* 消息列表 */}
        <div className="messages-container">
          <div className="messages-list">
            {messages.map((message) => (
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
            ))}
            <div ref={messagesEndRef} />
          </div>
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