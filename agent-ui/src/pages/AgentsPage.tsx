import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Typography, Tag, Button, Modal, Descriptions, Space } from 'antd';
import { RobotOutlined, MessageOutlined, SearchOutlined, FileTextOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title, Paragraph } = Typography;

interface Agent {
  name: string;
  description: string;
  capabilities: string[];
  status: 'active' | 'inactive';
}

const AgentsPage: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [modalVisible, setModalVisible] = useState(false);

  useEffect(() => {
    fetchAgents();
  }, []);

  const fetchAgents = async () => {
    try {
      const response = await axios.get('/api/agents');
      setAgents(response.data.agents || getMockAgents());
    } catch (error) {
      console.error('获取智能体失败:', error);
      setAgents(getMockAgents());
    } finally {
      setLoading(false);
    }
  };

  const getMockAgents = (): Agent[] => [
    {
      name: 'chat_agent',
      description: '通用聊天智能体，能够进行自然语言对话和问题解答',
      capabilities: ['自然语言对话', '问题解答', '情感交流', '上下文理解'],
      status: 'active'
    },
    {
      name: 'search_agent',
      description: '搜索和信息检索智能体，能够搜索网络和文档',
      capabilities: ['网络搜索', '文档搜索', '信息整理', '结果摘要'],
      status: 'active'
    },
    {
      name: 'report_agent',
      description: '报告生成智能体，能够分析数据并生成结构化报告',
      capabilities: ['数据分析', '报告生成', '图表制作', '内容总结'],
      status: 'active'
    }
  ];

  const getAgentIcon = (agentName: string) => {
    switch (agentName) {
      case 'chat_agent':
        return <MessageOutlined />;
      case 'search_agent':
        return <SearchOutlined />;
      case 'report_agent':
        return <FileTextOutlined />;
      default:
        return <RobotOutlined />;
    }
  };

  const handleAgentClick = (agent: Agent) => {
    setSelectedAgent(agent);
    setModalVisible(true);
  };

  return (
    <div>
      <Title level={2}>智能体管理</Title>
      <Paragraph>
        管理和配置各种AI智能体，每个智能体都有特定的功能和能力。
      </Paragraph>

      <Row gutter={[16, 16]}>
        {agents.map((agent) => (
          <Col xs={24} sm={12} lg={8} key={agent.name}>
            <Card
              hoverable
              actions={[
                <Button type="link" onClick={() => handleAgentClick(agent)}>
                  查看详情
                </Button>
              ]}
            >
              <Card.Meta
                avatar={getAgentIcon(agent.name)}
                title={
                  <Space>
                    {agent.name.replace('_', ' ').toUpperCase()}
                    <Tag color={agent.status === 'active' ? 'green' : 'red'}>
                      {agent.status === 'active' ? '活跃' : '非活跃'}
                    </Tag>
                  </Space>
                }
                description={agent.description}
              />
              <div style={{ marginTop: 16 }}>
                {agent.capabilities.slice(0, 3).map((capability) => (
                  <Tag key={capability} style={{ marginBottom: 4 }}>
                    {capability}
                  </Tag>
                ))}
                {agent.capabilities.length > 3 && (
                  <Tag>+{agent.capabilities.length - 3} 更多</Tag>
                )}
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Modal
        title="智能体详情"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setModalVisible(false)}>
            关闭
          </Button>
        ]}
        width={600}
      >
        {selectedAgent && (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="名称">{selectedAgent.name}</Descriptions.Item>
            <Descriptions.Item label="描述">{selectedAgent.description}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={selectedAgent.status === 'active' ? 'green' : 'red'}>
                {selectedAgent.status === 'active' ? '活跃' : '非活跃'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="能力">
              {selectedAgent.capabilities.map((capability) => (
                <Tag key={capability} style={{ marginBottom: 4 }}>
                  {capability}
                </Tag>
              ))}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default AgentsPage; 