"""RAG 混合检索服务：向量（Milvus）+ 关键词（pg_trgm）两路并发召回，RRF 融合排序。"""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# RRF 超参数
_RRF_K = 60
_VECTOR_WEIGHT = 0.7
_KEYWORD_WEIGHT = 0.3


@dataclass
class ChunkResult:
    """单个 chunk 的检索结果，向量路和关键词路均映射到此结构。"""
    id: str
    content: str
    filename: str
    chunk_index: int
    kb_id: str = ""
    vector_rank: int | None = None
    keyword_rank: int | None = None
    rrf_score: float = field(default=0.0, compare=False)


# ── 两路召回 ──────────────────────────────────────────────────────────────────

async def _vector_recall(
    kb_id: uuid.UUID,
    query_vector: list[float],
    top_k: int,
) -> list[ChunkResult]:
    """向量召回：asyncio.to_thread 包装同步 Milvus 搜索。"""
    from app.services import milvus_service

    raw = await asyncio.to_thread(milvus_service.search_vectors, kb_id, query_vector, top_k)
    return [
        ChunkResult(
            id=r["id"],
            content=r["content"],
            filename=r["filename"],
            chunk_index=r["chunk_index"],
            kb_id=str(kb_id),
            vector_rank=rank + 1,
        )
        for rank, r in enumerate(raw)
    ]


async def _keyword_recall(
    db: AsyncSession,
    kb_id: uuid.UUID,
    query: str,
    top_k: int,
) -> list[ChunkResult]:
    """关键词召回：pg_trgm similarity 排序。"""
    sql = text("""
        SELECT id, content, filename, chunk_index,
               similarity(:query, content) AS sim
        FROM kb_chunks
        WHERE kb_id = :kb_id
          AND similarity(:query, content) > 0.05
        ORDER BY sim DESC
        LIMIT :top_k
    """)
    result = await db.execute(sql, {
        "query": query,
        "kb_id": str(kb_id),
        "top_k": top_k,
    })
    rows = result.mappings().all()
    return [
        ChunkResult(
            id=row["id"],
            content=row["content"],
            filename=row["filename"],
            chunk_index=row["chunk_index"],
            kb_id=str(kb_id),
            keyword_rank=rank + 1,
        )
        for rank, row in enumerate(rows)
    ]


# ── RRF 融合 ──────────────────────────────────────────────────────────────────

def _rrf_merge(
    vector_hits: list[ChunkResult],
    keyword_hits: list[ChunkResult],
    top_n: int,
) -> list[ChunkResult]:
    """倒数排名融合（Reciprocal Rank Fusion）。

    score(d) = 0.7 / (60 + vector_rank) + 0.3 / (60 + keyword_rank)
    """
    merged: dict[str, ChunkResult] = {}

    for hit in vector_hits:
        merged[hit.id] = hit
        hit.rrf_score += _VECTOR_WEIGHT / (_RRF_K + hit.vector_rank)

    for hit in keyword_hits:
        if hit.id in merged:
            existing = merged[hit.id]
            existing.keyword_rank = hit.keyword_rank
            existing.rrf_score += _KEYWORD_WEIGHT / (_RRF_K + hit.keyword_rank)
        else:
            hit.rrf_score += _KEYWORD_WEIGHT / (_RRF_K + hit.keyword_rank)
            merged[hit.id] = hit

    ranked = sorted(merged.values(), key=lambda x: x.rrf_score, reverse=True)
    return ranked[:top_n]


def _rerank_globally(hits: list[ChunkResult], field: str) -> None:
    """多 kb 拼接后重新赋全局排名，确保 RRF 在全局候选池上计算。"""
    for i, h in enumerate(hits):
        setattr(h, field, i + 1)


# ── 跨语言查询翻译 ────────────────────────────────────────────────────────────

async def _translate_to_english(text: str) -> str:
    """将中文查询翻译为英文，用于关键词召回。失败时静默回退到原文。"""
    from app.core.config import settings
    from openai import AsyncOpenAI

    try:
        client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.DASHSCOPE_BASE_URL,
        )
        resp = await client.chat.completions.create(
            model=settings.LLM_TITLE_MODEL,
            messages=[
                {"role": "system", "content": "Translate the following search query to English. Output only the translation, no explanation."},
                {"role": "user", "content": text},
            ],
            max_tokens=200,
            temperature=0,
        )
        translated = resp.choices[0].message.content.strip()
        return translated if translated else text
    except Exception as e:
        logger.warning("查询翻译失败，回退到原文: %s", e)
        return text


# ── 公开接口 ──────────────────────────────────────────────────────────────────

_SELECT_THRESHOLD = 0.45
_COARSE_TOP_K = 3


