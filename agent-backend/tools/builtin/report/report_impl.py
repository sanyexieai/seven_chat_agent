import os
import re
from datetime import datetime
from typing import Optional, List, Literal, AsyncGenerator, Dict

from dotenv import load_dotenv
from jinja2 import Template
from loguru import logger

try:
    from genie_tool.util.file_util import download_all_files, truncate_files, flatten_search_file
    from genie_tool.util.prompt_util import get_prompt
    from genie_tool.util.log_util import timer
    from genie_tool.model.context import LLMModelInfoFactory
except ImportError:
    # 使用本地工具和 utils
    from tools.builtin.report.file_util import download_all_files, truncate_files, flatten_search_file
    from tools.builtin.report.prompt_util import get_prompt
    from utils.timer_decorator import timer
    from utils.context_helper import LLMModelInfoFactory

from utils.llm_helper import get_llm_helper
from database.database import SessionLocal
from models.database_models import PromptTemplate

load_dotenv()

# 报告 Markdown 提示词模板占位（真实内容由数据库中的 report_markdown_advanced 管理）
# 兜底内容只在 extract_prompts_to_db.py 中维护
_DEFAULT_MARKDOWN_REPORT_PROMPT = ""


def _get_markdown_report_prompt_template() -> Template:
    """从数据库获取 Markdown 报告提示词模板，不存在时回退到内置默认值"""
    db = SessionLocal()
    try:
        template = db.query(PromptTemplate).filter(
            PromptTemplate.name == "report_markdown_advanced",
            PromptTemplate.template_type == "system",
            PromptTemplate.is_active == True,
        ).first()
        
        if template:
            return Template(template.content)
        else:
            # 真正的兜底内容只在 extract_prompts_to_db.py 中维护，这里只给出技术性占位文本
            logger.warning("report_markdown_advanced 提示词未在数据库中配置，请在 prompt_templates 表中添加或通过提示词管理界面配置。")
            return Template(_DEFAULT_MARKDOWN_REPORT_PROMPT or "report_markdown_advanced 提示词未在数据库中配置。")
    except Exception as exc:
        logger.warning(f"从数据库获取 report_markdown_advanced 提示词失败: {exc}")
        return Template(_DEFAULT_MARKDOWN_REPORT_PROMPT or "report_markdown_advanced 提示词获取失败，请检查数据库配置。")
    finally:
        db.close()


def _get_report_model_name() -> str:
    """
    获取用于报告生成的模型名称
    优先从全局 LLM 配置（数据库）中读取，失败时回退到环境变量 REPORT_MODEL
    """
    try:
        llm_helper = get_llm_helper()
        cfg = llm_helper.get_config()
        model = (cfg or {}).get("model")
        if model:
            return model
    except Exception as exc:
        logger.warning(f"从 LLM 配置获取报告模型失败，使用环境变量 REPORT_MODEL: {exc}")
    
    # 回退到环境变量 / 默认值
    return os.getenv("REPORT_MODEL", "gpt-4.1")


@timer()
async def report(
        task: str,
        file_type: Literal["markdown", "html", "ppt"] = "markdown",
        file_names: Optional[List[str]] = None,
) -> AsyncGenerator:
    """
    生成报告
    
    Args:
        task: 任务描述
        file_type: 报告类型（markdown/html/ppt）
        file_names: 文件列表（可选，如果不提供则从 flow_state 获取）
    """
    report_factory = {
        "ppt": ppt_report,
        "markdown": markdown_report,
        "html": html_report,
    }
    # 如果提供了 file_names，传递给内部函数
    if file_names is not None:
        async for chunk in report_factory[file_type](task, file_names):
            yield chunk
    else:
        async for chunk in report_factory[file_type](task):
            yield chunk


