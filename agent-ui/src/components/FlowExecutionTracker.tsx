import React, { useState, useEffect, useRef } from 'react';
import { Card, Progress, Tag, Space, Typography, Button, List, Avatar, Timeline, Alert, Tooltip } from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  ReloadOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  InfoCircleOutlined
} from '@ant-design/icons';
import { motion, AnimatePresence } from 'framer-motion';

const { Title, Text, Paragraph } = Typography;

export interface FlowExecutionStatus {
  nodeId: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  startTime?: number;
  endTime?: number;
  duration?: number;
  result?: any;
  error?: string;
  progress?: number;
  label: string;
  nodeType: string;
}

export interface FlowExecutionState {
  isRunning: boolean;
  isPaused: boolean;
  currentNodeId: string | null;
  completedNodes: string[];
  failedNodes: string[];
  skippedNodes: string[];
  totalNodes: number;
  startTime: number | null;
  endTime: number | null;
  executionLog: Array<{
    timestamp: number;
    nodeId: string;
    action: string;
    message: string;
    level: 'info' | 'warning' | 'error' | 'success';
  }>;
  nodeStatuses: FlowExecutionStatus[];
}

interface FlowExecutionTrackerProps {
  executionState: FlowExecutionState;
  onStartExecution?: () => void;
  onPauseExecution?: () => void;
  onResumeExecution?: () => void;
  onStopExecution?: () => void;
  onResetExecution?: () => void;
  onNodeClick?: (nodeId: string) => void;
  showDetails?: boolean;
  compact?: boolean;
}

