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
      // 设置默认会话
      setCurrentSession({
        title: '新对话',
        agent: {
          id: 1,
          name: 'general_agent',
          display_name: 'AI助手',
          description: '通用智能体'
        }
      });
      setMessages([]);
    }
  }, [sessionId]);

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
          type: msg.type === 'user' ? 'user' : 'agent',
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

      // 保存用户消息到数据库
      if (sessionId) {
        try {
          await fetch(`/api/sessions/${sessionId}/messages`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
                      body: JSON.stringify({
            session_id: sessionId.toString(),
            user_id: 'default',
            message_type: 'user',
            content: inputValue,
          }),
          });
        } catch (error) {
          console.error('保存用户消息失败:', error);
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
            user_id: 'default',
            message: inputValue,
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

  // 测试流式功能
  const testStream = async () => {
    console.log('测试流式按钮被点击了！'); // 添加这行来确认按钮被点击
    
    try {
      // 先测试一个简单的GET请求
      console.log('开始测试流式功能...');
      
      // 测试1: 简单的GET请求
      console.log('测试1: 发送GET请求到 /api/chat/test-stream');
      const response = await fetch(`${apiBase}/api/chat/test-stream`, { headers: { 'Accept': 'text/event-stream', 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' } });
      
      console.log('收到响应:', response);
      console.log('响应状态:', response.status, response.statusText);
      console.log('响应头:', Object.fromEntries(response.headers.entries()));
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // 测试2: 检查响应类型
      const contentType = response.headers.get('content-type');
      console.log('响应类型:', contentType);
      
      if (!contentType || !contentType.includes('text/event-stream')) {
        console.warn('响应类型不是text/event-stream:', contentType);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('无法获取响应流');
      }

      console.log('开始读取流式数据...');
      let fullContent = '';
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log('流式读取完成');
          break;
        }

        const chunk = decoder.decode(value);
        console.log('收到原始数据块:', chunk);
        buffer += chunk;
        
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.trim() && line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              console.log('解析的流式数据:', data);
              
              if (data.type === 'content' && data.content) {
                fullContent += data.content;
                console.log('累积内容:', fullContent);
              } else if (data.type === 'done') {
                console.log('测试流式完成');
              }
            } catch (e) {
              console.error('解析测试流式数据失败:', e, line);
            }
          }
        }
      }
      
      console.log('测试完成，总内容:', fullContent);
      message.success('流式测试完成！');
    } catch (error: any) {
      console.error('测试流式功能失败:', error);
      // 显示错误信息给用户
      message.error(`测试失败: ${error.message || '未知错误'}`);
    }
  };

  // 简单测试函数：实际发起网络请求便于在Network中观察
  const simpleTest = async () => {
    console.log('简单测试按钮被点击了！');
    try {
      const resp = await fetch('/api/chat/test-stream', {
        method: 'GET',
        headers: { 'Accept': 'text/event-stream' },
        cache: 'no-store'
      });
      console.log('简单测试响应状态:', resp.status, resp.statusText);
      console.log('简单测试响应头:', Object.fromEntries(resp.headers.entries()));
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      message.success(`简单测试请求已发送，状态 ${resp.status}`);
    } catch (e: any) {
      console.error('简单测试请求失败:', e);
      message.error(`简单测试失败: ${e?.message || '未知错误'}`);
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
              <Button
                type="default"
                onClick={testStream}
                className="test-button"
              >
                测试流式
              </Button>
              <Button
                type="dashed"
                onClick={simpleTest}
                className="simple-test-button"
              >
                简单测试
              </Button>

            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatPage; 