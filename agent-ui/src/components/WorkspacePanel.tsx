import React, { useEffect, useRef } from 'react';
import { Tabs, Empty, Button, Typography } from 'antd';

const { Text } = Typography;

export interface WorkspaceTabItem {
	key: string;
	title: string;
	toolName?: string;
	content: string;
	createdAt: Date;
	closable?: boolean;
}

interface WorkspacePanelProps {
	tabs: WorkspaceTabItem[];
	activeKey?: string;
	onChange?: (key: string) => void;
	onClose?: (key: string) => void;
	onClear?: () => void;
	onCollapse?: () => void;
}

const WorkspacePanel: React.FC<WorkspacePanelProps> = ({ tabs, activeKey, onChange, onClose, onClear, onCollapse }) => {
	const bodyRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (bodyRef.current) {
			try {
				bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
			} catch {}
		}
	}, [tabs, activeKey]);

	if (!tabs || tabs.length === 0) {
		return (
			<div className="workspace-panel">
				<div className="workspace-header">
					<Text strong>工作空间</Text>
					<div style={{ display: 'flex', gap: 8 }}>
						<Button size="small" onClick={onCollapse}>收起</Button>
					</div>
				</div>
				<div className="workspace-body" ref={bodyRef}>
					<Empty description="工具执行结果会显示在这里" />
				</div>
			</div>
		);
	}

	return (
		<div className="workspace-panel">
			<div className="workspace-header">
				<Text strong>工作空间</Text>
				<div style={{ display: 'flex', gap: 8 }}>
					<Button size="small" onClick={onClear}>清空</Button>
					<Button size="small" onClick={onCollapse}>收起</Button>
				</div>
			</div>
			<div className="workspace-body" ref={bodyRef}>
				<Tabs
					type="editable-card"
					hideAdd
					activeKey={activeKey}
					onChange={(key) => onChange && onChange(key)}
					onEdit={(targetKey, action) => {
						if (action === 'remove' && typeof targetKey === 'string') {
							onClose && onClose(targetKey);
						}
					}}
					items={tabs.map(tab => ({
						key: tab.key,
						label: tab.title,
						closable: tab.closable !== false,
						children: (
							<div className="workspace-content">
								{tab.content && tab.content.trim().startsWith('<') ? (
									<div dangerouslySetInnerHTML={{ __html: tab.content }} />
								) : (
									<pre className="workspace-pre">{tab.content}</pre>
								)}
							</div>
						)
					}))}
				/>
			</div>
		</div>
	);
};

export default WorkspacePanel; 