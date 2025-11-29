"""报告生成文件工具"""
from typing import List, Optional, Dict, Any
from pathlib import Path
import os


def truncate_files(
    files: List[Any],
    max_tokens: int
) -> List[Any]:
    """截断文件列表以适应token限制"""
    # 简单的实现：如果文件列表太长，截取前面的
    # 实际应该根据内容长度计算token
    if len(files) <= max_tokens // 100:  # 假设每个文件平均100 tokens
        return files
    return files[:max_tokens // 100]


def flatten_search_file(file: Dict[str, Any]) -> List[Dict[str, Any]]:
    """展平搜索文件"""
    # 如果文件是搜索结果格式，需要展平
    if isinstance(file, dict) and "content" in file:
        return [file]
    return [file] if isinstance(file, dict) else []


async def download_all_files(file_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    下载所有文件并读取内容
    
    Args:
        file_names: 文件路径列表或文件对象列表
                    - 如果是字符串列表：文件路径（相对或绝对）
                    - 如果是字典列表：已经包含 content 的文件对象
        
    Returns:
        文件字典列表，每个字典包含 file_name, file_path, content 等字段
    """
    if not file_names:
        return []
    
    downloaded_files = []
    
    # 获取项目根目录
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent.resolve()
    
    for file_item in file_names:
        # 如果已经是文件对象（字典），直接使用
        if isinstance(file_item, dict):
            # 确保包含必要的字段
            file_info = {
                "file_name": file_item.get("file_name") or file_item.get("name") or "未命名文件",
                "file_path": file_item.get("file_path") or file_item.get("file_name") or "",
                "content": file_item.get("content") or "",
                "description": file_item.get("description") or file_item.get("file_name") or "文件"
            }
            downloaded_files.append(file_info)
            continue
        
        # 如果是字符串，作为文件路径处理
        file_name = str(file_item)
        file_info = {
            "file_name": file_name,
            "file_path": file_name,
            "content": "",
            "description": ""
        }
        
        # 尝试多种路径解析方式
        file_path = None
        
        # 1. 如果是绝对路径，直接使用
        if os.path.isabs(file_name):
            file_path = file_name
        # 2. 尝试相对于项目根目录
        else:
            # 先尝试直接路径
            potential_paths = [
                file_name,  # 直接路径
                os.path.join(project_root, file_name),  # 相对于项目根目录
                os.path.join(project_root, "reports", file_name),  # reports 目录
                os.path.join(project_root, "data", file_name),  # data 目录
            ]
            
            for path in potential_paths:
                if os.path.exists(path) and os.path.isfile(path):
                    file_path = path
                    break
        
        # 如果找到文件路径，读取文件内容
        if file_path and os.path.exists(file_path):
            try:
                # 根据文件扩展名决定读取方式
                ext = Path(file_path).suffix.lower()
                
                # 文本文件：直接读取
                if ext in ['.txt', '.md', '.markdown', '.html', '.htm', '.json', '.csv', '.py', '.js', '.ts', '.tsx', '.jsx', '.css', '.yaml', '.yml']:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                # 其他文件：尝试以文本方式读取，失败则跳过
                else:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                    except UnicodeDecodeError:
                        # 二进制文件，跳过内容读取
                        content = f"（二进制文件，无法读取文本内容）"
                
                file_info["file_path"] = file_path
                file_info["content"] = content
                file_info["description"] = f"从 {file_path} 读取的文件"
                
            except Exception as e:
                # 读取失败，记录错误但继续处理
                file_info["content"] = f"（读取文件失败: {str(e)}）"
                file_info["description"] = f"文件读取失败: {file_path}"
        else:
            # 文件不存在，可能是已经在 flow_state 中的文件对象
            file_info["content"] = f"（文件路径不存在: {file_name}，可能需要从 flow_state 获取）"
            file_info["description"] = f"文件路径不存在: {file_name}"
        
        downloaded_files.append(file_info)
    
    return downloaded_files

