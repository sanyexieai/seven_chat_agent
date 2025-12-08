import React, { useState } from 'react';
import {
  Card,
  Collapse,
  Typography,
  Tag,
  Space,
  Empty,
  Button,
  Tooltip,
  Badge,
  Divider
} from 'antd';
import {
  DatabaseOutlined,
  FileOutlined,
  HistoryOutlined,
  CopyOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import './FlowContextPanel.css';

const { Panel } = Collapse;
const { Text, Paragraph } = Typography;

export interface PipelineData {
  pipeline_data?: Record<string, Record<string, any>>;
  pipeline_files?: Record<string, Record<string, any>>;
  pipeline_history?: Array<{
    timestamp?: string;
    action: string;
    namespace: string;
    key: string;
    value?: any;
  }>;
  flow_state?: Record<string, any>;
  memory_summary?: Record<string, {
    count: number;
    size: number;
    namespace: string;
    config: Record<string, any>;
    keys: string[];
  }>;
}

interface FlowContextPanelProps {
  contextData?: PipelineData;
  onRefresh?: () => void;
  collapsed?: boolean;
  onCollapseChange?: (collapsed: boolean) => void;
}

const FlowContextPanel: React.FC<FlowContextPanelProps> = ({
  contextData,
  onRefresh,
  collapsed = false,
  onCollapseChange
}) => {
  const [expandedKeys, setExpandedKeys] = useState<string[]>(['data', 'files']);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // 复制到剪贴板
  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  // 格式化值显示
  const formatValue = (value: any): string => {
    if (value === null || value === undefined) {
      return 'null';
    }
    if (typeof value === 'string') {
      return value;
    }
    if (typeof value === 'object') {
      return JSON.stringify(value, null, 2);
    }
    return String(value);
  };

  // 获取值预览（截断长文本）
  const getValuePreview = (value: any, maxLength: number = 100): string => {
    const formatted = formatValue(value);
    if (formatted.length <= maxLength) {
      return formatted;
    }
    return formatted.substring(0, maxLength) + '...';
  };

  // 判断是否为记忆类型命名空间
  const isMemoryNamespace = (namespace: string): boolean => {
    return namespace.startsWith('memory_');
  };

  // 获取记忆类型的中文名称
  const getMemoryTypeName = (namespace: string): string => {
    const memoryTypeMap: Record<string, string> = {
      'memory_subconscious': '潜意识记忆',
      'memory_long_term': '长期记忆',
      'memory_short_term': '短期记忆'
    };
    return memoryTypeMap[namespace] || namespace;
  };

  // 获取记忆类型的颜色
  const getMemoryTypeColor = (namespace: string): string => {
    const colorMap: Record<string, string> = {
      'memory_subconscious': 'purple',
      'memory_long_term': 'gold',
      'memory_short_term': 'cyan'
    };
    return colorMap[namespace] || 'blue';
  };

  // 渲染数据面板
  const renderDataPanel = () => {
    const pipelineData = contextData?.pipeline_data || {};
    const memorySummary = contextData?.memory_summary || {};
    const namespaces = Object.keys(pipelineData);

    if (namespaces.length === 0) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无数据"
          style={{ padding: '20px 0' }}
        />
      );
    }

    // 分离记忆类型和其他命名空间
    const memoryNamespaces = namespaces.filter(ns => isMemoryNamespace(ns));
    const otherNamespaces = namespaces.filter(ns => !isMemoryNamespace(ns));

    return (
      <div className="context-panel-content">
        {/* 优先显示记忆类型 */}
        {memoryNamespaces.map((namespace) => {
          const namespaceData = pipelineData[namespace] || {};
          const keys = Object.keys(namespaceData).filter(k => !k.endsWith('_metadata'));
          const summary = memorySummary[namespace.replace('memory_', '')];

          return (
            <div key={namespace} className="context-namespace" style={{ marginBottom: '16px' }}>
              <div className="context-namespace-header">
                <Space>
                  <Tag color={getMemoryTypeColor(namespace)}>
                    {getMemoryTypeName(namespace)}
                  </Tag>
                  {summary && (
                    <>
                      <Text type="secondary" style={{ fontSize: '12px' }}>
                        {summary.count} 条
                      </Text>
                      <Text type="secondary" style={{ fontSize: '11px' }}>
                        ({summary.size} 字符)
                      </Text>
                    </>
                  )}
                  {!summary && keys.length > 0 && (
                    <Text type="secondary" style={{ fontSize: '12px' }}>
                      {keys.length} 项
                    </Text>
                  )}
                </Space>
              </div>
              {keys.length === 0 ? (
                <div style={{ padding: '8px', color: '#999', fontSize: '12px' }}>
                  暂无记忆
                </div>
              ) : (
                <div className="context-namespace-content">
                  {keys.map((key) => {
                    const value = namespaceData[key];
                    const metadata = namespaceData[`${key}_metadata`];
                    const preview = getValuePreview(value);
                    const fullValue = formatValue(value);

                    return (
                      <div key={key} className="context-item">
                        <div className="context-item-header">
                          <Space>
                            <Text strong>{key}</Text>
                            {metadata?.quality_score != null && typeof metadata.quality_score === 'number' && (
                              <Tag color="orange" style={{ fontSize: '11px', padding: '0 4px' }}>
                                质量: {metadata.quality_score.toFixed(2)}
                              </Tag>
                            )}
                            {metadata?.created_at && (
                              <Text type="secondary" style={{ fontSize: '11px' }}>
                                {new Date(metadata.created_at).toLocaleString()}
                              </Text>
                            )}
                          </Space>
                          <Space size="small">
                            <Tooltip title="复制完整值">
                              <Button
                                type="text"
                                size="small"
                                icon={<CopyOutlined />}
                                onClick={() => handleCopy(fullValue, `${namespace}.${key}`)}
                              />
                            </Tooltip>
                          </Space>
                        </div>
                        <div className="context-item-value">
                          <Paragraph
                            copyable={false}
                            ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                            style={{ margin: 0, fontSize: '12px' }}
                          >
                            {preview}
                          </Paragraph>
                        </div>
                        {copiedKey === `${namespace}.${key}` && (
                          <Text type="success" style={{ fontSize: '12px' }}>
                            已复制
                          </Text>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        {/* 显示其他命名空间 */}
        {otherNamespaces.map((namespace) => {
          const namespaceData = pipelineData[namespace] || {};
          const keys = Object.keys(namespaceData);

          if (keys.length === 0) {
            return null;
          }

          return (
            <div key={namespace} className="context-namespace">
              <div className="context-namespace-header">
                <Tag color="blue">{namespace}</Tag>
                <Text type="secondary" style={{ fontSize: '12px' }}>
                  {keys.length} 项
                </Text>
              </div>
              <div className="context-namespace-content">
                {keys.map((key) => {
                  const value = namespaceData[key];
                  const preview = getValuePreview(value);
                  const fullValue = formatValue(value);

                  return (
                    <div key={key} className="context-item">
                      <div className="context-item-header">
                        <Text strong>{key}</Text>
                        <Space size="small">
                          <Tooltip title="复制完整值">
                            <Button
                              type="text"
                              size="small"
                              icon={<CopyOutlined />}
                              onClick={() => handleCopy(fullValue, `${namespace}.${key}`)}
                            />
                          </Tooltip>
                        </Space>
                      </div>
                      <div className="context-item-value">
                        <Paragraph
                          copyable={false}
                          ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                          style={{ margin: 0, fontSize: '12px' }}
                        >
                          {preview}
                        </Paragraph>
                      </div>
                      {copiedKey === `${namespace}.${key}` && (
                        <Text type="success" style={{ fontSize: '12px' }}>
                          已复制
                        </Text>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // 渲染文件面板
  const renderFilesPanel = () => {
    const pipelineFiles = contextData?.pipeline_files || {};
    const namespaces = Object.keys(pipelineFiles);

    if (namespaces.length === 0) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无文件"
          style={{ padding: '20px 0' }}
        />
      );
    }

    return (
      <div className="context-panel-content">
        {namespaces.map((namespace) => {
          const namespaceFiles = pipelineFiles[namespace] || {};
          const filenames = Object.keys(namespaceFiles);

          if (filenames.length === 0) {
            return null;
          }

          return (
            <div key={namespace} className="context-namespace">
              <div className="context-namespace-header">
                <Tag color="green">{namespace}</Tag>
                <Text type="secondary" style={{ fontSize: '12px' }}>
                  {filenames.length} 个文件
                </Text>
              </div>
              <div className="context-namespace-content">
                {filenames.map((filename) => {
                  const fileInfo = namespaceFiles[filename];
                  const { path, type, metadata } = fileInfo || {};

                  return (
                    <div key={filename} className="context-item">
                      <div className="context-item-header">
                        <Space>
                          <FileOutlined />
                          <Text strong>{filename}</Text>
                          {type && <Tag style={{ fontSize: '11px', padding: '0 4px' }}>{type}</Tag>}
                        </Space>
                      </div>
                      <div className="context-item-value">
                        <Text type="secondary" style={{ fontSize: '12px' }}>
                          路径: {path || '未知'}
                        </Text>
                        {metadata && Object.keys(metadata).length > 0 && (
                          <div style={{ marginTop: '4px' }}>
                            <Text type="secondary" style={{ fontSize: '12px' }}>
                              元数据: {JSON.stringify(metadata, null, 2)}
                            </Text>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // 渲染历史面板
  const renderHistoryPanel = () => {
    const history = contextData?.pipeline_history || [];

    if (history.length === 0) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无历史记录"
          style={{ padding: '20px 0' }}
        />
      );
    }

    return (
      <div className="context-panel-content">
        <div className="context-history-list">
          {history.map((entry, index) => (
            <div key={index} className="context-history-item">
              <div className="context-history-header">
                <Space>
                  <Tag color="purple">{entry.action}</Tag>
                  <Text type="secondary" style={{ fontSize: '12px' }}>
                    {entry.namespace}
                  </Text>
                  <Text strong style={{ fontSize: '12px' }}>
                    {entry.key}
                  </Text>
                </Space>
                {entry.timestamp && (
                  <Text type="secondary" style={{ fontSize: '11px' }}>
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </Text>
                )}
              </div>
              {entry.value !== undefined && (
                <div className="context-history-value">
                  <Text type="secondary" style={{ fontSize: '12px' }}>
                    {getValuePreview(entry.value, 150)}
                  </Text>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  // 统计信息
  const getStats = () => {
    const pipelineData = contextData?.pipeline_data || {};
    const pipelineFiles = contextData?.pipeline_files || {};
    const history = contextData?.pipeline_history || {};
    const memorySummary = contextData?.memory_summary || {};

    let dataCount = 0;
    let memoryCount = 0;
    Object.entries(pipelineData).forEach(([namespace, ns]) => {
      const count = Object.keys(ns || {}).filter(k => !k.endsWith('_metadata')).length;
      dataCount += count;
      if (isMemoryNamespace(namespace)) {
        memoryCount += count;
      }
    });

    let fileCount = 0;
    Object.values(pipelineFiles).forEach((ns) => {
      fileCount += Object.keys(ns || {}).length;
    });

    // 从 memory_summary 获取记忆统计
    const memoryTypesCount = Object.values(memorySummary).reduce((sum, summary: any) => {
      return sum + (summary.count || 0);
    }, 0);

    return {
      dataCount,
      memoryCount: memoryTypesCount > 0 ? memoryTypesCount : memoryCount,
      fileCount,
      historyCount: Array.isArray(history) ? history.length : 0,
      namespaceCount: Object.keys(pipelineData).length + Object.keys(pipelineFiles).length
    };
  };

  const stats = getStats();

  return (
    <Card
      className="flow-context-panel"
      title={
        <Space>
          <DatabaseOutlined />
          <span>流程上下文</span>
          {onRefresh && (
            <Tooltip title="刷新">
              <Button
                type="text"
                size="small"
                icon={<ReloadOutlined />}
                onClick={onRefresh}
              />
            </Tooltip>
          )}
        </Space>
      }
      extra={
        <Space>
          {stats.memoryCount > 0 && (
            <Badge count={stats.memoryCount} showZero>
              <Tag color="gold">记忆</Tag>
            </Badge>
          )}
          {stats.dataCount > 0 && (
            <Badge count={stats.dataCount} showZero>
              <Tag color="blue">数据</Tag>
            </Badge>
          )}
          {stats.fileCount > 0 && (
            <Badge count={stats.fileCount} showZero>
              <Tag color="green">文件</Tag>
            </Badge>
          )}
          {stats.historyCount > 0 && (
            <Badge count={stats.historyCount} showZero>
              <Tag color="purple">历史</Tag>
            </Badge>
          )}
        </Space>
      }
      size="small"
      style={{ height: '100%' }}
      bodyStyle={{ padding: '8px', height: 'calc(100% - 57px)', overflow: 'auto' }}
    >
      {!contextData || (stats.dataCount === 0 && stats.fileCount === 0 && stats.historyCount === 0) ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无上下文数据"
          style={{ padding: '40px 0' }}
        />
      ) : (
        <Collapse
          activeKey={expandedKeys}
          onChange={(keys) => setExpandedKeys(keys as string[])}
          ghost
        >
          <Panel
            header={
              <Space>
                <DatabaseOutlined />
                <span>数据</span>
                {stats.dataCount > 0 && (
                  <Badge count={stats.dataCount} size="small" />
                )}
              </Space>
            }
            key="data"
          >
            {renderDataPanel()}
          </Panel>

          <Panel
            header={
              <Space>
                <FileOutlined />
                <span>文件</span>
                {stats.fileCount > 0 && (
                  <Badge count={stats.fileCount} size="small" />
                )}
              </Space>
            }
            key="files"
          >
            {renderFilesPanel()}
          </Panel>

          <Panel
            header={
              <Space>
                <HistoryOutlined />
                <span>历史记录</span>
                {stats.historyCount > 0 && (
                  <Badge count={stats.historyCount} size="small" />
                )}
              </Space>
            }
            key="history"
          >
            {renderHistoryPanel()}
          </Panel>
        </Collapse>
      )}
    </Card>
  );
};

export default FlowContextPanel;

