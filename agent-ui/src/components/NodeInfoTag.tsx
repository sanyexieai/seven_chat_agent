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
    // 统一处理路由 / 参数推理 等节点类型
    const normalizedType = nodeType.startsWith('router')
      ? 'router'
      : nodeType;
    
    switch (normalizedType) {
      case 'llm':
        return <RobotOutlined />;
      case 'tool':
        return <ToolOutlined />;
      case 'auto_param':
      case 'auto_infer':
        // 自动参数推理节点，视为工具的一种
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
    // 统一处理路由 / 参数推理 等节点类型
    const normalizedType = nodeType.startsWith('router')
      ? 'router'
      : nodeType;
    
    switch (normalizedType) {
      case 'llm':
        return 'blue';
      case 'tool':
        return 'green';
      case 'auto_param':
      case 'auto_infer':
        // 参数推理节点，用不同颜色区分
        return 'geekblue';
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
    // 统一处理路由 / 参数推理 等节点类型
    const normalizedType = nodeType.startsWith('router')
      ? 'router'
      : nodeType;
    
    switch (normalizedType) {
      case 'llm':
        return 'LLM';
      case 'tool':
        return '工具';
      case 'auto_param':
      case 'auto_infer':
        return '参数推理';
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

  // 构造用于展示的节点名称（优先使用工具名等业务字段）
  const getDisplayName = () => {
    let name = nodeLabel || nodeName;

    // 如果是工具或参数推理节点，优先显示具体的工具名称
    const normalizedType = nodeType.startsWith('router')
      ? 'router'
      : nodeType;

    if (
      normalizedType === 'tool' ||
      normalizedType === 'auto_param' ||
      normalizedType === 'auto_infer'
    ) {
      const rawToolName =
        metadata?.tool_name ||
        metadata?.toolName ||
        metadata?.config?.tool_name ||
        metadata?.config?.tool;

      if (typeof rawToolName === 'string' && rawToolName.trim()) {
        let displayToolName = rawToolName.trim();

        // MCP 工具：mcp_{server}_{tool} → 显示最后一段
        if (displayToolName.startsWith('mcp_')) {
          const parts = displayToolName.split('_');
          if (parts.length >= 3) {
            displayToolName = parts.slice(2).join('_');
          } else if (parts.length === 2) {
            displayToolName = parts[1];
          }
        }

        // 临时工具：temp_xxx → 去掉前缀
        if (displayToolName.startsWith('temp_')) {
          displayToolName = displayToolName.substring('temp_'.length);
        }

        return displayToolName;
      }
    }

    return name;
  };

  // 构建提示信息
  const buildTooltipContent = () => {
    const displayName = getDisplayName();
    let content = `节点类型: ${getNodeTypeLabel()}\n节点名称: ${displayName}`;
    
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
      if (metadata.tool_name) {
        content += `\n工具名称: ${metadata.tool_name}`;
      }
      if (metadata.tool_type) {
        content += `\n工具类型: ${metadata.tool_type}`;
      }
      if (metadata.server) {
        content += `\n工具服务器: ${metadata.server}`;
      }
      if (metadata.tool_score !== undefined) {
        content += `\n当前评分: ${Number(metadata.tool_score).toFixed(2)}`;
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
        {getNodeTypeLabel()}: {getDisplayName()}
        {metadata?.tool_score !== undefined && (
          <span style={{ marginLeft: 4, fontSize: 10 }}>
            ({Number(metadata.tool_score).toFixed(1)}★)
          </span>
        )}
      </Tag>
    </Tooltip>
  );
};

export default NodeInfoTag; 