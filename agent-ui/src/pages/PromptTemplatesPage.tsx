import React, { useState, useEffect } from 'react';
import { API_PATHS } from '../config/api';
import {
  Layout,
  Card,
  Button,
  Table,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  Space,
  message,
  Popconfirm,
  Tag,
  Typography,
  Tabs
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  ReloadOutlined,
  FileTextOutlined
} from '@ant-design/icons';
import './PromptTemplatesPage.css';

const { Title, Text } = Typography;
const { Option } = Select;
const { TextArea } = Input;

interface PromptTemplate {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  template_type: 'system' | 'user';
  content: string;
  variables?: string[];
  is_builtin: boolean;
  version?: string;
  usage_count: number;
  source_file?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const PromptTemplatesPage: React.FC = () => {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<PromptTemplate | null>(null);
  const [templateTypeFilter, setTemplateTypeFilter] = useState<string>('all');
  const [form] = Form.useForm();

  useEffect(() => {
    fetchTemplates();
  }, [templateTypeFilter]);

  const fetchTemplates = async () => {
    setLoading(true);
    try {
      const url = templateTypeFilter === 'all' 
        ? API_PATHS.PROMPT_TEMPLATES
        : `${API_PATHS.PROMPT_TEMPLATES}?template_type=${templateTypeFilter}`;
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        setTemplates(data);
      } else {
        message.error('获取提示词模板失败');
      }
    } catch (error) {
      console.error('获取提示词模板失败:', error);
      message.error('获取提示词模板失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingTemplate(null);
    form.resetFields();
    form.setFieldsValue({
      template_type: 'system',
      is_active: true,
      version: '1.0.0',
      variables: []
    });
    setModalVisible(true);
  };

  const handleEdit = (template: PromptTemplate) => {
    setEditingTemplate(template);
    form.setFieldsValue({
      name: template.name,
      display_name: template.display_name,
      description: template.description,
      template_type: template.template_type,
      content: template.content,
      variables: Array.isArray(template.variables) ? template.variables.join(', ') : '',
      version: template.version || '1.0.0',
      is_active: template.is_active
    });
    setModalVisible(true);
  };

  const handleDelete = async (templateId: number) => {
    try {
      const response = await fetch(API_PATHS.PROMPT_TEMPLATE_BY_ID(templateId), {
        method: 'DELETE'
      });
      if (response.ok) {
        message.success('删除成功');
        fetchTemplates();
      } else {
        const errorData = await response.json();
        message.error(errorData.detail || '删除失败');
      }
    } catch (error) {
      console.error('删除失败:', error);
      message.error('删除失败');
    }
  };

  const handleSubmit = async (values: any) => {
    try {
      // 处理变量列表：如果是字符串，转换为数组
      let variables: string[] = [];
      if (typeof values.variables === 'string') {
        variables = values.variables.split(',').map((v: string) => v.trim()).filter((v: string) => v);
      } else if (Array.isArray(values.variables)) {
        variables = values.variables;
      }
      
      const templateData = {
        ...values,
        variables: variables
      };

      const url = editingTemplate 
        ? API_PATHS.PROMPT_TEMPLATE_BY_ID(editingTemplate.id)
        : API_PATHS.PROMPT_TEMPLATES;
      
      const method = editingTemplate ? 'PUT' : 'POST';
      
      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(templateData),
      });

      if (response.ok) {
        message.success(editingTemplate ? '更新成功' : '创建成功');
        setModalVisible(false);
        fetchTemplates();
      } else {
        const errorData = await response.json();
        message.error(errorData.detail || (editingTemplate ? '更新失败' : '创建失败'));
      }
    } catch (error) {
      console.error('提交失败:', error);
      message.error('提交失败');
    }
  };

  const columns = [
    {
      title: '显示名称',
      dataIndex: 'display_name',
      key: 'display_name',
      render: (text: string, record: PromptTemplate) => (
        <Space>
          <Text strong>{text}</Text>
          {record.is_builtin && <Tag color="blue" icon={<CheckCircleOutlined />}>内置</Tag>}
          {!record.is_active && <Tag color="red">禁用</Tag>}
        </Space>
      )
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string) => <Text code>{text}</Text>
    },
    {
      title: '类型',
      dataIndex: 'template_type',
      key: 'template_type',
      render: (type: string) => (
        <Tag color={type === 'system' ? 'blue' : 'purple'}>
          {type === 'system' ? '系统' : '用户'}
        </Tag>
      )
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 100,
      render: (version: string) => version || <Text type="secondary">-</Text>
    },
    {
      title: '引用次数',
      dataIndex: 'usage_count',
      key: 'usage_count',
      width: 100,
      render: (count: number) => <Text>{count || 0}</Text>
    },
    {
      title: '来源文件',
      dataIndex: 'source_file',
      key: 'source_file',
      ellipsis: true,
      render: (file: string) => file ? <Text code style={{ fontSize: '12px' }}>{file}</Text> : <Text type="secondary">-</Text>
    },
    {
      title: '变量',
      dataIndex: 'variables',
      key: 'variables',
      render: (variables: string[]) => (
        variables && variables.length > 0 ? (
          <Space wrap>
            {variables.slice(0, 3).map((v, i) => (
              <Tag key={i} color="cyan">{v}</Tag>
            ))}
            {variables.length > 3 && <Tag>+{variables.length - 3}</Tag>}
          </Space>
        ) : <Text type="secondary">无</Text>
      )
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (text: string, record: PromptTemplate) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          {!record.is_builtin && (
            <Popconfirm
              title="确定要删除这个提示词模板吗？"
              onConfirm={() => handleDelete(record.id)}
            >
              <Button type="link" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      )
    }
  ];

