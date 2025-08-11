from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from database.database import get_db
from tools.tool_manager import ToolManager
from utils.log_helper import get_logger

logger = get_logger("tools_api")
router = APIRouter(prefix="/api/tools", tags=["tools"])

@router.get("/")
async def get_tools(db: Session = Depends(get_db)):
    """获取所有可用工具"""
    try:
        # 获取工具管理器实例
        tool_manager = ToolManager()
        
        # 获取所有注册的工具
        tools = tool_manager.get_all_tools()
        
        # 转换为前端需要的格式
        tool_list = []
        for tool_name, tool in tools.items():
            tool_info = {
                "name": tool_name,
                "description": getattr(tool, 'description', ''),
                "category": getattr(tool, 'category', 'general'),
                "parameters": getattr(tool, 'parameters', {}),
                "is_active": True
            }
            tool_list.append(tool_info)
        return tool_list
    except Exception as e:
        logger.error(f"Error fetching tools: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch tools: {e}") 