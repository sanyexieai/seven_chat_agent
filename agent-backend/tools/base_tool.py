from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import asyncio
import uuid
from datetime import datetime

class BaseTool(ABC):
    """工具基类"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.id = str(uuid.uuid4())
        self.created_at = datetime.now()
    
    @abstractmethod
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """执行工具"""
        pass
    
    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        pass
    
    def get_info(self) -> Dict[str, Any]:
        """获取工具信息"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parameters": self.get_parameters_schema(),
            "created_at": self.created_at.isoformat()
        }
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """验证参数"""
        schema = self.get_parameters_schema()
        required_params = schema.get("required", [])
        
        for param in required_params:
            if param not in parameters:
                raise ValueError(f"缺少必需参数: {param}")
        
        return True
    
    async def execute_with_validation(self, parameters: Dict[str, Any]) -> Any:
        """带验证的执行"""
        self.validate_parameters(parameters)
        return await self.execute(parameters) 