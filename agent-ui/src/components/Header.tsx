import React from 'react';
import { Layout, Avatar, Dropdown, Menu, Space } from 'antd';
import { UserOutlined, LogoutOutlined, SettingOutlined } from '@ant-design/icons';

const { Header } = Layout;

const AppHeader: React.FC = () => {
  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人资料',
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: '设置',
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
    },
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    switch (key) {
      case 'logout':
        // 处理退出登录
        console.log('退出登录');
        break;
      case 'profile':
        // 处理个人资料
        console.log('个人资料');
        break;
      case 'settings':
        // 处理设置
        console.log('设置');
        break;
      default:
        break;
    }
  };

  return (
    <Header style={{ background: '#fff', padding: '0 24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: '100%' }}>
        <div>
          <h2 style={{ margin: 0, color: '#1890ff' }}>AI Agent System</h2>
        </div>
        <Space>
          <Dropdown
            menu={{
              items: userMenuItems,
              onClick: handleMenuClick,
            }}
            placement="bottomRight"
          >
            <Avatar
              style={{ cursor: 'pointer' }}
              icon={<UserOutlined />}
            />
          </Dropdown>
        </Space>
      </div>
    </Header>
  );
};

export default AppHeader; 