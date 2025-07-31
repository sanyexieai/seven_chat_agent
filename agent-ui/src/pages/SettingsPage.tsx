import React, { useState } from 'react';
import { Card, Form, Input, Button, Switch, Select, Divider, message } from 'antd';
import { SaveOutlined, ReloadOutlined } from '@ant-design/icons';

const { Option } = Select;

interface Settings {
  apiUrl: string;
  model: string;
  maxTokens: number;
  temperature: number;
  enableStreaming: boolean;
  enableLogging: boolean;
  language: string;
}

const SettingsPage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  const initialSettings: Settings = {
    apiUrl: 'http://localhost:8000',
    model: 'gpt-3.5-turbo',
    maxTokens: 2048,
    temperature: 0.7,
    enableStreaming: true,
    enableLogging: true,
    language: 'zh-CN',
  };

  const handleSave = async (values: Settings) => {
    setLoading(true);
    try {
      // 这里应该调用API保存设置
      console.log('保存设置:', values);
      message.success('设置保存成功');
    } catch (error) {
      message.error('设置保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    form.setFieldsValue(initialSettings);
    message.info('设置已重置');
  };

  return (
    <div className="settings-container">
      <h2>系统设置</h2>
      <p>配置系统参数和偏好设置</p>

      <Form
        form={form}
        layout="vertical"
        initialValues={initialSettings}
        onFinish={handleSave}
      >
        <Card title="API 配置" className="settings-section">
          <Form.Item
            label="API 地址"
            name="apiUrl"
            rules={[{ required: true, message: '请输入API地址' }]}
          >
            <Input placeholder="http://localhost:8000" />
          </Form.Item>

          <Form.Item
            label="模型"
            name="model"
            rules={[{ required: true, message: '请选择模型' }]}
          >
            <Select>
              <Option value="gpt-3.5-turbo">GPT-3.5 Turbo</Option>
              <Option value="gpt-4">GPT-4</Option>
              <Option value="claude-3">Claude-3</Option>
              <Option value="deepseek-chat">DeepSeek Chat</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="最大令牌数"
            name="maxTokens"
            rules={[{ required: true, message: '请输入最大令牌数' }]}
          >
            <Input type="number" min={1} max={8192} />
          </Form.Item>

          <Form.Item
            label="温度"
            name="temperature"
            rules={[{ required: true, message: '请输入温度值' }]}
          >
            <Input type="number" min={0} max={2} step={0.1} />
          </Form.Item>
        </Card>

        <Card title="功能设置" className="settings-section">
          <Form.Item
            label="启用流式输出"
            name="enableStreaming"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            label="启用日志记录"
            name="enableLogging"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            label="界面语言"
            name="language"
          >
            <Select>
              <Option value="zh-CN">中文</Option>
              <Option value="en-US">English</Option>
            </Select>
          </Form.Item>
        </Card>

        <Card title="智能体设置" className="settings-section">
          <Form.Item
            label="默认智能体"
            name="defaultAgent"
          >
            <Select>
              <Option value="chat_agent">聊天智能体</Option>
              <Option value="search_agent">搜索智能体</Option>
              <Option value="report_agent">报告智能体</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="自动选择智能体"
            name="autoSelectAgent"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Card>

        <Card title="工具设置" className="settings-section">
          <Form.Item
            label="启用网络搜索"
            name="enableWebSearch"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            label="启用文档搜索"
            name="enableDocumentSearch"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            label="启用文件操作"
            name="enableFileOperations"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Card>

        <Divider />

        <div style={{ textAlign: 'center' }}>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            htmlType="submit"
            loading={loading}
            style={{ marginRight: 16 }}
          >
            保存设置
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={handleReset}
          >
            重置设置
          </Button>
        </div>
      </Form>
    </div>
  );
};

export default SettingsPage; 