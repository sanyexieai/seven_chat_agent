import os
import io
import base64
import tempfile
from typing import Optional, Tuple, Dict, Any
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
            'csv': self._extract_csv_text,
            'log': self._extract_txt_text,
            'html': self._extract_html_text,
            'htm': self._extract_html_text,
            'xml': self._extract_xml_text,
            'rtf': self._extract_rtf_text,
            'odt': self._extract_odt_text,
            'epub': self._extract_epub_text,
            'mobi': self._extract_mobi_text,
            'azw': self._extract_mobi_text,
            'azw3': self._extract_mobi_text,
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
    
    def _extract_csv_text(self, file_content: bytes, filename: str = None) -> Tuple[str, dict]:
        """提取CSV文件文本内容"""
        try:
            import pandas as pd
            
            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            for encoding in encodings:
                try:
                    df = pd.read_csv(io.BytesIO(file_content), encoding=encoding)
                    text = df.to_string(index=False)
                    return text, {"encoding": encoding, "extraction_method": "pandas", "rows": len(df), "columns": len(df.columns)}
                except UnicodeDecodeError:
                    continue
            
            # 如果都失败，使用latin-1
            df = pd.read_csv(io.BytesIO(file_content), encoding='latin-1')
            text = df.to_string(index=False)
            return text, {"encoding": "latin-1", "extraction_method": "pandas", "rows": len(df), "columns": len(df.columns)}
            
        except ImportError:
            logger.warning("pandas未安装，使用文本提取")
            return self._extract_txt_text(file_content, filename)
        except Exception as e:
            logger.error(f"CSV文本提取失败: {str(e)}")
            raise
    
    def _extract_html_text(self, file_content: bytes, filename: str = None) -> Tuple[str, dict]:
        """提取HTML文件文本内容"""
        try:
            from bs4 import BeautifulSoup
            
            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            for encoding in encodings:
                try:
                    html_content = file_content.decode(encoding)
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # 移除脚本和样式标签
                    for script in soup(["script", "style"]):
                        script.decompose()
                    
                    text = soup.get_text()
                    return text, {"encoding": encoding, "extraction_method": "BeautifulSoup"}
                except UnicodeDecodeError:
                    continue
            
            # 如果都失败，使用latin-1
            html_content = file_content.decode('latin-1')
            soup = BeautifulSoup(html_content, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text()
            return text, {"encoding": "latin-1", "extraction_method": "BeautifulSoup"}
            
        except ImportError:
            logger.warning("BeautifulSoup未安装，使用文本提取")
            return self._extract_txt_text(file_content, filename)
        except Exception as e:
            logger.error(f"HTML文本提取失败: {str(e)}")
            raise
    
    def _extract_xml_text(self, file_content: bytes, filename: str = None) -> Tuple[str, dict]:
        """提取XML文件文本内容"""
        try:
            from bs4 import BeautifulSoup
            
            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            for encoding in encodings:
                try:
                    xml_content = file_content.decode(encoding)
                    soup = BeautifulSoup(xml_content, 'xml')
                    text = soup.get_text()
                    return text, {"encoding": encoding, "extraction_method": "BeautifulSoup-XML"}
                except UnicodeDecodeError:
                    continue
            
            # 如果都失败，使用latin-1
            xml_content = file_content.decode('latin-1')
            soup = BeautifulSoup(xml_content, 'xml')
            text = soup.get_text()
            return text, {"encoding": "latin-1", "extraction_method": "BeautifulSoup-XML"}
            
        except ImportError:
            logger.warning("BeautifulSoup未安装，使用文本提取")
            return self._extract_txt_text(file_content, filename)
        except Exception as e:
            logger.error(f"XML文本提取失败: {str(e)}")
            raise
    
    def _extract_rtf_text(self, file_content: bytes, filename: str = None) -> Tuple[str, dict]:
        """提取RTF文件文本内容"""
        try:
            import striprtf
            
            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            for encoding in encodings:
                try:
                    rtf_content = file_content.decode(encoding)
                    text = striprtf.striprtf(rtf_content)
                    return text, {"encoding": encoding, "extraction_method": "striprtf"}
                except UnicodeDecodeError:
                    continue
            
            # 如果都失败，使用latin-1
            rtf_content = file_content.decode('latin-1')
            text = striprtf.striprtf(rtf_content)
            return text, {"encoding": "latin-1", "extraction_method": "striprtf"}
            
        except ImportError:
            logger.warning("striprtf未安装，使用文本提取")
            return self._extract_txt_text(file_content, filename)
        except Exception as e:
            logger.error(f"RTF文本提取失败: {str(e)}")
            raise
    
    def _extract_odt_text(self, file_content: bytes, filename: str = None) -> Tuple[str, dict]:
        """提取ODT文件文本内容"""
        try:
            from odf import text, teletype
            from odf.opendocument import load
            
            # 加载ODT文档
            doc = load(io.BytesIO(file_content))
            
            # 提取文本
            text_content = ""
            for paragraph in doc.getElementsByType(text.P):
                text_content += teletype.extractText(paragraph) + "\n"
            
            return text_content, {"extraction_method": "odf"}
            
        except ImportError:
            logger.warning("odfpy未安装，使用文本提取")
            return self._extract_txt_text(file_content, filename)
        except Exception as e:
            logger.error(f"ODT文本提取失败: {str(e)}")
            raise
    
    def _extract_epub_text(self, file_content: bytes, filename: str = None) -> Tuple[str, dict]:
        """提取EPUB文件文本内容"""
        try:
            import zipfile
            from bs4 import BeautifulSoup
            
            # EPUB是ZIP格式
            with zipfile.ZipFile(io.BytesIO(file_content)) as epub:
                # 读取OPF文件
                opf_files = [f for f in epub.namelist() if f.endswith('.opf')]
                if not opf_files:
                    raise Exception("未找到OPF文件")
                
                opf_content = epub.read(opf_files[0])
                opf_soup = BeautifulSoup(opf_content, 'xml')
                
                # 获取所有HTML文件
                html_files = []
                for item in opf_soup.find_all('item'):
                    if item.get('media-type') == 'application/xhtml+xml':
                        html_files.append(item.get('href'))
                
                # 提取所有HTML文件的文本
                text_content = ""
                for html_file in html_files:
                    try:
                        html_content = epub.read(html_file)
                        soup = BeautifulSoup(html_content, 'html.parser')
                        text_content += soup.get_text() + "\n"
                    except Exception as e:
                        logger.warning(f"提取HTML文件 {html_file} 失败: {str(e)}")
                        continue
                
                return text_content, {"extraction_method": "epub", "html_files": len(html_files)}
            
        except ImportError:
            logger.warning("zipfile或BeautifulSoup未安装，使用文本提取")
            return self._extract_txt_text(file_content, filename)
        except Exception as e:
            logger.error(f"EPUB文本提取失败: {str(e)}")
            raise
    
    def _extract_mobi_text(self, file_content: bytes, filename: str = None) -> Tuple[str, dict]:
        """提取MOBI文件文本内容"""
        try:
            from mobi import Mobi
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.mobi', delete=False) as temp_file:
                temp_file.write(file_content)
                temp_file.flush()
                
                # 提取文本
                mobi = Mobi(temp_file.name)
                text = mobi.get_text()
                
                # 清理临时文件
                os.unlink(temp_file.name)
                
                return text, {"extraction_method": "mobi"}
            
        except ImportError:
            logger.warning("mobi未安装，使用文本提取")
            return self._extract_txt_text(file_content, filename)
        except Exception as e:
            logger.error(f"MOBI文本提取失败: {str(e)}")
            raise
    
    def get_file_info(self, file_content: bytes, filename: str = None) -> Dict[str, Any]:
        """获取文件信息"""
        file_type = filename.split('.')[-1].lower() if filename else 'unknown'
        
        return {
            "filename": filename,
            "file_type": file_type,
            "file_size": len(file_content),
            "is_supported": self.is_supported_format(file_type),
            "supported_formats": list(self.supported_formats.keys())
        }
    
    def is_supported_format(self, file_type: str) -> bool:
        """检查文件格式是否支持文本提取"""
        return file_type.lower() in self.supported_formats 