const FlowExecutionTracker: React.FC<FlowExecutionTrackerProps> = ({
  executionState,
  onStartExecution,
  onPauseExecution,
  onResumeExecution,
  onStopExecution,
  onResetExecution,
  onNodeClick,
  showDetails = true,
  compact = false
}) => {
  const [showExecutionLog, setShowExecutionLog] = useState(false);
  const [showNodeDetails, setShowNodeDetails] = useState(false);
  const progressRef = useRef<HTMLDivElement>(null);

  // 计算执行进度
  const executionProgress = executionState.totalNodes > 0 
    ? Math.round((executionState.completedNodes.length / executionState.totalNodes) * 100)
    : 0;

  // 计算执行时间
  const executionTime = executionState.startTime && executionState.endTime
    ? executionState.endTime - executionState.startTime
    : executionState.startTime
    ? Date.now() - executionState.startTime
    : 0;

  // 获取状态颜色
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return '#52c41a';
      case 'running': return '#1890ff';
      case 'failed': return '#ff4d4f';
      case 'skipped': return '#faad14';
      default: return '#d9d9d9';
    }
  };

  // 获取状态图标
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircleOutlined />;
      case 'running': return <LoadingOutlined />;
      case 'failed': return <ExclamationCircleOutlined />;
      case 'skipped': return <ClockCircleOutlined />;
      default: return <InfoCircleOutlined />;
    }
  };

  // 获取状态标签颜色
  const getStatusTagColor = (status: string) => {
    switch (status) {
      case 'completed': return 'success';
      case 'running': return 'processing';
      case 'failed': return 'error';
      case 'skipped': return 'warning';
      default: return 'default';
    }
  };

  // 格式化时间
  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${Math.round(ms / 1000)}s`;
    return `${Math.round(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
  };

  // 自动滚动到当前执行节点
  useEffect(() => {
    if (executionState.currentNodeId && progressRef.current) {
      const element = document.getElementById(`node-${executionState.currentNodeId}`);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [executionState.currentNodeId]);

  if (compact) {
    return (
      <Card size="small" style={{ marginBottom: '8px' }}>
        <Space size="small" align="center">
          <Text strong>执行状态:</Text>
          <Tag color={executionState.isRunning ? 'processing' : 'default'}>
            {executionState.isRunning ? '运行中' : '已停止'}
          </Tag>
          <Progress 
            percent={executionProgress} 
            size="small" 
            showInfo={false}
            style={{ width: '100px' }}
          />
          <Text type="secondary">
            {executionState.completedNodes.length}/{executionState.totalNodes}
          </Text>
          {executionState.isRunning && (
            <Button
              size="small"
              icon={<StopOutlined />}
              onClick={onStopExecution}
              danger
            />
          )}
        </Space>
      </Card>
    );
  }

  return (
    <div>
      {/* 执行控制面板 */}
      <Card 
        size="small" 
        style={{ marginBottom: '16px' }}
        bodyStyle={{ padding: '12px 16px' }}
      >
        <Space size="middle" align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <Title level={5} style={{ margin: 0 }}>流程执行器</Title>
            <Tag color={executionState.isRunning ? 'processing' : 'default'}>
              {executionState.isRunning ? '运行中' : '已停止'}
            </Tag>
          </Space>
          
          <Space>
            {!executionState.isRunning ? (
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={onStartExecution}
                disabled={executionState.isRunning}
              >
                开始执行
              </Button>
            ) : (
              <>
                {executionState.isPaused ? (
                  <Button
                    icon={<PlayCircleOutlined />}
                    onClick={onResumeExecution}
                  >
                    恢复
                  </Button>
                ) : (
                  <Button
                    icon={<PauseCircleOutlined />}
                    onClick={onPauseExecution}
                  >
                    暂停
                  </Button>
                )}
                
                <Button
                  danger
                  icon={<StopOutlined />}
                  onClick={onStopExecution}
                >
                  停止
                </Button>
              </>
            )}
            
            <Button
              icon={<ReloadOutlined />}
              onClick={onResetExecution}
              disabled={executionState.isRunning}
            >
              重置
            </Button>
            
            <Button
              icon={<EyeOutlined />}
              onClick={() => setShowExecutionLog(!showExecutionLog)}
            >
              执行日志
            </Button>
          </Space>
        </Space>

        {/* 执行进度 */}
        <div style={{ marginTop: '12px' }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text>执行进度</Text>
              <Text type="secondary">
                {executionState.completedNodes.length} / {executionState.totalNodes} 节点
              </Text>
            </div>
            <Progress 
              percent={executionProgress} 
              status={executionState.failedNodes.length > 0 ? 'exception' : 'normal'}
              strokeColor={{
                '0%': '#108ee9',
                '100%': '#87d068',
              }}
            />
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Space>
                <Tag color="blue">运行中: {executionState.currentNodeId ? 1 : 0}</Tag>
                <Tag color="green">已完成: {executionState.completedNodes.length}</Tag>
                <Tag color="red">失败: {executionState.failedNodes.length}</Tag>
                <Tag color="orange">跳过: {executionState.failedNodes.length}</Tag>
              </Space>
              <Text type="secondary">
                执行时间: {formatDuration(executionTime)}
              </Text>
            </div>
          </Space>
        </div>
      </Card>

      {/* 节点状态概览 */}
      {showDetails && (
        <Card size="small" title="节点状态概览" style={{ marginBottom: '16px' }}>
          <div ref={progressRef}>
            <List
              size="small"
              dataSource={executionState.nodeStatuses}
              renderItem={(nodeStatus) => (
                <List.Item
                  id={`node-${nodeStatus.nodeId}`}
                  style={{
                    background: executionState.currentNodeId === nodeStatus.nodeId ? '#f0f8ff' : 'transparent',
                    border: executionState.currentNodeId === nodeStatus.nodeId ? '1px solid #1890ff' : '1px solid transparent',
                    borderRadius: '4px',
                    padding: '8px',
                    margin: '4px 0',
                    cursor: onNodeClick ? 'pointer' : 'default'
                  }}
                  onClick={() => onNodeClick?.(nodeStatus.nodeId)}
                >
                  <List.Item.Meta
                    avatar={
                      <Avatar
                        style={{
                          backgroundColor: getStatusColor(nodeStatus.status),
                          color: 'white'
                        }}
                        icon={getStatusIcon(nodeStatus.status)}
                      />
                    }
                    title={
                      <Space>
                        <Text strong>{nodeStatus.label}</Text>
                        <Tag color={getStatusTagColor(nodeStatus.status)}>
                          {nodeStatus.status === 'pending' ? '等待中' :
                           nodeStatus.status === 'running' ? '运行中' :
                           nodeStatus.status === 'completed' ? '已完成' :
                           nodeStatus.status === 'failed' ? '失败' : '跳过'}
                        </Tag>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size="small" style={{ width: '100%' }}>
                        <Text type="secondary">{nodeStatus.nodeType}</Text>
                        
                        {nodeStatus.status === 'running' && nodeStatus.progress !== undefined && (
                          <Progress 
                            percent={nodeStatus.progress} 
                            size="small" 
                            showInfo={false}
                            strokeColor={getStatusColor(nodeStatus.status)}
                          />
                        )}
                        
                        {nodeStatus.duration && (
                          <Text type="secondary">
                            执行时间: {formatDuration(nodeStatus.duration)}
                          </Text>
                        )}
                        
                        {nodeStatus.error && (
                          <Alert 
                            message={nodeStatus.error} 
                            type="error" 
                            showIcon 
                            style={{ marginTop: '4px' }}
                          />
                        )}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </div>
        </Card>
      )}

      {/* 执行日志 */}
      <AnimatePresence>
        {showExecutionLog && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <Card size="small" title="执行日志" style={{ marginBottom: '16px' }}>
              <Timeline>
                {executionState.executionLog.map((log, index) => (
                  <Timeline.Item
                    key={index}
                    color={
                      log.level === 'error' ? 'red' :
                      log.level === 'warning' ? 'orange' :
                      log.level === 'success' ? 'green' : 'blue'
                    }
                  >
                    <div>
                      <Space>
                        <Text strong>{log.action}</Text>
                        <Text type="secondary">-</Text>
                        <Text type="secondary">{log.message}</Text>
                      </Space>
                      <br />
                      <Text type="secondary" style={{ fontSize: '12px' }}>
                        {new Date(log.timestamp).toLocaleTimeString()}
                      </Text>
                    </div>
                  </Timeline.Item>
                ))}
              </Timeline>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default FlowExecutionTracker; 