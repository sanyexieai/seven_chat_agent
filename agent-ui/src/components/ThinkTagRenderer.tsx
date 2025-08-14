import React, { useState, useEffect, useRef } from 'react';
import { Button, Card, Typography, Space } from 'antd';
import { 
  BulbOutlined
} from '@ant-design/icons';
import './ThinkTagRenderer.css';

const { Text, Paragraph } = Typography;

interface ThinkTagRendererProps {
  content: string;
  className?: string;
}

const ThinkTagRenderer: React.FC<ThinkTagRendererProps> = ({ content, className = '' }) => {
  // 使用 localStorage 来保持思考过程的显示状态
  const [showThink, setShowThink] = useState(() => {
    try {
      return localStorage.getItem('think-tag-visible') !== 'false';
    } catch {
      return true;
    }
  });
  const [thinkCount, setThinkCount] = useState(0);

  // 使用 ref 来避免状态比较的问题
  const visibleRef = useRef(showThink);

  // 更新 ref 值
  useEffect(() => {
    visibleRef.current = showThink;
  }, [showThink]);

  // 监听状态变化，确保新消息能继承状态
  useEffect(() => {
    const handleStorageChange = () => {
      try {
        const newVisible = localStorage.getItem('think-tag-visible') !== 'false';
        
        // 使用 ref 值进行比较，避免循环更新
        if (newVisible !== visibleRef.current) {
          setShowThink(newVisible);
        }
      } catch {}
    };

    // 监听 storage 事件（跨标签页同步）
    window.addEventListener('storage', handleStorageChange);
    
    // 只在组件挂载时检查一次状态，避免频繁更新
    handleStorageChange();
    
    return () => {
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []); // 移除依赖项，避免循环更新

  // 解析内容中的<think>标签，处理流式加载中的不完整标签
  const parseThinkContent = (text: string) => {
    const parts = [];
    let currentText = '';
    let currentThink = '';
    let inThinkTag = false;
    let i = 0;

    while (i < text.length) {
      if (text.slice(i, i + 7) === '<think>') {
        // 如果之前有文本内容，先保存
        if (currentText.trim()) {
          parts.push({
            type: 'text',
            content: currentText.trim()
          });
          currentText = '';
        }
        
        inThinkTag = true;
        i += 7;
        continue;
      }

      if (text.slice(i, i + 8) === '</think>') {
        // 保存思考内容
        if (currentThink.trim()) {
          parts.push({
            type: 'think',
            content: currentThink.trim()
          });
        }
        
        inThinkTag = false;
        currentThink = '';
        i += 8;
        continue;
      }

      if (inThinkTag) {
        currentThink += text[i];
      } else {
        currentText += text[i];
      }
      
      i++;
    }

    // 处理剩余内容
    if (currentText.trim()) {
      parts.push({
        type: 'text',
        content: currentText.trim()
      });
    }

    // 如果还有未闭合的think标签，将其作为特殊的不完整思考过程处理
    if (currentThink.trim()) {
      parts.push({
        type: 'incomplete_think',
        content: currentThink.trim()
      });
    }

    return parts;
  };

  const parts = parseThinkContent(content);

  // 监听内容变化，更新think标签计数
  useEffect(() => {
    const thinkParts = parts.filter(part => part.type === 'think');
    setThinkCount(thinkParts.length);
  }, [content]);

  if (parts.length === 0) {
    return <div className={className}>{content}</div>;
  }

  // 检查是否有think标签
  const hasThinkTags = parts.some(part => part.type === 'think');

  return (
    <div className={`think-tag-container ${className}`}>
      {parts.map((part, index) => {
        if (part.type === 'text') {
          return (
            <div key={index} style={{ whiteSpace: 'pre-wrap' }}>
              {part.content}
            </div>
          );
        }

        if (part.type === 'think') {
          if (!showThink) return null;

          return (
            <Card
              key={index}
              size="small"
              className="think-tag-card"
              bodyStyle={{ padding: '8px 12px' }}
            >
              <div className="think-tag-header">
                <div className="think-tag-title">
                  <BulbOutlined />
                  <Text type="secondary">
                    思考过程 {thinkCount > 1 ? `(${index + 1}/${thinkCount})` : ''}
                  </Text>
                  {/* 展开/收起按钮已移除，思考过程内容直接显示 */}
                </div>
                <div className="think-tag-actions">
                  {/* 隐藏按钮已移至输入框上方，由全局开关控制 */}
                </div>
              </div>
              
              <div className="think-tag-content">
                <Paragraph className="think-tag-text">
                  {part.content}
                </Paragraph>
              </div>
            </Card>
          );
        }

        if (part.type === 'incomplete_think') {
          if (!showThink) return null;

          return (
            <Card
              key={index}
              size="small"
              className="think-tag-card think-tag-incomplete"
              bodyStyle={{ padding: '8px 12px' }}
            >
              <div className="think-tag-header">
                <div className="think-tag-title">
                  <BulbOutlined style={{ color: '#ff7875' }} />
                  <Text type="secondary">
                    思考过程（进行中...）
                  </Text>
                  {/* 等待完成提示 */}
                  <Text type="secondary" style={{ fontSize: '12px', opacity: 0.7 }}>
                    等待完成...
                  </Text>
                </div>
                <div className="think-tag-actions">
                  {/* 隐藏按钮已移至输入框上方，由全局开关控制 */}
                </div>
              </div>
              
              <div className="think-tag-content">
                <Paragraph className="think-tag-text think-tag-streaming">
                  {part.content}
                  <span style={{ color: '#ff7875', fontStyle: 'italic' }}>...</span>
                </Paragraph>
              </div>
            </Card>
          );
        }

        return null;
      })}
    </div>
  );
};

export default ThinkTagRenderer; 