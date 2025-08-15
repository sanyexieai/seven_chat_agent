// API路径配置 - 统一使用不带尾部斜杠的格式
export const API_PATHS = {
  // 智能体相关
  AGENTS: '/api/agents',
  AGENT_BY_ID: (id: number | string) => `/api/agents/${id}`,
  AGENT_RELOAD: '/api/agents/reload',
  AGENT_CREATE_FROM_FLOW: '/api/agents/create_from_flow',
  
  // 会话相关
  SESSIONS: '/api/sessions',
  SESSION_BY_ID: (id: number | string) => `/api/sessions/${id}`,
  SESSION_MESSAGES: (id: number | string) => `/api/sessions/${id}/messages`,
  SESSION_TITLE: (id: number | string | undefined,title:string) => `/api/sessions/${id}/title?title=${title}`,
  // 创建新会话 (POST only)
  CREATE_SESSION: '/api/chat/sessions',
  // 获取用户会话 (GET)
  GET_USER_SESSIONS: (userId: string) => `/api/sessions?user_id=${userId}`,
  
  // 聊天相关
  CHAT: '/api/chat',
  CHAT_STREAM: '/api/chat/stream',
  
  // MCP相关
  MCP_SERVERS: '/api/mcp/servers',
  MCP_SERVER_BY_ID: (id: number | string) => `/api/mcp/servers/${id}`,
  MCP_SERVER_TOOLS: (id: number | string) => `/api/mcp/servers/${id}/tools`,
  MCP_SERVER_SYNC: (name: string) => `/api/mcp/servers/${name}/sync`,
  MCP_TOOLS: '/api/mcp/tools',
  MCP_TOOL_BY_ID: (id: number | string) => `/api/mcp/tools/${id}`,
  
  // 流程图相关
  FLOWS: '/api/flows',
  FLOW_BY_ID: (id: number | string) => `/api/flows/${id}`,
  FLOW_TEST: (id: number | string) => `/api/flows/${id}/test`,
  
  // LLM配置相关
  LLM_CONFIG: '/api/llm-config',
  LLM_CONFIG_BY_ID: (id: number | string) => `/api/llm-config/${id}`,
  LLM_CONFIG_SET_DEFAULT: (id: number | string) => `/api/llm-config/${id}/set-default`,
  LLM_CONFIG_REFRESH: '/api/llm-config/refresh',
  LLM_CONFIG_RELOAD: '/api/llm-config/reload',
  
  // 知识库相关
  KNOWLEDGE_BASE: '/api/knowledge-base',
  KNOWLEDGE_BASE_BY_ID: (id: number | string) => `/api/knowledge-base/${id}`,
  KNOWLEDGE_BASE_DOCUMENTS: (id: number | string) => `/api/knowledge-base/${id}/documents`,
  KNOWLEDGE_BASE_QUERY: (id: number | string) => `/api/knowledge-base/${id}/query`,
  KNOWLEDGE_BASE_UPLOAD: (id: number | string) => `/api/knowledge-base/${id}/documents/upload`,
  KNOWLEDGE_BASE_DOCUMENT: (id: number | string) => `/api/knowledge-base/documents/${id}`,
  
  // 健康检查
  HEALTH: '/api/health',
  HEALTH_ROOT: '/health',
  ROOT: '/api',
} as const;

// 导出类型
export type ApiPath = typeof API_PATHS[keyof typeof API_PATHS]; 