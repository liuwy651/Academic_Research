"""DashScope Cross-Encoder 重排服务。

调用 gte-rerank 模型对候选 chunk 进行精准相关性评分，
输入 query + 候选列表，输出按相关性降序排列的 (id, score) 列表。
"""
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_RERANK_PATH = "/rerank"


async def rerank(
    query: str,
    candidates: list[tuple[str, str]],
    top_n: int,
) -> list[tuple[str, float]]:
    """Cross-Encoder 重排。

    Args:
        query: 用户查询文本。
        candidates: [(chunk_id, content), ...] 候选列表。
        top_n: 返回数量。

    Returns:
        [(chunk_id, score), ...] 按 score 降序，长度 <= top_n。
        失败时静默回退：按原顺序截断返回 (chunk_id, 0.0)。
    """
    if not candidates:
        return []

    top_n = min(top_n, len(candidates))
    url = settings.DASHSCOPE_BASE_URL.rstrip("/") + _RERANK_PATH

    payload = {
        "model": settings.RERANKER_MODEL,
        "query": query,
        "documents": [content for _, content in candidates],
        "top_n": top_n,
        "return_documents": False,
    }
    id_map = {i: chunk_id for i, (chunk_id, _) in enumerate(candidates)}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        ranked = [
            (id_map[r["index"]], float(r["relevance_score"]))
            for r in results
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        logger.debug("Rerank 完成: candidates=%d top_n=%d", len(candidates), top_n)
        return ranked[:top_n]

    except Exception as exc:
        logger.warning("Rerank 调用失败，回退到原始顺序: %s", exc)
        return [(chunk_id, 0.0) for chunk_id, _ in candidates[:top_n]]
