from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from models.database_models import PipelineState
from utils.log_helper import get_logger
import copy

logger = get_logger("pipeline_state_service")


class PipelineStateService:
    """Pipeline 状态持久化服务
    
    以 (user_id, agent_name, session_id) 作为键，存取 Pipeline.export() 的完整状态。
    注意：只保存**可 JSON 序列化**的部分，例如 `agent_contexts` 里包含的 AgentContext 会被剥离。
    """

    @staticmethod
    def get_state(
        db: Session,
        user_id: str,
        agent_name: str,
        session_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """从数据库获取 Pipeline 状态"""
        try:
            query = db.query(PipelineState).filter(
                PipelineState.user_id == user_id,
                PipelineState.agent_name == agent_name,
            )
            if session_id:
                query = query.filter(PipelineState.session_id == session_id)
            else:
                query = query.filter(PipelineState.session_id.is_(None))

            record = query.first()
            return record.state if record else None
        except Exception as e:
            logger.warning(f"获取 PipelineState 失败: {e}")
            return None

    @staticmethod
    def _make_state_json_safe(state: Dict[str, Any]) -> Dict[str, Any]:
        """移除 / 简化不能 JSON 序列化的字段（例如 AgentContext 实例）。"""
        safe_state = copy.deepcopy(state)
        try:
            data = safe_state.get("data") or safe_state.get("data".encode("utf-8"), {})
        except Exception:
            data = safe_state.get("data", {})

        if isinstance(data, dict):
            # 1. 直接移除 agent_contexts 命名空间（其中存的是 AgentContext 对象）
            if "agent_contexts" in data:
                data.pop("agent_contexts", None)
            safe_state["data"] = data

        return safe_state

    @staticmethod
    def save_state(
        db: Session,
        user_id: str,
        agent_name: str,
        session_id: Optional[str],
        state: Dict[str, Any],
    ) -> None:
        """保存或更新 Pipeline 状态（仅保存 JSON 安全的部分）"""
        try:
            safe_state = PipelineStateService._make_state_json_safe(state)

            query = db.query(PipelineState).filter(
                PipelineState.user_id == user_id,
                PipelineState.agent_name == agent_name,
            )
            if session_id:
                query = query.filter(PipelineState.session_id == session_id)
            else:
                query = query.filter(PipelineState.session_id.is_(None))

            record = query.first()
            if record:
                record.state = safe_state
                record.pipeline_id = safe_state.get("pipeline_id")
            else:
                record = PipelineState(
                    pipeline_id=safe_state.get("pipeline_id"),
                    user_id=user_id,
                    agent_name=agent_name,
                    session_id=session_id,
                    state=safe_state,
                )
                db.add(record)

            db.commit()
        except Exception as e:
            logger.warning(f"保存 PipelineState 失败: {e}")
            db.rollback()


