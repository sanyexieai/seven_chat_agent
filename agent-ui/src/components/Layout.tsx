import React, { useState, createContext, useContext } from 'react';
import { Layout as AntLayout } from 'antd';
import Sidebar from './Sidebar';

const { Content } = AntLayout;

interface LayoutProps {
  children: React.ReactNode;
}

// 创建上下文来共享侧边栏宽度
interface SidebarWidthContextType {
  sidebarWidth: number;
  setSidebarWidth: (width: number) => void;
}

export const SidebarWidthContext = createContext<SidebarWidthContextType>({
  sidebarWidth: 280,
  setSidebarWidth: () => {},
});

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [sidebarWidth, setSidebarWidth] = useState(280); // 默认主侧边栏宽度

  return (
    <SidebarWidthContext.Provider value={{ sidebarWidth, setSidebarWidth }}>
      <AntLayout style={{ height: '100vh' }}>
        <Sidebar />
        <Content style={{ 
          marginLeft: sidebarWidth, 
          padding: '0 24px 24px 24px', 
          backgroundColor: '#f0f2f5',
          minHeight: '100vh',
          overflow: 'auto',
          transition: 'margin-left 0.2s'
        }}>
          {children}
        </Content>
      </AntLayout>
    </SidebarWidthContext.Provider>
  );
};

export default Layout;