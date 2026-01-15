import React, { useState, useEffect } from 'react';
import { API_PATHS } from '../config/api';
import { Button, Input, Modal, message, Card, Space, Tag, Popconfirm, Upload, Form, Select, Progress } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined, UploadOutlined } from '@ant-design/icons';
import './KnowledgeBasePage.css';

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
  config?: any;
  created_at: string;
  updated_at: string;
}

interface Document {
  id: number;
  knowledge_base_id: number;
  name: string;
  file_type: string;
  file_size?: number;
  content?: string;
  document_metadata?: any;
  metadata?: any;
  status: string;
  kg_extraction_status?: string;
  kg_extraction_progress?: {
    total_chunks: number;
    processed: number;
    failed: number;
  };
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface DocumentStatus {
  document_id: number;
  status: string;
  kg_extraction_status: string;
  kg_extraction_progress: {
    total_chunks: number;
    processed: number;
    failed: number;
  };
  chunk_stats: {
    total: number;
    pending: number;
    processing: number;
    completed: number;
    failed: number;
  };
  total_triples: number;
  is_processing: boolean;
}

const KnowledgeBasePage: React.FC = () => {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedKb, setSelectedKb] = useState<KnowledgeBase | null>(null);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isUploadModalVisible, setIsUploadModalVisible] = useState(false);
  const [editingKb, setEditingKb] = useState<KnowledgeBase | null>(null);
  const [form] = Form.useForm();
  const [uploadForm] = Form.useForm();

  const API_BASE = 'http://localhost:8000';

  useEffect(() => {
    fetchKnowledgeBases();
  }, []);

  const fetchKnowledgeBases = async () => {
    setLoading(true);
    try {
      console.log('获取知识库列表...');
      const response = await fetch(`${API_BASE}${API_PATHS.KNOWLEDGE_BASE}?include_public=true`);
      console.log('知识库列表响应状态:', response.status);
      
      if (response.ok) {
        const data = await response.json();
        console.log('知识库列表数据:', data);
        setKnowledgeBases(data);
      } else {
        const errorText = await response.text();
        console.error('获取知识库列表失败:', errorText);
        message.error(`获取知识库列表失败: ${response.status}`);
      }
    } catch (error) {
      console.error('获取知识库列表错误:', error);
      message.error(`网络错误: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchDocuments = async (kbId: number) => {
    try {
      const response = await fetch(`${API_BASE}${API_PATHS.KNOWLEDGE_BASE_DOCUMENTS(kbId)}`);
      if (response.ok) {
        const data = await response.json();
        setDocuments(data);
        
        // 检查是否有处理中的文档，如果有则启动轮询
        const hasProcessing = data.some((doc: Document) => doc.status === 'processing');
        if (hasProcessing) {
          startPollingDocuments(kbId);
        }
      } else {
        const errorText = await response.text();
        console.error('获取文档列表失败:', errorText);
        message.error('获取文档列表失败');
      }
    } catch (error) {
      console.error('获取文档列表错误:', error);
      message.error('网络错误');
    }
  };

  // 轮询文档状态（用于实时显示处理进度）
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);
  const [documentStatuses, setDocumentStatuses] = useState<Record<number, DocumentStatus>>({});

  const fetchDocumentStatus = async (kbId: number, docId: number) => {
    try {
      const response = await fetch(`${API_BASE}${API_PATHS.KNOWLEDGE_BASE_DOCUMENT_STATUS(kbId, docId)}`);
      if (response.ok) {
        const status: DocumentStatus = await response.json();
        setDocumentStatuses(prev => ({ ...prev, [docId]: status }));
        return status;
      }
    } catch (error) {
      console.error(`查询文档 ${docId} 状态失败:`, error);
    }
    return null;
  };

  const startPollingDocuments = (kbId: number) => {
    // 如果已经有轮询在运行，先清除
    if (pollingInterval) {
      clearInterval(pollingInterval);
    }

    const interval = setInterval(async () => {
      try {
        // 更新文档列表
        const docsResponse = await fetch(`${API_BASE}${API_PATHS.KNOWLEDGE_BASE_DOCUMENTS(kbId)}`);
        if (docsResponse.ok) {
          const data = await docsResponse.json();
          setDocuments(data);
          
          // 更新每个文档的状态（只更新处理中的文档）
          const processingDocs = data.filter((doc: Document) => 
            doc.status === 'processing' || 
            doc.status === 'chunked' || 
            (doc.kg_extraction_status && doc.kg_extraction_status === 'processing')
          );
          
          for (const doc of processingDocs) {
            await fetchDocumentStatus(kbId, doc.id);
          }
          
          // 如果没有处理中的文档了，停止轮询
          const hasProcessing = data.some((doc: Document) => 
            doc.status === 'processing' || 
            doc.status === 'chunked' || 
            (doc.kg_extraction_status && doc.kg_extraction_status === 'processing')
          );
          if (!hasProcessing) {
            clearInterval(interval);
            setPollingInterval(null);
          }
        }
      } catch (err) {
        console.error('轮询文档状态失败:', err);
        clearInterval(interval);
        setPollingInterval(null);
      }
    }, 3000); // 每3秒轮询一次

    setPollingInterval(interval);
  };

  useEffect(() => {
    // 组件卸载时清除轮询
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [pollingInterval]);

  const handleCreateKb = () => {
    setEditingKb(null);
    form.resetFields();
    setIsModalVisible(true);
  };

  const handleEditKb = (kb: KnowledgeBase) => {
    setEditingKb(kb);
    form.setFieldsValue({
      name: kb.name,
      display_name: kb.display_name,
      description: kb.description,
      is_public: kb.is_public,
      config: kb.config
    });
    setIsModalVisible(true);
  };

  const handleDeleteKb = async (kbId: number) => {
    try {
      const response = await fetch(`${API_BASE}${API_PATHS.KNOWLEDGE_BASE_BY_ID(kbId)}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        message.success('知识库删除成功');
        fetchKnowledgeBases();
      } else {
        message.error('删除失败');
      }
    } catch (error) {
      message.error('网络错误');
    }
  };

  const handleSubmitKb = async (values: any) => {
    try {
      const url = editingKb 
        ? `${API_BASE}${API_PATHS.KNOWLEDGE_BASE_BY_ID(editingKb.id)}`
        : `${API_BASE}${API_PATHS.KNOWLEDGE_BASE}`;
      
      const method = editingKb ? 'PUT' : 'POST';
      
      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          ...values,
          owner_id: 'user123' // 临时用户ID
        })
      });

      if (response.ok) {
        message.success(editingKb ? '知识库更新成功' : '知识库创建成功');
        setIsModalVisible(false);
        fetchKnowledgeBases();
      } else {
        message.error('操作失败');
      }
    } catch (error) {
      message.error('网络错误');
    }
  };

  const handleUploadDocument = async (values: any) => {
    try {
      console.log('开始上传文档:', values);
      console.log('选中的知识库ID:', selectedKb?.id);
      
      if (!selectedKb?.id) {
        message.error('请先选择知识库');
        return;
      }

      console.log('values.file:', values.file);
      
      // 检查文件对象的结构 - 可能是数组或单个对象
      let fileObj;
      if (Array.isArray(values.file)) {
        if (!values.file[0]) {
          message.error('请选择文件');
          return;
        }
        fileObj = values.file[0];
      } else if (values.file && values.file.file) {
        // 如果是 {file: {...}} 结构
        fileObj = values.file.file;
      } else {
        message.error('请选择文件');
        return;
      }
      
      console.log('文件对象:', fileObj);
      
      // Ant Design Upload组件返回的文件对象结构
      let file;
      if (fileObj.originFileObj) {
        file = fileObj.originFileObj;
      } else if (fileObj.file) {
        file = fileObj.file;
      } else if (fileObj instanceof File) {
        file = fileObj;
      } else {
        console.error('无法识别的文件对象结构:', fileObj);
        message.error('文件对象无效');
        return;
      }
      
      console.log('最终文件对象:', file);
      
      const formData = new FormData();
      formData.append('file', file);
      if (values.metadata) {
        formData.append('metadata', values.metadata);
      }

              console.log('准备发送请求到:', `${API_BASE}${API_PATHS.KNOWLEDGE_BASE_UPLOAD(selectedKb.id)}`);

      const response = await fetch(
                  `${API_BASE}${API_PATHS.KNOWLEDGE_BASE_UPLOAD(selectedKb.id)}`,
        {
          method: 'POST',
          body: formData
        }
      );

      console.log('响应状态:', response.status);
      console.log('响应头:', response.headers);

      if (response.ok) {
        const result = await response.json();
        console.log('上传成功:', result);
        message.success('文档上传成功，正在处理中...');
        setIsUploadModalVisible(false);
        uploadForm.resetFields();
        if (selectedKb) {
          fetchDocuments(selectedKb.id);
          // 启动轮询以显示处理进度
          setTimeout(() => {
            if (selectedKb) {
              startPollingDocuments(selectedKb.id);
            }
          }, 1000);
        }
      } else {
        let errorMessage = `上传失败: ${response.status} ${response.statusText}`;
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            errorMessage = `上传失败: ${errorData.detail}`;
          }
        } catch (e) {
          const errorText = await response.text();
          if (errorText) {
            errorMessage = `上传失败: ${errorText}`;
          }
        }
        console.error('上传失败:', errorMessage);
        message.error(errorMessage);
      }
    } catch (error) {
      console.error('上传错误:', error);
      message.error(`网络错误: ${error}`);
    }
  };

  const handleDeleteDocument = async (docId: number) => {
    try {
      const response = await fetch(`${API_BASE}${API_PATHS.KNOWLEDGE_BASE_DOCUMENT(docId)}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        message.success('文档删除成功');
        if (selectedKb) {
          fetchDocuments(selectedKb.id);
        }
      } else {
        message.error('删除失败');
      }
    } catch (error) {
      message.error('网络错误');
    }
  };

  const handleSelectKb = (kb: KnowledgeBase) => {
    setSelectedKb(kb);
    fetchDocuments(kb.id);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'green';
      case 'processing': return 'blue';
      case 'failed': return 'red';
      default: return 'default';
    }
  };

  return (
    <div className="knowledge-base-page">
      <div className="kb-header">
        <h1>知识库管理</h1>
        <Button 
          type="primary" 
          icon={<PlusOutlined />}
          onClick={handleCreateKb}
        >
          创建知识库
        </Button>
      </div>

      <div className="kb-content">
        <div className="kb-sidebar">
          <h3>知识库列表</h3>
          <div className="kb-list">
            {knowledgeBases.map(kb => (
              <Card
                key={kb.id}
                className={`kb-item ${selectedKb?.id === kb.id ? 'selected' : ''}`}
                onClick={() => handleSelectKb(kb)}
              >
                <div className="kb-item-header">
                  <h4>{kb.display_name}</h4>
                  <Space>
                    <Tag color={kb.is_public ? 'green' : 'blue'}>
                      {kb.is_public ? '公开' : '私有'}
                    </Tag>
                    <Tag color={kb.is_active ? 'green' : 'red'}>
                      {kb.is_active ? '激活' : '停用'}
                    </Tag>
                  </Space>
                </div>
                <p className="kb-description">{kb.description || '暂无描述'}</p>
                <div className="kb-actions">
                  <Button 
                    size="small" 
                    icon={<EditOutlined />}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleEditKb(kb);
                    }}
                  >
                    编辑
                  </Button>
                  <Popconfirm
                    title="确定要删除这个知识库吗？"
                    onConfirm={() => handleDeleteKb(kb.id)}
                  >
                    <Button 
                      size="small" 
                      danger 
                      icon={<DeleteOutlined />}
                      onClick={(e) => e.stopPropagation()}
                    >
                      删除
                    </Button>
                  </Popconfirm>
                </div>
              </Card>
            ))}
          </div>
        </div>

        <div className="kb-main">
          {selectedKb ? (
            <div className="kb-detail">
              <div className="kb-detail-header">
                <h2>{selectedKb.display_name}</h2>
                <Button 
                  type="primary" 
                  icon={<UploadOutlined />}
                  onClick={() => setIsUploadModalVisible(true)}
                >
                  上传文档
                </Button>
              </div>
              
              <div className="kb-detail-content">
                <p><strong>描述:</strong> {selectedKb.description || '暂无描述'}</p>
                <p><strong>所有者:</strong> {selectedKb.owner_id}</p>
                <p><strong>创建时间:</strong> {new Date(selectedKb.created_at).toLocaleString()}</p>
              </div>

              <div className="documents-section">
                <h3>文档列表</h3>
                <div className="documents-list">
                  {documents.map(doc => {
                    const metadata = doc.document_metadata || doc.metadata || {};
                    const error = metadata.error;
                    const chunkCount = metadata.chunk_count;
                    
                    return (
                      <Card key={doc.id} className="document-item">
                        <div className="document-header">
                          <h4>{doc.name}</h4>
                          <Space>
                            <Tag color={getStatusColor(doc.status)}>
                              {doc.status === 'processing' ? '处理中...' : 
                               doc.status === 'completed' ? '已完成' : 
                               doc.status === 'failed' ? '失败' : 
                               doc.status === 'pending' ? '等待中' : doc.status}
                            </Tag>
                            <Tag>{doc.file_type}</Tag>
                            {chunkCount && (
                              <Tag color="blue">分块数: {chunkCount}</Tag>
                            )}
                          </Space>
                        </div>
                        <div className="document-content">
                          <p><strong>大小:</strong> {doc.file_size ? `${doc.file_size} bytes` : '未知'}</p>
                          <p><strong>创建时间:</strong> {new Date(doc.created_at).toLocaleString()}</p>
                          {error && (
                            <div style={{ 
                              marginTop: '8px', 
                              padding: '8px', 
                              backgroundColor: '#fff2f0', 
                              border: '1px solid #ffccc7',
                              borderRadius: '4px'
                            }}>
                              <p style={{ color: '#ff4d4f', margin: 0, fontWeight: 'bold' }}>
                                ❌ 处理失败:
                              </p>
                              <p style={{ color: '#cf1322', margin: '4px 0 0 0', fontSize: '12px' }}>
                                {error}
                              </p>
                            </div>
                          )}
                          {(doc.status === 'processing' || doc.status === 'chunking') && (
                            <div style={{ 
                              marginTop: '8px', 
                              padding: '8px', 
                              backgroundColor: '#e6f7ff', 
                              border: '1px solid #91d5ff',
                              borderRadius: '4px'
                            }}>
                              <p style={{ color: '#1890ff', margin: 0, fontSize: '12px' }}>
                                ⏳ 正在处理文档，请稍候...
                              </p>
                            </div>
                          )}
                          {doc.status === 'chunked' && (
                            <div style={{ 
                              marginTop: '8px', 
                              padding: '8px', 
                              backgroundColor: '#f6ffed', 
                              border: '1px solid #b7eb8f',
                              borderRadius: '4px'
                            }}>
                              <p style={{ color: '#52c41a', margin: 0, fontSize: '12px', fontWeight: 'bold' }}>
                                ✅ 分块完成
                              </p>
                              {doc.kg_extraction_status === 'processing' && (
                                <>
                                  {(() => {
                                    const status = documentStatuses[doc.id];
                                    const progress = status?.kg_extraction_progress || doc.kg_extraction_progress;
                                    const percent = progress && progress.total_chunks > 0
                                      ? Math.round((progress.processed / progress.total_chunks) * 100)
                                      : 0;
                                    return (
                                      <>
                                        <p style={{ color: '#52c41a', margin: '4px 0 0 0', fontSize: '11px' }}>
                                          📊 正在抽取知识图谱...
                                        </p>
                                        {progress && (
                                          <>
                                            <Progress 
                                              percent={percent}
                                              size="small"
                                              status="active"
                                              style={{ marginTop: '4px' }}
                                            />
                                            <p style={{ color: '#52c41a', margin: '4px 0 0 0', fontSize: '11px' }}>
                                              已处理: {progress.processed} / {progress.total_chunks}
                                              {progress.failed > 0 && ` (失败: ${progress.failed})`}
                                            </p>
                                          </>
                                        )}
                                      </>
                                    );
                                  })()}
                                </>
                              )}
                              {doc.kg_extraction_status === 'completed' && (
                                <p style={{ color: '#52c41a', margin: '4px 0 0 0', fontSize: '11px' }}>
                                  ✅ 知识图谱抽取完成
                                  {(() => {
                                    const status = documentStatuses[doc.id];
                                    if (status && status.total_triples > 0) {
                                      return ` (${status.total_triples} 个三元组)`;
                                    }
                                    return '';
                                  })()}
                                </p>
                              )}
                            </div>
                          )}
                        </div>
                        <div className="document-actions">
                          <Popconfirm
                            title="确定要删除这个文档吗？"
                            onConfirm={() => handleDeleteDocument(doc.id)}
                          >
                            <Button size="small" danger icon={<DeleteOutlined />}>
                              删除
                            </Button>
                          </Popconfirm>
                        </div>
                      </Card>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div className="kb-empty">
              <p>请选择一个知识库查看详情</p>
            </div>
          )}
        </div>
      </div>

      {/* 知识库编辑模态框 */}
      <Modal
        title={editingKb ? '编辑知识库' : '创建知识库'}
        open={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        footer={null}
        width={600}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmitKb}
        >
          <Form.Item
            name="name"
            label="知识库名称"
            rules={[{ required: true, message: '请输入知识库名称' }]}
          >
            <Input placeholder="请输入知识库名称" />
          </Form.Item>

          <Form.Item
            name="display_name"
            label="显示名称"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="请输入显示名称" />
          </Form.Item>

          <Form.Item
            name="description"
            label="描述"
          >
            <TextArea rows={3} placeholder="请输入描述" />
          </Form.Item>

          <Form.Item
            name="is_public"
            label="是否公开"
            initialValue={false}
          >
            <Select>
              <Option value={true}>公开</Option>
              <Option value={false}>私有</Option>
            </Select>
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                {editingKb ? '更新' : '创建'}
              </Button>
              <Button onClick={() => setIsModalVisible(false)}>
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 文档上传模态框 */}
      <Modal
        title="上传文档"
        open={isUploadModalVisible}
        onCancel={() => setIsUploadModalVisible(false)}
        footer={null}
        width={500}
      >
        <Form
          form={uploadForm}
          layout="vertical"
          onFinish={handleUploadDocument}
        >
          <Form.Item
            name="file"
            label="选择文件"
            rules={[{ required: true, message: '请选择文件' }]}
          >
            <Upload.Dragger
              beforeUpload={() => false}
              accept=".txt,.md,.pdf,.doc,.docx"
              maxCount={1}
            >
              <p className="ant-upload-drag-icon">
                <UploadOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
              <p className="ant-upload-hint">
                支持 txt, md, pdf, doc, docx 格式
              </p>
            </Upload.Dragger>
          </Form.Item>

          <Form.Item
            name="metadata"
            label="元数据 (JSON格式)"
          >
            <TextArea 
              rows={3} 
              placeholder='{"author": "张三", "category": "技术"}'
            />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                上传
              </Button>
              <Button onClick={() => setIsUploadModalVisible(false)}>
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default KnowledgeBasePage; 