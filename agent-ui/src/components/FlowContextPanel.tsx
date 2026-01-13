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
  pipeline_data_3d?: Record<string, Record<string, Record<string, Record<string, any>>>>;
  pipeline_files?: Record<string, Record<string, any>>;
  pipeline_history?: Array<{
    timestamp?: string;
    action: string;
    namespace?: string;
    user_id?: string;
    topic_id?: string;
    agent_id?: string;
    key: string;
    value?: any;
  }>;
  flow_state?: Record<string, any>;
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


  // 渲染数据面板
  const renderDataPanel = () => {
    const pipelineData = contextData?.pipeline_data || {};
    const pipelineData3d = contextData?.pipeline_data_3d || {};
    const namespaces = Object.keys(pipelineData);

    // 组织三维数据：按用户、话题、智能体分组
    const organize3dData = () => {
      const users = Object.keys(pipelineData3d);
      if (users.length === 0) return null;

      // 按用户分组
      const userGroups: Record<string, {
        topics: Record<string, {
          agents: Record<string, Record<string, any>>
        }>
      }> = {};

      users.forEach((userId) => {
        if (!userGroups[userId]) {
          userGroups[userId] = { topics: {} };
        }
        const topics = Object.keys(pipelineData3d[userId] || {});
        topics.forEach((topicId) => {
          if (!userGroups[userId].topics[topicId]) {
            userGroups[userId].topics[topicId] = { agents: {} };
          }
          const agents = Object.keys(pipelineData3d[userId][topicId] || {});
          agents.forEach((agentId) => {
            userGroups[userId].topics[topicId].agents[agentId] = pipelineData3d[userId][topicId][agentId] || {};
          });
        });
      });

      return userGroups;
    };

    // 渲染三维数据（按用户-话题-智能体结构）
    const render3dData = () => {
      const userGroups = organize3dData();
      if (!userGroups) return null;

      return (
        <div style={{ marginBottom: '16px' }}>
          {Object.entries(userGroups).map(([userId, userData]) => {
            const topics = Object.keys(userData.topics);
            
            // 收集用户级别的数据（跨话题的）
            const userLevelData: Record<string, any> = {};
            // 收集话题级别的数据
            const topicGroups: Record<string, Record<string, any>> = {};
            // 收集智能体级别的数据（跨话题的）
            const agentGroups: Record<string, Record<string, any>> = {};

            // 提取话题列表（从 topics_list key）
            let topicsList: string[] = [];
            topics.forEach((topicId) => {
              const agents = Object.keys(userData.topics[topicId].agents);
              agents.forEach((agentId) => {
                const agentData = userData.topics[topicId].agents[agentId];
                const keys = Object.keys(agentData).filter(k => !k.endsWith('_metadata'));

                keys.forEach((key) => {
                  const value = agentData[key];
                  const metadata = agentData[`${key}_metadata`] || {};
                  const keyLower = key.toLowerCase();
                  const valueStr = typeof value === 'string' ? value : JSON.stringify(value);
                  
                  // 提取话题列表
                  if (key === 'topics_list') {
                    try {
                      const parsed = typeof value === 'string' ? JSON.parse(value) : value;
                      if (Array.isArray(parsed)) {
                        topicsList = parsed;
                      }
                    } catch (e) {
                      // 解析失败，忽略
                    }
                  }
                  
                  // 根据 key 和 metadata 判断属于哪个维度
                  const category = metadata.category || '';
                  const tags = metadata.tags || [];
                  
                  // 用户维度：用户偏好、习惯、特征等
                  if (keyLower.includes('user') || keyLower.includes('preference') || 
                      keyLower.includes('like') || keyLower.includes('习惯') ||
                      keyLower.includes('特征') || category === 'user_preference' ||
                      tags.some((t: string) => t.includes('用户') || t.includes('偏好') || t.includes('习惯'))) {
                    // 合并相同 key 的内容
                    if (!userLevelData[key]) {
                      userLevelData[key] = value;
                    } else if (typeof userLevelData[key] === 'string' && typeof value === 'string') {
                      // 如果已存在，合并内容
                      userLevelData[key] = userLevelData[key] + '\n' + value;
                    }
                  }
                  // 智能体维度：聊天内容、提炼内容、记忆等
                  else if (!keyLower.includes('topic') && !keyLower.includes('session')) {
                    if (!agentGroups[agentId]) {
                      agentGroups[agentId] = {};
                    }
                    // 如果 key 相同，合并内容
                    if (agentGroups[agentId][key] && typeof agentGroups[agentId][key] === 'string' && typeof value === 'string') {
                      agentGroups[agentId][key] = agentGroups[agentId][key] + '\n' + value;
                    } else {
                      agentGroups[agentId][key] = value;
                    }
                  }
                });
              });
            });
            
            // 如果没有从数据中提取到话题列表，使用默认的空数组
            if (topicsList.length === 0) {
              topicsList = [];
            }

            return (
              <div key={userId} style={{ marginBottom: '24px', padding: '12px', border: '1px solid #e8e8e8', borderRadius: '4px' }}>
                {/* 用户维度 - 始终显示标题 */}
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ marginBottom: '8px' }}>
                    <Text strong style={{ fontSize: '14px' }}>用户：</Text>
                  </div>
                  <div style={{ paddingLeft: '20px' }}>
                    {Object.keys(userLevelData).length > 0 ? (
                      Object.entries(userLevelData).map(([key, value]) => {
                        const preview = getValuePreview(value, 200);
                        const fullValue = formatValue(value);
                        return (
                          <div key={key} style={{ marginBottom: '8px', fontSize: '12px', color: '#666', lineHeight: '1.6' }}>
                            {preview}
                            <Tooltip title="复制">
                              <Button
                                type="text"
                                size="small"
                                icon={<CopyOutlined />}
                                onClick={() => handleCopy(fullValue, `user-${key}`)}
                                style={{ marginLeft: '8px' }}
                              />
                            </Tooltip>
                          </div>
                        );
                      })
                    ) : (
                      <Text type="secondary" style={{ fontSize: '12px', fontStyle: 'italic' }}>
                        暂无用户数据
                      </Text>
                    )}
                  </div>
                </div>

                {/* 话题维度 - 始终显示标题 */}
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ marginBottom: '8px' }}>
                    <Text strong style={{ fontSize: '14px' }}>话题：</Text>
                  </div>
                  <div style={{ paddingLeft: '20px' }}>
                    {topicsList.length > 0 ? (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                        {topicsList.map((topic, index) => (
                          <Tag key={index} color="blue" style={{ fontSize: '12px', marginBottom: '4px' }}>
                            {topic}
                          </Tag>
                        ))}
                      </div>
                    ) : (
                      <Text type="secondary" style={{ fontSize: '12px', fontStyle: 'italic' }}>
                        暂无话题数据
                      </Text>
                    )}
                  </div>
                </div>

                {/* 智能体维度 - 始终显示标题 */}
                <div>
                  <div style={{ marginBottom: '8px' }}>
                    <Text strong style={{ fontSize: '14px' }}>智能体：</Text>
                  </div>
                  <div style={{ paddingLeft: '20px' }}>
                    {Object.keys(agentGroups).length > 0 ? (
                      Object.entries(agentGroups).map(([agentId, agentData]) => {
                        // 合并智能体下的所有内容为一个摘要（长度限制）
                        const agentSummary = Object.values(agentData)
                          .map(v => typeof v === 'string' ? v : JSON.stringify(v))
                          .join(' ')
                          .substring(0, 300);
                        
                        return (
                          <div key={agentId} style={{ marginBottom: '8px', fontSize: '12px', color: '#666', lineHeight: '1.6' }}>
                            {agentSummary}
                            {agentSummary.length >= 300 && <span style={{ color: '#999' }}>...</span>}
                            <Tooltip title="复制完整内容">
                              <Button
                                type="text"
                                size="small"
                                icon={<CopyOutlined />}
                                onClick={() => handleCopy(
                                  Object.values(agentData).map(v => typeof v === 'string' ? v : JSON.stringify(v)).join('\n'),
                                  `agent-${agentId}`
                                )}
                                style={{ marginLeft: '8px' }}
                              />
                            </Tooltip>
                          </div>
                        );
                      })
                    ) : (
                      <Text type="secondary" style={{ fontSize: '12px', fontStyle: 'italic' }}>
                        暂无智能体数据
                      </Text>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      );
    };

    const userGroups = organize3dData();
    const has3dData = userGroups && Object.keys(userGroups).length > 0;

    if (namespaces.length === 0 && !has3dData) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无数据"
          style={{ padding: '20px 0' }}
        />
      );
    }

    return (
      <div className="context-panel-content">
        {/* 显示三维数据（按用户-话题-智能体结构） */}
        {has3dData && render3dData()}

        {/* 显示命名空间数据（向后兼容） */}
        {namespaces.map((namespace) => {
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
                  {entry.namespace && (
                    <Text type="secondary" style={{ fontSize: '12px' }}>
                      {entry.namespace}
                    </Text>
                  )}
                  {(entry.user_id || entry.topic_id || entry.agent_id) && (
                    <Space size="small">
                      {entry.user_id && <Tag color="purple" style={{ fontSize: '11px' }}>用户: {entry.user_id}</Tag>}
                      {entry.topic_id && <Tag color="blue" style={{ fontSize: '11px' }}>话题: {entry.topic_id}</Tag>}
                      {entry.agent_id && <Tag color="green" style={{ fontSize: '11px' }}>智能体: {entry.agent_id}</Tag>}
                    </Space>
                  )}
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
    const pipelineData3d = contextData?.pipeline_data_3d || {};
    const pipelineFiles = contextData?.pipeline_files || {};
    const history = contextData?.pipeline_history || {};

    let dataCount = 0;
    Object.entries(pipelineData).forEach(([namespace, ns]) => {
      const count = Object.keys(ns || {}).filter(k => !k.endsWith('_metadata')).length;
      dataCount += count;
    });

    // 统计三维数据
    let data3dCount = 0;
    Object.values(pipelineData3d).forEach((userData) => {
      Object.values(userData).forEach((topicData) => {
        Object.values(topicData).forEach((agentData) => {
          data3dCount += Object.keys(agentData || {}).filter(k => !k.endsWith('_metadata')).length;
        });
      });
    });

    let fileCount = 0;
    Object.values(pipelineFiles).forEach((ns) => {
      fileCount += Object.keys(ns || {}).length;
    });

    return {
      dataCount: dataCount + data3dCount,
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

