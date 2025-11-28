from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.base_tool import BaseTool
from tools.containers.base_container import BaseContainer


class FileContainer(BaseContainer):
    """
    文件容器

    典型用途：代码执行输出、报告生成、文档写入等。
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(container_type=BaseContainer.TYPE_FILE, config=config)

    async def handle_result(self, tool: BaseTool, result: Any) -> Any:
        """
        默认行为：
        - 如果工具或容器配置中提供了 workspace_dir，则保证目录存在；
        - 不强制落盘，只是返回工作目录信息，具体写文件逻辑交给工具本身。
        """
        workspace_dir: Path | None = self.get_workspace_dir(tool)
        if workspace_dir is None:
            # 没有工作目录配置，直接透传
            return result

        # 可以在 metadata 中附带 workspace_dir 信息，便于前端或上层逻辑展示
        if isinstance(result, dict):
            result.setdefault("container_workspace_dir", str(workspace_dir))
            return result

        return {
            "content": result,
            "container_workspace_dir": str(workspace_dir),
        }


