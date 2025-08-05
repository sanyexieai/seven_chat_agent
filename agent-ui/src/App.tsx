import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import AgentsPage from './pages/AgentsPage';
import AgentTestPage from './pages/AgentTestPage';
import MCPPage from './pages/MCPPage';
import FlowEditorPage from './pages/FlowEditorPage';
import './App.css';

const App: React.FC = () => {
  return (
    <ConfigProvider locale={zhCN}>
      <Router>
        <Layout>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/agents" element={<AgentsPage />} />
            <Route path="/agent-test" element={<AgentTestPage />} />
            <Route path="/mcp" element={<MCPPage />} />
            <Route path="/flow-editor" element={<FlowEditorPage />} />
          </Routes>
        </Layout>
      </Router>
    </ConfigProvider>
  );
};

export default App; 