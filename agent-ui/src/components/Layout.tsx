import React from 'react';
import { Layout as AntLayout } from 'antd';
import Sidebar from './Sidebar';

const { Content } = AntLayout;

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <AntLayout style={{ height: '100vh' }}>
      <Sidebar />
      <Content style={{ 
        marginLeft: 280, 
        padding: '0 24px 24px 24px', 
        backgroundColor: '#f0f2f5',
        minHeight: '100vh',
        overflow: 'auto'
      }}>
        {children}
      </Content>
    </AntLayout>
  );
};

export default Layout;