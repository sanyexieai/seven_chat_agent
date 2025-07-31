import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Layout } from 'antd';
import './App.css';

import ChatPage from './pages/ChatPage';
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
          </Routes>
        </Content>
      </Layout>
    </Router>
  );
}

export default App; 