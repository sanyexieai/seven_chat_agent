from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from database.database import get_db
from models.database_models import (
    MCPServerCreate, MCPServerUpdate, MCPServerResponse,
    MCPToolCreate, MCPToolUpdate, MCPToolResponse, MCPServer, MCPTool
)
from utils.log_helper import get_logger
from agents.agent_manager import AgentManager

logger = get_logger("mcp_api")
router = APIRouter(prefix="/api/mcp", tags=["mcp"])

# 获取AgentManager实例
def get_agent_manager():
    from main import agent_manager
    if agent_manager is None:
        raise HTTPException(status_code=503, detail="系统正在初始化，请稍后再试")
    return agent_manager

@router.get("/servers", response_model=List[MCPServerResponse])
async def get_mcp_servers(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """获取所有MCP服务器"""
    try:
        query = db.query(MCPServer)
        if active_only:
            query = query.filter(MCPServer.is_active == True)
        servers = query.all()
        return servers
    except Exception as e:
        logger.error(f"获取MCP服务器失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取MCP服务器失败")

@router.get("/servers/{server_id}", response_model=MCPServerResponse)
async def get_mcp_server(
    server_id: int,
    db: Session = Depends(get_db)
):
    """根据ID获取MCP服务器"""
    try:
        server = db.query(MCPServer).filter(MCPServer.id == server_id).first()
        if not server:
            raise HTTPException(status_code=404, detail="MCP服务器不存在")
        return server
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取MCP服务器失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取MCP服务器失败")

@router.post("/servers", response_model=MCPServerResponse)
async def create_mcp_server(
    server_data: MCPServerCreate,
    db: Session = Depends(get_db),
    agent_manager: AgentManager = Depends(get_agent_manager)
):
    """创建MCP服务器"""
    try:
        # 检查是否已存在
        existing = db.query(MCPServer).filter(MCPServer.name == server_data.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="MCP服务器名称已存在")
        
        # 创建新服务器
        server = MCPServer(
            name=server_data.name,
            display_name=server_data.display_name,
            description=server_data.description,
            transport=server_data.transport,
            command=server_data.command,
            args=server_data.args,
            env=server_data.env,
            url=server_data.url,
            is_active=True
        )
        
        db.add(server)
        db.commit()
        db.refresh(server)
        
        # 重新加载MCP配置
        await agent_manager._load_mcp_configs()
        
        return server
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建MCP服务器失败: {str(e)}")
        raise HTTPException(status_code=500, detail="创建MCP服务器失败")

@router.put("/servers/{server_id}", response_model=MCPServerResponse)
async def update_mcp_server(
    server_id: int,
    server_data: MCPServerUpdate,
    db: Session = Depends(get_db),
    agent_manager: AgentManager = Depends(get_agent_manager)
):
    """更新MCP服务器"""
    try:
        server = db.query(MCPServer).filter(MCPServer.id == server_id).first()
        if not server:
            raise HTTPException(status_code=404, detail="MCP服务器不存在")
        
        # 更新字段
        update_data = server_data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(server, key, value)
        
        db.commit()
        db.refresh(server)
        
        # 重新加载MCP配置
        await agent_manager._load_mcp_configs()
        
        return server
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新MCP服务器失败: {str(e)}")
        raise HTTPException(status_code=500, detail="更新MCP服务器失败")

@router.delete("/servers/{server_id}")
async def delete_mcp_server(
    server_id: int,
    db: Session = Depends(get_db),
    agent_manager: AgentManager = Depends(get_agent_manager)
):
    """删除MCP服务器"""
    try:
        server = db.query(MCPServer).filter(MCPServer.id == server_id).first()
        if not server:
            raise HTTPException(status_code=404, detail="MCP服务器不存在")
        
        db.delete(server)
        db.commit()
        
        # 重新加载MCP配置
        await agent_manager._load_mcp_configs()
        
        return {"message": "MCP服务器删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除MCP服务器失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除MCP服务器失败")

@router.get("/tools", response_model=List[MCPToolResponse])
async def get_all_mcp_tools(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """获取所有MCP工具"""
    try:
        query = db.query(MCPTool)
        if active_only:
            query = query.filter(MCPTool.is_active == True)
        tools = query.all()
        return tools
    except Exception as e:
        logger.error(f"获取MCP工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取MCP工具失败")

@router.get("/servers/{server_id}/tools", response_model=List[MCPToolResponse])
async def get_mcp_tools(
    server_id: int,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """获取MCP服务器的工具列表"""
    try:
        query = db.query(MCPTool).filter(MCPTool.server_id == server_id)
        if active_only:
            query = query.filter(MCPTool.is_active == True)
        tools = query.all()
        return tools
    except Exception as e:
        logger.error(f"获取MCP工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取MCP工具失败")

@router.post("/servers/{server_id}/tools", response_model=MCPToolResponse)
async def create_mcp_tool(
    server_id: int,
    tool_data: MCPToolCreate,
    db: Session = Depends(get_db)
):
    """创建MCP工具"""
    try:
        # 检查服务器是否存在
        server = db.query(MCPServer).filter(MCPServer.id == server_id).first()
        if not server:
            raise HTTPException(status_code=404, detail="MCP服务器不存在")
        
        # 检查工具是否已存在
        existing = db.query(MCPTool).filter(
            MCPTool.server_id == server_id,
            MCPTool.name == tool_data.name
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="工具名称已存在")
        
        # 创建新工具
        tool = MCPTool(
            server_id=server_id,
            name=tool_data.name,
            display_name=tool_data.display_name,
            description=tool_data.description,
            tool_type=tool_data.tool_type,
            input_schema=tool_data.input_schema,
            output_schema=tool_data.output_schema,
            examples=tool_data.examples,
            is_active=True
        )
        
        db.add(tool)
        db.commit()
        db.refresh(tool)
        
        return tool
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建MCP工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail="创建MCP工具失败")

@router.put("/tools/{tool_id}", response_model=MCPToolResponse)
async def update_mcp_tool(
    tool_id: int,
    tool_data: MCPToolUpdate,
    db: Session = Depends(get_db)
):
    """更新MCP工具"""
    try:
        tool = db.query(MCPTool).filter(MCPTool.id == tool_id).first()
        if not tool:
            raise HTTPException(status_code=404, detail="MCP工具不存在")
        
        # 更新字段
        update_data = tool_data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(tool, key, value)
        
        db.commit()
        db.refresh(tool)
        
        return tool
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新MCP工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail="更新MCP工具失败")

@router.delete("/tools/{tool_id}")
async def delete_mcp_tool(
    tool_id: int,
    db: Session = Depends(get_db)
):
    """删除MCP工具"""
    try:
        tool = db.query(MCPTool).filter(MCPTool.id == tool_id).first()
        if not tool:
            raise HTTPException(status_code=404, detail="MCP工具不存在")
        
        db.delete(tool)
        db.commit()
        
        return {"message": "MCP工具删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除MCP工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除MCP工具失败")

@router.post("/servers/{server_name}/sync")
async def sync_mcp_tools(
    server_name: str,
    agent_manager: AgentManager = Depends(get_agent_manager)
):
    """同步MCP服务器工具"""
    try:
        success = await agent_manager.sync_mcp_tools(server_name)
        if not success:
            raise HTTPException(status_code=500, detail="同步MCP工具失败")
        return {"message": "MCP工具同步成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"同步MCP工具失败: {str(e)}")
        raise HTTPException(status_code=500, detail="同步MCP工具失败")

@router.get("/config")
async def get_mcp_config(
    agent_manager: AgentManager = Depends(get_agent_manager)
):
    """获取当前MCP配置"""
    try:
        configs = await agent_manager.get_mcp_configs()
        return {"configs": configs}
    except Exception as e:
        logger.error(f"获取MCP配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取MCP配置失败") 