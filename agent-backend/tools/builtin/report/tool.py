# -*- coding: utf-8 -*-
"""
报告生成工具
"""
from typing import Dict, Any
from tools.base_tool import BaseTool
from utils.log_helper import get_logger
import json
import os

logger = get_logger("report_tool")


class ReportTool(BaseTool):
    """报告生成工具"""
    
    def __init__(self):
        super().__init__(
            name="report",
            description="报告生成工具，可以生成markdown、html或ppt格式的报告",
            container_type=BaseTool.CONTAINER_TYPE_FILE,  # 绑定文件容器
            container_config={
                "workspace_dir": "reports",
                "allowed_formats": ["markdown", "html", "ppt"]
            }
        )
    
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """执行报告生成"""
        # 从本地模块导入报告生成函数
        try:
            from tools.builtin.report.report_impl import report
        except ImportError:
            try:
                from genie_tool.tool.report import report
            except ImportError:
                raise RuntimeError(
                    "报告生成工具不可用：缺少依赖。"
                    "请确保已安装相关依赖，或安装 genie_tool 包。"
                )
        
        task = parameters.get("task", "")
        file_names = parameters.get("file_names", [])
        file_type = parameters.get("file_type", "markdown")
        output_path = parameters.get("output_path")  # 可选：指定输出路径
        
        # 过滤掉已废弃的 model 参数（如果存在）
        # model 参数已移除，现在从环境变量 REPORT_MODEL 获取
        
        results = []
        async for chunk in report(
            task=task,
            file_type=file_type,
            file_names=file_names if file_names else None
        ):
            results.append(chunk)
        
        # 合并所有结果
        report_content = "".join(results)
        
        # 保存到本地文件
        if report_content:
            try:
                from datetime import datetime
                
                # 如果没有指定输出路径，使用默认路径
                if not output_path:
                    # 使用配置的工作目录
                    workspace_dir = self.container_config.get("workspace_dir", "reports")
                    os.makedirs(workspace_dir, exist_ok=True)
                    
                    # 生成文件名：基于任务和时间戳
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    # 从任务中提取关键词作为文件名（取前20个字符）
                    task_slug = "".join(c for c in task[:20] if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
                    if not task_slug:
                        task_slug = "report"
                    
                    # 根据文件类型确定扩展名
                    ext_map = {
                        "markdown": ".md",
                        "html": ".html",
                        "ppt": ".pptx"
                    }
                    ext = ext_map.get(file_type, ".md")
                    
                    output_path = os.path.join(workspace_dir, f"{task_slug}_{timestamp}{ext}")
                
                # 确保目录存在
                output_dir = os.path.dirname(output_path)
                if output_dir:  # 只有当目录不为空时才创建
                    os.makedirs(output_dir, exist_ok=True)
                
                # 写入文件（根据文件类型选择写入模式）
                if file_type == "ppt":
                    # PPT 文件可能是二进制，但这里先按文本处理
                    # 如果后续需要支持真正的 PPT 二进制格式，需要额外处理
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(report_content)
                else:
                    # Markdown 和 HTML 文件使用文本模式
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(report_content)
                
                logger.info(f"报告已保存到: {output_path}")
                
                # 计算相对路径（相对于项目根目录）
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
                try:
                    rel_path = os.path.relpath(output_path, project_root)
                    # 统一使用正斜杠作为路径分隔符（用于URL）
                    rel_path = rel_path.replace("\\", "/")
                except ValueError:
                    # 如果无法计算相对路径，使用绝对路径
                    rel_path = output_path.replace("\\", "/")
                
                # 生成下载URL
                download_url = f"/api/files/download/{rel_path}"
                
                # 返回结构化的结果，包含下载链接信息（JSON格式，方便前端解析）
                result_data = {
                    "message": "报告已生成并保存",
                    "file_path": output_path,
                    "file_name": os.path.basename(output_path),
                    "download_url": download_url,
                    "file_size": len(report_content),
                    "preview": report_content[:500] + "..." if len(report_content) > 500 else report_content,
                    "full_content": report_content  # 保留完整内容供后续使用
                }
                
                # 返回格式化的文本，包含可点击的下载链接标记
                return f"✅ 报告已生成并保存\n\n📄 文件名: {result_data['file_name']}\n📁 路径: {output_path}\n💾 大小: {len(report_content)} 字符\n\n🔗 [下载链接]({download_url})\n\n📝 内容预览:\n{result_data['preview']}\n\n<!-- REPORT_DOWNLOAD_INFO: {json.dumps(result_data, ensure_ascii=False)} -->"
            except Exception as e:
                logger.error(f"保存报告文件失败: {e}")
                # 即使保存失败，也返回报告内容
                return f"报告生成成功，但保存文件失败: {str(e)}\n\n报告内容:\n{report_content}"
        
        return report_content
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "报告生成任务描述"
                },
                "file_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要处理的文件名列表",
                    "default": []
                },
                "file_type": {
                    "type": "string",
                    "enum": ["markdown", "html", "ppt"],
                    "description": "报告类型",
                    "default": "markdown"
                },
                "output_path": {
                    "type": "string",
                    "description": "输出文件路径（可选，如果不指定则自动生成）",
                    "default": None
                }
            },
            "required": ["task"]
        }
