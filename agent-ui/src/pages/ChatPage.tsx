import React, { useState, useRef, useEffect } from 'react';
import { Layout, Input, Button, Avatar, Typography, Space, Card, Empty, Spin, message, Select, Modal, Tag } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, SettingOutlined, PictureOutlined, BulbOutlined, EyeOutlined, EyeInvisibleOutlined, MenuUnfoldOutlined, MenuFoldOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { useChat } from '../hooks/useChat';
import ThinkTagRenderer from '../components/ThinkTagRenderer';
import { API_PATHS } from '../config/api';
import { getApiUrl, apiConfigManager } from '../utils/apiConfig';
import { isUserMessage, isAgentMessage } from '../config/messageTypes';
import './ChatPage.css';
import WorkspacePanel, { WorkspaceTabItem } from '../components/WorkspacePanel';
import NodeInfoTag from '../components/NodeInfoTag';

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
  metadata?: any;
  toolName?: string;
  rawType?: string; // 后端原始 message_type
  message_id?: string; // 后端消息UUID
  // 智能体消息的节点信息
  nodes?: Array<{
    node_id: string;
    node_type: string;
    node_name: string;
    node_label: string;
    content?: string;
    chunk_count?: number; // 片段数量（从数据库获取）
    chunk_list: Array<{
      chunk_id: string;
      content: string;
      type: string;
    }>;
  }>;
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
    flow_config?: any;
  } | null>(null);
  // 智能体选择器显示状态
  const [agentSelectorVisible, setAgentSelectorVisible] = useState(false);
  // 智能体列表
  const [agents, setAgents] = useState<Array<{
    id: number;
    name: string;
    display_name: string;
    description?: string;
    agent_type?: string;
    flow_config?: any;
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

  // 右侧工作空间：用于展示每次工具执行的结果
  const [workspaceTabs, setWorkspaceTabs] = useState<WorkspaceTabItem[]>([
    { key: 'live_follow', title: '实时跟随', content: '', createdAt: new Date(), closable: false },
    { key: 'browser', title: '浏览器', content: '这里可展示网页预览或抓取结果', createdAt: new Date(), closable: false },
    { key: 'files', title: '文件', content: '这里显示相关文件/下载链接', createdAt: new Date(), closable: false },
    { key: 'todolist', title: '待办', content: '', createdAt: new Date(), closable: false },
  ]);
  const [activeWorkspaceKey, setActiveWorkspaceKey] = useState<string | undefined>('live_follow');
  const [workspaceCollapsed, setWorkspaceCollapsed] = useState<boolean>(false);
  // 标记工作空间是否已被清空，清空后不再从其他消息中提取内容
  const [workspaceCleared, setWorkspaceCleared] = useState<boolean>(false);

  // 从后端获取智能体流程图配置
  const fetchAgentFlowConfig = async (agentName: string) => {
    try {
      // 首先获取智能体信息
      const response = await fetch(getApiUrl('/api/agents'));
      if (!response.ok) {
        throw new Error('获取智能体列表失败');
      }
      
      const agents = await response.json();
      const agent = agents.find((a: any) => a.name === agentName);
      
      if (!agent) {
        console.warn(`未找到智能体: ${agentName}`);
        return null;
      }
      
      // 如果智能体有flow_config，直接使用
      if (agent.flow_config && agent.flow_config.nodes && agent.flow_config.nodes.length > 0) {
        console.log(`从智能体配置中获取流程图: ${agentName}`, agent.flow_config);
        return {
          nodes: agent.flow_config.nodes.map((node: any) => ({
            id: node.id,
            label: node.data?.label || node.name || node.id,
            nodeType: node.type || node.data?.type || 'default',
            status: 'pending' as 'completed' | 'pending' | 'running' | 'failed'
          })),
          edges: agent.flow_config.edges || []
        };
      }
      
      // 如果没有flow_config，返回null（使用默认流程图）
      console.log(`智能体 ${agentName} 没有流程图配置`);
      return null;
      
    } catch (error) {
      console.error('获取智能体流程图配置失败:', error);
      return null;
    }
  };

  // 流程图数据状态
  const [flowData, setFlowData] = useState({
    nodes: [] as Array<{
      id: string;
      label: string;
      nodeType: string;
      status: 'completed' | 'pending' | 'running' | 'failed';
    }>,
    edges: [] as Array<{
      id: string;
      source: string;
      target: string;
    }>,
    executionState: {
      isRunning: false,
      currentNodeId: undefined as string | undefined,
      completedNodes: [] as string[],
      failedNodes: [] as string[]
    }
  });

  // 从智能体配置生成流程图数据
  const generateFlowDataFromAgent = (agent: any) => {
    if (!agent || !agent.flow_config || !agent.flow_config.nodes) {
      return {
        nodes: [],
        edges: [],
        executionState: {
          isRunning: false,
          currentNodeId: undefined,
          completedNodes: [],
          failedNodes: []
        }
      };
    }

    // 转换节点数据
    const nodes = agent.flow_config.nodes.map((node: any) => ({
      id: node.id,
      label: node.data?.label || node.id,
      nodeType: node.type || 'default',
      status: 'pending' as const
    }));

    // 转换边数据
    const edges = (agent.flow_config.edges || []).map((edge: any) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle, // 关键：保留sourceHandle用于路由节点分支
      targetHandle: edge.targetHandle, // 保留targetHandle
      type: edge.type || 'default'
    }));

    return {
      nodes,
      edges,
      executionState: {
        isRunning: false,
        currentNodeId: undefined,
        completedNodes: [],
        failedNodes: []
      }
    };
  };

  // 工具分类辅助
  const isBrowserTool = (toolName: string) => {
    const name = (toolName || '').toLowerCase();
    return ['browser', 'fetch', 'http', 'url', 'web', 'crawl', 'search'].some(k => name.includes(k));
  };
  const isFileTool = (toolName: string) => {
    const name = (toolName || '').toLowerCase();
    return ['file', 'download', 'save', 'export', 'write', 'read', 'pdf', 'doc', 'excel'].some(k => name.includes(k));
  };

  // 更新流程图状态
  const updateFlowExecution = (nodeId: string, status: 'pending' | 'running' | 'completed' | 'failed') => {
    setFlowData(prev => ({
      ...prev,
      nodes: prev.nodes.map(node => 
        node.id === nodeId ? { ...node, status } : node
      ),
      executionState: {
        ...prev.executionState,
        currentNodeId: status === 'running' ? nodeId : undefined,
        completedNodes: status === 'completed' 
          ? [...prev.executionState.completedNodes, nodeId]
          : prev.executionState.completedNodes.filter(id => id !== nodeId),
        failedNodes: status === 'failed'
          ? [...prev.executionState.failedNodes, nodeId]
          : prev.executionState.failedNodes.filter(id => id !== nodeId)
      }
    }));
  };

  // 根据消息内容自动更新流程图状态
  const updateFlowFromMessage = (message: Message) => {
    if (message.type === 'agent') {
      // 智能体开始处理 - 设置流程图为运行状态
      setFlowData(prev => {
        // 如果有开始节点，将其标记为完成
        const startNode = prev.nodes.find((node: any) => node.nodeType === 'start');
        if (startNode) {
          // 延迟更新开始节点状态，避免在setState回调中调用另一个setState
          setTimeout(() => updateFlowExecution(startNode.id, 'completed'), 0);
        }
        
        return {
          ...prev,
          executionState: {
            ...prev.executionState,
            isRunning: true,
            currentNodeId: undefined
          }
        };
      });
    }
  };

  // 智能体完成LLM分析
  const completeLLMAnalysis = () => {
    updateFlowExecution('llm', 'completed');
    setFlowData(prev => ({
      ...prev,
      executionState: {
        ...prev.executionState,
        currentNodeId: undefined,
        completedNodes: [...prev.executionState.completedNodes, 'llm']
      }
    }));
  };

  // 智能体开始工具调用
  const startToolExecution = () => {
    updateFlowExecution('tool', 'running');
    setFlowData(prev => ({
      ...prev,
      executionState: {
        ...prev.executionState,
        currentNodeId: 'tool'
      }
    }));
  };

  // 智能体完成工具调用
  const completeToolExecution = () => {
    updateFlowExecution('tool', 'completed');
    updateFlowExecution('end', 'running');
    setFlowData(prev => ({
      ...prev,
      executionState: {
        ...prev.executionState,
        currentNodeId: 'end',
        completedNodes: [...prev.executionState.completedNodes, 'tool']
      }
    }));
  };

  // 智能体完成整个流程
  const completeFlow = () => {
    updateFlowExecution('end', 'completed');
    setFlowData(prev => ({
      ...prev,
      executionState: {
        ...prev.executionState,
        isRunning: false,
        currentNodeId: undefined,
        completedNodes: [...prev.executionState.completedNodes, 'end']
      }
    }));
  };

  // 当选择智能体时更新流程图
  const updateFlowForAgent = async (agentName: string) => {
    const newFlow = await fetchAgentFlowConfig(agentName);
    if (newFlow) {
      setFlowData({
        ...newFlow,
        executionState: {
          isRunning: false,
          currentNodeId: undefined,
          completedNodes: [],
          failedNodes: []
        }
      });
    } else {
      // 如果没有获取到流程图配置，显示提示信息
      setFlowData({
        nodes: [{
          id: 'no-flow',
          label: `${agentName} 没有流程图配置`,
          nodeType: 'info',
          status: 'pending' as const
        }],
        edges: [],
        executionState: {
          isRunning: false,
          currentNodeId: undefined,
          completedNodes: [],
          failedNodes: []
        }
      });
    }
  };

  // 根据工具执行结果更新流程图
  const updateFlowFromToolExecution = (toolName: string, success: boolean) => {
    if (success) {
      updateFlowExecution('tool', 'completed');
      // 工具执行完成后，进入结束阶段
      setTimeout(() => {
        updateFlowExecution('end', 'running');
        setTimeout(() => {
          updateFlowExecution('end', 'completed');
          setFlowData(prev => ({
            ...prev,
            executionState: {
              ...prev.executionState,
              isRunning: false
            }
          }));
        }, 500);
      }, 500);
    } else {
      updateFlowExecution('tool', 'failed');
    }
  };

  // 前端不再重复保存到后端，避免重复插入
  // 后端已在流式响应结束时保存 workspace_summary

  const appendToolToTabs = (toolName: string, content: string) => {
    // 如果工作空间已被清空，不再添加新的工具执行结果
    if (workspaceCleared) {
      return;
    }
    const name = (toolName || '').toLowerCase();
    setWorkspaceTabs(prev => {
      const next = prev.map(t => {
        if (t.key === 'live_follow') {
          return { ...t, content: (t.content ? t.content + '\n\n' : '') + `[${toolName}]\n` + content };
        }
        if (t.key === 'browser' && isBrowserTool(toolName)) {
          return { ...t, content: (t.content ? t.content + '\n\n' : '') + content };
        }
        if (t.key === 'files' && isFileTool(toolName)) {
          return { ...t, content: (t.content ? t.content + '\n\n' : '') + content };
        }
        if (t.key === 'todolist' && (name.includes('todo') || name === 'todolist')) {
          return { ...t, content: (t.content ? t.content + '\n' : '') + content };
        }
        return t;
      });
      return next;
    });
  };

  // 不再使用本地缓存
  // const getWorkspaceCacheKey = (): string | undefined => {
  //   const sid = (currentSession && (currentSession as any).session_id) || (currentSession && currentSession.id);
  //   if (!sid) return undefined;
  //   return `workspace-tabs-${sid}`;
  // };

  // 不再使用本地缓存
  // const loadWorkspaceFromCache = () => {
  //   try {
  //     const key = getWorkspaceCacheKey();
  //     if (!key) return;
  //     const raw = localStorage.getItem(key);
  //     if (!raw) return;
  //     const cached: Array<{ key: string; title: string; content: string }> = JSON.parse(raw);
  //     setWorkspaceTabs(prev => prev.map(t => {
  //       const c = cached.find(x => x.key === t.key);
  //       // return c ? { ...t, content: c.content } : t;
  //     }));
  //   } catch {}
  // };

  // 不再保存到本地缓存
  // const saveWorkspaceToCache = (tabs: WorkspaceTabItem[]) => {
  //   try {
  //     const key = getWorkspaceCacheKey();
  //     if (!key) return;
  //     localStorage.setItem(key, JSON.stringify(tabs.map(({ key, title, content }) => ({ key, title, content }))));
  //   } catch {}
  // };

  // 不再从本地缓存恢复
  // useEffect(() => {
  //   loadWorkspaceFromCache();
  //   // eslint-disable-next-line react-hooks/exhaustive-deps
  // }, [currentSession?.session_id, currentSession?.id]);

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
      const response = await fetch(getApiUrl(API_PATHS.AGENTS));
      if (response.ok) {
        const data = await response.json();
        const agentsList = Array.isArray(data) ? data : [];
        setAgents(agentsList);
        
        // 如果没有选中的智能体，设置第一个作为默认值
        if (agentsList.length > 0 && !selectedAgent) {
          setSelectedAgent(agentsList[0]);
          // 加载第一个智能体的流程图
          await updateFlowForAgent(agentsList[0].name);
        }
      }
    } catch (error) {
      console.error('获取智能体列表失败:', error);
    }
  };

  // 当选择的智能体变化时，更新流程图
  useEffect(() => {
    if (selectedAgent) {
      updateFlowForAgent(selectedAgent.name);
    }
  }, [selectedAgent]);

  // 处理根路径访问
  const handleRootPathAccess = async () => {
    try {
      // 检查是否有现有会话
      const response = await fetch(getApiUrl(API_PATHS.GET_USER_SESSIONS('default_user')));
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
      const response = await fetch(getApiUrl(API_PATHS.GET_USER_SESSIONS('default_user')));
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
      const response = await fetch(getApiUrl(API_PATHS.SESSION_BY_ID(sessionId)));
      if (response.ok) {
        const session = await response.json();
        setCurrentSession(session);
        
        // 重置工作空间清空状态，新会话可以正常工作
        setWorkspaceCleared(false);
        
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
      // 优先请求服务端的 workspace_summary
      try {
        console.debug('[Workspace] fetching summary:', getApiUrl(API_PATHS.WORKSPACE_SUMMARY(sessionId)));
        const summaryResp = await fetch(getApiUrl(API_PATHS.WORKSPACE_SUMMARY(sessionId)));
        if (summaryResp.ok) {
          const summary = await summaryResp.json();
          const text = summary?.content || '';
          if (text) {
            console.debug('[Workspace] summary loaded, length:', text.length);
            setWorkspaceTabs(prev => {
              const next = prev.map(t => t.key === 'live_follow' ? { ...t, content: text } : t);
              return next;
            });
          }
        } else {
          console.debug('[Workspace] summary not found, status:', summaryResp.status);
        }
      } catch {}

      const response = await fetch(getApiUrl(API_PATHS.SESSION_MESSAGES(sessionId)));
      if (response.ok) {
        const messages = await response.json();
        
        if (Array.isArray(messages) && messages.length > 0) {
          // 按创建时间排序消息（升序：最早的在前）
          const sortedMessages = messages.sort((a: any, b: any) => {
            const timeA = new Date(a.created_at).getTime();
            const timeB = new Date(b.created_at).getTime();
            return timeA - timeB;
          });
          
          // 有消息，格式化显示 - 统一使用一个数组，智能体消息直接包含节点信息
          const formattedMessages: Message[] = sortedMessages.map((msg: any) => {
            const baseMessage = {
              id: msg.id.toString(),
              message_id: msg.message_id,
              timestamp: new Date(msg.created_at),
              agentName: msg.agent_name,
              metadata: msg.metadata,
              toolName: msg.metadata && msg.metadata.tool_name ? msg.metadata.tool_name : undefined,
              rawType: msg.message_type
            };
            
            if (isUserMessage(msg.message_type)) {
              // 用户消息：直接挂content
              return {
                ...baseMessage,
                type: 'user' as const,
                content: msg.content || ''
              };
            } else {
              // 智能体消息：挂nodes数组，content可选
              return {
                ...baseMessage,
                type: 'agent' as const,
                content: msg.content || '',
                nodes: msg.nodes ? msg.nodes.map((node: any) => ({
                  node_id: node.node_id,
                  node_type: node.node_type,
                  node_name: node.node_name,
                  node_label: node.node_label,
                  content: node.content,
                  chunk_count: node.chunk_count || 0,
                  chunk_list: []
                })) : []
              };
            }
          });
          
          setMessages(formattedMessages);
          

          
          // 工作空间内容只从 workspace_summary 接口获取，不再从其他消息中提取
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

    // 创建用户消息（临时ID，时间会在数据库保存后更新）
    const userMessage: Message = {
      id: `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      message_id: `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`, // 设置message_id
      content: inputValue,
      type: 'user',
      timestamp: new Date() // 临时时间，会在数据库保存后更新
    };

    // 先添加到前端状态，立即显示
    setMessages(prev => {
      const updated = [...prev, userMessage];
      return updated;
    });

    // 清空输入框
    setInputValue('');

    try {
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
                const messageResponse = await fetch(getApiUrl(API_PATHS.SESSION_MESSAGES(sessionData.id)), {
                  method: 'POST',
                  headers: {
                    'Content-Type': 'application/json',
                  },
                  body: JSON.stringify({
                    session_id: sessionData.session_id, // 添加必需的session_id字段
                    user_id: 'default_user',
                    message_type: 'user',
                    content: inputValue,
                    agent_name: selectedAgent?.name || 'general_agent',
                    metadata: {}
                  })
                });
                
                        if (messageResponse.ok) {
          console.log('✅ 用户消息保存成功');
          // 重新加载消息列表，确保时间正确
          if (currentSession.id) {
            await loadSessionMessages(currentSession.id);
          }
        } else {
          console.error('❌ 保存用户消息失败');
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


    // 如果是第一次发送消息，更新会话标题
    if (messages.length === 0 && currentSession && !currentSession.isTemp) {
      const title = extractTitleFromMessage(inputValue);
      // 更新会话标题
      try {
        await fetch(getApiUrl(API_PATHS.SESSION_TITLE(currentSession.id,title)), {
          method: 'PUT',
        });
      } catch (error) {
        console.error('更新会话标题失败:', error);
      }
    }

    // 保存用户消息到数据库（如果不是临时会话）
    if (currentSession && !currentSession.isTemp && currentSession.id) {
      try {
        const messageResponse = await fetch(getApiUrl(API_PATHS.SESSION_MESSAGES(currentSession.id)), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            session_id: currentSession.session_id,
            user_id: 'default_user',
            message_type: 'user',
            content: inputValue,
            agent_name: selectedAgent?.name || 'general_agent',
            metadata: {}
          })
        });
        
        if (messageResponse.ok) {
          console.log('✅ 用户消息保存成功');
          // 重新加载消息列表，确保时间正确
          if (currentSession.id) {
            await loadSessionMessages(currentSession.id);
          }
        } else {
          console.error('❌ 保存用户消息失败');
        }
      } catch (error) {
        console.error('❌ 保存用户消息失败:', error);
      }
    }

    // 发送消息到智能体
    if (currentSession?.session_id) {
      // 创建智能体消息占位符 - 使用更唯一的ID
      const agentMessageId = `agent_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      const agentMessage: Message = {
        id: agentMessageId,
        message_id: agentMessageId, // 设置message_id
        content: '正在思考...',
        type: 'agent',
        timestamp: new Date(),
        agentName: selectedAgent?.display_name || 'AI助手',
        nodes: [] // 初始时不创建任何节点，等待流式响应
      };

        setMessages(prev => {
          const updated = [...prev, agentMessage];
          return updated;
        });

        // 更新流程图状态 - 智能体开始处理
        updateFlowFromMessage(agentMessage);

        // 使用流式API获取响应
        const agentName = selectedAgent?.name || 'general_agent';
        const agentDisplayName = selectedAgent?.display_name || 'AI助手';
        
        // 设置流式状态
        setMessages(prev => prev.map(msg => 
          msg.id === agentMessageId 
            ? { ...msg, isStreaming: true }
            : msg
        ));
        
        try {
          const response = await fetch(getApiUrl(API_PATHS.CHAT_STREAM), {
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
              agent_name: agentName,  // 使用name字段，不是display_name
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
                  

                  
                  if (data.type === 'node_start' && data.content) {
                    // 收到节点开始标识，更新当前消息的metadata中的当前节点信息
                    
                    setMessages(prev => {
                      const updated = prev.map(msg => 
                        msg.id === agentMessageId 
                          ? { 
                              ...msg, 
                              metadata: {
                                ...msg.metadata,
                                current_node: {
                                  node_id: data.metadata?.node_id,
                                  node_type: data.metadata?.node_type,
                                  node_name: data.metadata?.node_name,
                                  node_label: data.metadata?.node_label
                                }
                              }
                            }
                          : msg
                      );
                      
                      return updated;
                    });
                    
                    // 更新流程图状态 - 节点开始运行
                    if (data.metadata?.node_id) {
                      updateFlowExecution(data.metadata.node_id, 'running');
                    }
                    
                  } else if (data.type === 'tool_result' && data.content) {
                    // 收到工具结果：在右侧工作空间新增/更新一个标签
                    const toolName = data.tool_name || '工具';
                    const appendText = typeof data.content === 'string' ? data.content : JSON.stringify(data.content);
                    appendToolToTabs(toolName, appendText);
                    setActiveWorkspaceKey('live_follow');

                    // 更新流程图状态 - 工具执行完成
                    updateFlowFromToolExecution(toolName, true);

                    // 兼容：也将工具结果拼到聊天内容里
                    fullContent += `\n\n${typeof data.content === 'string' ? data.content : JSON.stringify(data.content)}`;
                    setMessages(prev => prev.map(msg => 
                      msg.id === agentMessageId 
                        ? { ...msg, content: fullContent }
                        : msg
                    ));

                  } else if (data.type === 'final_response' && data.content) {
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
                    
                    // 更新流程图状态 - 所有节点完成
                    setFlowData(prev => ({
                      ...prev,
                      nodes: prev.nodes.map(node => ({
                        ...node,
                        status: 'completed' as const
                      })),
                      executionState: {
                        ...prev.executionState,
                        isRunning: false,
                        currentNodeId: undefined,
                        completedNodes: prev.nodes.map(node => node.id)
                      }
                    }));
                    
                    // 自动滚动到底部
                    if (messagesEndRef.current) {
                      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
                    }
                    
                  } else if (data.content) {
                    // 直接使用content字段，支持多种数据格式
                    fullContent += data.content;
                    
                    // 检查是否包含节点信息，如果有就记录
                    if (data.metadata?.node_id && data.metadata?.node_name) {
                      
                      // 直接更新messages数组中的节点信息
                      setMessages(prev => {
                        const updated = prev.map(msg => {
                          if (msg.id === agentMessageId) {
                            // 找到目标消息，更新其节点信息
                            const existingNodeIndex = msg.nodes?.findIndex(node => node.node_id === data.metadata.node_id) ?? -1;
                            
                            if (existingNodeIndex !== -1) {
                              // 节点已存在，添加新的片段
                              const updatedNodes = [...(msg.nodes || [])];
                              updatedNodes[existingNodeIndex] = {
                                ...updatedNodes[existingNodeIndex],
                                chunk_count: (updatedNodes[existingNodeIndex].chunk_count || 0) + 1,
                                chunk_list: [
                                  ...(updatedNodes[existingNodeIndex].chunk_list || []),
                                  {
                                    chunk_id: data.chunk_id,
                                    content: data.content,
                                    type: data.type
                                  }
                                ]
                              };
                              return { ...msg, nodes: updatedNodes };
                            } else {
                              // 节点不存在，创建新节点
                              const newNodes = [
                                ...(msg.nodes || []),
                                {
                                  node_id: data.metadata.node_id,
                                  node_type: data.metadata.node_type,
                                  node_name: data.metadata.node_name,
                                  node_label: data.metadata.node_label,
                                  chunk_count: 1,
                                  chunk_list: [{
                                    chunk_id: data.chunk_id,
                                    content: data.content,
                                    type: data.type
                                  }]
                                }
                              ];
                              return { ...msg, nodes: newNodes };
                            }
                          }
                          return msg;
                        });
                        return updated;
                      });
                    }
                    
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
                    
                    // 添加小延迟，确保流式效果可见
                    await new Promise(resolve => setTimeout(resolve, 50));
                    
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
                    
                    // 添加小延迟，确保流式效果可见
                    await new Promise(resolve => setTimeout(resolve, 50));
                    
                  } else if (data.is_end || data.type === 'done' || data.done) {
                    // 流式响应完成，清除流式状态
                    

                    
                    // 更新messages数组，确保流式完成后的消息能正确显示
                    setMessages(prev => {
                      const updated = prev.map(msg => {
                        if (msg.id === agentMessageId) {
                          // 更新节点内容为最终完整内容
                          // 如果已有节点，更新节点内容；如果没有节点，保持空数组
                          const updatedNodes = msg.nodes && msg.nodes.length > 0 
                            ? msg.nodes.map(node => ({
                                ...node,
                                content: fullContent
                              }))
                            : [];
                          
                          return {
                            ...msg,
                            content: fullContent,
                            nodes: updatedNodes
                          };
                        }
                        return msg;
                      });
                      

                      return updated;
                    });
                    
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

                    // 流式响应完成，更新流程图状态
                    if (!fullContent.includes('工具') && !fullContent.includes('调用')) {
                      // 如果没有工具调用，直接完成整个流程
                      updateFlowExecution('llm', 'completed');
                      setTimeout(() => {
                        updateFlowExecution('end', 'running');
                        setTimeout(() => {
                          updateFlowExecution('end', 'completed');
                          setFlowData(prev => ({
                            ...prev,
                            executionState: {
                              ...prev.executionState,
                              isRunning: false
                            }
                          }));
                        }, 500);
                      }, 500);
                                          }
                     
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
    // 统一使用本地时间，避免时区问题
    return date.toLocaleTimeString('zh-CN', { 
      hour: '2-digit', 
      minute: '2-digit',
      timeZone: 'Asia/Shanghai' // 明确指定时区
    });
  };

  // 移除sessionId检查，现在可以直接聊天

  return (
    <div className="chat-layout">
      {/* 主聊天区域 */}
      <div className="chat-main">
        {/* 左侧：聊天区 */}
        <div className="chat-left" style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
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
              {workspaceCollapsed && (
                <Button type="primary" size="small" icon={<MenuUnfoldOutlined />} onClick={() => setWorkspaceCollapsed(false)} style={{ marginRight: 8 }}>
                  展开工作空间
                </Button>
              )}
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
                {/* 统一使用messages数组，按时间排序显示 */}
                {messages.map((msg, index) => {
                  if (msg.type === 'user') {
                    // 渲染用户消息
                    return (
                      <div
                        key={msg.id}
                        className="message-wrapper user"
                      >
                        <div className="message-content">
                          <Avatar 
                            icon={<UserOutlined style={{ color: '#fff' }} />}
                            size={36}
                            className="message-avatar"
                            style={{ backgroundColor: '#1890ff' }}
                          />
                          <div className="message-bubble">
                            <div className="message-header">
                              <Text className="message-name">我</Text>
                            </div>
                            <div className="message-text">
                              {msg.content}
                            </div>
                            <div className="message-time">
                              {formatTime(msg.timestamp)}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  } else {
                    // 渲染智能体消息
                    return (
                      <div key={`message-${msg.message_id}`} className="message-group">
                        <div className="message-content">
                          <Avatar 
                            icon={<RobotOutlined style={{ color: '#1890ff' }} />}
                            size={36}
                            className="message-avatar"
                            style={{ backgroundColor: '#e6f6ff', border: '1px solid #91d5ff' }}
                          />
                          <div className="message-bubble">
                            <div className="message-header">
                              <Text className="message-name">AI助手</Text>
                            </div>
                                                        <div className="message-text">
                              {msg.nodes && msg.nodes.length > 0 ? (
                                msg.nodes.map((node: any, nodeIndex: number) => (
                                  <div key={`node-${node.node_id}`} className="node-group">
                                    {/* 节点标题 */}
                                    <div className="node-header" style={{ 
                                      padding: '8px 16px', 
                                      backgroundColor: '#f5f5f5', 
                                      borderLeft: '4px solid #1890ff',
                                      margin: '16px 0 8px 0',
                                      borderRadius: '4px'
                                    }}>
                                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <NodeInfoTag
                                          nodeType={node.node_type || 'unknown'}
                                          nodeName={node.node_name || '未知节点'}
                                          nodeLabel={node.node_label}
                                          metadata={node}
                                        />
                                        <Text type="secondary" style={{ fontSize: '12px' }}>
                                          片段数量: {node.chunk_count || node.chunk_list?.length || 0}
                                        </Text>
                                      </div>
                                    </div>
                                    
                                    {/* 节点内容 - 支持两种格式 */}
                                    <div className="node-content" style={{ padding: '0 16px 16px 16px' }}>
                                      <div className="combined-content" style={{
                                        padding: '12px',
                                        backgroundColor: '#fafafa',
                                        borderRadius: '4px',
                                        border: '1px solid #e8e8e8'
                                      }}>
                                        {/* 优先使用后台存储的content，前端分片用于流式显示 */}
                                        {node.content ? (
                                          <ThinkTagRenderer
                                            content={node.content}
                                            nodeInfo={{
                                              node_type: node.node_type,
                                              node_name: node.node_name,
                                              node_label: node.node_label
                                            }}
                                          />
                                        ) : node.chunk_list && node.chunk_list.length > 0 ? (
                                          <ThinkTagRenderer
                                            content={node.chunk_list.map((chunk: any) => chunk.content).join('')}
                                            nodeInfo={{
                                              node_type: node.node_type,
                                              node_name: node.node_name,
                                              node_label: node.node_label
                                            }}
                                          />
                                        ) : (
                                          <Text type="secondary">暂无内容</Text>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                ))
                              ) : (
                                // 如果没有节点，显示消息内容
                                <div style={{ padding: '16px' }}>
                                  {msg.content || '正在思考...'}
                                </div>
                              )}
                            </div>
                            <div className="message-time">
                              {formatTime(msg.timestamp)}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  }
                })}
                

                
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
                    const selectedAgentData = {
                      id: agent.id,
                      name: agent.name,
                      display_name: agent.display_name,
                      description: agent.description,
                      flow_config: agent.flow_config
                    };
                    setSelectedAgent(selectedAgentData);
                    
                    // 生成流程图数据
                    let newFlowData;
                    if (agent.flow_config && agent.flow_config.nodes && agent.flow_config.nodes.length > 0) {
                      // 使用智能体的实际流程图配置
                      newFlowData = generateFlowDataFromAgent(agent);

                    } else if (agent.agent_type === 'flow_driven') {
                      // 为流程图智能体生成默认流程图
                      newFlowData = {
                        nodes: [
                          { id: 'start', label: '开始', nodeType: 'start', status: 'pending' },
                          { id: 'llm', label: 'LLM分析', nodeType: 'llm', status: 'pending' },
                          { id: 'router', label: '路由判断', nodeType: 'router', status: 'pending' },
                          { id: 'tool', label: '工具调用', nodeType: 'tool', status: 'pending' },
                          { id: 'end', label: '结束', nodeType: 'end', status: 'pending' }
                        ],
                        edges: [
                          { id: 'edge1', source: 'start', target: 'llm' },
                          { id: 'edge2', source: 'llm', target: 'router' },
                          { id: 'edge3', source: 'router', target: 'tool' },
                          { id: 'edge4', source: 'tool', target: 'end' }
                        ],
                        executionState: {
                          isRunning: false,
                          currentNodeId: undefined,
                          completedNodes: [],
                          failedNodes: []
                        }
                      };
                    } else {
                      // 为其他类型智能体生成简单流程图
                      newFlowData = {
                        nodes: [
                          { id: 'start', label: '开始', nodeType: 'start', status: 'pending' },
                          { id: 'llm', label: 'LLM处理', nodeType: 'llm', status: 'pending' },
                          { id: 'end', label: '结束', nodeType: 'end', status: 'pending' }
                        ],
                        edges: [
                          { id: 'edge1', source: 'start', target: 'llm' },
                          { id: 'edge2', source: 'llm', target: 'end' }
                        ],
                        executionState: {
                          isRunning: false,
                          currentNodeId: undefined,
                          completedNodes: [],
                          failedNodes: []
                        }
                      };
                    }
                    
                    setFlowData(newFlowData);
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

        {/* 右侧：工作空间 */}
        {workspaceCollapsed ? (
          <div className="workspace-collapsed-handle" onClick={() => setWorkspaceCollapsed(false)} title="展开工作空间">
            »
          </div>
        ) : (
          <WorkspacePanel
            tabs={workspaceTabs}
            activeKey={activeWorkspaceKey}
            onChange={(key) => setActiveWorkspaceKey(key)}
            onClose={(key) => {
              setWorkspaceTabs(prev => prev.filter(t => t.key !== key || t.closable === false));
              if (activeWorkspaceKey === key) {
                setActiveWorkspaceKey('live_follow');
              }
            }}
            onClear={async () => {
              setWorkspaceTabs(prev => {
                const next = prev.map(t => t.key === 'live_follow' ? { ...t, content: '' } : t);
                // 不再保存到本地缓存
                // saveWorkspaceToCache(next);
                // 不再重复保存到后端
                // scheduleSaveWorkspaceSummary(next);
                return next;
              });
              setActiveWorkspaceKey('live_follow');
              // 标记工作空间已被清空
              setWorkspaceCleared(true);
              try {
                if (currentSession && currentSession.id) {
                  await fetch(getApiUrl(API_PATHS.WORKSPACE_CLEAR(currentSession.id as any)), { method: 'DELETE' });
                }
              } catch {}
            }}
            onCollapse={() => setWorkspaceCollapsed(true)}
            flowData={flowData}
          />
        )}
      </div>
    </div>
  );
};

export default ChatPage; 