from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncGenerator, List
import asyncio
import uuid
from datetime import datetime
from utils.log_helper import get_logger

logger = get_logger("base_tool")


class ToolResult:
    """工具执行结果"""
    
    def __init__(
        self,
        frontend_output: str = "",  # 前台输出（流式）- 工具在前端显示的文本
        backend_output: str = "",   # 后台输出 - 工具后台记录的日志
        container_output: str = "", # 容器输出 - 工具在工作空间对应的输出内容
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.frontend_output = frontend_output
        self.backend_output = backend_output
        self.container_output = container_output
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "frontend_output": self.frontend_output,
            "backend_output": self.backend_output,
            "container_output": self.container_output,
            "metadata": self.metadata
        }


class BaseTool(ABC):
    """工具基类"""
    
    # 容器类型枚举
    CONTAINER_TYPE_BROWSER = "browser"      # 浏览容器（用于搜索工具）
    CONTAINER_TYPE_FILE = "file"           # 文件容器（用于代码工具、报告工具）
    CONTAINER_TYPE_NONE = "none"           # 无容器
    
    def __init__(
        self,
        name: str,
        description: str,
        container_type: str = CONTAINER_TYPE_NONE,
        container_config: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.description = description
        self.id = str(uuid.uuid4())
        self.created_at = datetime.now()
        self.container_type = container_type  # 绑定的容器类型
        self.container_config = container_config or {}  # 容器配置
        self._workspace_path: Optional[str] = None  # 工作空间路径
    
    @abstractmethod
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """执行工具"""
        pass
    
    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        pass
    
    def get_container_type(self) -> str:
        """获取绑定的容器类型"""
        return self.container_type
    
    def get_container_config(self) -> Dict[str, Any]:
        """获取容器配置"""
        return self.container_config
    
    def set_workspace_path(self, workspace_path: str):
        """设置工作空间路径"""
        self._workspace_path = workspace_path
        logger.info(f"工具 {self.name} 设置工作空间路径: {workspace_path}")
    
    def get_workspace_path(self) -> Optional[str]:
        """获取工作空间路径"""
        return self._workspace_path
    
    async def execute_with_result(
        self,
        parameters: Dict[str, Any],
        stream: bool = False
    ) -> AsyncGenerator[ToolResult, None]:
        """
        执行工具并返回结果（包含前台输出、后台输出、容器输出）
        
        Args:
            parameters: 工具参数
            stream: 是否流式返回
            
        Yields:
            ToolResult: 工具执行结果
        """
        # 验证参数
        try:
            self.validate_parameters(parameters)
        except ValueError as e:
            logger.error(f"工具 {self.name} 参数验证失败: {e}")
            yield ToolResult(
                frontend_output=f"参数错误: {str(e)}",
                backend_output=f"参数验证失败: {str(e)}",
                container_output="",
                metadata={"error": str(e)}
            )
            return
        
        # 记录开始执行
        logger.info(f"工具 {self.name} 开始执行，参数: {parameters}")
        backend_log = f"[{datetime.now().isoformat()}] 工具 {self.name} 开始执行\n"
        backend_log += f"参数: {parameters}\n"
        
        try:
            # 执行工具
            result = await self.execute(parameters)
            
            # 处理结果
            if stream and hasattr(result, '__aiter__'):
                # 流式结果
                frontend_output = ""
                container_output = ""
                
                async for chunk in result:
                    # 根据chunk类型处理
                    if isinstance(chunk, ToolResult):
                        # 如果返回的是ToolResult，直接yield
                        yield chunk
                        frontend_output += chunk.frontend_output
                        container_output += chunk.container_output
                        backend_log += chunk.backend_output
                    elif isinstance(chunk, str):
                        # 字符串chunk，添加到前台输出
                        frontend_output += chunk
                        yield ToolResult(
                            frontend_output=chunk,
                            backend_output=f"流式输出: {chunk[:100]}...",
                            container_output="",
                            metadata={"chunk_type": "stream"}
                        )
                    else:
                        # 其他类型，转换为字符串
                        chunk_str = str(chunk)
                        frontend_output += chunk_str
                        yield ToolResult(
                            frontend_output=chunk_str,
                            backend_output=f"流式输出: {chunk_str[:100]}...",
                            container_output="",
                            metadata={"chunk_type": "other"}
                        )
                
                # 最终结果
                backend_log += f"执行完成，前台输出长度: {len(frontend_output)}\n"
                yield ToolResult(
                    frontend_output=frontend_output,
                    backend_output=backend_log,
                    container_output=container_output,
                    metadata={"status": "completed", "stream": True}
                )
            else:
                # 非流式结果
                frontend_output = self._format_frontend_output(result)
                container_output = self._format_container_output(result)
                backend_log += f"执行完成，结果类型: {type(result).__name__}\n"
                backend_log += f"前台输出: {frontend_output[:200]}...\n"
                
                yield ToolResult(
                    frontend_output=frontend_output,
                    backend_output=backend_log,
                    container_output=container_output,
                    metadata={"status": "completed", "stream": False}
                )
        
        except Exception as e:
            error_msg = f"工具执行失败: {str(e)}"
            logger.error(f"工具 {self.name} 执行失败: {e}", exc_info=True)
            backend_log += f"执行失败: {str(e)}\n"
            
            yield ToolResult(
                frontend_output=error_msg,
                backend_output=backend_log,
                container_output="",
                metadata={"error": str(e), "status": "failed"}
            )
    
    def _format_frontend_output(self, result: Any) -> str:
        """格式化前台输出（工具在前端显示的文本）"""
        if isinstance(result, str):
            return result
        elif isinstance(result, dict):
            # 如果是字典，提取主要信息
            if "content" in result:
                return str(result["content"])
            elif "message" in result:
                return str(result["message"])
            else:
                return str(result)
        elif isinstance(result, list):
            # 如果是列表，合并为字符串
            return "\n".join(str(item) for item in result)
        else:
            return str(result)
    
    def _format_container_output(self, result: Any) -> str:
        """格式化容器输出（工具在工作空间对应的输出内容）"""
        # 默认实现：如果工作空间路径存在，尝试保存结果到工作空间
        if not self._workspace_path:
            return ""
        
        # 子类可以重写此方法来实现具体的容器输出逻辑
        # 例如：保存文件到工作空间、写入日志等
        if isinstance(result, dict) and "file_path" in result:
            # 如果结果包含文件路径，返回文件路径
            return result["file_path"]
        elif isinstance(result, str):
            # 如果是字符串，可能是文件内容或路径
            return result
        else:
            return ""
    
    def get_info(self) -> Dict[str, Any]:
        """获取工具信息"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parameters": self.get_parameters_schema(),
            "container_type": self.container_type,
            "container_config": self.container_config,
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