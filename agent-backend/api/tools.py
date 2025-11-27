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
    ToolConfig, ToolConfigCreate, ToolConfigUpdate, ToolConfigResponse
)
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper
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
        return {
            "success": True,
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


@router.post("/infer-params")
async def infer_tool_params(
    req: InferParamsRequest,
    tool_manager: ToolManager = Depends(get_tool_manager),
):
    """使用与自动推理节点相同的逻辑，AI 推断工具入参"""
    try:
        # 获取工具参数 Schema（复用自动推断节点的逻辑）
        schema: Optional[Dict[str, Any]] = None
        try:
            tool_name = req.tool_name
            tool_type = req.tool_type
            server = req.server

            target_name = tool_name
            if tool_type == "mcp" and server and tool_name and not tool_name.startswith("mcp_"):
                target_name = f"mcp_{server}_{tool_name}"

            tool_obj = tool_manager.get_tool(target_name) if target_name else None
            if tool_obj and hasattr(tool_obj, "get_parameters_schema"):
                schema = tool_obj.get_parameters_schema()
        except Exception as exc:
            logger.warning(f"获取工具 schema 失败: {exc}")

        # 过滤掉已废弃的参数（如 model），与自动推断节点保持一致
        if schema and isinstance(schema, dict):
            schema = schema.copy()
            if "properties" in schema and isinstance(schema["properties"], dict):
                schema["properties"] = {
                    k: v for k, v in schema["properties"].items() if k != "model"
                }
            if "required" in schema and isinstance(schema["required"], list):
                schema["required"] = [r for r in schema["required"] if r != "model"]

        # 构造提示词（与 AutoParamNode 中默认提示保持一致）
        system_prompt = (
            "你是一个工具参数推理助手。请根据用户输入和工具描述，生成满足工具 schema 的 JSON 参数。"
            "必须输出 JSON，对每个必填字段给出合理值。"
            "注意：不要生成 'model' 参数，该参数已废弃，由系统自动管理。"
        )
        user_prompt = (
            "工具名称：{tool_name}\n"
            "工具类型：{tool_type}\n"
            "服务器：{server}\n"
            "参数 Schema：\n{schema_json}\n\n"
            "用户输入：{message}\n"
            "如果需要上下文，可参考上一节点输出：{previous_output}\n\n"
            "请输出 JSON，严格遵守 schema 格式。"
            "重要：不要包含 'model' 参数（如果 schema 中有，请忽略它）。"
        )

        schema_json = json.dumps(schema, ensure_ascii=False, indent=2) if schema else "{}"
        # 如果没有提供用户输入，自动构造一段用于推断的说明
        message_text = req.message or (
            f"请为工具 {req.tool_name} 生成一组合理的示例参数，用于一次标准测试调用。"
        )
        prompt_variables = {
            "message": message_text,
            "tool_name": req.tool_name,
            "tool_type": req.tool_type,
            "server": req.server,
            "schema_json": schema_json,
            "previous_output": None,
        }

        system_text = system_prompt.format(**prompt_variables)
        try:
            user_text = user_prompt.format(**prompt_variables)
        except Exception:
            # 简单兜底：不做模板替换
            user_text = user_prompt

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

        return {"success": True, "params": params}
    except Exception as e:
        logger.error(f"AI 推断工具参数失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI 推断工具参数失败: {str(e)}")


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
            # 解析工具名称：mcp_{server_id}_{tool_name}
            parts = tool_name.split("_", 2)
            if len(parts) >= 3:
                server_id = int(parts[1])
                mcp_tool_name = parts[2]
                mcp_tool = db.query(MCPTool).filter(
                    MCPTool.server_id == server_id,
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

