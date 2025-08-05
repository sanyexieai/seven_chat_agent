import React from 'react';
import { Layout as AntLayout, Menu, Typography } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  HomeOutlined,
  RobotOutlined,
  ExperimentOutlined,
  ApiOutlined,
  BranchesOutlined
} from '@ant-design/icons';

const { Header, Sider, Content } = AntLayout;
const { Title } = Typography;

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    {
      key: '/',
      icon: <HomeOutlined />,
      label: '首页',
    },
    {
      key: '/agents',
      icon: <RobotOutlined />,
      label: '智能体管理',
    },
    {
      key: '/agent-test',
      icon: <ExperimentOutlined />,
      label: '智能体测试',
    },
    {
      key: '/mcp',
      icon: <ApiOutlined />,
      label: 'MCP管理',
    },
    {
      key: '/flow-editor',
      icon: <BranchesOutlined />,
      label: '流程图编辑器',
    },
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key);
  };

  return (
    <AntLayout style={{ height: '100vh' }}>
      <Header style={{ 
        display: 'flex', 
        alignItems: 'center', 
        background: '#001529',
        padding: '0 24px'
      }}>
        <Title level={3} style={{ color: 'white', margin: 0 }}>
          Seven Chat Agent
        </Title>
      </Header>
      <AntLayout>
        <Sider width={250} theme="light">
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={handleMenuClick}
            style={{ height: '100%', borderRight: 0 }}
          />
        </Sider>
        <Content style={{ padding: 0, margin: 0 }}>
          {children}
        </Content>
      </AntLayout>
    </AntLayout>
  );
};

export default Layout;