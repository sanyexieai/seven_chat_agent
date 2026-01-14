import React, { useState, useEffect } from 'react';
import { API_PATHS } from '../config/api';
import { Button, Input, Select, Card, Space, Tag, message, Spin, Empty, Divider } from 'antd';
import { SearchOutlined, BookOutlined, FileTextOutlined, ReloadOutlined } from '@ant-design/icons';
import './KnowledgeQueryPage.css';

const { TextArea } = Input;
const { Option } = Select;

interface KnowledgeBase {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  owner_id: string;
  is_public: boolean;
  is_active: boolean;
}

interface QueryResult {
  query: string;
  response: string;
  sources: Array<{
    document_id: number;
    chunk_index: number;
    content: string;
    similarity: number;
  }>;
  metadata: {
    total_chunks: number;
    max_results: number;
  };
}

const KnowledgeQueryPage: React.FC = () => {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKb, setSelectedKb] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [queryHistory, setQueryHistory] = useState<QueryResult[]>([]);

  const API_BASE = 'http://localhost:8000';

  useEffect(() => {
    fetchKnowledgeBases();
  }, []);

  const fetchKnowledgeBases = async () => {
    try {
      const response = await fetch(`${API_BASE}${API_PATHS.KNOWLEDGE_BASE}?include_public=true`);
      if (response.ok) {
        const data = await response.json();
        setKnowledgeBases(data);
      } else {
        message.error('获取知识库列表失败');
      }
    } catch (error) {
      message.error('网络错误');
    }
  };

  const handleQuery = async () => {
    if (!selectedKb) {
      message.warning('请先选择知识库');
      return;
    }

    if (!query.trim()) {
      message.warning('请输入查询内容');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}${API_PATHS.KNOWLEDGE_BASE_QUERY(selectedKb)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          knowledge_base_id: selectedKb,
          query: query.trim(),
          user_id: 'user123',
          max_results: 5
        })
      });

      if (response.ok) {
        const result = await response.json();
        setQueryResult(result);
        setQueryHistory(prev => [result, ...prev.slice(0, 9)]); // 保留最近10条记录
        message.success('查询完成');
      } else {
        let errorMessage = '查询失败';
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            errorMessage = `查询失败: ${errorData.detail}`;
          }
        } catch (e) {
          const errorText = await response.text();
          if (errorText) {
            try {
              const errorJson = JSON.parse(errorText);
              errorMessage = `查询失败: ${errorJson.detail || errorText}`;
            } catch {
              errorMessage = `查询失败: ${errorText}`;
            }
          }
        }
        console.error('查询失败:', errorMessage);
        message.error(errorMessage);
        
        // 显示错误信息在结果区域
        setQueryResult({
          query: query.trim(),
          response: `❌ 查询失败: ${errorMessage}`,
          sources: [],
          metadata: {
            total_chunks: 0,
            max_results: 0
          }
        });
      }
    } catch (error) {
      message.error('网络错误');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleQuery();
    }
  };

  const getSelectedKbInfo = () => {
    return knowledgeBases.find(kb => kb.id === selectedKb);
  };

  const formatSimilarity = (similarity: number) => {
    return (similarity * 100).toFixed(1) + '%';
  };

  const truncateText = (text: string, maxLength: number = 150) => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  return (
    <div className="knowledge-query-page">
      <div className="query-header">
        <h1>知识库查询</h1>
        <Button 
          icon={<ReloadOutlined />} 
          onClick={fetchKnowledgeBases}
        >
          刷新知识库
        </Button>
      </div>

      <div className="query-content">
        <div className="query-panel">
          <Card title="查询设置" className="query-card">
            <div className="query-form">
              <div className="form-item">
                <label>选择知识库:</label>
                <Select
                  placeholder="请选择知识库"
                  value={selectedKb}
                  onChange={setSelectedKb}
                  style={{ width: '100%' }}
                >
                  {knowledgeBases.map(kb => (
                    <Option key={kb.id} value={kb.id}>
                      <div className="kb-option">
                        <span className="kb-name">{kb.display_name}</span>
                        <Tag color={kb.is_public ? 'green' : 'blue'}>
                          {kb.is_public ? '公开' : '私有'}
                        </Tag>
                      </div>
                    </Option>
                  ))}
                </Select>
              </div>

              {selectedKb && (
                <div className="kb-info">
                  <Card size="small" className="kb-info-card">
                    <div className="kb-info-header">
                      <BookOutlined className="kb-icon" />
                      <span className="kb-title">{getSelectedKbInfo()?.display_name}</span>
                    </div>
                    <p className="kb-description">
                      {getSelectedKbInfo()?.description || '暂无描述'}
                    </p>
                  </Card>
                </div>
              )}

              <div className="form-item">
                <label>查询内容:</label>
                <TextArea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="请输入您的问题..."
                  rows={4}
                  className="query-input"
                />
              </div>

              <div className="form-actions">
                <Button
                  type="primary"
                  icon={<SearchOutlined />}
                  onClick={handleQuery}
                  loading={loading}
                  disabled={!selectedKb || !query.trim()}
                  size="large"
                >
                  开始查询
                </Button>
              </div>
            </div>
          </Card>
        </div>

        <div className="result-panel">
          {loading ? (
            <div className="loading-container">
              <Spin size="large" />
              <p>正在查询中...</p>
            </div>
          ) : queryResult ? (
            <div className="result-content">
              <Card title="查询结果" className="result-card">
                <div className="query-info">
                  <p><strong>查询:</strong> {queryResult.query}</p>
                  <p><strong>匹配文档数:</strong> {queryResult.metadata.total_chunks}</p>
                </div>

                <Divider />

                <div className="response-section">
                  <h3>回答</h3>
                  <div className="response-content">
                    {queryResult.response}
                  </div>
                </div>

                {queryResult.sources.length > 0 && (
                  <>
                    <Divider />
                    <div className="sources-section">
                      <h3>来源文档</h3>
                      <div className="sources-list">
                        {queryResult.sources.map((source, index) => (
                          <Card key={index} size="small" className="source-item">
                            <div className="source-header">
                              <FileTextOutlined className="source-icon" />
                              <span className="source-title">
                                文档 {source.document_id} - 分块 {source.chunk_index}
                              </span>
                                                             <Tag color="blue">
                                 相似度: {formatSimilarity(source.similarity)}
                               </Tag>
                            </div>
                            <div className="source-content">
                              {truncateText(source.content)}
                            </div>
                          </Card>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </Card>
            </div>
          ) : (
            <div className="empty-state">
              <Empty
                description="请输入查询内容开始搜索"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            </div>
          )}
        </div>
      </div>

      {queryHistory.length > 0 && (
        <div className="history-section">
          <Card title="查询历史" className="history-card">
            <div className="history-list">
              {queryHistory.map((item, index) => (
                <Card key={index} size="small" className="history-item">
                  <div className="history-header">
                    <span className="history-query">{item.query}</span>
                    <span className="history-time">
                      {new Date().toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="history-response">
                    {truncateText(item.response, 100)}
                  </div>
                  <div className="history-sources">
                                       <Tag>
                     {item.sources.length} 个来源
                   </Tag>
                  </div>
                </Card>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};

export default KnowledgeQueryPage; 