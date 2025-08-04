import os
import io
import base64
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class FileExtractor:
    """文件内容提取器，支持多种文件格式的文本提取"""
    
    def __init__(self):
        self.supported_formats = {
            'pdf': self._extract_pdf_text,
            'doc': self._extract_doc_text,
            'docx': self._extract_docx_text,
            'txt': self._extract_txt_text,
            'md': self._extract_txt_text,
            'json': self._extract_txt_text,
            'csv': self._extract_txt_text,
            'log': self._extract_txt_text,
        }
    
    def extract_text(self, file_content: bytes, file_type: str, filename: str = None) -> Tuple[str, dict]:
        """
        提取文件中的文本内容
        
        Args:
            file_content: 文件二进制内容
            file_type: 文件类型（扩展名）
            filename: 文件名
            
        Returns:
            (text_content, metadata): 提取的文本内容和元数据
        """
        file_type = file_type.lower()
        
        # 对于文本文件，直接解码
        if file_type in ['txt', 'md', 'json', 'csv', 'log']:
            return self._extract_txt_text(file_content, filename)
        
        # 对于支持的文件格式，使用相应的提取器
        if file_type in self.supported_formats:
            try:
                return self.supported_formats[file_type](file_content, filename)
            except Exception as e:
                logger.error(f"提取{file_type}文件内容失败: {str(e)}")
                # 如果提取失败，返回base64编码的内容
                return self._fallback_to_base64(file_content, file_type, filename)
        
        # 对于不支持的文件格式，返回base64编码
        return self._fallback_to_base64(file_content, file_type, filename)
    
    def _extract_txt_text(self, file_content: bytes, filename: str = None) -> Tuple[str, dict]:
        """提取文本文件内容"""
        try:
            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            for encoding in encodings:
                try:
                    text = file_content.decode(encoding)
                    return text, {"encoding": encoding, "extraction_method": "text_decode"}
                except UnicodeDecodeError:
                    continue
            
            # 如果所有编码都失败，使用latin-1作为最后选择
            text = file_content.decode('latin-1')
            return text, {"encoding": "latin-1", "extraction_method": "text_decode"}
            
        except Exception as e:
            logger.error(f"文本文件解码失败: {str(e)}")
            raise
    
    def _extract_pdf_text(self, file_content: bytes, filename: str = None) -> Tuple[str, dict]:
        """提取PDF文件文本内容"""
        try:
            # 尝试使用PyPDF2
            try:
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                
                if text.strip():
                    return text, {"extraction_method": "PyPDF2", "pages": len(pdf_reader.pages)}
            except ImportError:
                logger.warning("PyPDF2未安装，尝试其他方法")
            
            # 尝试使用PyMuPDF
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(stream=file_content, filetype="pdf")
                text = ""
                for page in doc:
                    text += page.get_text() + "\n"
                doc.close()
                
                if text.strip():
                    return text, {"extraction_method": "PyMuPDF", "pages": len(doc)}
            except ImportError:
                logger.warning("PyMuPDF未安装")
            
            # 如果都失败了，返回错误信息
            raise Exception("PDF文本提取失败：需要安装PyPDF2或PyMuPDF")
            
        except Exception as e:
            logger.error(f"PDF文本提取失败: {str(e)}")
            raise
    
    def _extract_doc_text(self, file_content: bytes, filename: str = None) -> Tuple[str, dict]:
        """提取DOC文件文本内容"""
        try:
            # 尝试使用python-docx2txt
            try:
                import docx2txt
                # 将doc内容写入临时文件
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.doc', delete=False) as temp_file:
                    temp_file.write(file_content)
                    temp_file.flush()
                    text = docx2txt.process(temp_file.name)
                os.unlink(temp_file.name)
                
                if text.strip():
                    return text, {"extraction_method": "docx2txt"}
            except ImportError:
                logger.warning("docx2txt未安装")
            except Exception as e:
                logger.warning(f"docx2txt提取失败: {str(e)}")
            
            # 如果提取失败，返回错误信息
            raise Exception("DOC文本提取失败：需要安装docx2txt")
            
        except Exception as e:
            logger.error(f"DOC文本提取失败: {str(e)}")
            raise
    
    def _extract_docx_text(self, file_content: bytes, filename: str = None) -> Tuple[str, dict]:
        """提取DOCX文件文本内容"""
        try:
            # 尝试使用python-docx
            try:
                from docx import Document
                doc = Document(io.BytesIO(file_content))
                text = ""
                for paragraph in doc.paragraphs:
                    text += paragraph.text + "\n"
                
                if text.strip():
                    return text, {"extraction_method": "python-docx"}
            except ImportError:
                logger.warning("python-docx未安装")
            except Exception as e:
                logger.warning(f"python-docx提取失败: {str(e)}")
            
            # 尝试使用docx2txt作为备选
            try:
                import docx2txt
                text = docx2txt.process(io.BytesIO(file_content))
                
                if text.strip():
                    return text, {"extraction_method": "docx2txt"}
            except ImportError:
                logger.warning("docx2txt未安装")
            except Exception as e:
                logger.warning(f"docx2txt提取失败: {str(e)}")
            
            # 如果都失败了，返回错误信息
            raise Exception("DOCX文本提取失败：需要安装python-docx或docx2txt")
            
        except Exception as e:
            logger.error(f"DOCX文本提取失败: {str(e)}")
            raise
    
    def _fallback_to_base64(self, file_content: bytes, file_type: str, filename: str = None) -> Tuple[str, dict]:
        """对于不支持的文件格式，返回base64编码"""
        text = base64.b64encode(file_content).decode('utf-8')
        return text, {
            "encoding": "base64",
            "extraction_method": "base64_encoding",
            "note": f"文件类型{file_type}不支持文本提取，已编码为base64"
        }
    
    def is_supported_format(self, file_type: str) -> bool:
        """检查文件格式是否支持文本提取"""
        return file_type.lower() in self.supported_formats 