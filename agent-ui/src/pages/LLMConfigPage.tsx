import React, { useState, useEffect } from 'react';
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
  Typography
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  SettingOutlined,
  CheckCircleOutlined,
  ReloadOutlined,
  InfoCircleOutlined
} from '@ant-design/icons';
import './LLMConfigPage.css';

const { Title, Text } = Typography;
const { Option } = Select;
const { TextArea } = Input;

interface LLMConfig {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  provider: string;
  model_name: string;
  api_key?: string;
  api_base?: string;
  config?: any;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const LLMConfigPage: React.FC = () => {
  const [configs, setConfigs] = useState<LLMConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingConfig, setEditingConfig] = useState<LLMConfig | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<string>('');
  const [form] = Form.useForm();

  useEffect(() => {
    fetchConfigs();
  }, []);

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/llm-config/');
      if (response.ok) {
        const data = await response.json();
        setConfigs(data);
      } else {
        message.error('获取LLM配置失败');
      }
    } catch (error) {
      console.error('获取LLM配置失败:', error);
      message.error('获取LLM配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingConfig(null);
    setSelectedProvider('');
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (config: LLMConfig) => {
    setEditingConfig(config);
    setSelectedProvider(config.provider);
    form.setFieldsValue({
      name: config.name,
      display_name: config.display_name,
      description: config.description,
      provider: config.provider,
      model_name: config.model_name,
      api_key: config.api_key,
      api_base: config.api_base,
      config: config.config ? JSON.stringify(config.config, null, 2) : '',
      is_default: config.is_default
    });
    setModalVisible(true);
  };

  const handleDelete = async (configId: number) => {
    try {
      const response = await fetch(`/api/llm-config/${configId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        message.success('删除成功');
        fetchConfigs();
        // 自动重新加载配置
        await handleReloadConfig();
      } else {
        message.error('删除失败');
      }
    } catch (error) {
      console.error('删除失败:', error);
      message.error('删除失败');
    }
  };

  const handleSetDefault = async (configId: number) => {
    try {
      const response = await fetch(`/api/llm-config/${configId}/set-default`, {
        method: 'POST'
      });
      if (response.ok) {
        message.success('设置默认配置成功');
        fetchConfigs();
        // 自动重新加载配置
        await handleReloadConfig();
      } else {
        message.error('设置默认配置失败');
      }
    } catch (error) {
      console.error('设置默认配置失败:', error);
      message.error('设置默认配置失败');
    }
  };

  const handleRefreshConfig = async () => {
    try {
      const loadingMessage = message.loading('正在刷新配置...', 0);
      const response = await fetch('/api/llm-config/refresh', {
        method: 'POST'
      });
      loadingMessage();
      if (response.ok) {
        message.success('配置刷新成功');
      } else {
        message.error('配置刷新失败');
      }
    } catch (error) {
      console.error('配置刷新失败:', error);
      message.error('配置刷新失败');
    }
  };

  const handleReloadConfig = async () => {
    try {
      const loadingMessage = message.loading('正在重新加载配置...', 0);
      const response = await fetch('/api/llm-config/reload', {
        method: 'POST'
      });
      loadingMessage();
      if (response.ok) {
        message.success('配置重新加载成功');
      } else {
        message.error('配置重新加载失败');
      }
    } catch (error) {
      console.error('配置重新加载失败:', error);
      message.error('配置重新加载失败');
    }
  };

  const handleQuickOllamaConfig = () => {
    setSelectedProvider('ollama');
    form.setFieldsValue({
      name: 'ollama_qwen',
      display_name: 'Ollama Qwen 模型',
      description: 'Ollama Qwen 模型配置',
      provider: 'ollama',
      model_name: 'qwen3:32b',
      api_key: '',
      api_base: 'http://localhost:11434',
      config: JSON.stringify({
        temperature: 0.7,
        max_tokens: 2048
      }, null, 2),
      is_default: false
    });
    setModalVisible(true);
  };

  const handleQuickDeepSeekConfig = () => {
    setSelectedProvider('deepseek');
    form.setFieldsValue({
      name: 'deepseek_chat',
      display_name: 'DeepSeek Chat',
      description: 'DeepSeek Chat 模型配置',
      provider: 'deepseek',
      model_name: 'deepseek-chat',
      api_key: '',
      api_base: 'https://api.deepseek.com',
      config: JSON.stringify({
        temperature: 0.7,
        max_tokens: 2048
      }, null, 2),
      is_default: false
    });
    setModalVisible(true);
  };

  const handleSubmit = async (values: any) => {
    try {
      const configData = {
        ...values,
        config: values.config ? JSON.parse(values.config) : null
      };

      const url = editingConfig 
        ? `/api/llm-config/${editingConfig.id}`
        : '/api/llm-config/';
      
      const method = editingConfig ? 'PUT' : 'POST';
      
      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(configData),
      });

      if (response.ok) {
        message.success(editingConfig ? '更新成功' : '创建成功');
        setModalVisible(false);
        fetchConfigs();
        // 自动重新加载配置
        await handleReloadConfig();
      } else {
        message.error(editingConfig ? '更新失败' : '创建失败');
      }
    } catch (error) {
      console.error('提交失败:', error);
      message.error('提交失败');
    }
  };

  const columns = [
    {
      title: '配置名称',
      dataIndex: 'display_name',
      key: 'display_name',
      render: (text: string, record: LLMConfig) => (
        <Space>
          <Text strong>{text}</Text>
          {record.is_default && <Tag color="green" icon={<CheckCircleOutlined />}>默认</Tag>}
        </Space>
      )
    },
    {
      title: '提供商',
      dataIndex: 'provider',
      key: 'provider',
      render: (text: string) => <Tag color="blue">{text}</Tag>
    },
    {
      title: '模型',
      dataIndex: 'model_name',
      key: 'model_name',
    },
    {
      title: 'API密钥',
      dataIndex: 'api_key',
      key: 'api_key',
      render: (text: string) => text ? '***' + text.slice(-4) : '未设置'
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active: boolean) => (
        <Tag color={active ? 'green' : 'red'}>
          {active ? '启用' : '禁用'}
        </Tag>
      )
    },
    {
      title: '操作',
      key: 'action',
      render: (text: string, record: LLMConfig) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          {!record.is_default && (
            <Button
              type="link"
              onClick={() => handleSetDefault(record.id)}
            >
              设为默认
            </Button>
          )}
          <Popconfirm
            title="确定要删除这个配置吗？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <Layout className="llm-config-layout">
      <div className="llm-config-container">
        <div className="llm-config-header">
          <Title level={2}>LLM配置管理</Title>
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleCreate}
            >
              添加配置
            </Button>
            <Button
              icon={<InfoCircleOutlined />}
              onClick={handleQuickOllamaConfig}
            >
              快速Ollama配置
            </Button>
            <Button
              icon={<InfoCircleOutlined />}
              onClick={handleQuickDeepSeekConfig}
            >
              快速DeepSeek配置
            </Button>
            <Button
              icon={<SettingOutlined />}
              onClick={handleRefreshConfig}
            >
              刷新配置
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleReloadConfig}
            >
              重新加载
            </Button>
          </Space>
        </div>

        <Card>
          <Table
            columns={columns}
            dataSource={configs}
            rowKey="id"
            loading={loading}
            pagination={false}
          />
        </Card>

        <Modal
          title={editingConfig ? '编辑LLM配置' : '添加LLM配置'}
          open={modalVisible}
          onCancel={() => setModalVisible(false)}
          footer={null}
          width={600}
        >
          <Form
            form={form}
            layout="vertical"
            onFinish={handleSubmit}
          >
            <Form.Item
              name="name"
              label="配置名称"
              rules={[{ required: true, message: '请输入配置名称' }]}
            >
              <Input placeholder="请输入配置名称" />
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
              name="provider"
              label="提供商"
              rules={[{ required: true, message: '请选择提供商' }]}
              extra={
                selectedProvider === 'ollama' ? 
                <div style={{ color: '#1890ff', fontSize: '12px' }}>
                  <InfoCircleOutlined /> Ollama需要先安装并启动服务。下载地址：https://ollama.ai
                </div> :
                selectedProvider === 'deepseek' ? 
                <div style={{ color: '#1890ff', fontSize: '12px' }}>
                  <InfoCircleOutlined /> DeepSeek需要API密钥。获取地址：https://platform.deepseek.com
                </div> : undefined
              }
            >
              <Select 
                placeholder="请选择提供商"
                onChange={(value) => setSelectedProvider(value)}
              >
                <Option value="openai">OpenAI</Option>
                <Option value="anthropic">Anthropic</Option>
                <Option value="deepseek">DeepSeek</Option>
                <Option value="ollama">Ollama</Option>
                <Option value="local">本地模型</Option>
                <Option value="azure">Azure OpenAI</Option>
                <Option value="google">Google AI</Option>
              </Select>
            </Form.Item>

            <Form.Item
              name="model_name"
              label="模型名称"
              rules={[{ required: true, message: '请输入模型名称' }]}
            >
              <Input 
                placeholder={
                  selectedProvider === 'openai' ? 'gpt-4, gpt-3.5-turbo' :
                  selectedProvider === 'anthropic' ? 'claude-3-sonnet-20240229, claude-3-haiku-20240307' :
                  selectedProvider === 'deepseek' ? 'deepseek-chat, deepseek-coder' :
                  selectedProvider === 'ollama' ? 'qwen3:32b, llama3.2:3b, mistral:7b' :
                  selectedProvider === 'local' ? 'qwen3:32b, llama3.2:3b' :
                  '请输入模型名称'
                }
              />
            </Form.Item>

            <Form.Item
              name="api_key"
              label="API密钥"
            >
              <Input.Password placeholder="请输入API密钥" />
            </Form.Item>

            <Form.Item
              name="api_base"
              label="API基础URL"
            >
              <Input 
                placeholder={
                  selectedProvider === 'openai' ? 'https://api.openai.com/v1' :
                  selectedProvider === 'anthropic' ? 'https://api.anthropic.com' :
                  selectedProvider === 'deepseek' ? 'https://api.deepseek.com' :
                  selectedProvider === 'ollama' ? 'http://localhost:11434' :
                  selectedProvider === 'local' ? 'http://localhost:11434' :
                  '请输入API基础URL（可选）'
                }
              />
            </Form.Item>

            <Form.Item
              name="config"
              label="其他配置（JSON格式）"
            >
              <TextArea 
                rows={4} 
                placeholder='{"temperature": 0.7, "max_tokens": 2048}'
              />
            </Form.Item>

            <Form.Item
              name="is_default"
              label="设为默认配置"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>

            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit">
                  {editingConfig ? '更新' : '创建'}
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

export default LLMConfigPage; 