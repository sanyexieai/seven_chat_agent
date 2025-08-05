import React from 'react';
import { Card, Row, Col, Typography, Button, Space, Statistic } from 'antd';
import { useNavigate } from 'react-router-dom';
import {
  RobotOutlined,
  ApiOutlined,
  BranchesOutlined,
  ExperimentOutlined,
  MessageOutlined
} from '@ant-design/icons';

const { Title, Paragraph } = Typography;

const HomePage: React.FC = () => {
  const navigate = useNavigate();

  const features = [
    {
      title: '智能体管理',
      description: '创建和管理不同类型的智能体，包括提示词驱动、工具驱动和流程图驱动智能体',
      icon: <RobotOutlined style={{ fontSize: '48px', color: '#1890ff' }} />,
      path: '/agents'
    },
    {
      title: 'MCP管理',
      description: '管理MCP服务器和工具，支持多种传输协议和工具集成',
      icon: <ApiOutlined style={{ fontSize: '48px', color: '#52c41a' }} />,
      path: '/mcp'
    },
    {
      title: '流程图编辑器',
      description: '在线编辑流程图，将多个智能体组合成复杂的多智能体系统',
      icon: <BranchesOutlined style={{ fontSize: '48px', color: '#fa8c16' }} />,
      path: '/flow-editor'
    },
    {
      title: '智能体测试',
      description: '测试智能体的功能和性能，支持实时对话和调试',
      icon: <ExperimentOutlined style={{ fontSize: '48px', color: '#722ed1' }} />,
      path: '/agent-test'
    }
  ];

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ textAlign: 'center', marginBottom: '48px' }}>
        <Title level={1}>Seven Chat Agent</Title>
        <Paragraph style={{ fontSize: '18px', color: '#666' }}>
          多智能体聊天系统 - 通过在线编辑流程图创建复杂的多智能体组合
        </Paragraph>
      </div>

      <Row gutter={[24, 24]}>
        {features.map((feature, index) => (
          <Col xs={24} sm={12} lg={6} key={index}>
            <Card
              hoverable
              style={{ height: '100%', textAlign: 'center' }}
              onClick={() => navigate(feature.path)}
            >
              <div style={{ marginBottom: '16px' }}>
                {feature.icon}
              </div>
              <Title level={4}>{feature.title}</Title>
              <Paragraph style={{ color: '#666' }}>
                {feature.description}
              </Paragraph>
            </Card>
          </Col>
        ))}
      </Row>

      <div style={{ marginTop: '48px' }}>
        <Title level={2}>系统概览</Title>
        <Row gutter={[24, 24]}>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="智能体总数"
                value={8}
                prefix={<RobotOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="MCP服务器"
                value={3}
                prefix={<ApiOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="可用工具"
                value={25}
                prefix={<MessageOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="流程图"
                value={2}
                prefix={<BranchesOutlined />}
              />
            </Card>
          </Col>
        </Row>
      </div>

      <div style={{ marginTop: '48px', textAlign: 'center' }}>
        <Title level={3}>快速开始</Title>
        <Space size="large">
          <Button 
            type="primary" 
            size="large"
            onClick={() => navigate('/agents')}
          >
            创建智能体
          </Button>
          <Button 
            size="large"
            onClick={() => navigate('/flow-editor')}
          >
            编辑流程图
          </Button>
          <Button 
            size="large"
            onClick={() => navigate('/agent-test')}
          >
            测试智能体
          </Button>
        </Space>
      </div>
    </div>
  );
};

export default HomePage; 