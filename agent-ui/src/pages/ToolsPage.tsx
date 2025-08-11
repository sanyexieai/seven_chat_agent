import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Tag, Button, Modal, Descriptions, Select, Typography, Space } from 'antd';
import { ToolOutlined, SearchOutlined, FileTextOutlined, FileOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title, Paragraph } = Typography;

const { Option } = Select;

interface Tool {
  name: string;
  description: string;
  category: string;
  parameters: any;
}

const ToolsPage: React.FC = () => {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');

  useEffect(() => {
    fetchTools();
  }, []);

  const fetchTools = async () => {
    try {
      const response = await axios.get('/api/tools');
      setTools(response.data.tools || []);
    } catch (error) {
      console.error('获取工具列表失败:', error);
      // 使用模拟数据
      setTools([
        {
          name: 'web_search',
          description: '在网络上搜索信息',
          category: 'search',
          parameters: {}
        },
        {
          name: 'document_search',
          description: '在本地文档中搜索信息',
          category: 'search',
          parameters: {}
        },
        {
          name: 'data_analysis',
          description: '分析数据并生成统计信息',
          category: 'report',
          parameters: {}
        },
        {
          name: 'report_generator',
          description: '生成结构化报告',
          category: 'report',
          parameters: {}
        },
        {
          name: 'file_reader',
          description: '读取文件内容',
          category: 'file',
          parameters: {}
        },
        {
          name: 'file_writer',
          description: '写入文件内容',
          category: 'file',
          parameters: {}
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const getToolIcon = (category: string) => {
    switch (category) {
      case 'search':
        return <SearchOutlined />;
      case 'report':
        return <FileTextOutlined />;
      case 'file':
        return <FileOutlined />;
      default:
        return <ToolOutlined />;
    }
  };

  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'search':
        return '#52c41a';
      case 'report':
        return '#722ed1';
      case 'file':
        return '#faad14';
      default:
        return '#1890ff';
    }
  };

  const getCategoryName = (category: string) => {
    switch (category) {
      case 'search':
        return '搜索';
      case 'report':
        return '报告';
      case 'file':
        return '文件';
      default:
        return '工具';
    }
  };

  const filteredTools = selectedCategory === 'all' 
    ? tools 
    : tools.filter(tool => tool.category === selectedCategory);

  const handleToolClick = (tool: Tool) => {
    setSelectedTool(tool);
    setModalVisible(true);
  };

  const handleModalClose = () => {
    setModalVisible(false);
    setSelectedTool(null);
  };

  const categories = ['all', 'search', 'report', 'file'];

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        marginBottom: '24px',
        padding: '16px',
        backgroundColor: '#fff',
        borderRadius: '8px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
      }}>
        <div>
          <Title level={2} style={{ margin: 0 }}>工具管理</Title>
          <Paragraph style={{ margin: '8px 0 0 0', color: '#666' }}>
            查看和管理可用的工具
          </Paragraph>
        </div>
        <Select
          value={selectedCategory}
          onChange={setSelectedCategory}
          style={{ width: 120 }}
          placeholder="选择类别"
        >
          <Option value="all">全部</Option>
          {categories.filter(cat => cat !== 'all').map(category => (
            <Option key={category} value={category}>
              {getCategoryName(category)}
            </Option>
          ))}
        </Select>
      </div>
      
      <Row gutter={[24, 24]}>
        {filteredTools.map((tool) => (
          <Col xs={24} sm={12} lg={8} xl={6} key={tool.name}>
            <Card
              hoverable
              style={{
                height: '100%',
                cursor: 'pointer',
                transition: 'all 0.3s ease',
                border: '1px solid #f0f0f0'
              }}
              bodyStyle={{
                padding: '20px',
                textAlign: 'center',
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between'
              }}
              onClick={() => handleToolClick(tool)}
            >
              <div style={{ marginBottom: '16px' }}>
                <div
                  style={{
                    fontSize: '32px',
                    color: getCategoryColor(tool.category),
                    marginBottom: '12px'
                  }}
                >
                  {getToolIcon(tool.category)}
                </div>
                
                <div style={{
                  fontSize: '16px',
                  fontWeight: 'bold',
                  color: '#262626',
                  marginBottom: '8px'
                }}>
                  {tool.name}
                </div>
                
                <div style={{
                  fontSize: '14px',
                  color: '#666',
                  lineHeight: '1.5',
                  marginBottom: '12px'
                }}>
                  {tool.description}
                </div>
              </div>
              
              <div style={{
                display: 'flex',
                justifyContent: 'center'
              }}>
                <Tag 
                  color={getCategoryColor(tool.category)}
                  style={{
                    fontSize: '12px',
                    padding: '4px 8px',
                    borderRadius: '12px'
                  }}
                >
                  {getCategoryName(tool.category)}
                </Tag>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Modal
        title={
          <Space>
            <ToolOutlined style={{ color: '#1890ff' }} />
            工具详情
          </Space>
        }
        open={modalVisible}
        onCancel={handleModalClose}
        footer={[
          <Button key="close" onClick={handleModalClose}>
            关闭
          </Button>,
          <Button key="test" type="primary">
            测试工具
          </Button>
        ]}
        width={600}
      >
        {selectedTool && (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="名称" span={1}>
              <strong>{selectedTool.name}</strong>
            </Descriptions.Item>
            <Descriptions.Item label="描述" span={1}>
              {selectedTool.description}
            </Descriptions.Item>
            <Descriptions.Item label="类别" span={1}>
              <Tag color={getCategoryColor(selectedTool.category)}>
                {getCategoryName(selectedTool.category)}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="参数" span={1}>
              {Object.keys(selectedTool.parameters).length > 0 
                ? (
                  <pre style={{
                    backgroundColor: '#f5f5f5',
                    padding: '8px',
                    borderRadius: '4px',
                    fontSize: '12px',
                    overflow: 'auto'
                  }}>
                    {JSON.stringify(selectedTool.parameters, null, 2)}
                  </pre>
                )
                : '无参数'
              }
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default ToolsPage; 