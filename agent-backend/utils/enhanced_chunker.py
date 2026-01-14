# -*- coding: utf-8 -*-
from typing import List, Dict, Any, Optional
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from utils.log_helper import get_logger
import re

logger = get_logger("enhanced_chunker")


class EnhancedChunker:
    """增强的分块器：结合标题上下文和语义分块"""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.base_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?"]
        )

    def chunk_documents(self, documents: List[str], metadata: Optional[List[Dict[str, Any]]] = None) -> List[Document]:
        """分块文档，保留标题上下文"""
        all_chunks = []

        for i, doc_text in enumerate(documents):
            doc_metadata = metadata[i] if metadata and i < len(metadata) else {}

            # 提取文档结构
            sections = self._extract_sections(doc_text)

            if sections:
                # 按章节分块
                chunks = self._chunk_with_sections(sections, doc_metadata)
            else:
                # 无结构，直接分块
                chunks = self._chunk_plain_text(doc_text, doc_metadata)

            all_chunks.extend(chunks)

        logger.info(f"分块完成，共生成 {len(all_chunks)} 个 chunks")
        return all_chunks

    def _extract_sections(self, text: str) -> List[Dict[str, Any]]:
        """提取文档章节结构"""
        sections = []

        # 匹配标题模式：Markdown 标题、数字标题、中文章节
        patterns = [
            r'^(#{1,6})\s+(.+)$',  # Markdown: # Title
            r'^(\d+\.)+\s+(.+)$',  # 数字: 1.1 Title
            r'^第[一二三四五六七八九十\d]+[章节]\s+(.+)$',  # 中文: 第一章 Title
        ]

        lines = text.split('\n')
        current_section = None
        current_content = []

        for line in lines:
            is_header = False
            header_level = 0
            header_text = ""

            for pattern in patterns:
                match = re.match(pattern, line.strip())
                if match:
                    is_header = True
                    if pattern.startswith(r'^(#{1,6})'):
                        header_level = len(match.group(1))
                        header_text = match.group(2)
                    else:
                        header_level = 1
                        header_text = match.group(0)
                    break

            if is_header:
                # 保存前一个章节
                if current_section:
                    current_section['content'] = '\n'.join(current_content).strip()
                    if current_section['content']:
                        sections.append(current_section)

                # 开始新章节
                current_section = {
                    'title': header_text,
                    'level': header_level,
                    'content': ''
                }
                current_content = []
            else:
                current_content.append(line)

        # 保存最后一个章节
        if current_section:
            current_section['content'] = '\n'.join(current_content).strip()
            if current_section['content']:
                sections.append(current_section)

        return sections

    def _chunk_with_sections(self, sections: List[Dict[str, Any]], base_metadata: Dict[str, Any]) -> List[Document]:
        """按章节分块，保留标题上下文"""
        chunks = []

        for section in sections:
            title = section['title']
            content = section['content']
            level = section['level']

            # 如果章节内容较短，直接作为一个 chunk
            if len(content) <= self.chunk_size:
                chunk_metadata = {
                    **base_metadata,
                    'section_title': title,
                    'section_level': level,
                    'chunk_type': 'section'
                }
                chunks.append(Document(
                    page_content=f"# {title}\n\n{content}",
                    metadata=chunk_metadata
                ))
            else:
                # 章节内容较长，需要进一步分块
                sub_chunks = self.base_splitter.split_text(content)

                for idx, sub_chunk in enumerate(sub_chunks):
                    chunk_metadata = {
                        **base_metadata,
                        'section_title': title,
                        'section_level': level,
                        'chunk_index': idx,
                        'total_chunks': len(sub_chunks),
                        'chunk_type': 'section_part'
                    }
                    # 在每个子块前添加标题作为上下文
                    chunks.append(Document(
                        page_content=f"# {title}\n\n{sub_chunk}",
                        metadata=chunk_metadata
                    ))

        return chunks

    def _chunk_plain_text(self, text: str, base_metadata: Dict[str, Any]) -> List[Document]:
        """无结构文本的分块"""
        sub_chunks = self.base_splitter.split_text(text)

        chunks = []
        for idx, chunk in enumerate(sub_chunks):
            chunk_metadata = {
                **base_metadata,
                'chunk_index': idx,
                'total_chunks': len(sub_chunks),
                'chunk_type': 'plain'
            }
            chunks.append(Document(
                page_content=chunk,
                metadata=chunk_metadata
            ))

        return chunks