  const systemTemplates = templates.filter(t => t.template_type === 'system');
  const userTemplates = templates.filter(t => t.template_type === 'user');

  return (
    <Layout className="prompt-templates-layout">
      <div className="prompt-templates-container">
        <div className="prompt-templates-header">
          <Title level={2}>
            <FileTextOutlined style={{ marginRight: 8 }} />
            提示词模板管理
          </Title>
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleCreate}
            >
              添加模板
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchTemplates}
            >
              刷新
            </Button>
          </Space>
        </div>

        <Card>
          <Tabs
            defaultActiveKey="all"
            onChange={(key) => setTemplateTypeFilter(key)}
            items={[
              {
                key: 'all',
                label: `全部 (${templates.length})`,
                children: (
                  <Table
                    columns={columns}
                    dataSource={templates}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 20 }}
                  />
                )
              },
              {
                key: 'system',
                label: `系统提示词 (${systemTemplates.length})`,
                children: (
                  <Table
                    columns={columns}
                    dataSource={systemTemplates}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 20 }}
                  />
                )
              },
              {
                key: 'user',
                label: `用户提示词 (${userTemplates.length})`,
                children: (
                  <Table
                    columns={columns}
                    dataSource={userTemplates}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 20 }}
                  />
                )
              }
            ]}
          />
        </Card>

        <Modal
          title={editingTemplate ? '编辑提示词模板' : '添加提示词模板'}
          open={modalVisible}
          onCancel={() => setModalVisible(false)}
          footer={null}
          width={800}
        >
          <Form
            form={form}
            layout="vertical"
            onFinish={handleSubmit}
          >
            <Form.Item
              name="name"
              label="模板名称（唯一标识）"
              rules={[{ required: true, message: '请输入模板名称' }]}
              extra={editingTemplate ? '模板名称不可修改' : '用于代码中引用，建议使用下划线命名'}
            >
              <Input 
                placeholder="例如: auto_infer_system" 
                disabled={!!editingTemplate}
              />
            </Form.Item>

            <Form.Item
              name="display_name"
              label="显示名称"
              rules={[{ required: true, message: '请输入显示名称' }]}
            >
              <Input placeholder="例如: 自动推理系统提示词" />
            </Form.Item>

            <Form.Item
              name="description"
              label="描述"
            >
              <TextArea rows={2} placeholder="请输入描述" />
            </Form.Item>

            <Form.Item
              name="template_type"
              label="模板类型"
              rules={[{ required: true, message: '请选择模板类型' }]}
            >
              <Select disabled={!!editingTemplate}>
                <Option value="system">系统提示词</Option>
                <Option value="user">用户提示词</Option>
              </Select>
            </Form.Item>

            <Form.Item
              name="content"
              label="模板内容"
              rules={[{ required: true, message: '请输入模板内容' }]}
              extra="支持使用 {变量名} 作为占位符，例如: {tool_name}, {message}"
            >
              <TextArea 
                rows={12} 
                placeholder="请输入提示词模板内容..."
                style={{ fontFamily: 'monospace' }}
              />
            </Form.Item>

            <Form.Item
              name="variables"
              label="变量列表"
              extra="模板中使用的变量名，用逗号分隔，例如: tool_name,message,previous_output"
            >
              <Input 
                placeholder="tool_name, message, previous_output"
              />
            </Form.Item>

            <Form.Item
              name="version"
              label="版本号"
              rules={[{ required: true, message: '请输入版本号' }]}
              extra="例如: 1.0.0"
            >
              <Input placeholder="1.0.0" />
            </Form.Item>

            <Form.Item
              name="is_active"
              label="启用"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>

            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit">
                  {editingTemplate ? '更新' : '创建'}
                </Button>
                <Button onClick={() => setModalVisible(false)}>
                  取消
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </Layout>
  );
};

export default PromptTemplatesPage;

