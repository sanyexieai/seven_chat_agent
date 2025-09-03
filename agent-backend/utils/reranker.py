import os
from typing import List, Dict, Any, Optional
from functools import lru_cache

from utils.log_helper import get_logger

logger = get_logger("reranker")

DEFAULT_RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() == "true"


@lru_cache(maxsize=1)
def _get_cross_encoder(model_name: Optional[str] = None):
    if not RERANKER_ENABLED:
        return None
    try:
        from sentence_transformers import CrossEncoder
        model = CrossEncoder(model_name or DEFAULT_RERANKER_MODEL)
        logger.info(f"加载重排序模型成功: {model_name or DEFAULT_RERANKER_MODEL}")
        return model
    except Exception as exc:
        logger.warning(f"加载重排序模型失败，回退为禁用: {exc}")
        return None


def rerank(query: str, items: List[Dict[str, Any]], content_key: str = "content", top_k: Optional[int] = None,
           model_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    使用CrossEncoder对候选结果进行重排序。
    items: 形如 { 'content': str, ... } 的字典列表
    返回排序后的新列表（附加 'rerank_score' 字段）
    """
    if not items:
        return []

    model = _get_cross_encoder(model_name)
    if model is None:
        # 未启用或加载失败，直接按原顺序返回
        return items

    # 组装成 (query, passage)
    pairs = [(query, str(item.get(content_key, ""))) for item in items]
    try:
        scores = model.predict(pairs)
    except Exception as exc:
        logger.warning(f"重排序推理失败，回退为原顺序: {exc}")
        return items

    # 合并并排序
    enriched = []
    for item, score in zip(items, scores):
        new_item = dict(item)
        new_item["rerank_score"] = float(score)
        enriched.append(new_item)

    enriched.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)

    if top_k is not None and top_k > 0:
        enriched = enriched[:top_k]

    return enriched 