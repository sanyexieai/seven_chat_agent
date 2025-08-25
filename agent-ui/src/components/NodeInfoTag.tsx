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
    switch (nodeType) {
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
      case 'condition':
        return <CheckCircleOutlined />;
      default:
        return <RobotOutlined />;
    }
  };

  const getNodeColor = () => {
    switch (nodeType) {
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
      case 'condition':
        return 'geekblue';
      default:
        return 'default';
    }
  };

  const getNodeTypeLabel = () => {
    switch (nodeType) {
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
      case 'condition':
        return '条件';
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