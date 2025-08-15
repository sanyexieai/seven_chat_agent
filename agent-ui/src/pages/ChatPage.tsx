import React, { useState, useRef, useEffect } from 'react';
import { Layout, Input, Button, Avatar, Typography, Space, Card, Empty, Spin, message, Select, Modal } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, SettingOutlined, PictureOutlined, BulbOutlined, EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { useChat } from '../hooks/useChat';
import ThinkTagRenderer from '../components/ThinkTagRenderer';
import { API_PATHS } from '../config/api';
import { getApiUrl, apiConfigManager } from '../utils/apiConfig';
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
  isStreaming?: boolean; // 流式状态指示器
}

interface Session {
  id?: number | string; // 支持临时ID（字符串）
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
  isTemp?: boolean; // 标记是否为临时会话
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
  // 防止重复处理根路径访问的标志
  const [hasHandledRootPath, setHasHandledRootPath] = useState(false);
  // 思考过程显示状态
  const [thinkTagVisible, setThinkTagVisible] = useState(() => {
    try {
      return localStorage.getItem('think-tag-visible') !== 'false';
    } catch {
      return true;
    }
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sendMessage, isConnected } = useChat();
  // 使用统一的API配置
  
  // 使用ref追踪最新的消息状态，解决闭包问题
  const messagesRef = useRef<Message[]>([]);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // 监听思考过程显示状态变化
  useEffect(() => {
    const handleStorageChange = () => {
      try {
        const newVisible = localStorage.getItem('think-tag-visible') !== 'false';
        setThinkTagVisible(newVisible);
      } catch {}
    };

    // 监听 storage 事件（跨标签页同步）
    window.addEventListener('storage', handleStorageChange);
    
    // 初始化时检查一次状态
    handleStorageChange();
    
    return () => {
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  // 处理sessionId变化
  useEffect(() => {
    if (sessionId) {
      if (sessionId.startsWith('temp_')) {
        // 临时会话，不需要加载
      } else if (!isNaN(parseInt(sessionId))) {
        // 加载指定会话
        loadSession(parseInt(sessionId));
      }
    }
  }, [sessionId]);

  // 处理根路径访问（只在组件初始化时执行一次）
  useEffect(() => {
    if (!sessionId && !hasHandledRootPath) {
      setHasHandledRootPath(true);
      handleRootPathAccess();
    }
  }, [hasHandledRootPath]);

  // 初始化API配置并获取智能体列表
  useEffect(() => {
    const initApi = async () => {
      try {
        await apiConfigManager.initialize();
        fetchAgents();
      } catch (error) {
        console.error('API配置初始化失败:', error);
        fetchAgents(); // 即使配置失败也尝试获取智能体
      }
    };
    
    initApi();
  }, []);

  // 获取智能体列表
  const fetchAgents = async () => {
    try {
      const response = await fetch(getApiUrl('/api/agents/'));
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

  // 处理根路径访问
  const handleRootPathAccess = async () => {
    try {
      // 检查是否有现有会话
      const response = await fetch(getApiUrl('/api/sessions?user_id=default_user'));
      // 检查是否有现有会话
      const response = await fetch(getApiUrl('/api/sessions?user_id=default_user'));
      if (response.ok) {
        const sessions = await response.json();
        
        if (Array.isArray(sessions) && sessions.length > 0) {
          // 有现有会话，按创建时间排序，最新的在最上面
          const sortedSessions = sessions.sort((a, b) => {
            const timeA = new Date(a.created_at || 0).getTime();
            const timeB = new Date(b.created_at || 0).getTime();
            return timeB - timeA; // 降序排列，最新的在最上面
          });
          const latestSession = sortedSessions[0];
          setCurrentSession(latestSession);
          
          // 确保有选中的智能体
          if (!selectedAgent && agents.length > 0) {
            setSelectedAgent(agents[0]);
          }
          
          // 加载会话消息
          if (latestSession.id) {
            loadSessionMessages(latestSession.id);
          }
          // 更新URL，不替换，直接跳转
          navigate(`/chat/${latestSession.id}`);
        } else {
          // 没有现有会话，创建临时会话
          const tempSession = {
            id: `temp_${Date.now()}`,
            title: '新对话',
            isTemp: true
          };
          setCurrentSession(tempSession);
          
          // 跳转到临时会话
          navigate(`/chat/${tempSession.id}`);
        }
      } else {
        // API调用失败，创建临时会话
        const tempSession = {
          id: `temp_${Date.now()}`,
          title: '新对话',
          isTemp: true
        };
        setCurrentSession(tempSession);
        
        // 跳转到临时会话
        navigate(`/chat/${tempSession.id}`);
      }
    } catch (error) {
      console.error('处理根路径访问失败:', error);
      // 出错时创建临时会话
      const tempSession = {
        id: `temp_${Date.now()}`,
        title: '新对话',
        isTemp: true
      };
      setCurrentSession(tempSession);
      
      // 跳转到临时会话
      navigate(`/chat/${tempSession.id}`);
    }
  };

  // 检查现有会话（保留用于其他用途）
  const checkExistingSessions = async () => {
    try {
      const response = await fetch(getApiUrl('/api/sessions?user_id=default_user'));
      if (response.ok) {
        const sessions = await response.json();
        if (Array.isArray(sessions) && sessions.length > 0) {
          // 有现有会话，按创建时间排序，最新的在最上面
          const sortedSessions = sessions.sort((a, b) => {
            const timeA = new Date(a.created_at || 0).getTime();
            const timeB = new Date(b.created_at || 0).getTime();
            return timeB - timeA; // 降序排列，最新的在最上面
          });
          const latestSession = sortedSessions[0];
          setCurrentSession(latestSession);
          
          // 确保有选中的智能体
          if (!selectedAgent && agents.length > 0) {
            setSelectedAgent(agents[0]);
          }
          
          // 加载会话消息
          if (latestSession.id) {
            loadSessionMessages(latestSession.id);
          }
          // 更新URL，不替换，直接跳转
          navigate(`/chat/${latestSession.id}`);
        } else {
          // 没有现有会话，创建临时会话
          createTempSession();
        }
      } else {
        // API调用失败，创建临时会话
        console.error('获取会话列表失败，创建临时会话');
        createTempSession();
    }
    } catch (error) {
      console.error('检查现有会话失败，创建临时会话:', error);
      createTempSession();
    }
  };

  // 创建临时会话（不保存到数据库）
  const createTempSession = () => {
    const tempSession = {
      id: `temp_${Date.now()}`, // 临时ID
      session_id: `temp_${Date.now()}`, // 临时session_id
      title: '新对话',
      isTemp: true // 标记为临时会话
    };
    setCurrentSession(tempSession);
    setMessages([]);
    
    // 设置默认智能体（使用第一个可用的智能体）
    if (agents.length > 0) {
      setSelectedAgent(agents[0]);
    } else {
      // 如果智能体列表还没有加载完成，等待加载完成后再设置
      setTimeout(() => {
        if (agents.length > 0 && !selectedAgent) {
          setSelectedAgent(agents[0]);
        }
      }, 100);
    }
    
    // 更新URL，使用临时ID
    navigate(`/chat/${tempSession.id}`);
  };

  // 加载会话信息
  const loadSession = async (sessionId: number | string) => {
    // 验证sessionId是否有效
    if (typeof sessionId === 'string' && sessionId.startsWith('temp_')) {
      // 临时会话，不需要加载
      return;
    }
    
    if (typeof sessionId === 'number' && (isNaN(sessionId) || sessionId <= 0)) {
      console.error('无效的会话ID:', sessionId);
      message.error('无效的会话ID');
      return;
    }
    
    try {
      const response = await fetch(getApiUrl(`/api/sessions/${sessionId}`));
      if (response.ok) {
        const session = await response.json();
        setCurrentSession(session);
        
        // 加载会话消息
        await loadSessionMessages(sessionId);
      }
    } catch (error) {
      console.error('加载会话失败:', error);
    }
  };

  // 加载会话消息
  const loadSessionMessages = async (sessionId: number | string) => {
    // 验证sessionId是否有效
    if (typeof sessionId === 'string' && sessionId.startsWith('temp_')) {
      // 临时会话，不需要加载消息
      return;
    }
    
    if (typeof sessionId === 'number' && (isNaN(sessionId) || sessionId <= 0)) {
      console.error('无效的会话ID:', sessionId);
      return;
    }
    
    try {
      const response = await fetch(getApiUrl(`/api/sessions/${sessionId}/messages`));
      if (response.ok) {
        const messages = await response.json();
        
        if (Array.isArray(messages) && messages.length > 0) {
          // 有消息，格式化显示
          const formattedMessages: Message[] = messages.map((msg: any) => ({
            id: msg.id,
            content: msg.content,
            type: msg.message_type === 'user' ? 'user' : 'agent',
            timestamp: new Date(msg.created_at),
            agentName: msg.agent_name
          }));
          setMessages(formattedMessages);
        } else {
          // 没有消息，显示空消息列表
          setMessages([]);
        }
      } else {
        console.error('加载会话消息失败');
        // 显示空消息列表
        setMessages([]);
      }
    } catch (error) {
      console.error('加载会话消息失败:', error);
      // 显示空消息列表
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

    // 创建用户消息
    const userMessage: Message = {
      id: `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      content: inputValue,
      type: 'user',
      timestamp: new Date()
    };

    setMessages(prev => {
      const updated = [...prev, userMessage];
      return updated;
    });

    // 清空输入框
    setInputValue('');

    try {
      // 检查是否选择了智能体
      if (!selectedAgent) {
        message.error('请先选择智能体');
        return;
      }

      // 如果是临时会话且是第一条消息，先创建真正的会话
      if (currentSession?.isTemp && messages.length === 0) {
          try {
            const response = await fetch(getApiUrl(API_PATHS.CREATE_SESSION), {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                user_id: 'default_user',
                session_name: extractTitleFromMessage(inputValue)
              })
            });

            if (response.ok) {
              const sessionData = await response.json();
              const realSession = {
                id: sessionData.id,
                session_id: sessionData.session_id,
                title: sessionData.session_name,
                isTemp: false
              };
              setCurrentSession(realSession);
              
              // 更新URL为真正的会话ID，使用replace避免重新渲染
              window.history.replaceState(null, '', `/chat/${sessionData.id}`);
              
              // 立即保存用户消息到数据库
              try {
                const messageResponse = await fetch(getApiUrl(`/api/sessions/${sessionData.id}/messages`), {
                  method: 'POST',
                  headers: {
                    'Content-Type': 'application/json',
                  },
                  body: JSON.stringify({
                    session_id: sessionData.session_id, // 添加必需的session_id字段
                    user_id: 'default_user',
                    message_type: 'user',
                    content: inputValue,
                    agent_name: selectedAgent.name,
                    metadata: {}
                  })
                });
                
                if (messageResponse.ok) {
                  // 用户消息保存成功
                } else {
                  console.error('保存用户消息失败');
                }
              } catch (error) {
                console.error('保存用户消息失败:', error);
              }
            } else {
              console.error('创建会话失败');
              message.error('创建会话失败');
              return;
            }
          } catch (error) {
            console.error('创建会话失败:', error);
            message.error('创建会话失败');
            return;
          }
        }

      // 确保有当前会话
      if (!currentSession?.session_id) {
        message.error('请先创建会话');
        return;
      }

    // 如果是第一次发送消息，更新会话标题
    if (messages.length === 0 && currentSession && !currentSession.isTemp) {
      const title = extractTitleFromMessage(inputValue);
      // 更新会话标题
      try {
        await fetch(getApiUrl(`/api/sessions/${currentSession.id}/title?title=${encodeURIComponent(title)}`), {
          method: 'PUT',
        });
      } catch (error) {
        console.error('更新会话标题失败:', error);
      }
    }

    // 发送消息到智能体
    if (currentSession?.session_id) {
      // 创建智能体消息占位符 - 使用更唯一的ID
      const agentMessageId = `agent_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      const agentMessage: Message = {
        id: agentMessageId,
        content: '正在思考...',
        type: 'agent',
        timestamp: new Date(),
        agentName: selectedAgent.display_name
      };

        setMessages(prev => {
          const updated = [...prev, agentMessage];
          return updated;
        });

        // 使用流式API获取响应
        const agentName = selectedAgent.name;
        
        // 设置流式状态
        setMessages(prev => prev.map(msg => 
          msg.id === agentMessageId 
            ? { ...msg, isStreaming: true }
            : msg
        ));
        
        try {
          const response = await fetch(getApiUrl('/api/chat/stream'), {
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
                
                // 处理特殊的SSE结束标记
                if (line === 'data: [DONE]') {
                  break;
                }
                try {
                  const data = JSON.parse(line.slice(6));
                  
                  if (data.type === 'final_response' && data.content) {
                    // 最终响应：直接替换内容，不累加
                    fullContent = data.content; // 直接替换，不累加
                    
                    // 实时更新消息内容
                    setMessages(prev => {
                      const updated = prev.map(msg => 
                        msg.id === agentMessageId 
                          ? { ...msg, content: fullContent }
                          : msg
                      );
                      return updated;
                    });
                    
                    // 自动滚动到底部
                    if (messagesEndRef.current) {
                      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
                    }
                    
                  } else if (data.content) {
                    // 直接使用content字段，支持多种数据格式
                    fullContent += data.content;
                    
                    // 实时更新消息内容，显示流式效果
                    setMessages(prev => {
                      // 验证消息ID是否存在
                      const targetMessage = prev.find(msg => msg.id === agentMessageId);
                      if (!targetMessage) {
                        console.error('警告：找不到目标消息ID:', agentMessageId);
                        return prev; // 如果找不到，不更新
                      }
                      
                      const updated = prev.map(msg => 
                        msg.id === agentMessageId 
                          ? { ...msg, content: fullContent, isStreaming: true }
                          : msg
                      );
                      return updated;
                    });
                    
                    // 自动滚动到底部
                    if (messagesEndRef.current) {
                      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
                    }
                    
                  } else if (data.type === 'content' && data.content) {
                    // 兼容旧格式：type: 'content'
                    fullContent += data.content;
                    
                    // 实时更新消息内容，显示流式效果
                    setMessages(prev => {
                      const updated = prev.map(msg => 
                        msg.id === agentMessageId 
                          ? { ...msg, content: fullContent, isStreaming: true }
                          : msg
                      );
                      return updated;
                    });
                    
                    // 自动滚动到底部
                    if (messagesEndRef.current) {
                      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
                    }
                    
                  } else if (data.message && data.message.content) {
                    // Ollama格式：{message: {content: "..."}}
                    const content = data.message.content;
                    fullContent += content;
                    
                    // 实时更新消息内容，显示流式效果
                    setMessages(prev => {
                      const updated = prev.map(msg => 
                        msg.id === agentMessageId 
                          ? { ...msg, content: fullContent, isStreaming: true }
                          : msg
                      );
                      return updated;
                    });
                    
                    // 自动滚动到底部
                    if (messagesEndRef.current) {
                      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
                    }
                    
                  } else if (data.is_end || data.type === 'done' || data.done) {
                    // 流式响应完成，清除流式状态
                    
                    // 使用函数式更新，确保状态正确
                    setMessages(prev => {
                      // 状态保护：如果prev为空，说明状态异常
                      if (!prev || prev.length === 0) {
                        console.error('警告：消息状态异常，prev为空或长度为0');
                        // 尝试恢复消息状态
                        const recoveredMessage: Message = {
                          id: agentMessageId,
                          content: fullContent,
                          type: 'agent',
                          timestamp: new Date(),
                          agentName: selectedAgent?.display_name || 'AI助手',
                          isStreaming: false
                        };
                        return [recoveredMessage];
                      }
                      
                      const updated = prev.map(msg => 
                        msg.id === agentMessageId 
                          ? { ...msg, isStreaming: false }
                          : msg
                      );
                      return updated;
                    });
                    
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
              {messages.map((message) => (
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
                        : { backgroundColor: '#e6f6ff', border: '1px solid #91d5ff' }}
                    />
                    <div className="message-bubble">
                      <div className="message-header">
                        <Text className="message-name">
                          {message.agentName || (message.type === 'user' ? '我' : 'AI助手')}
                        </Text>
                      </div>
                      <div className="message-text">
                        {message.type === 'agent' ? (
                          <>
                            <ThinkTagRenderer content={message.content} />
                            {message.isStreaming && (
                              <span className="streaming-indicator">▋</span>
                            )}
                          </>
                        ) : (
                          message.content
                        )}
                      </div>
                      <div className="message-time">
                        {formatTime(message.timestamp)}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
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
              <Button 
                type="text" 
                icon={<BulbOutlined />}
                className={`input-btn ${thinkTagVisible ? 'active' : 'inactive'}`}
                onClick={() => {
                  try {
                    const newVisible = !thinkTagVisible;
                    setThinkTagVisible(newVisible);
                    localStorage.setItem('think-tag-visible', newVisible.toString());
                    // 触发页面重新渲染
                    window.dispatchEvent(new Event('storage'));
                  } catch {}
                }}
              >
                思考过程
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