/**
 * 消息类型配置
 * 统一管理前端和后端的消息类型映射
 */

// 用户消息类型
export const USER_MESSAGE_TYPES = ['user', 'human'] as const;

// 智能体消息类型
export const AGENT_MESSAGE_TYPES = ['agent', 'assistant', 'ai'] as const;

// 系统消息类型
export const SYSTEM_MESSAGE_TYPES = ['system', 'tool', 'workspace_summary'] as const;

// 所有消息类型
export const ALL_MESSAGE_TYPES = [
  ...USER_MESSAGE_TYPES,
  ...AGENT_MESSAGE_TYPES,
  ...SYSTEM_MESSAGE_TYPES
] as const;

// 类型判断函数
export const isUserMessage = (messageType: string): boolean => {
  return USER_MESSAGE_TYPES.includes(messageType as any);
};

export const isAgentMessage = (messageType: string): boolean => {
  return AGENT_MESSAGE_TYPES.includes(messageType as any);
};

export const isSystemMessage = (messageType: string): boolean => {
  return SYSTEM_MESSAGE_TYPES.includes(messageType as any);
};

// 前端显示类型映射
export const getDisplayType = (messageType: string): 'user' | 'agent' | 'system' => {
  if (isUserMessage(messageType)) return 'user';
  if (isAgentMessage(messageType)) return 'agent';
  if (isSystemMessage(messageType)) return 'system';
  return 'agent'; // 默认作为智能体消息处理
}; 