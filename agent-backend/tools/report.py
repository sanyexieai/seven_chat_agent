# -*- coding: utf-8 -*-
# =====================
# 
# 
# Author: liumin.423
# Date:   2025/7/7
# =====================
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
    # 使用适配层
    from tools.genie_tool_adapter.util.file_util import download_all_files, truncate_files, flatten_search_file
    from tools.genie_tool_adapter.util.prompt_util import get_prompt
    from tools.genie_tool_adapter.util.log_util import timer
    from tools.genie_tool_adapter.model.context import LLMModelInfoFactory

from utils.llm_helper import get_llm_helper

load_dotenv()

MARKDOWN_REPORT_PROMPT_TEMPLATE = Template("""
你是资深数据分析师和执行专家，需要基于提供的文件内容**实际执行分析任务**，而不是只写规划。

你的任务是：
1. **深入分析**：仔细阅读所有文件内容，提取关键数据、统计信息、趋势、异常等
2. **执行计算**：进行数据统计、对比分析、问题识别等实际分析工作
3. **得出结论**：基于实际分析结果给出具体、可执行的结论和建议

---
【任务上下文】
- 任务：{{ task }}
- 当前时间：{{ current_time }}
- 相关文件概览：
{{ file_summary_table }}

【文件详细内容 - 请仔细分析以下内容】
{{ file_details }}

---
【执行要求】
1. **必须基于实际文件内容进行分析**，不要写泛泛而谈的内容或占位符
2. **使用文件统计信息**：利用文件统计信息（字符数、行数、错误数、警告数等）进行数据分析
3. **提取具体数据**：从文件中提取数字、统计、关键信息、错误信息等实际数据
4. **识别问题**：基于文件中的错误和警告统计，找出实际问题、异常、风险点
5. **执行计算**：进行数据对比、趋势分析、问题统计等实际计算
6. **给出结论**：基于实际分析结果，给出具体可执行的建议，不要写"示例"或"占位符"
7. 如果文件内容不足，明确说明缺少什么信息，需要什么补充

---
【报告结构 - 请按此结构输出，但内容必须基于实际分析】

# 任务报告：{{ task }}

**日期**：{{ current_time }}

## 目录

1. [任务概述](#任务概述)
2. [文件列表](#文件列表)
3. [执行详情](#执行详情)
4. [结论](#结论)

---

## 任务概述

### 任务描述

当前任务为：`{{ task }}`

**请基于文件内容，说明任务的实际执行情况和完成度**。

---

## 文件列表

{{ file_summary_table }}

---

## 执行详情

### 步骤摘要

**请基于实际文件内容，描述以下步骤的真实执行情况：**

1. **输入验证**：基于 `{{ file_names_desc }}` 等文件，说明实际验证了哪些内容，发现了什么问题
2. **核心处理**：基于文件内容，说明实际执行了哪些关键操作，处理了哪些数据，得到了什么结果
3. **结果输出**：说明实际生成了哪些输出，状态如何

### 关键数据

**请从文件中提取实际的关键数据，不要写占位符：**

```yaml
任务状态: [基于文件内容判断：已完成/进行中/失败/阻塞，并说明原因]
处理时间: {{ current_time }}
涉及文件:
{{ yaml_files_block }}
实际处理的数据量: [从文件中提取]
关键指标: [从文件中提取具体数字或指标]
发现的问题: [从文件中识别出的实际问题]
```

---

## 结论

**请基于实际分析结果，给出具体可执行的结论：**

> 1. **主要发现**：[基于文件内容的具体发现，不要写"示例"或占位符]
> 2. **问题与风险**：[从文件中识别出的实际问题和风险]
> 3. **下一步建议**：[基于实际分析结果，给出具体可执行的建议]
> 4. **信息缺口**：[如果信息不足，明确说明缺少什么，需要补充什么]
""")


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

    model = os.getenv("REPORT_MODEL", "gpt-4.1")
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

    model = os.getenv("REPORT_MODEL", "gpt-4.1")
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
    prompt = MARKDOWN_REPORT_PROMPT_TEMPLATE.render(
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
    model = os.getenv("REPORT_MODEL", "gpt-4.1")
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


if __name__ == "__main__":
    pass