async def select_relevant_kbs(
    db: AsyncSession,
    user_id: uuid.UUID,
    query_vector: list[float],
    threshold: float = _SELECT_THRESHOLD,
) -> list[uuid.UUID]:
    """粗筛向量搜索，从用户所有 KB 中自动选出与 query 相关的。

    策略：
    - 对每个 KB 并发做 top_k=3 的粗筛搜索，取各 KB 的 max(score)
    - 返回 score >= threshold 的 KB
    - 全部低于阈值时兜底返回分数最高的 1 个，避免空结果
    """
    from app.services import milvus_service
    from app.services.knowledge_base_service import list_kbs

    all_kbs = await list_kbs(db, user_id)
    if not all_kbs:
        return []

    tasks = [
        asyncio.to_thread(milvus_service.search_vectors, kb.id, query_vector, _COARSE_TOP_K)
        for kb in all_kbs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    kb_scores: list[tuple[uuid.UUID, float]] = []
    for kb, result in zip(all_kbs, results):
        if isinstance(result, Exception) or not result:
            logger.debug("粗筛跳过 KB %s: %s", kb.id, result)
            continue
        max_score = max(r["score"] for r in result)
        kb_scores.append((kb.id, max_score))
        logger.debug("粗筛 KB %s max_score=%.3f", kb.id, max_score)

    if not kb_scores:
        return []

    kb_scores.sort(key=lambda x: x[1], reverse=True)
    selected = [kb_id for kb_id, score in kb_scores if score >= threshold]

    if not selected:
        selected = [kb_scores[0][0]]
        logger.info(
            "自动选库兜底：无 KB 超过阈值 %.2f，选最高分 %s (score=%.3f)",
            threshold, selected[0], kb_scores[0][1],
        )
    else:
        logger.info("自动选库：%d/%d 个 KB 入选（阈值 %.2f）", len(selected), len(all_kbs), threshold)

    return selected


async def retrieve(
    db: AsyncSession,
    kb_ids: list[uuid.UUID],
    query: str,
    top_n: int = 5,
    recall_k: int = 20,
    query_vector: list[float] | None = None,
) -> list[ChunkResult]:
    """混合检索主入口：embedding → 两路并发召回 → RRF 融合 → top_n。

    Args:
        db: 异步数据库会话（用于关键词召回）。
        kb_ids: 目标知识库 UUID 列表，支持跨库检索。
        query: 用户原始查询文本。
        top_n: 最终返回的 chunk 数量（注入 Agent 上下文）。
        recall_k: 每路每个 kb 的召回数量。
        query_vector: 预计算好的查询向量，传入时跳过 embedding 调用（避免自动选库时重复 embed）。
    """
    from app.services.embedding_service import encode_batch, is_cjk_query

    if not kb_ids or not query.strip():
        return []

    # 查询向量化（若外部已传入则跳过，避免自动选库时重复 embed）
    if query_vector is None:
        vectors = await encode_batch([query])
        query_vector = vectors[0]

    # 跨语言：中文查询翻译为英文供关键词召回使用；向量召回保持原始查询
    if is_cjk_query(query):
        keyword_query = await _translate_to_english(query)
        logger.debug("跨语言关键词查询: %r → %r", query[:40], keyword_query[:40])
    else:
        keyword_query = query

    # 跨 kb 并发两路召回
    vector_tasks = [_vector_recall(kb_id, query_vector, recall_k) for kb_id in kb_ids]
    keyword_tasks = [_keyword_recall(db, kb_id, keyword_query, recall_k) for kb_id in kb_ids]

    all_results = await asyncio.gather(*vector_tasks, *keyword_tasks, return_exceptions=True)

    n = len(kb_ids)
    all_vector_hits: list[ChunkResult] = []
    all_keyword_hits: list[ChunkResult] = []

    for i, result in enumerate(all_results):
        if isinstance(result, Exception):
            kind = "vector" if i < n else "keyword"
            kb_id = kb_ids[i if i < n else i - n]
            logger.warning("召回异常 kind=%s kb=%s: %s", kind, kb_id, result)
            continue
        if i < n:
            all_vector_hits.extend(result)
        else:
            all_keyword_hits.extend(result)

    # 多 kb 时重新全局排名，保证 RRF 在全局候选池上计算
    if len(kb_ids) > 1:
        _rerank_globally(all_vector_hits, "vector_rank")
        _rerank_globally(all_keyword_hits, "keyword_rank")

    result_chunks = _rrf_merge(all_vector_hits, all_keyword_hits, top_n)

    logger.info(
        "RAG 检索完成: query=%r kb_count=%d vector_hits=%d keyword_hits=%d top_n=%d",
        query[:50], len(kb_ids), len(all_vector_hits), len(all_keyword_hits), len(result_chunks),
    )
    return result_chunks
