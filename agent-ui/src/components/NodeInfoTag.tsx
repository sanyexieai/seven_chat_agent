import React from 'react';
import { Tag, Tooltip } from 'antd';
import { 
  RobotOutlined, 
  ToolOutlined, 
  BranchesOutlined, 
  CheckCircleOutlined,
  QuestionCircleOutlined,
  CodeOutlined
} from '@ant-design/icons';

interface NodeInfoTagProps {
  nodeType: string;
  nodeName: string;
  nodeLabel?: string;
  metadata?: any;
}

const NodeInfoTag: React.FC<NodeInfoTagProps> = ({ 
  nodeType, 
  nodeName, 
  nodeLabel, 
  metadata 
}) => {
  // 根据节点类型选择图标和颜色
  const getNodeIcon = () => {
    // 统一处理路由节点类型
    const normalizedType = nodeType.startsWith('router') ? 'router' : nodeType;
    
    switch (normalizedType) {
      case 'llm':
        return <RobotOutlined />;
      case 'tool':
        return <ToolOutlined />;
      case 'router':
        return <BranchesOutlined />;
      case 'judge':
        return <QuestionCircleOutlined />;
      case 'agent':
        return <CodeOutlined />;
      case 'knowledgeBase':
      case 'knowledge_base':
        return <div style={{ fontSize: '16px' }}>📚</div>;
      case 'start':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      case 'end':
        return <CheckCircleOutlined style={{ color: '#ff4d4f' }} />;

      default:
        return <RobotOutlined />;
    }
  };

  const getNodeColor = () => {
    // 统一处理路由节点类型
    const normalizedType = nodeType.startsWith('router') ? 'router' : nodeType;
    
    switch (normalizedType) {
      case 'llm':
        return 'blue';
      case 'tool':
        return 'green';
      case 'router':
        return 'purple';
      case 'judge':
        return 'orange';
      case 'agent':
        return 'cyan';
      case 'knowledgeBase':
      case 'knowledge_base':
        return 'orange';
      case 'start':
        return 'success';
      case 'end':
        return 'error';

      default:
        return 'default';
    }
  };

  const getNodeTypeLabel = () => {
    // 统一处理路由节点类型
    const normalizedType = nodeType.startsWith('router') ? 'router' : nodeType;
    
    switch (normalizedType) {
      case 'llm':
        return 'LLM';
      case 'tool':
        return '工具';
      case 'router':
        return '路由';
      case 'judge':
        return '判断';
      case 'agent':
        return '智能体';
      case 'knowledgeBase':
      case 'knowledge_base':
        return '知识库';
      case 'start':
        return '开始';
      case 'end':
        return '结束';

      default:
        return nodeType;
    }
  };

  // 构建提示信息
  const buildTooltipContent = () => {
    let content = `节点类型: ${getNodeTypeLabel()}\n节点名称: ${nodeName}`;
    
    if (nodeLabel && nodeLabel !== nodeName) {
      content += `\n显示标签: ${nodeLabel}`;
    }
    
    if (metadata) {
      if (metadata.judge_type) {
        content += `\n判断类型: ${metadata.judge_type}`;
      }
      if (metadata.selected_branch) {
        content += `\n选择分支: ${metadata.selected_branch}`;
      }
      if (metadata.agent_name) {
        content += `\n目标智能体: ${metadata.agent_name}`;
      }
      if (metadata.knowledge_base_id) {
        content += `\n知识库ID: ${metadata.knowledge_base_id}`;
      }
      if (metadata.query_type) {
        content += `\n查询类型: ${metadata.query_type}`;
      }
      if (metadata.result_count !== undefined) {
        content += `\n结果数量: ${metadata.result_count}`;
      }
    }
    
    return content;
  };

  return (
    <Tooltip title={buildTooltipContent()} placement="top">
      <Tag 
        color={getNodeColor()} 
        icon={getNodeIcon()}
        style={{ 
          marginRight: 8, 
          cursor: 'pointer',
          fontSize: '11px',
          padding: '2px 6px',
          borderRadius: '4px',
          border: 'none',
          boxShadow: '0 1px 2px rgba(0,0,0,0.1)'
        }}
      >
        {getNodeTypeLabel()}: {nodeLabel || nodeName}
      </Tag>
    </Tooltip>
  );
};

export default NodeInfoTag; 