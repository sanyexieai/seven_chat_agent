import { useState, useEffect } from 'react';
import axios from 'axios';

interface ChatResponse {
  success: boolean;
  message: string;
  agent_name?: string;
  tools_used?: string[];
  timestamp: string;
}

interface ChatRequest {
  user_id: string;
  message: string;
  context?: Record<string, any>;
  agent_type?: string;
  stream?: boolean;
}

export const useChat = () => {
  const [isConnected, setIsConnected] = useState(false);
  const [userId] = useState(() => `user_${Date.now()}`);

  useEffect(() => {
    // 检查连接状态
    checkConnection();
  }, []);

  const checkConnection = async () => {
    try {
      const response = await axios.get('/health');
      setIsConnected(response.status === 200);
    } catch (error) {
      setIsConnected(false);
      console.error('连接检查失败:', error);
    }
  };

  const sendMessage = async (message: string, agentName?: string): Promise<ChatResponse> => {
    try {
      const request: ChatRequest = {
        user_id: userId,
        message,
        context: {},
        agent_type: agentName,
        stream: false,
      };

      const response = await axios.post<ChatResponse>('/api/chat', request);
      
      if (!response.data.success) {
        throw new Error(response.data.message || '发送消息失败');
      }

      return response.data;
    } catch (error) {
      console.error('发送消息失败:', error);
      throw error;
    }
  };

  const sendMessageStream = async (
    message: string,
    onChunk: (chunk: any) => void,
    onComplete: () => void,
    onError: (error: any) => void,
    agentName?: string
  ) => {
    try {
      const request: ChatRequest = {
        user_id: userId,
        message,
        context: {},
        agent_type: agentName,
        stream: true,
      };

      const response = await axios.post('/api/chat/stream', request, {
        responseType: 'stream',
      });

      const reader = response.data.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          onComplete();
          break;
        }

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onChunk(data);
            } catch (e) {
              console.error('解析流数据失败:', e);
            }
          }
        }
      }
    } catch (error) {
      console.error('流式发送消息失败:', error);
      onError(error);
    }
  };

  return {
    sendMessage,
    sendMessageStream,
    isConnected,
    userId,
  };
}; 