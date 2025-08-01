import React, { useState, useEffect } from 'react';
import { 
  Card, Row, Col, Typography, Button, Input, Select, Space, 
  message, Divider, Tabs, Tag, Spin, Alert, Collapse
} from 'antd';
import { 
  RobotOutlined, MessageOutlined, SearchOutlined, FileTextOutlined,
  SettingOutlined, PlayCircleOutlined, StopOutlined, ReloadOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;
const { Option } = Select;
const { TabPane } = Tabs;
const { Panel } = Collapse;

interface Agent {
  id: number;
  name: string;
  display_name: string;
  description: string;
  agent_type: string;
  is_active: boolean;
  system_prompt?: string;
  bound_tools?: string[];
  flow_config?: any;
}

interface ChatMessage {
  id: string;
  type: 'user' | 'agent';
  content: string;
  timestamp: string;
}

const AgentTestPage: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamContent, setStreamContent] = useState('');

  useEffect(() => {
    fetchAgents();
  }, []);

  const fetchAgents = async () => {
    try {
      const response = await axios.get('/api/agents');
      setAgents(response.data || []);
    } catch (error) {
      console.error('获取智能体失败:', error);
      message.error('获取智能体失败');
    }
  };

  const getAgentIcon = (agentType: string) => {
    switch (agentType) {
      case 'chat':
        return <MessageOutlined />;
      case 'search':
        return <SearchOutlined />;
      case 'report':
        return <FileTextOutlined />;
      case 'prompt_driven':
        return <RobotOutlined style={{ color: '#1890ff' }} />;
      case 'tool_driven':
        return <SettingOutlined style={{ color: '#52c41a' }} />;
      case 'flow_driven':
        return <RobotOutlined style={{ color: '#722ed1' }} />;
      default:
        return <RobotOutlined />;
    }
  };

  const getAgentTypeLabel = (agentType: string) => {
    switch (agentType) {
      case 'chat':
        return '聊天智能体';
      case 'search':
        return '搜索智能体';
      case 'report':
        return '报告智能体';
      case 'prompt_driven':
        return '提示词驱动';
      case 'tool_driven':
        return '工具驱动';
      case 'flow_driven':
        return '流程图驱动';
      default:
        return agentType;
    }
  };

  const getAgentTypeColor = (agentType: string) => {
    switch (agentType) {
      case 'chat':
        return 'blue';
      case 'search':
        return 'green';
      case 'report':
        return 'orange';
      case 'prompt_driven':
        return 'cyan';
      case 'tool_driven':
        return 'purple';
      case 'flow_driven':
        return 'magenta';
      default:
        return 'default';
    }
  };

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || !selectedAgent) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: inputMessage,
      timestamp: new Date().toISOString()
    };

    setChatMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setLoading(true);

    try {
      const response = await axios.post('/api/chat', {
        user_id: 'test_user',
        message: inputMessage,
        agent_name: selectedAgent.name
      });

      const agentMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        type: 'agent',
        content: response.data.message,
        timestamp: new Date().toISOString()
      };

      setChatMessages(prev => [...prev, agentMessage]);
    } catch (error) {
      console.error('发送消息失败:', error);
      message.error('发送消息失败');
    } finally {
      setLoading(false);
    }
  };

  const handleStreamChat = async () => {
    if (!inputMessage.trim() || !selectedAgent) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: inputMessage,
      timestamp: new Date().toISOString()
    };

    setChatMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setStreaming(true);
    setStreamContent('');

    try {
      const response = await fetch(`/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: 'test_user',
          message: inputMessage,
          agent_name: selectedAgent.name
        }),
      });

      const reader = response.body?.getReader();
      if (!reader) return;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = new TextDecoder().decode(value);
        const lines = chunk.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'content') {
                setStreamContent(prev => prev + data.content);
              } else if (data.type === 'final') {
                const agentMessage: ChatMessage = {
                  id: (Date.now() + 1).toString(),
                  type: 'agent',
                  content: data.content,
                  timestamp: new Date().toISOString()
                };
                setChatMessages(prev => [...prev, agentMessage]);
                setStreamContent('');
                setStreaming(false);
                break;
              }
            } catch (e) {
              console.error('解析流数据失败:', e);
            }
          }
        }
      }
    } catch (error) {
      console.error('流式聊天失败:', error);
      message.error('流式聊天失败');
      setStreaming(false);
    }
  };

  const handleAgentSelect = (agent: Agent) => {
    setSelectedAgent(agent);
    setChatMessages([]);
    setStreamContent('');
  };

  const renderAgentInfo = (agent: Agent) => (
    <Card size="small" style={{ marginBottom: 16 }}>
      <Space direction="vertical" style={{ width: '100%' }}>
        <div>
          <Text strong>类型: </Text>
          <Tag color={getAgentTypeColor(agent.agent_type)}>
            {getAgentTypeLabel(agent.agent_type)}
          </Tag>
        </div>
        <div>
          <Text strong>描述: </Text>
          <Text>{agent.description}</Text>
        </div>
        {agent.system_prompt && (
          <div>
            <Text strong>系统提示词: </Text>
            <Text type="secondary" style={{ fontSize: '12px' }}>
              {agent.system_prompt.substring(0, 100)}...
            </Text>
          </div>
        )}
        {agent.bound_tools && agent.bound_tools.length > 0 && (
          <div>
            <Text strong>绑定工具: </Text>
                         {agent.bound_tools.map(tool => (
               <Tag key={tool}>{tool}</Tag>
             ))}
          </div>
        )}
      </Space>
    </Card>
  );

  const renderChatInterface = () => (
    <Card title="聊天界面" style={{ height: '500px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, overflowY: 'auto', marginBottom: 16, padding: 16 }}>
        {chatMessages.map(message => (
          <div key={message.id} style={{ marginBottom: 16 }}>
            <div style={{ 
              textAlign: message.type === 'user' ? 'right' : 'left',
              marginBottom: 4
            }}>
              <Tag color={message.type === 'user' ? 'blue' : 'green'}>
                {message.type === 'user' ? '用户' : selectedAgent?.display_name}
              </Tag>
            </div>
            <div style={{
              padding: 12,
              borderRadius: 8,
              backgroundColor: message.type === 'user' ? '#e6f7ff' : '#f6ffed',
              border: `1px solid ${message.type === 'user' ? '#91d5ff' : '#b7eb8f'}`,
              textAlign: message.type === 'user' ? 'right' : 'left'
            }}>
              {message.content}
            </div>
            <div style={{ 
              fontSize: '12px', 
              color: '#999',
              textAlign: message.type === 'user' ? 'right' : 'left',
              marginTop: 4
            }}>
              {new Date(message.timestamp).toLocaleTimeString()}
            </div>
          </div>
        ))}
        {streaming && streamContent && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 4 }}>
              <Tag color="green">{selectedAgent?.display_name}</Tag>
            </div>
            <div style={{
              padding: 12,
              borderRadius: 8,
              backgroundColor: '#f6ffed',
              border: '1px solid #b7eb8f',
              textAlign: 'left'
            }}>
              {streamContent}
              <span style={{ animation: 'blink 1s infinite' }}>|</span>
            </div>
          </div>
        )}
        {loading && (
          <div style={{ textAlign: 'center', padding: 20 }}>
            <Spin /> <Text>智能体正在思考...</Text>
          </div>
        )}
      </div>
      <div style={{ borderTop: '1px solid #f0f0f0', padding: 16 }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onPressEnter={handleSendMessage}
            placeholder="输入消息..."
            disabled={!selectedAgent || loading || streaming}
          />
          <Button 
            type="primary" 
            onClick={handleSendMessage}
            disabled={!selectedAgent || loading || streaming}
          >
            发送
          </Button>
          <Button 
            onClick={handleStreamChat}
            disabled={!selectedAgent || loading || streaming}
            icon={<PlayCircleOutlined />}
          >
            流式
          </Button>
        </Space.Compact>
      </div>
    </Card>
  );

  return (
    <div>
      <Title level={2}>智能体测试</Title>
      <Paragraph>
        测试不同类型的智能体，体验它们的功能和特点。
      </Paragraph>

      <Row gutter={[16, 16]}>
        <Col span={8}>
          <Card title="选择智能体" size="small">
            <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
              {agents.map(agent => (
                <Card
                  key={agent.id}
                  size="small"
                  style={{ 
                    marginBottom: 8, 
                    cursor: 'pointer',
                    border: selectedAgent?.id === agent.id ? '2px solid #1890ff' : '1px solid #f0f0f0'
                  }}
                  onClick={() => handleAgentSelect(agent)}
                >
                  <Card.Meta
                    avatar={getAgentIcon(agent.agent_type)}
                    title={
                      <Space>
                        {agent.display_name}
                                                 <Tag color={getAgentTypeColor(agent.agent_type)}>
                           {getAgentTypeLabel(agent.agent_type)}
                         </Tag>
                         {agent.is_active ? (
                           <Tag color="green">活跃</Tag>
                         ) : (
                           <Tag color="red">非活跃</Tag>
                         )}
                      </Space>
                    }
                    description={agent.description}
                  />
                </Card>
              ))}
            </div>
          </Card>
        </Col>

        <Col span={16}>
          {selectedAgent ? (
            <div>
              {renderAgentInfo(selectedAgent)}
              {renderChatInterface()}
            </div>
          ) : (
            <Card>
              <div style={{ textAlign: 'center', padding: 40 }}>
                <RobotOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />
                <div style={{ marginTop: 16 }}>
                  <Text type="secondary">请选择一个智能体开始测试</Text>
                </div>
              </div>
            </Card>
          )}
        </Col>
      </Row>

      <Divider />

      <Card title="智能体类型说明">
        <Tabs defaultActiveKey="prompt_driven">
          <TabPane tab="提示词驱动" key="prompt_driven">
            <Alert
              message="提示词驱动智能体"
              description="通过数据库配置的系统提示词来实现不同的功能。这种智能体完全依赖提示词来定义行为，不需要特定的工具。"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Paragraph>
              <Text strong>特点：</Text>
            </Paragraph>
            <ul>
              <li>完全依赖系统提示词定义行为</li>
              <li>不需要特定的工具支持</li>
              <li>可以通过修改提示词快速调整功能</li>
              <li>适合对话、问答等场景</li>
            </ul>
          </TabPane>

          <TabPane tab="工具驱动" key="tool_driven">
            <Alert
              message="工具驱动智能体"
              description="通过绑定MCP工具，根据工具的内容和参数反向生成提示词。这种智能体专注于工具的使用。"
              type="success"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Paragraph>
              <Text strong>特点：</Text>
            </Paragraph>
            <ul>
              <li>根据绑定的工具自动生成系统提示词</li>
              <li>专注于工具的使用和调用</li>
              <li>支持多种MCP工具集成</li>
              <li>适合搜索、数据处理等场景</li>
            </ul>
          </TabPane>

          <TabPane tab="流程图驱动" key="flow_driven">
            <Alert
              message="流程图驱动智能体"
              description="通过流程图定义复杂的业务流程，每个节点可以绑定不同的提示词和工具。"
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Paragraph>
              <Text strong>特点：</Text>
            </Paragraph>
            <ul>
              <li>支持复杂的业务流程定义</li>
              <li>每个节点可以绑定不同的提示词和工具</li>
              <li>支持条件分支和循环</li>
              <li>适合复杂的业务场景</li>
            </ul>
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default AgentTestPage; 