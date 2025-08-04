import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Layout } from 'antd';
import './App.css';

import ChatPage from './pages/ChatPage';
import MCPPage from './pages/MCPPage';
import AgentsPage from './pages/AgentsPage';
import AgentTestPage from './pages/AgentTestPage';
import KnowledgeBasePage from './pages/KnowledgeBasePage';
import KnowledgeQueryPage from './pages/KnowledgeQueryPage';
import Sidebar from './components/Sidebar';

const { Content } = Layout;

function App() {
  return (
    <Router>
      <Layout style={{ height: '100vh' }}>
        <Sidebar />
        <Content style={{ padding: 0, margin: 0 }}>
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:sessionId" element={<ChatPage />} />
            <Route path="/mcp" element={<MCPPage />} />
            <Route path="/agents" element={<AgentsPage />} />
            <Route path="/agent-test" element={<AgentTestPage />} />
            <Route path="/knowledge-base" element={<KnowledgeBasePage />} />
            <Route path="/knowledge-query" element={<KnowledgeQueryPage />} />
          </Routes>
        </Content>
      </Layout>
    </Router>
  );
}

export default App; 