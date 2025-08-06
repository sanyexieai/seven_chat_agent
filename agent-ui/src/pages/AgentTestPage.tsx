import React, { useState, useEffect } from 'react';
import {
  Card,
  Input,
  Button,
  Space,
  Typography,
  Select,
  message,
  Divider,
  List,
  Avatar,
  Tag
} from 'antd';
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  LoadingOutlined
} from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';

const { TextArea } = Input;
const { Title, Paragraph } = Typography;
const { Option } = Select;

interface Agent {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  agent_type: string;
  is_active: boolean;
}

interface Message {
  id: string;
  type: 'user' | 'agent';
  content: string;
  timestamp: Date;
}

const AgentTestPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);

  useEffect(() => {
    fetchAgents();
    // 从URL参数获取智能体ID
    const agentId = searchParams.get('agent_id');
    if (agentId) {
      setSelectedAgentId(parseInt(agentId));
    }
  }, [searchParams]);

  const fetchAgents = async () => {
    try {
      const response = await fetch('/api/agents');
      if (response.ok) {
        const data = await response.json();
        setAgents(data);
      } else {
        message.error('获取智能体列表失败');
      }
    } catch (error) {
      console.error('获取智能体列表失败:', error);
      message.error('获取智能体列表失败');
    }
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || !selectedAgentId) {
      return;
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputValue,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: 'test_user',
          message: userMessage.content,
          agent_id: selectedAgentId
        }),
      });

      if (response.ok) {
        const data = await response.json();
        const agentMessage: Message = {
          id: (Date.now() + 1).toString(),
          type: 'agent',
          content: data.content,
          timestamp: new Date()
        };
        setMessages(prev => [...prev, agentMessage]);
      } else {
        const error = await response.json();
        message.error(`发送消息失败: ${error.detail || '未知错误'}`);
      }
    } catch (error) {
      console.error('发送消息失败:', error);
      message.error('发送消息失败');
    } finally {
      setLoading(false);
    }
  };

  const handleStreamMessage = async () => {
    if (!inputValue.trim() || !selectedAgentId) {
      return;
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputValue,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setStreaming(true);

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: 'test_user',
          message: userMessage.content,
          agent_id: selectedAgentId
        }),
      });

      if (response.ok) {
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let agentMessage: Message = {
          id: (Date.now() + 1).toString(),
          type: 'agent',
          content: '',
          timestamp: new Date()
        };

        setMessages(prev => [...prev, agentMessage]);

        if (reader) {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (data === '[DONE]') {
                  break;
                }
                try {
                  const parsed = JSON.parse(data);
                  if (parsed.content) {
                    agentMessage.content += parsed.content;
                    setMessages(prev => [...prev.slice(0, -1), { ...agentMessage }]);
                  }
                } catch (e) {
                  // 忽略解析错误
                }
              }
            }
          }
        }
      } else {
        const error = await response.json();
        message.error(`流式发送消息失败: ${error.detail || '未知错误'}`);
      }
    } catch (error) {
      console.error('流式发送消息失败:', error);
      message.error('流式发送消息失败');
    } finally {
      setStreaming(false);
    }
  };

  const getAgentTypeLabel = (type: string) => {
    const typeMap: { [key: string]: string } = {
      'chat': '聊天智能体',
      'search': '搜索智能体',
      'report': '报告智能体',
      'prompt_driven': '提示词驱动',
      'tool_driven': '工具驱动',
      'flow_driven': '流程图驱动'
    };
    return typeMap[type] || type;
  };

  const getAgentTypeColor = (type: string) => {
    const colorMap: { [key: string]: string } = {
      'chat': 'blue',
      'search': 'green',
      'report': 'orange',
      'prompt_driven': 'purple',
      'tool_driven': 'cyan',
      'flow_driven': 'magenta'
    };
    return colorMap[type] || 'default';
  };

  const selectedAgent = agents.find(agent => agent.id === selectedAgentId);

  return (
    <div style={{ padding: '24px', height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Card style={{ marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: '16px' }}>
          <Title level={3} style={{ margin: 0, marginRight: '16px' }}>
            <RobotOutlined style={{ marginRight: '8px' }} />
            智能体测试
          </Title>
          <Select
            placeholder="选择要测试的智能体"
            style={{ width: 300 }}
            value={selectedAgentId}
            onChange={setSelectedAgentId}
          >
            {agents.map(agent => (
              <Option key={agent.id} value={agent.id}>
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <RobotOutlined style={{ marginRight: '8px' }} />
                  <div>
                    <div>{agent.display_name}</div>
                    <div style={{ fontSize: '12px', color: '#666' }}>
                      <Tag color={getAgentTypeColor(agent.agent_type)}>
                        {getAgentTypeLabel(agent.agent_type)}
                      </Tag>
                    </div>
                  </div>
                </div>
              </Option>
            ))}
          </Select>
        </div>

        {selectedAgent && (
          <div>
            <Paragraph>
              <strong>智能体:</strong> {selectedAgent.display_name}
            </Paragraph>
            <Paragraph>
              <strong>类型:</strong>
              <Tag color={getAgentTypeColor(selectedAgent.agent_type)} style={{ marginLeft: '8px' }}>
                {getAgentTypeLabel(selectedAgent.agent_type)}
              </Tag>
            </Paragraph>
            {selectedAgent.description && (
              <Paragraph>
                <strong>描述:</strong> {selectedAgent.description}
              </Paragraph>
            )}
          </div>
        )}
      </Card>

      <Card style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: 1, overflow: 'auto', marginBottom: '16px' }}>
          <List
            dataSource={messages}
            renderItem={(message) => (
              <List.Item style={{ border: 'none', padding: '8px 0' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', width: '100%' }}>
                  <Avatar
                    icon={message.type === 'user' ? <UserOutlined /> : <RobotOutlined />}
                    style={{
                      backgroundColor: message.type === 'user' ? '#1890ff' : '#52c41a',
                      marginRight: '12px'
                    }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{
                      background: message.type === 'user' ? '#f0f8ff' : '#f6ffed',
                      padding: '12px',
                      borderRadius: '8px',
                      border: `1px solid ${message.type === 'user' ? '#d6e4ff' : '#b7eb8f'}`
                    }}>
                      {message.content}
                    </div>
                    <div style={{ fontSize: '12px', color: '#666', marginTop: '4px' }}>
                      {message.timestamp.toLocaleTimeString()}
                    </div>
                  </div>
                </div>
              </List.Item>
            )}
          />
          {(loading || streaming) && (
            <div style={{ display: 'flex', alignItems: 'center', padding: '12px' }}>
              <LoadingOutlined style={{ marginRight: '8px' }} />
              <span>智能体正在思考...</span>
            </div>
          )}
        </div>

        <Divider />

        <div style={{ display: 'flex', gap: '8px' }}>
          <TextArea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="输入消息..."
            autoSize={{ minRows: 2, maxRows: 4 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            style={{ flex: 1 }}
          />
          <Space direction="vertical">
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSendMessage}
              loading={loading}
              disabled={!selectedAgentId || !inputValue.trim()}
            >
              发送
            </Button>
            <Button
              icon={<SendOutlined />}
              onClick={handleStreamMessage}
              loading={streaming}
              disabled={!selectedAgentId || !inputValue.trim()}
            >
              流式
            </Button>
          </Space>
        </div>
      </Card>
    </div>
  );
};

export default AgentTestPage; 