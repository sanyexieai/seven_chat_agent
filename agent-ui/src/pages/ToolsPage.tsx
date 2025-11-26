import React, { useState, useEffect } from 'react';
import { API_PATHS } from '../config/api';
import {
  Card,
  Table,
  Button,
  Input,
  Select,
  Modal,
  Form,
  Input as AntInput,
  Tabs,
  Tag,
  Space,
  message,
  Descriptions,
  Typography,
  Divider,
  Popconfirm,
} from 'antd';
import {
  SearchOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

const { TextArea } = AntInput;
const { Title, Text } = Typography;
const { TabPane } = Tabs;

interface Tool {
  name: string;
  description: string;
  parameters: any;
  category: string;
  type: 'builtin' | 'mcp' | 'temporary';
  container_type?: string;  // 容器类型
  container_config?: any;   // 容器配置
  score?: number;           // 工具评分（持久化后从后端返回）
}

interface TemporaryTool {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  code: string;
  input_schema?: any;
  output_schema?: any;
  examples?: any[];
  container_type?: string;
  container_config?: any;
  is_active: boolean;
  is_temporary: boolean;
  created_at: string;
  updated_at: string;
}

interface ToolStatistics {
  total_tools: number;
  categories: Record<string, number>;
  types: Record<string, number>;
}

const ToolsPage: React.FC = () => {
  const [tools, setTools] = useState<Tool[]>([]);
  const [temporaryTools, setTemporaryTools] = useState<TemporaryTool[]>([]);
  const [statistics, setStatistics] = useState<ToolStatistics | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState<string>('all');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [showTemporaryToolModal, setShowTemporaryToolModal] = useState(false);
  const [editingTool, setEditingTool] = useState<TemporaryTool | null>(null);
  const [toolForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState('all');

  // 加载工具列表
  const loadTools = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (selectedType !== 'all') {
        params.append('tool_type', selectedType);
      }
      if (selectedCategory !== 'all') {
        params.append('category', selectedCategory);
      }
      
      const url = `${API_PATHS.TOOLS}${params.toString() ? '?' + params.toString() : ''}`;
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        setTools(data.tools || []);
        setStatistics(data.statistics || null);
      } else {
        message.error('加载工具列表失败');
      }
    } catch (error) {
      message.error('加载工具列表失败');
    } finally {
      setLoading(false);
    }
  };

  // 加载临时工具列表
  const loadTemporaryTools = async () => {
    try {
      const response = await fetch(API_PATHS.TOOLS_TEMPORARY);
      if (response.ok) {
        const data = await response.json();
        setTemporaryTools(data || []);
      }
    } catch (error) {
      message.error('加载临时工具失败');
    }
  };

  // 搜索工具
  const searchTools = async () => {
    if (!searchQuery.trim()) {
      loadTools();
      return;
    }
    try {
      setLoading(true);
      const response = await fetch(API_PATHS.TOOLS_SEARCH(searchQuery));
      if (response.ok) {
        const data = await response.json();
        setTools(data || []);
      } else {
        message.error('搜索工具失败');
      }
    } catch (error) {
      message.error('搜索工具失败');
    } finally {
      setLoading(false);
    }
  };

  // 创建临时工具
  const createTemporaryTool = async (values: any) => {
    try {
      setLoading(true);
      const response = await fetch(API_PATHS.TOOLS_TEMPORARY, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(values),
      });
      if (response.ok) {
        message.success('创建临时工具成功');
        setShowTemporaryToolModal(false);
        toolForm.resetFields();
        await loadTemporaryTools();
        await loadTools();
      } else {
        const error = await response.json();
        message.error(error.detail || '创建临时工具失败');
      }
    } catch (error) {
      message.error('创建临时工具失败');
    } finally {
      setLoading(false);
    }
  };

  // 更新临时工具
  const updateTemporaryTool = async (id: number, values: any) => {
    try {
      setLoading(true);
      const response = await fetch(API_PATHS.TOOLS_TEMPORARY_BY_ID(id), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(values),
      });
      if (response.ok) {
        message.success('更新临时工具成功');
        setShowTemporaryToolModal(false);
        setEditingTool(null);
        toolForm.resetFields();
        await loadTemporaryTools();
        await loadTools();
      } else {
        const error = await response.json();
        message.error(error.detail || '更新临时工具失败');
      }
    } catch (error) {
      message.error('更新临时工具失败');
    } finally {
      setLoading(false);
    }
  };

  // 删除临时工具
  const deleteTemporaryTool = async (id: number) => {
    try {
      setLoading(true);
      const response = await fetch(API_PATHS.TOOLS_TEMPORARY_BY_ID(id), {
        method: 'DELETE',
      });
      if (response.ok) {
        message.success('删除临时工具成功');
        await loadTemporaryTools();
        await loadTools();
      } else {
        message.error('删除临时工具失败');
      }
    } catch (error) {
      message.error('删除临时工具失败');
    } finally {
      setLoading(false);
    }
  };

  // 重新加载工具
  const reloadTools = async (type?: string) => {
    try {
      setLoading(true);
      const url = type ? API_PATHS.TOOLS_RELOAD(type) : API_PATHS.TOOLS_RELOAD();
      const response = await fetch(url, {
        method: 'POST',
      });
      if (response.ok) {
        message.success('重新加载工具成功');
        await loadTools();
        await loadTemporaryTools();
      } else {
        message.error('重新加载工具失败');
      }
    } catch (error) {
      message.error('重新加载工具失败');
    } finally {
      setLoading(false);
    }
  };

  const [showContainerModal, setShowContainerModal] = useState(false);
  const [editingContainerTool, setEditingContainerTool] = useState<Tool | null>(null);
  const [containerForm] = Form.useForm();

  // 执行工具（显示工具详情）
  const executeTool = async (toolName: string) => {
    const tool = tools.find(t => t.name === toolName);
    Modal.info({
      title: '工具详情',
      width: 600,
      content: (
        <div>
          <Descriptions column={1} bordered>
            <Descriptions.Item label="工具名称">{toolName}</Descriptions.Item>
            <Descriptions.Item label="描述">{tool?.description || '-'}</Descriptions.Item>
            <Descriptions.Item label="类型">
              <Tag color={tool?.type === 'builtin' ? 'blue' : tool?.type === 'mcp' ? 'green' : 'orange'}>
                {tool?.type === 'builtin' ? '内置' : tool?.type === 'mcp' ? 'MCP' : '临时'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="类别">{tool?.category || '-'}</Descriptions.Item>
            <Descriptions.Item label="绑定容器">
              {tool?.container_type && tool.container_type !== 'none' ? (
                <Tag color={tool.container_type === 'browser' ? 'cyan' : 'purple'}>
                  {tool.container_type === 'browser' ? '浏览容器' : '文件容器'}
                </Tag>
              ) : (
                <Tag color="default">无容器</Tag>
              )}
            </Descriptions.Item>
            {tool?.container_config && Object.keys(tool.container_config).length > 0 && (
              <Descriptions.Item label="容器配置">
                <pre style={{ margin: 0, fontSize: '12px', maxHeight: '200px', overflow: 'auto' }}>
                  {JSON.stringify(tool.container_config, null, 2)}
                </pre>
              </Descriptions.Item>
            )}
            <Descriptions.Item label="参数Schema">
              <pre style={{ margin: 0, fontSize: '12px', maxHeight: '200px', overflow: 'auto' }}>
                {JSON.stringify(tool?.parameters || {}, null, 2)}
              </pre>
            </Descriptions.Item>
          </Descriptions>
          <Divider />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                Modal.destroyAll();
                editContainer(tool!);
              }}
            >
              编辑容器配置
            </Button>
            <Button onClick={() => Modal.destroyAll()}>关闭</Button>
          </Space>
        </div>
      ),
    });
  };

  // 编辑容器配置
  const editContainer = (tool: Tool) => {
    setEditingContainerTool(tool);
    containerForm.setFieldsValue({
      container_type: tool.container_type || 'none',
      container_config: tool.container_config ? JSON.stringify(tool.container_config, null, 2) : '{}',
    });
    setShowContainerModal(true);
  };

  // 保存容器配置
  const saveContainerConfig = async () => {
    try {
      const values = await containerForm.validateFields();
      let containerConfig = {};
      try {
        containerConfig = values.container_config ? JSON.parse(values.container_config) : {};
      } catch (e) {
        message.error('容器配置JSON格式错误');
        return;
      }

      if (!editingContainerTool) return;

      const response = await fetch(API_PATHS.TOOLS_CONTAINER(editingContainerTool.name), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          container_type: values.container_type,
          container_config: containerConfig,
        }),
      });

      if (response.ok) {
        message.success('容器配置更新成功');
        setShowContainerModal(false);
        setEditingContainerTool(null);
        containerForm.resetFields();
        await loadTools();
      } else {
        const error = await response.json();
        message.error(error.detail || '更新容器配置失败');
      }
    } catch (error) {
      message.error('更新容器配置失败');
    }
  };

  // 编辑临时工具
  const editTemporaryTool = (tool: TemporaryTool) => {
    setEditingTool(tool);
    toolForm.setFieldsValue({
      name: tool.name,
      display_name: tool.display_name,
      description: tool.description,
      code: tool.code,
      input_schema: tool.input_schema ? JSON.stringify(tool.input_schema, null, 2) : '',
      output_schema: tool.output_schema ? JSON.stringify(tool.output_schema, null, 2) : '',
      examples: tool.examples ? JSON.stringify(tool.examples, null, 2) : '',
      container_type: tool.container_type || 'none',
      container_config: tool.container_config ? JSON.stringify(tool.container_config, null, 2) : '{}',
    });
    setShowTemporaryToolModal(true);
  };

  // 初始化
  useEffect(() => {
    loadTools();
    loadTemporaryTools();
  }, []);

  // 当筛选条件变化时重新加载
  useEffect(() => {
    if (activeTab === 'all') {
      loadTools();
    }
  }, [selectedType, selectedCategory, activeTab]);

  // 工具表格列定义
  const toolColumns: ColumnsType<Tool> = [
    {
      title: '工具名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type: string) => {
        const colorMap: Record<string, string> = {
          builtin: 'blue',
          mcp: 'green',
          temporary: 'orange',
        };
        const labelMap: Record<string, string> = {
          builtin: '内置',
          mcp: 'MCP',
          temporary: '临时',
        };
        return <Tag color={colorMap[type] || 'default'}>{labelMap[type] || type}</Tag>;
      },
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 100,
    },
    {
      title: '评分',
      dataIndex: 'score',
      key: 'score',
      width: 100,
      render: (score?: number) => (
        <Tag color={score && score >= 3 ? 'green' : score && score >= 1.5 ? 'blue' : 'red'}>
          {score !== undefined ? score.toFixed(2) : '—'}
        </Tag>
      ),
    },
    {
      title: '绑定容器',
      dataIndex: 'container_type',
      key: 'container_type',
      width: 120,
      render: (containerType: string, record: Tool) => {
        if (!containerType || containerType === 'none') {
          return <Tag color="default">无容器</Tag>;
        }
        const colorMap: Record<string, string> = {
          browser: 'cyan',
          file: 'purple',
        };
        const labelMap: Record<string, string> = {
          browser: '浏览容器',
          file: '文件容器',
        };
        return (
          <Tag color={colorMap[containerType] || 'default'}>
            {labelMap[containerType] || containerType}
          </Tag>
        );
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            icon={<PlayCircleOutlined />}
            onClick={() => executeTool(record.name)}
          >
            详情
          </Button>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => editContainer(record)}
          >
            编辑容器
          </Button>
        </Space>
      ),
    },
  ];

  // 临时工具表格列定义
  const temporaryToolColumns: ColumnsType<TemporaryTool> = [
    {
      title: '名称',
      dataIndex: 'display_name',
      key: 'display_name',
      width: 200,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 100,
      render: (isActive: boolean) => (
        <Tag color={isActive ? 'green' : 'red'}>{isActive ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '绑定容器',
      key: 'container_type',
      width: 120,
      render: (_, record: TemporaryTool) => {
        // 优先使用数据库中的容器类型
        const containerType = record.container_type || 'none';
        
        if (containerType === 'none') {
          return <Tag color="default">无容器</Tag>;
        }
        const colorMap: Record<string, string> = {
          browser: 'cyan',
          file: 'purple',
        };
        const labelMap: Record<string, string> = {
          browser: '浏览容器',
          file: '文件容器',
        };
        return (
          <Tag color={colorMap[containerType] || 'default'}>
            {labelMap[containerType] || containerType}
          </Tag>
        );
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => new Date(text).toLocaleString(),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => editTemporaryTool(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这个临时工具吗？"
            onConfirm={() => deleteTemporaryTool(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button
              type="link"
              danger
              icon={<DeleteOutlined />}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={2}>工具管理</Title>
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => reloadTools()}
              loading={loading}
            >
              重新加载
            </Button>
            {activeTab === 'temporary' && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => {
                  setEditingTool(null);
                  toolForm.resetFields();
                  setShowTemporaryToolModal(true);
                }}
              >
                创建临时工具
              </Button>
            )}
          </Space>
        </div>

        {statistics && (
          <div style={{ marginBottom: '16px' }}>
            <Space>
              <Text>总工具数: <strong>{statistics.total_tools}</strong></Text>
              {statistics.types && Object.entries(statistics.types).map(([type, count]) => (
                <Text key={type}>
              {type === 'builtin' ? '内置' : type === 'mcp' ? 'MCP' : '临时'}: <strong>{count}</strong>
            </Text>
              ))}
            </Space>
          </div>
        )}

        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="所有工具" key="all">
            <div style={{ marginBottom: '16px' }}>
              <Space>
                <Input
                  placeholder="搜索工具..."
                  prefix={<SearchOutlined />}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onPressEnter={searchTools}
                  style={{ width: 300 }}
                />
                <Button onClick={searchTools}>搜索</Button>
                <Select
                  value={selectedType}
                  onChange={setSelectedType}
                  style={{ width: 120 }}
                >
                  <Select.Option value="all">所有类型</Select.Option>
                  <Select.Option value="builtin">内置工具</Select.Option>
                  <Select.Option value="mcp">MCP工具</Select.Option>
                  <Select.Option value="temporary">临时工具</Select.Option>
                </Select>
                <Select
                  value={selectedCategory}
                  onChange={setSelectedCategory}
                  style={{ width: 120 }}
                >
                  <Select.Option value="all">所有类别</Select.Option>
                  <Select.Option value="search">搜索</Select.Option>
                  <Select.Option value="report">报告</Select.Option>
                  <Select.Option value="file">文件</Select.Option>
                  <Select.Option value="utility">工具</Select.Option>
                </Select>
              </Space>
            </div>
            <Table
              columns={toolColumns}
              dataSource={tools}
              rowKey="name"
              loading={loading}
              pagination={{ pageSize: 20 }}
            />
          </TabPane>
          <TabPane tab="临时工具" key="temporary">
            <Table
              columns={temporaryToolColumns}
              dataSource={temporaryTools}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 20 }}
            />
          </TabPane>
        </Tabs>
      </Card>

      {/* 创建/编辑临时工具模态框 */}
      <Modal
        title={editingTool ? '编辑临时工具' : '创建临时工具'}
        open={showTemporaryToolModal}
        onCancel={() => {
          setShowTemporaryToolModal(false);
          setEditingTool(null);
          toolForm.resetFields();
        }}
        onOk={() => {
          toolForm.validateFields().then((values) => {
            try {
              if (values.input_schema) {
                values.input_schema = JSON.parse(values.input_schema);
              }
              if (values.output_schema) {
                values.output_schema = JSON.parse(values.output_schema);
              }
              if (values.examples) {
                values.examples = JSON.parse(values.examples);
              }
              if (values.container_config) {
                values.container_config = JSON.parse(values.container_config);
              }
              if (editingTool) {
                updateTemporaryTool(editingTool.id, values);
              } else {
                createTemporaryTool(values);
              }
            } catch (error) {
              message.error('JSON格式错误，请检查输入');
            }
          });
        }}
        width={800}
        confirmLoading={loading}
      >
        <Form
          form={toolForm}
          layout="vertical"
        >
          <Form.Item
            name="name"
            label="工具名称"
            rules={[{ required: true, message: '请输入工具名称' }]}
          >
            <AntInput placeholder="工具名称（唯一标识）" />
          </Form.Item>
          <Form.Item
            name="display_name"
            label="显示名称"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <AntInput placeholder="显示名称" />
          </Form.Item>
          <Form.Item
            name="description"
            label="描述"
          >
            <TextArea rows={2} placeholder="工具描述" />
          </Form.Item>
          <Form.Item
            name="code"
            label="工具代码"
            rules={[{ required: true, message: '请输入工具代码' }]}
          >
            <TextArea
              rows={10}
              placeholder="Python代码，执行后应将结果赋值给result变量"
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
          <Form.Item
            name="input_schema"
            label="输入Schema (JSON)"
          >
            <TextArea
              rows={4}
              placeholder='{"type": "object", "properties": {...}, "required": [...]}'
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
          <Form.Item
            name="output_schema"
            label="输出Schema (JSON)"
          >
            <TextArea
              rows={4}
              placeholder='{"type": "object", "properties": {...}}'
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
          <Form.Item
            name="examples"
            label="示例 (JSON数组)"
          >
            <TextArea
              rows={3}
              placeholder='[{"input": {...}, "output": {...}}]'
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
          <Form.Item
            name="container_type"
            label="容器类型"
            initialValue="none"
          >
            <Select>
              <Select.Option value="none">无容器</Select.Option>
              <Select.Option value="browser">浏览容器</Select.Option>
              <Select.Option value="file">文件容器</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="container_config"
            label="容器配置 (JSON)"
            initialValue="{}"
            rules={[
              {
                validator: (_, value) => {
                  if (!value) return Promise.resolve();
                  try {
                    JSON.parse(value);
                    return Promise.resolve();
                  } catch (e) {
                    return Promise.reject(new Error('请输入有效的JSON格式'));
                  }
                },
              },
            ]}
          >
            <TextArea
              rows={4}
              placeholder='{"workspace_dir": "files", "timeout": 30}'
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑容器配置模态框 */}
      <Modal
        title="编辑容器配置"
        open={showContainerModal}
        onCancel={() => {
          setShowContainerModal(false);
          setEditingContainerTool(null);
          containerForm.resetFields();
        }}
        onOk={saveContainerConfig}
        width={600}
      >
        <Form
          form={containerForm}
          layout="vertical"
        >
          <Form.Item
            name="container_type"
            label="容器类型"
            rules={[{ required: true, message: '请选择容器类型' }]}
          >
            <Select>
              <Select.Option value="none">无容器</Select.Option>
              <Select.Option value="browser">浏览容器</Select.Option>
              <Select.Option value="file">文件容器</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="container_config"
            label="容器配置 (JSON)"
            rules={[
              {
                validator: (_, value) => {
                  if (!value) return Promise.resolve();
                  try {
                    JSON.parse(value);
                    return Promise.resolve();
                  } catch (e) {
                    return Promise.reject(new Error('请输入有效的JSON格式'));
                  }
                },
              },
            ]}
          >
            <TextArea
              rows={8}
              placeholder='{"workspace_dir": "files", "timeout": 30}'
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ToolsPage;

