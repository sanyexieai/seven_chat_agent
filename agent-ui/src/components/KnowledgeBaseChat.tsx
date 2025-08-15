import React, { useState, useEffect } from 'react';
import { API_PATHS } from '../config/api';
import { Card, Select, Button, Input, message, Space, Tag, Divider } from 'antd';
import { BookOutlined, SearchOutlined, FileTextOutlined } from '@ant-design/icons';

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

interface KnowledgeBaseChatProps {
  onSendMessage: (message: string, context?: any) => void;
}

const KnowledgeBaseChat: React.FC<KnowledgeBaseChatProps> = ({ onSendMessage }) => {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKb, setSelectedKb] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);

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
          max_results: 3
        })
      });

      if (response.ok) {
        const result = await response.json();
        setQueryResult(result);
        
        // 发送到聊天
        const formattedMessage = formatQueryResult(result);
        onSendMessage(formattedMessage, {
          knowledge_base_id: selectedKb,
          query_result: result
        });
        
        setQuery('');
        setQueryResult(null);
      } else {
        message.error('查询失败');
      }
    } catch (error) {
      message.error('网络错误');
    } finally {
      setLoading(false);
    }
  };

  const formatQueryResult = (result: QueryResult): string => {
    let message = `📚 知识库查询结果\n\n`;
    message += `🔍 查询: ${result.query}\n\n`;
    message += `💡 回答:\n${result.response}\n\n`;
    
    if (result.sources.length > 0) {
      message += `📖 来源文档:\n`;
      result.sources.forEach((source, index) => {
        const similarity = (source.similarity * 100).toFixed(1);
        message += `${index + 1}. 文档${source.document_id} (相似度: ${similarity}%)\n`;
        message += `   ${source.content.substring(0, 100)}...\n\n`;
      });
    }
    
    return message;
  };

  const getSelectedKbInfo = () => {
    return knowledgeBases.find(kb => kb.id === selectedKb);
  };

  return (
    <Card 
      title={
        <Space>
          <BookOutlined />
          <span>知识库查询</span>
        </Space>
      }
      size="small"
      style={{ marginBottom: 16 }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
            选择知识库:
          </label>
          <Select
            placeholder="请选择知识库"
            value={selectedKb}
            onChange={setSelectedKb}
            style={{ width: '100%' }}
            size="small"
          >
            {knowledgeBases.map(kb => (
              <Option key={kb.id} value={kb.id}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{kb.display_name}</span>
                  <Tag color={kb.is_public ? 'green' : 'blue'}>
                    {kb.is_public ? '公开' : '私有'}
                  </Tag>
                </div>
              </Option>
            ))}
          </Select>
        </div>

        {selectedKb && (
          <div style={{ 
            background: '#f8f9fa', 
            padding: 8, 
            borderRadius: 4,
            fontSize: '12px',
            color: '#666'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
              <BookOutlined style={{ color: '#1890ff' }} />
              <span style={{ fontWeight: 500 }}>
                {getSelectedKbInfo()?.display_name}
              </span>
            </div>
            <div>{getSelectedKbInfo()?.description || '暂无描述'}</div>
          </div>
        )}

        <div>
          <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
            查询内容:
          </label>
          <TextArea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="请输入您的问题..."
            rows={3}
            size="small"
          />
        </div>

        <Button
          type="primary"
          icon={<SearchOutlined />}
          onClick={handleQuery}
          loading={loading}
          disabled={!selectedKb || !query.trim()}
          size="small"
          block
        >
          查询知识库
        </Button>

        {queryResult && (
          <div style={{ 
            background: '#f0f8ff', 
            padding: 8, 
            borderRadius: 4,
            border: '1px solid #d6e4ff'
          }}>
            <div style={{ fontWeight: 500, marginBottom: 4 }}>
              📋 查询结果
            </div>
            <div style={{ fontSize: '12px', color: '#666' }}>
              {queryResult.response.substring(0, 100)}...
            </div>
            <div style={{ marginTop: 4 }}>
                             <Tag color="blue">
                 {queryResult.sources.length} 个来源
               </Tag>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
};

export default KnowledgeBaseChat; 