# -*- coding: utf-8 -*-
"""
工具管理API
提供工具管理的相关接口
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from database.database import get_db
from pydantic import BaseModel
from models.database_models import (
    TemporaryTool, TemporaryToolCreate, TemporaryToolUpdate, TemporaryToolResponse,
    ToolConfig, ToolConfigCreate, ToolConfigUpdate, ToolConfigResponse,
    PromptTemplate
)
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper
from utils.prompt_templates import PromptTemplates
from tools.tool_manager import ToolManager
import json

logger = get_logger("tools_api")
router = APIRouter(prefix="/api/tools", tags=["tools"])

# 获取ToolManager实例
def get_tool_manager() -> ToolManager:
    """获取工具管理器实例"""
    from main import agent_manager
    if agent_manager is None:
        raise HTTPException(status_code=503, detail="系统正在初始化，请稍后再试")
    
    # 从agent_manager获取tool_manager，如果不存在则创建
    if not hasattr(agent_manager, 'tool_manager') or agent_manager.tool_manager is None:
        tool_manager = ToolManager()
        tool_manager.set_agent_manager(agent_manager)
        agent_manager.tool_manager = tool_manager
        # 注意：这里不自动初始化，因为可能需要在应用启动时统一初始化
    
    return agent_manager.tool_manager


@router.get("/", response_model=Dict[str, Any])
async def get_all_tools(
    tool_type: Optional[str] = None,
    category: Optional[str] = None,
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """获取所有工具列表"""
    try:
        tools = tool_manager.get_available_tools(tool_type=tool_type)
        
        if category:
            tools = [t for t in tools if t.get("category") == category]
        
        statistics = tool_manager.get_tool_statistics()
        
        return {
            "tools": tools,
            "statistics": statistics
        }
    except Exception as e:
        logger.error(f"获取工具列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取工具列表失败: {str(e)}")


# 兼容无尾斜杠路径：/api/tools
@router.get("", response_model=Dict[str, Any])
async def get_all_tools_no_slash(
    tool_type: Optional[str] = None,
    category: Optional[str] = None,
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """
    兼容 /api/tools（无尾斜杠） 的访问方式。
    实际逻辑复用 get_all_tools，避免在生产环境被 SPA 通配符路由拦截成 404。
    """
    return await get_all_tools(tool_type=tool_type, category=category, tool_manager=tool_manager)


@router.get("/types/{tool_type}", response_model=List[Dict[str, Any]])
async def get_tools_by_type(
    tool_type: str,
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """按类型获取工具"""
    try:
        tools = tool_manager.get_tools_by_type(tool_type)
        return tools
    except Exception as e:
        logger.error(f"获取工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取工具失败: {str(e)}")


@router.get("/categories/{category}", response_model=List[Dict[str, Any]])
async def get_tools_by_category(
    category: str,
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """按类别获取工具"""
    try:
        tools = tool_manager.get_tools_by_category(category)
        return tools
    except Exception as e:
        logger.error(f"获取工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取工具失败: {str(e)}")


@router.get("/search", response_model=List[Dict[str, Any]])
async def search_tools(
    q: str,
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """搜索工具"""
    try:
        tools = tool_manager.search_tools(q)
        return tools
    except Exception as e:
        logger.error(f"搜索工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"搜索工具失败: {str(e)}")


@router.get("/statistics", response_model=Dict[str, Any])
async def get_tool_statistics(
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """获取工具统计信息"""
    try:
        return tool_manager.get_tool_statistics()
    except Exception as e:
        logger.error(f"获取工具统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取工具统计失败: {str(e)}")


@router.post("/execute")
async def execute_tool(
    tool_name: str,
    parameters: Dict[str, Any],
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """执行工具"""
    try:
        result = await tool_manager.execute_tool(tool_name, parameters)

        # 使用与 ToolManager 内部一致的逻辑来判断此次执行是否“成功”
        try:
            is_success = tool_manager._is_result_successful(tool_name, result)  # type: ignore[attr-defined]
        except Exception:
            # 兜底：如果判断失败，按成功处理，避免影响主流程
            is_success = True

        return {
            "success": is_success,
            "result": result
        }
    except Exception as e:
        logger.error(f"执行工具失败: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


class InferParamsRequest(BaseModel):
    """AI 自动推断工具参数请求"""
    tool_name: str
    tool_type: Optional[str] = None
    server: Optional[str] = None
    message: Optional[str] = None


class ResetToolScoreRequest(BaseModel):
    """重置工具评分请求"""
    tool_name: str


@router.post("/infer-params")
async def infer_tool_params(
    req: InferParamsRequest,
    tool_manager: ToolManager = Depends(get_tool_manager),
    db: Session = Depends(get_db),
):
    """使用与自动推理节点相同的逻辑，AI 推断工具入参"""
    try:
        # 获取工具参数 Schema（复用自动推断节点的逻辑）
        schema: Optional[Dict[str, Any]] = None
        tool_metadata: Optional[Dict[str, Any]] = None
        raw_data: Optional[Dict[str, Any]] = None
        tool_examples: Optional[List[Dict[str, Any]]] = None
        
        try:
            tool_name = req.tool_name
            tool_type = req.tool_type
            server = req.server

            # 解析 MCP 工具名称：如果 tool_name 是 mcp_{server}_{tool} 格式，自动解析
            actual_tool_name = tool_name
            actual_server = server
            if tool_name.startswith("mcp_"):
                parts = tool_name.split("_", 2)
                if len(parts) >= 3:
                    actual_server = parts[1]  # 服务器名称
                    actual_tool_name = parts[2]  # 实际工具名称
                    logger.info(f"从工具名称 {tool_name} 解析出服务器: {actual_server}, 工具名: {actual_tool_name}")
                elif len(parts) == 2:
                    # 可能是 mcp_toolname 格式，尝试作为工具名
                    actual_tool_name = parts[1]
            elif tool_type == "mcp" and server and tool_name and not tool_name.startswith("mcp_"):
                # 如果提供了 server 但没有 mcp_ 前缀，构建完整名称
                tool_name = f"mcp_{server}_{tool_name}"

            target_name = tool_name
            tool_obj = tool_manager.get_tool(target_name) if target_name else None
            if tool_obj and hasattr(tool_obj, "get_parameters_schema"):
                schema = tool_obj.get_parameters_schema()
            
            # 如果是 MCP 工具，从数据库获取额外信息
            # 优先使用解析出的 server，如果没有则使用请求中的 server
            query_server = actual_server or server
            query_tool_name = actual_tool_name if tool_name.startswith("mcp_") else tool_name
            
            if (tool_type == "mcp" or tool_name.startswith("mcp_")) and query_server and query_tool_name:
                from models.database_models import MCPTool, MCPServer
                # 通过服务器名称查找服务器ID
                db_server = db.query(MCPServer).filter(MCPServer.name == query_server).first()
                if db_server:
                    mcp_tool = db.query(MCPTool).filter(
                        MCPTool.server_id == db_server.id,
                        MCPTool.name == query_tool_name,
                        MCPTool.is_active == True
                    ).first()
                    if mcp_tool:
                        tool_metadata = mcp_tool.tool_metadata
                        raw_data = mcp_tool.raw_data
                        tool_examples = mcp_tool.examples
                        logger.info(f"从数据库获取 MCP 工具 {query_tool_name} (服务器: {query_server}) 的元数据信息")
                        if tool_metadata:
                            logger.info(f"  元数据: {json.dumps(tool_metadata, ensure_ascii=False)[:200]}...")
                        if raw_data:
                            logger.info(f"  原始数据: {json.dumps(raw_data, ensure_ascii=False)[:200]}...")
                    else:
                        logger.warning(f"未找到 MCP 工具: 服务器={query_server}, 工具名={query_tool_name}")
                else:
                    logger.warning(f"未找到 MCP 服务器: {query_server}")
        except Exception as exc:
            logger.warning(f"获取工具信息失败: {exc}")

        # 提取必填字段信息
        required_fields = []
        if schema and isinstance(schema, dict):
            required = schema.get("required", [])
            properties = schema.get("properties", {})
            if isinstance(required, list) and required:
                for field in required:
                    field_info = properties.get(field, {})
                    field_type = field_info.get("type", "string")
                    field_desc = field_info.get("description", "无描述")
                    required_fields.append(f"  - {field} ({field_type}): {field_desc}")
        
        required_fields_text = ""
        if required_fields:
            required_fields_text = "\n\n必填字段（必须全部提供）：\n" + "\n".join(required_fields)
        
        # 构建增强的上下文信息（包含工具元数据）
        additional_context = ""
        if tool_metadata:
            metadata_parts = []
            if tool_metadata.get("args_description"):
                metadata_parts.append(f"参数说明：{tool_metadata['args_description']}")
            if tool_metadata.get("usage_scenarios"):
                scenarios = tool_metadata["usage_scenarios"]
                if isinstance(scenarios, list) and scenarios:
                    metadata_parts.append(f"使用场景：{', '.join(scenarios)}")
            if tool_metadata.get("notes"):
                metadata_parts.append(f"注意事项：{tool_metadata['notes']}")
            if tool_metadata.get("best_practices"):
                metadata_parts.append(f"最佳实践：{tool_metadata['best_practices']}")
            if metadata_parts:
                additional_context = "\n\n工具元数据信息：\n" + "\n".join(f"  - {part}" for part in metadata_parts)
        
        # 如果有原始数据中的 args 信息，也添加到上下文
        if raw_data and isinstance(raw_data, dict):
            raw_args = raw_data.get("args", {})
            if raw_args:
                additional_context += f"\n\n原始参数信息：\n{json.dumps(raw_args, ensure_ascii=False, indent=2)}"
        
        # 如果有示例，添加到上下文
        if tool_examples:
            additional_context += f"\n\n工具示例：\n{json.dumps(tool_examples, ensure_ascii=False, indent=2)}"
        
        # 从统一模板获取提示词
        system_prompt = PromptTemplates.get_auto_infer_system_prompt()

        schema_json = json.dumps(schema, ensure_ascii=False, indent=2) if schema else "{}"
        # 如果没有提供用户输入，自动构造一段用于推断的说明
        message_text = req.message or (
            f"请为工具 {req.tool_name} 生成一组合理的示例参数，用于一次标准测试调用。"
            "请确保包含所有必填字段。"
        )
        
        # 使用统一模板生成用户提示词，并添加额外上下文
        user_text = PromptTemplates.get_auto_infer_user_prompt(
            tool_name=req.tool_name or "",
            tool_type=req.tool_type,
            server=req.server,
            schema_json=schema_json,
            message=message_text,
            previous_output=None,
            required_fields_text=required_fields_text + additional_context,  # 添加元数据信息
            use_simple=False  # 使用完整模板（包含 required_fields_text）
        )
        
        system_text = system_prompt

        llm_helper = get_llm_helper()
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]

        try:
            response_text = await llm_helper.call(messages, max_tokens=800)
        except Exception as exc:
            logger.error(f"调用 LLM 推断参数失败: {exc}")
            # 退化为简单兜底逻辑
            params = _fallback_params(message_text, schema)
            return {"success": True, "params": params, "fallback": True}

        params = _parse_params(response_text)
        if not params:
            params = _fallback_params(message_text, schema)
            return {"success": True, "params": params, "fallback": True}

        # 验证必填字段是否都已提供
        if schema and isinstance(schema, dict):
            required = schema.get("required", [])
            if isinstance(required, list) and required:
                missing_fields = [f for f in required if f not in params or params[f] is None or params[f] == ""]
                if missing_fields:
                    logger.warning(f"AI 推断的参数缺少必填字段: {missing_fields}，尝试补充")
                    # 尝试为缺失的必填字段生成默认值
                    properties = schema.get("properties", {})
                    for field in missing_fields:
                        field_info = properties.get(field, {})
                        field_type = field_info.get("type", "string")
                        # 根据字段类型生成合理的默认值
                        if field_type == "string":
                            params[field] = message_text or f"示例{field}"
                        elif field_type == "number" or field_type == "integer":
                            params[field] = 0
                        elif field_type == "boolean":
                            params[field] = False
                        elif field_type == "array":
                            params[field] = []
                        elif field_type == "object":
                            params[field] = {}
                        else:
                            params[field] = message_text or f"示例{field}"

        return {"success": True, "params": params}
    except Exception as e:
        logger.error(f"AI 推断工具参数失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI 推断工具参数失败: {str(e)}")


@router.post("/reset-score")
async def reset_tool_score(
    req: ResetToolScoreRequest,
    tool_manager: ToolManager = Depends(get_tool_manager),
):
    """重置指定工具的评分为默认值"""
    try:
        new_score = tool_manager.reset_tool_score(req.tool_name)
        return {
            "success": True,
            "tool_name": req.tool_name,
            "score": new_score,
        }
    except ValueError as ve:
        # 工具不存在
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"重置工具评分失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重置工具评分失败: {str(e)}")


@router.get("/prompt-templates/auto-infer")
async def get_auto_infer_prompt_templates():
    """获取自动推理工具参数的提示词模板（返回模板字符串，不格式化）"""
    # 从数据库获取模板内容（不格式化）
    from database.database import SessionLocal
    from models.database_models import PromptTemplate
    
    db = SessionLocal()
    try:
        system_template = db.query(PromptTemplate).filter(
            PromptTemplate.name == "auto_infer_system",
            PromptTemplate.template_type == "system",
            PromptTemplate.is_active == True
        ).first()
        
        user_template_simple = db.query(PromptTemplate).filter(
            PromptTemplate.name == "auto_infer_user_simple",
            PromptTemplate.template_type == "user",
            PromptTemplate.is_active == True
        ).first()
        
        user_template_full = db.query(PromptTemplate).filter(
            PromptTemplate.name == "auto_infer_user_full",
            PromptTemplate.template_type == "user",
            PromptTemplate.is_active == True
        ).first()
        
        # 如果数据库中没有，使用默认值
        from utils.prompt_templates import _DEFAULT_SYSTEM_PROMPT, _DEFAULT_USER_PROMPT_SIMPLE_TEMPLATE, _DEFAULT_USER_PROMPT_TEMPLATE
        
        return {
            "system_prompt": system_template.content if system_template else _DEFAULT_SYSTEM_PROMPT,
            "user_prompt_template": user_template_simple.content if user_template_simple else _DEFAULT_USER_PROMPT_SIMPLE_TEMPLATE,
            "user_prompt_template_full": user_template_full.content if user_template_full else _DEFAULT_USER_PROMPT_TEMPLATE
        }
    except Exception as e:
        logger.error(f"获取提示词模板失败: {str(e)}")
        # 返回默认值
        from utils.prompt_templates import _DEFAULT_SYSTEM_PROMPT, _DEFAULT_USER_PROMPT_SIMPLE_TEMPLATE, _DEFAULT_USER_PROMPT_TEMPLATE
        return {
            "system_prompt": _DEFAULT_SYSTEM_PROMPT,
            "user_prompt_template": _DEFAULT_USER_PROMPT_SIMPLE_TEMPLATE,
            "user_prompt_template_full": _DEFAULT_USER_PROMPT_TEMPLATE
        }
    finally:
        db.close()


def _parse_params(text: str) -> Optional[Dict[str, Any]]:
    """解析 LLM 返回的 JSON 字符串，兼容 ```json 包裹"""
    if not text:
        return None
    try:
        clean = text.strip()
        if clean.startswith("```"):
            # 去掉代码块包裹和可能的语言标识
            clean = clean.strip("`")
            clean = clean.replace("json", "", 1).strip()
        return json.loads(clean)
    except Exception:
        return None