@timer()
async def ppt_report(
        task: str,
        file_names: Optional[List[str]] = None,
        temperature: float = None,
        top_p: float = 0.6,
) -> AsyncGenerator:
    if file_names is None:
        file_names = []
    files = await download_all_files(file_names)
    flat_files = []

    # 1. 首先解析 md html 文件，没有这部分文件则使用全部
    filtered_files = [f for f in files if f["file_name"].split(".")[-1] in ["md", "html"]
                      and not f["file_name"].endswith("_搜索结果.md")] or files
    for f in filtered_files:
        # 对于搜索文件有结构，需要重新解析
        if f["file_name"].endswith("_search_result.txt"):
            flat_files.extend(flatten_search_file(f))
        else:
            flat_files.append(f)

    # 从数据库/LLM 默认配置中获取模型名称，用于计算上下文长度
    model = _get_report_model_name()
    truncate_flat_files = truncate_files(flat_files, max_tokens=int(LLMModelInfoFactory.get_context_length(model) * 0.8))
    prompt = Template(get_prompt("report")["ppt_prompt"]) \
        .render(task=task, files=truncate_flat_files, date=datetime.now().strftime("%Y-%m-%d"))

    # 使用全局统一的 llm_helper
    # 不传入配置，让它自动从数据库获取默认配置
    llm_helper = get_llm_helper()
    
    # 传递 temperature 和 top_p 参数
    async for chunk in llm_helper.call_stream(messages=prompt, temperature=temperature, top_p=top_p):
        yield chunk


@timer()
async def markdown_report(
        task,
        file_names: Optional[List[str]] = None,
        temperature: float = 0,
        top_p: float = 0.9,
) -> AsyncGenerator:
    if file_names is None:
        file_names = []
    files = await download_all_files(file_names)
    flat_files = []
    for f in files:
        # 对于搜索文件有结构，需要重新解析
        if f["file_name"].endswith("_search_result.txt"):
            flat_files.extend(flatten_search_file(f))
        else:
            flat_files.append(f)

    # 从数据库/LLM 默认配置中获取模型名称，用于计算上下文长度
    model = _get_report_model_name()
    truncate_flat_files = truncate_files(flat_files, max_tokens=int(LLMModelInfoFactory.get_context_length(model) * 0.8))

    file_entries: List[Dict[str, str]] = []
    for f in truncate_flat_files:
        raw_name = f.get("file_name") or f.get("description") or "未命名文件"
        file_name = os.path.basename(raw_name)
        description = f.get("description") or "与任务相关的输入/输出文件"
        content = (f.get("content") or "").strip()
        
        # 提取文件统计信息
        content_length = len(content)
        line_count = content.count('\n') + 1 if content else 0
        word_count = len(content.split()) if content else 0
        
        # 尝试提取关键数据（数字、错误、警告等）
        numbers = re.findall(r'\d+\.?\d*', content)
        errors = len(re.findall(r'(?i)(error|失败|异常|exception)', content))
        warnings = len(re.findall(r'(?i)(warning|警告|注意)', content))
        
        # 保留更多内容供分析（增加到3000字符）
        if len(content) > 3000:
            content_preview = content[:3000] + "\n...（内容已截断，完整内容请参考原文件）"
        else:
            content_preview = content
        
        file_entries.append({
            "name": file_name,
            "description": description,
            "content": content_preview or "（文件无可用内容）",
            "stats": {
                "length": content_length,
                "lines": line_count,
                "words": word_count,
                "numbers_found": len(numbers),
                "errors": errors,
                "warnings": warnings
            }
        })

    if not file_entries:
        file_entries.append({
            "name": "暂无文件",
            "description": "未获取到可供分析的文件",
            "content": "（其他节点未提供文件内容，无法进一步分析）",
            "stats": {}
        })

    # 生成文件列表表格（包含统计信息）
    file_table_rows = []
    for entry in file_entries:
        stats = entry.get("stats", {})
        if stats:
            stats_desc = f"大小:{stats.get('length', 0)}字符, 行数:{stats.get('lines', 0)}"
            if stats.get('errors', 0) > 0:
                stats_desc += f", 错误:{stats.get('errors', 0)}"
            if stats.get('warnings', 0) > 0:
                stats_desc += f", 警告:{stats.get('warnings', 0)}"
        else:
            stats_desc = "-"
        file_table_rows.append(f"| {entry['name']} | {entry['description']} | {stats_desc} |")
    
    file_summary_table = "\n".join([
        "| 文件名 | 说明 | 统计信息 |",
        "|--------------|------------------------|------------------|",
        *file_table_rows
    ])

    # 生成详细文件内容（包含统计信息）
    file_details_parts = []
    for entry in file_entries:
        stats = entry.get("stats", {})
        stats_info = ""
        if stats:
            stats_info = f"\n**文件统计**：字符数 {stats.get('length', 0)}, 行数 {stats.get('lines', 0)}, 词数 {stats.get('words', 0)}"
            if stats.get('numbers_found', 0) > 0:
                stats_info += f", 发现数字 {stats.get('numbers_found', 0)} 个"
            if stats.get('errors', 0) > 0:
                stats_info += f", ⚠️ 错误 {stats.get('errors', 0)} 处"
            if stats.get('warnings', 0) > 0:
                stats_info += f", ⚠️ 警告 {stats.get('warnings', 0)} 处"
        
        file_details_parts.append(
            f"### 文件：{entry['name']}\n"
            f"说明：{entry['description']}{stats_info}\n"
            f"**完整内容**：\n{entry['content']}"
        )
    
    file_details = "\n\n---\n\n".join(file_details_parts)
    file_names_desc = "、".join(entry["name"] for entry in file_entries)
    yaml_files_block = "\n".join(f"  - {entry['name']}" for entry in file_entries)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    markdown_template = _get_markdown_report_prompt_template()
    prompt = markdown_template.render(
        task=task,
        current_time=current_time,
        file_summary_table=file_summary_table,
        file_details=file_details,
        file_names_desc=file_names_desc,
        yaml_files_block=yaml_files_block or "  - 暂无文件"
    )

    # 使用全局统一的 llm_helper
    # 不传入配置，让它自动从数据库获取默认配置
    llm_helper = get_llm_helper()
    
    # 传递 temperature 和 top_p 参数
    async for chunk in llm_helper.call_stream(messages=prompt, temperature=temperature, top_p=top_p):
        yield chunk


