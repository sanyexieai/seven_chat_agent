import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import Layout from './components/Layout';
import AgentsPage from './pages/AgentsPage';
import AgentTestPage from './pages/AgentTestPage';
import MCPPage from './pages/MCPPage';
import FlowEditorPage from './pages/FlowEditorPage';


import ChatPage from './pages/ChatPage';
import LLMConfigPage from './pages/LLMConfigPage';
import KnowledgeBasePage from './pages/KnowledgeBasePage';
import KnowledgeQueryPage from './pages/KnowledgeQueryPage';

import SettingsPage from './pages/SettingsPage';

import './App.css';

const App: React.FC = () => {
  return (
    <ConfigProvider locale={zhCN}>
      <Router>
        <Layout>
          <Routes>
            <Route path="/" element={<ChatPage />} />

            <Route path="/agent-management" element={<AgentsPage />} />
            <Route path="/agent-test" element={<AgentTestPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:sessionId" element={<ChatPage />} />
            <Route path="/mcp" element={<MCPPage />} />
            <Route path="/flow-editor" element={<FlowEditorPage />} />
            <Route path="/llm-config" element={<LLMConfigPage />} />
            <Route path="/knowledge-base" element={<KnowledgeBasePage />} />
            <Route path="/knowledge-query" element={<KnowledgeQueryPage />} />

            <Route path="/settings" element={<SettingsPage />} />

          </Routes>
        </Layout>
      </Router>
    </ConfigProvider>
  );
};

export default App; 