def _fallback_params(message: str, schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """兜底：按必填字段或 query 字段填充"""
    params: Dict[str, Any] = {}
    required = schema.get("required") if isinstance(schema, dict) else None
    if isinstance(required, list) and required:
        for field in required:
            params[field] = message
    else:
        params["query"] = message
    return params

# 临时工具管理API
@router.get("/temporary", response_model=List[TemporaryToolResponse])
async def get_temporary_tools(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """获取所有临时工具"""
    try:
        query = db.query(TemporaryTool)
        if active_only:
            query = query.filter(TemporaryTool.is_active == True)
        tools = query.all()
        return tools
    except Exception as e:
        logger.error(f"获取临时工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取临时工具失败")


@router.get("/temporary/{tool_id}", response_model=TemporaryToolResponse)
async def get_temporary_tool(
    tool_id: int,
    db: Session = Depends(get_db)
):
    """根据ID获取临时工具"""
    try:
        tool = db.query(TemporaryTool).filter(TemporaryTool.id == tool_id).first()
        if not tool:
            raise HTTPException(status_code=404, detail="临时工具不存在")
        return tool
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取临时工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取临时工具失败")


@router.post("/temporary", response_model=TemporaryToolResponse)
async def create_temporary_tool(
    tool_data: TemporaryToolCreate,
    db: Session = Depends(get_db),
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """创建临时工具"""
    try:
        # 检查是否已存在
        existing = db.query(TemporaryTool).filter(TemporaryTool.name == tool_data.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="工具名称已存在")
        
        # 创建新工具
        tool = TemporaryTool(
            name=tool_data.name,
            display_name=tool_data.display_name,
            description=tool_data.description,
            code=tool_data.code,
            input_schema=tool_data.input_schema,
            output_schema=tool_data.output_schema,
            examples=tool_data.examples,
            container_type=tool_data.container_type or "none",
            container_config=tool_data.container_config or {},
            is_active=True,
            is_temporary=True
        )
        
        db.add(tool)
        db.commit()
        db.refresh(tool)
        
        # 重新加载临时工具
        await tool_manager.reload_temporary_tools()
        
        return tool
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"创建临时工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建临时工具失败: {str(e)}")


@router.put("/temporary/{tool_id}", response_model=TemporaryToolResponse)
async def update_temporary_tool(
    tool_id: int,
    tool_data: TemporaryToolUpdate,
    db: Session = Depends(get_db),
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """更新临时工具"""
    try:
        tool = db.query(TemporaryTool).filter(TemporaryTool.id == tool_id).first()
        if not tool:
            raise HTTPException(status_code=404, detail="临时工具不存在")
        
        # 更新字段
        update_data = tool_data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(tool, key, value)
        
        db.commit()
        db.refresh(tool)
        
        # 重新加载临时工具
        await tool_manager.reload_temporary_tools()
        
        return tool
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"更新临时工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新临时工具失败: {str(e)}")


@router.delete("/temporary/{tool_id}")
async def delete_temporary_tool(
    tool_id: int,
    db: Session = Depends(get_db),
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """删除临时工具"""
    try:
        tool = db.query(TemporaryTool).filter(TemporaryTool.id == tool_id).first()
        if not tool:
            raise HTTPException(status_code=404, detail="临时工具不存在")
        
        db.delete(tool)
        db.commit()
        
        # 重新加载临时工具
        await tool_manager.reload_temporary_tools()
        
        return {"message": "临时工具删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除临时工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除临时工具失败: {str(e)}")


@router.post("/reload")
async def reload_tools(
    tool_type: Optional[str] = None,
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """重新加载工具"""
    try:
        if tool_type == "mcp":
            await tool_manager.reload_mcp_tools()
        elif tool_type == "temporary":
            await tool_manager.reload_temporary_tools()
        else:
            await tool_manager.reload_tools()
        
        return {"message": "工具重新加载成功"}
    except Exception as e:
        logger.error(f"重新加载工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重新加载工具失败: {str(e)}")


# 工具容器配置请求模型
class ContainerConfigUpdate(BaseModel):
    container_type: Optional[str] = None
    container_config: Optional[Dict[str, Any]] = None

# 工具容器配置管理API
@router.put("/{tool_name}/container")
async def update_tool_container(
    tool_name: str,
    config: ContainerConfigUpdate,
    tool_manager: ToolManager = Depends(get_tool_manager),
    db: Session = Depends(get_db)
):
    """更新工具的容器配置（支持所有类型的工具）"""
    try:
        from models.database_models import ToolConfig, TemporaryTool, MCPTool
        
        container_type = config.container_type
        container_config = config.container_config
        
        # 获取工具信息
        tool = tool_manager.get_tool(tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail="工具不存在")
        
        # 确定工具类型
        tool_type = tool_manager.tool_types.get(tool_name, "unknown")
        
        # 根据工具类型更新相应的数据库表
        if tool_type == "temporary":
            # 更新临时工具表
            temp_tool_name = tool_name.replace("temp_", "")
            temp_tool = db.query(TemporaryTool).filter(TemporaryTool.name == temp_tool_name).first()
            if temp_tool:
                if container_type is not None:
                    temp_tool.container_type = container_type
                if container_config is not None:
                    temp_tool.container_config = container_config
                db.commit()
                db.refresh(temp_tool)
        elif tool_type == "mcp":
            # 更新MCP工具表
            # 解析工具名称：mcp_{server_name}_{tool_name}
            parts = tool_name.split("_", 2)
            if len(parts) >= 3:
                server_name = parts[1]
                mcp_tool_name = parts[2]
                # 通过服务器名称查找服务器ID
                from models.database_models import MCPServer
                server = db.query(MCPServer).filter(MCPServer.name == server_name).first()
                if server:
                    mcp_tool = db.query(MCPTool).filter(
                        MCPTool.server_id == server.id,
                        MCPTool.name == mcp_tool_name
                    ).first()
                    if mcp_tool:
                        if container_type is not None:
                            mcp_tool.container_type = container_type
                        if container_config is not None:
                            mcp_tool.container_config = container_config
                        db.commit()
                        db.refresh(mcp_tool)
        elif tool_type == "builtin":
            # 更新工具配置表（用于内置工具）
            tool_config = db.query(ToolConfig).filter(
                ToolConfig.tool_name == tool_name,
                ToolConfig.tool_type == "builtin"
            ).first()
            
            if tool_config:
                # 更新现有配置
                if container_type is not None:
                    tool_config.container_type = container_type
                if container_config is not None:
                    tool_config.container_config = container_config
            else:
                # 创建新配置
                tool_config = ToolConfig(
                    tool_name=tool_name,
                    tool_type="builtin",
                    container_type=container_type or "none",
                    container_config=container_config or {}
                )
                db.add(tool_config)
            
            db.commit()
            db.refresh(tool_config)
        
        # 重新加载工具以应用新配置
        await tool_manager.reload_tools()
        
        return {"message": "容器配置更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"更新工具容器配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新工具容器配置失败: {str(e)}")


# ==================== 提示词模板管理 API ====================

class PromptTemplateCreate(BaseModel):
    """创建提示词模板请求"""
    name: str
    display_name: str
    description: Optional[str] = None
    template_type: str  # system, user
    content: str
    variables: Optional[List[str]] = None
    version: Optional[str] = None  # 版本号，如 "1.0.0"
    is_active: bool = True


class PromptTemplateUpdate(BaseModel):
    """更新提示词模板请求"""
    display_name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    variables: Optional[List[str]] = None
    version: Optional[str] = None
    is_active: Optional[bool] = None


class PromptTemplateResponse(BaseModel):
    """提示词模板响应"""
    id: int
    name: str
    display_name: str
    description: Optional[str]
    template_type: str
    content: str
    variables: Optional[List[str]]
    is_builtin: bool
    version: Optional[str]
    usage_count: int
    source_file: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


@router.get("/prompt-templates", response_model=List[PromptTemplateResponse])
async def get_prompt_templates(
    template_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """获取所有提示词模板"""
    try:
        query = db.query(PromptTemplate)
        
        if template_type:
            query = query.filter(PromptTemplate.template_type == template_type)
        if is_active is not None:
            query = query.filter(PromptTemplate.is_active == is_active)
        
        templates = query.order_by(PromptTemplate.template_type, PromptTemplate.name).all()
        
        return [
            PromptTemplateResponse(
                id=t.id,
                name=t.name,
                display_name=t.display_name,
                description=t.description,
                template_type=t.template_type,
                content=t.content,
                variables=t.variables,
                is_builtin=t.is_builtin if hasattr(t, 'is_builtin') else False,
                version=t.version if hasattr(t, 'version') else None,
                usage_count=t.usage_count if hasattr(t, 'usage_count') else 0,
                source_file=t.source_file if hasattr(t, 'source_file') else None,
                is_active=t.is_active,
                created_at=t.created_at.isoformat() if t.created_at else "",
                updated_at=t.updated_at.isoformat() if t.updated_at else ""
            )
            for t in templates
        ]
    except Exception as e:
        logger.error(f"获取提示词模板列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取提示词模板列表失败: {str(e)}")


@router.get("/prompt-templates/{template_id}", response_model=PromptTemplateResponse)
async def get_prompt_template(
    template_id: int,
    db: Session = Depends(get_db)
):
    """获取单个提示词模板"""
    try:
        template = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="提示词模板不存在")
        
        return PromptTemplateResponse(
            id=template.id,
            name=template.name,
            display_name=template.display_name,
            description=template.description,
            template_type=template.template_type,
            content=template.content,
            variables=template.variables,
            is_builtin=template.is_builtin if hasattr(template, 'is_builtin') else False,
            version=template.version if hasattr(template, 'version') else None,
            usage_count=template.usage_count if hasattr(template, 'usage_count') else 0,
            source_file=template.source_file if hasattr(template, 'source_file') else None,
            is_active=template.is_active,
            created_at=template.created_at.isoformat() if template.created_at else "",
            updated_at=template.updated_at.isoformat() if template.updated_at else ""
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取提示词模板失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取提示词模板失败: {str(e)}")


@router.post("/prompt-templates", response_model=PromptTemplateResponse)
async def create_prompt_template(
    template_data: PromptTemplateCreate,
    db: Session = Depends(get_db)
):
    """创建提示词模板"""
    try:
        # 检查名称是否已存在
        existing = db.query(PromptTemplate).filter(PromptTemplate.name == template_data.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="提示词模板名称已存在")
        
        template = PromptTemplate(
            name=template_data.name,
            display_name=template_data.display_name,
            description=template_data.description,
            template_type=template_data.template_type,
            content=template_data.content,
            variables=template_data.variables,
            version=template_data.version or "1.0.0",
            is_builtin=False,  # 用户创建的模板不是内置的
            usage_count=0,
            is_active=template_data.is_active
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        
        # 清除缓存
        PromptTemplates.clear_cache()
        
        return PromptTemplateResponse(
            id=template.id,
            name=template.name,
            display_name=template.display_name,
            description=template.description,
            template_type=template.template_type,
            content=template.content,
            variables=template.variables,
            is_builtin=template.is_builtin if hasattr(template, 'is_builtin') else False,
            version=template.version if hasattr(template, 'version') else None,
            usage_count=template.usage_count if hasattr(template, 'usage_count') else 0,
            source_file=template.source_file if hasattr(template, 'source_file') else None,
            is_active=template.is_active,
            created_at=template.created_at.isoformat() if template.created_at else "",
            updated_at=template.updated_at.isoformat() if template.updated_at else ""
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"创建提示词模板失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建提示词模板失败: {str(e)}")


@router.put("/prompt-templates/{template_id}", response_model=PromptTemplateResponse)
async def update_prompt_template(
    template_id: int,
    template_data: PromptTemplateUpdate,
    db: Session = Depends(get_db)
):
    """更新提示词模板"""
    try:
        template = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="提示词模板不存在")
        
        # 更新字段
        if template_data.display_name is not None:
            template.display_name = template_data.display_name
        if template_data.description is not None:
            template.description = template_data.description
        if template_data.content is not None:
            template.content = template_data.content
        if template_data.variables is not None:
            template.variables = template_data.variables
        if template_data.version is not None:
            template.version = template_data.version
        if template_data.is_active is not None:
            template.is_active = template_data.is_active
        
        db.commit()
        db.refresh(template)
        
        # 清除缓存
        PromptTemplates.clear_cache()
        
        return PromptTemplateResponse(
            id=template.id,
            name=template.name,
            display_name=template.display_name,
            description=template.description,
            template_type=template.template_type,
            content=template.content,
            variables=template.variables,
            is_builtin=template.is_builtin if hasattr(template, 'is_builtin') else False,
            version=template.version if hasattr(template, 'version') else None,
            usage_count=template.usage_count if hasattr(template, 'usage_count') else 0,
            source_file=template.source_file if hasattr(template, 'source_file') else None,
            is_active=template.is_active,
            created_at=template.created_at.isoformat() if template.created_at else "",
            updated_at=template.updated_at.isoformat() if template.updated_at else ""
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"更新提示词模板失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新提示词模板失败: {str(e)}")


@router.delete("/prompt-templates/{template_id}")
async def delete_prompt_template(
    template_id: int,
    db: Session = Depends(get_db)
):
    """删除提示词模板"""
    try:
        template = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="提示词模板不存在")
        
        # 不允许删除内置模板
        if hasattr(template, 'is_builtin') and template.is_builtin:
            raise HTTPException(status_code=400, detail="不能删除内置模板")
        
        db.delete(template)
        db.commit()
        
        # 清除缓存
        PromptTemplates.clear_cache()
        
        return {"message": "提示词模板删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除提示词模板失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除提示词模板失败: {str(e)}")