@timer()
async def html_report(
        task,
        file_names: Optional[List[str]] = None,
        temperature: float = 0,
        top_p: float = 0.9,
) -> AsyncGenerator:
    if file_names is None:
        file_names = []
    files = await download_all_files(file_names)
    key_files = []
    flat_files = []
    # 对于搜索文件有结构，需要重新解析
    for f in files:
        fpath = f["file_name"]
        fname = os.path.basename(fpath)
        if fname.split(".")[-1] in ["md", "txt", "csv"]:
            # CI 输出结果
            if "代码输出" in fname:
                key_files.append({"content": f["content"], "description": fname, "type": "txt", "link": fpath})
            # 搜索文件
            elif fname.endswith("_search_result.txt"):
                try:
                    flat_files.extend([{
                            "content": tf["content"],
                            "description": tf.get("title") or tf["content"][:20],
                            "type": "txt",
                            "link": tf.get("link"),
                        } for tf in flatten_search_file(f)
                    ])
                except Exception as e:
                    logger.warning(f"html_report parser file [{fpath}] error: {e}")
            # 其他文件
            else:
                flat_files.append({
                    "content": f["content"],
                    "description": fname,
                    "type": "txt",
                    "link": fpath
                })
    # 从数据库/LLM 默认配置中获取模型名称，用于计算上下文长度
    model = _get_report_model_name()
    discount = int(LLMModelInfoFactory.get_context_length(model) * 0.8)
    key_files = truncate_files(key_files, max_tokens=discount)
    flat_files = truncate_files(flat_files, max_tokens=discount - sum([len(f["content"]) for f in key_files]))

    report_prompts = get_prompt("report")
    prompt = Template(report_prompts["html_task"]) \
        .render(task=task, key_files=key_files, files=flat_files, date=datetime.now().strftime('%Y年%m月%d日'))

    # 使用全局统一的 llm_helper
    # 不传入配置，让它自动从数据库获取默认配置
    llm_helper = get_llm_helper()
    
    # 如果需要自定义 temperature 和 top_p，可以通过 kwargs 传递
    
    async for chunk in llm_helper.call_stream(
            messages=[{"role": "system", "content": report_prompts["html_prompt"]},
                      {"role": "user", "content": prompt}],
            temperature=temperature, top_p=top_p):
        yield chunk

