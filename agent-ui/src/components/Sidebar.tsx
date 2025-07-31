import React from 'react';
import { Layout, Menu } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  MessageOutlined,
  RobotOutlined,
  ToolOutlined,
  SettingOutlined,
} from '@ant-design/icons';

const { Sider } = Layout;

const Sidebar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    {
      key: '/chat',
      icon: <MessageOutlined />,
      label: '聊天',
    },
    {
      key: '/agents',
      icon: <RobotOutlined />,
      label: '智能体',
    },
    {
      key: '/tools',
      icon: <ToolOutlined />,
      label: '工具',
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: '设置',
    },
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key);
  };

  return (
    <Sider
      width={200}
      style={{
        background: '#001529',
      }}
    >
      <div style={{ padding: '16px', textAlign: 'center' }}>
        <h2 style={{ color: 'white', margin: 0 }}>AI Agent</h2>
      </div>
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[location.pathname]}
        items={menuItems}
        onClick={handleMenuClick}
        style={{ borderRight: 0 }}
      />
    </Sider>
  );
};

export default Sidebar; 