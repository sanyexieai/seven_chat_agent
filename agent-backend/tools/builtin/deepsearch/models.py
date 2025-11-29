"""深度搜索相关模型"""
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class Doc:
    """文档模型"""
    content: str
    title: Optional[str] = None
    link: Optional[str] = None
    source: Optional[str] = None
    doc_type: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.data and not self.metadata:
            self.metadata = self.data
        if not self.title:
            self.title = self.content[:50] if self.content else ""
    
    def to_html(self) -> str:
        """转换为HTML格式"""
        html = f"<h3>{self.title or '无标题'}</h3>\n"
        html += f"<p>{self.content}</p>\n"
        if self.link:
            html += f"<a href='{self.link}'>来源链接</a>\n"
        return html
    
    def to_dict(self, truncate_len: int = 200) -> Dict[str, Any]:
        """转换为字典"""
        content = self.content[:truncate_len] if len(self.content) > truncate_len else self.content
        return {
            "title": self.title or "",
            "content": content,
            "link": self.link,
            "source": self.source,
            "doc_type": self.doc_type,
            "metadata": self.metadata or {}
        }


@dataclass
class StreamMode:
    """流式模式配置"""
    token: int = 100  # 每次输出的token数

