"""DashScope text-embedding-v4 向量化服务。"""
import logging

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


async def encode_batch(texts: list[str]) -> list[list[float]]:
    """将文本列表向量化，按批次处理，返回 1024 维向量列表。"""
    if not texts:
        return []

    client = AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
    )

    all_vectors: list[list[float]] = []
    batch_size = settings.EMBEDDING_BATCH_SIZE

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=batch,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        batch_vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        all_vectors.extend(batch_vectors)
        logger.debug("Embedding 完成批次 %d/%d，共 %d 条", i // batch_size + 1, -(-len(texts) // batch_size), len(batch))

    return all_vectors
