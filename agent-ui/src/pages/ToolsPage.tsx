import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Tag, Button, Modal, Descriptions, Select } from 'antd';
import { ToolOutlined, SearchOutlined, FileTextOutlined, FileOutlined } from '@ant-design/icons';
import axios from 'axios';

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
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div>
          <h2>工具管理</h2>
          <p>查看和管理可用的工具</p>
        </div>
        <Select
          value={selectedCategory}
          onChange={setSelectedCategory}
          style={{ width: 120 }}
        >
          <Option value="all">全部</Option>
          {categories.filter(cat => cat !== 'all').map(category => (
            <Option key={category} value={category}>
              {getCategoryName(category)}
            </Option>
          ))}
        </Select>
      </div>
      
      <Row gutter={[16, 16]} className="tools-grid">
        {filteredTools.map((tool) => (
          <Col xs={24} sm={12} lg={8} key={tool.name}>
            <Card
              hoverable
              className="tool-card"
              onClick={() => handleToolClick(tool)}
            >
              <div style={{ textAlign: 'center', marginBottom: '12px' }}>
                <div
                  className="tool-icon"
                  style={{ color: getCategoryColor(tool.category) }}
                >
                  {getToolIcon(tool.category)}
                </div>
              </div>
              
              <div className="tool-title">{tool.name}</div>
              <div className="tool-description">{tool.description}</div>
              
              <div className="tool-category">
                {getCategoryName(tool.category)}
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Modal
        title="工具详情"
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
          <Descriptions column={1}>
            <Descriptions.Item label="名称">{selectedTool.name}</Descriptions.Item>
            <Descriptions.Item label="描述">{selectedTool.description}</Descriptions.Item>
            <Descriptions.Item label="类别">
              <Tag color={getCategoryColor(selectedTool.category)}>
                {getCategoryName(selectedTool.category)}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="参数">
              {Object.keys(selectedTool.parameters).length > 0 
                ? JSON.stringify(selectedTool.parameters, null, 2)
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