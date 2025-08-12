import React, { useState, useRef, useEffect } from 'react';
import { Layout, Input, Button, Avatar, Typography, Space, Card, Empty, Spin, message } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, SettingOutlined } from '@ant-design/icons';
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
  const { sessionId } = useParams<{ sessionId?: string }>();
  const [inputValue, setInputValue] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(false);
  const [sessionCreated, setSessionCreated] = useState(false);

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
          session_name: '新对话',
          agent_type: 'general'
        })
      });
      
      if (response.ok) {
        const sessionData = await response.json();
        const newSession = {
          id: sessionData.session_id,
          session_id: sessionData.session_id,
          title: sessionData.session_name,
          agent: {
            id: 1,
            name: 'general_agent',
            display_name: 'AI助手',
            description: '通用智能体'
          }
        };
        setCurrentSession(newSession);
        setMessages([]);
        setSessionCreated(true);
        
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

  const createSession = async (title: string) => {
    try {
      const response = await fetch('/api/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: 'default',
          agent_id: currentSession?.agent?.id || 1,
          title: title,
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
        // 更新URL以反映新的会话ID
        navigate(`/chat/${session.id}`, { replace: true });
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
      let sessionId = currentSession?.id;
      if (!sessionCreated && !sessionId) {
        const title = extractTitleFromMessage(inputValue);
        const session = await createSession(title);
        if (session) {
          sessionId = session.id;
          // 更新当前会话信息
          setCurrentSession(prev => prev ? {
            ...prev,
            id: session.id,
            session_id: session.session_id,
            created_at: session.created_at
          } : null);
        }
      }

      // 发送消息到智能体
      if (sessionId) {
        try {
          const response = await fetch(`${apiBase}/api/chat/stream`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              user_id: 'default_user',
              message: inputValue,
              session_id: sessionId.toString(),
              agent_type: 'general'
            })
          });

          if (response.ok) {
            const reader = response.body?.getReader();
            if (reader) {
              const decoder = new TextDecoder();
              let buffer = '';
              
              while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                
                for (const line of lines) {
                  if (line.startsWith('data: ')) {
                    try {
                      const data = JSON.parse(line.slice(6));
                      
                      if (data.type === 'content') {
                        // 添加或更新助手消息
                        setMessages(prev => {
                          const lastMessage = prev[prev.length - 1];
                          if (lastMessage && lastMessage.type === 'agent') {
                            // 更新现有消息
                            return prev.map((msg, index) => 
                              index === prev.length - 1 
                                ? { ...msg, content: msg.content + data.content }
                                : msg
                            );
                          } else {
                            // 创建新消息
                            const agentMessage: Message = {
                              id: Date.now().toString(),
                              content: data.content,
                              type: 'agent',
                              timestamp: new Date(),
                              agentName: currentSession?.agent?.display_name
                            };
                            return [...prev, agentMessage];
                          }
                        });
                      } else if (data.type === 'tool_result') {
                        // 添加工具执行结果
                        setMessages(prev => {
                          const lastMessage = prev[prev.length - 1];
                          if (lastMessage && lastMessage.type === 'agent') {
                            return prev.map((msg, index) => 
                              index === prev.length - 1 
                                ? { ...msg, content: msg.content + data.content }
                                : msg
                            );
                          }
                          return prev;
                        });
                      } else if (data.type === 'done') {
                        // 消息完成
                        console.log('聊天完成，使用的工具:', data.tools_used);
                      }
                    } catch (e) {
                      console.error('解析SSE数据失败:', e);
                    }
                  }
                }
              }
            }
          } else {
            console.error('发送消息失败');
            message.error('发送消息失败');
          }
        } catch (error) {
          console.error('发送消息失败:', error);
          message.error('发送消息失败');
        }
      }

      // 创建智能体消息占位符
      const agentMessageId = (Date.now() + 1).toString();
      const agentMessage: Message = {
        id: agentMessageId,
        content: '正在思考...',  // 添加初始内容
        type: 'agent',
        timestamp: new Date(),
        agentName: currentSession?.agent?.display_name || 'AI助手'
      };

      console.log('创建智能体消息:', agentMessage);
      setMessages(prev => {
        const newMessages = [...prev, agentMessage];
        console.log('添加消息后的消息列表:', newMessages);
        return newMessages;
      });

      // 使用流式API获取响应
      const agentName = currentSession?.agent?.name || 'general_agent';
      try {
        console.log('开始流式请求...');
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
            session_id: sessionId?.toString(),
            agent_type: agentName,
            context: {}
          }),
        });

        console.log('流式响应状态:', response.status, response.statusText);
        console.log('响应头:', Object.fromEntries(response.headers.entries()));

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
          
          // 处理完整的行
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // 保留最后一个不完整的行
          
          for (const line of lines) {
            if (line.trim() && line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                console.log('收到流式数据:', data); // 调试日志
                
                if (data.type === 'content' && data.content) {
                  fullContent += data.content;
                  console.log('收到内容块:', data.content, '累积内容:', fullContent);
                  
                  // 实时更新消息内容 - 使用函数式更新确保状态正确
                  setMessages(prev => {
                    const newMessages = prev.map(msg => 
                      msg.id === agentMessageId 
                        ? { ...msg, content: fullContent }
                        : msg
                    );
                    console.log('更新后的消息列表:', newMessages);
                    return newMessages;
                  });
                  
                  // 立即滚动到底部，显示最新内容（关闭平滑滚动以减少抖动）
                  if (messagesEndRef.current) {
                    messagesEndRef.current.scrollIntoView({ behavior: 'auto' });
                  }
                  
                  // 去掉提示弹窗，减少抖动
                  // console.info('AI开始回复...');
                  
                  // console.log('实时更新内容完成，当前长度:', fullContent.length);
                  
                } else if (data.type === 'done') {
                  // 流式响应完成
                  // console.log('流式响应完成，使用的工具:', data.tools_used);
                  // 去掉成功弹窗，减少抖动
                  
                } else if (data.error) {
                  // 处理错误
                  setMessages(prev => prev.map(msg => 
                    msg.id === agentMessageId 
                      ? { ...msg, content: `错误: ${data.error}` }
                      : msg
                  ));
                  // 保留错误，但不弹窗
                  console.error('流式响应错误:', data.error);
                }
              } catch (e) {
                console.error('解析流式数据失败:', e, line);
              }
            }
          }
        }

        // 保存完整的智能体消息到数据库
        if (sessionId && fullContent) {
          await fetch(`/api/sessions/${sessionId}/messages`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              session_id: sessionId.toString(),
              user_id: 'default',
              message_type: 'agent',
              content: fullContent,
              agent_name: currentSession?.agent?.name || 'general_agent',
            }),
          });
        }

      } catch (error) {
        console.error('流式请求失败:', error);
        // 如果流式请求失败，回退到普通请求
        try {
          const response = await sendMessage(inputValue, agentName);
          setMessages(prev => prev.map(msg => 
            msg.id === agentMessageId 
              ? { ...msg, content: response.message }
              : msg
          ));
        } catch (fallbackError) {
          console.error('回退请求也失败:', fallbackError);
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
              <Text strong>{currentSession?.agent?.display_name || 'AI助手'}</Text>
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
            <div className="button-group">
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