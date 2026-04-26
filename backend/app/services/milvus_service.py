"""Milvus 向量数据库操作。

每个知识库对应一个独立集合，命名规则：kb_{uuid_no_dashes}
Schema（6字段）：id, doc_id, filename, content, chunk_index, vector
"""
import hashlib
import logging
import uuid

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

_VECTOR_DIM = 1024
_NLIST = 128


def _collection_name(kb_id: uuid.UUID) -> str:
    return f"kb_{kb_id.hex}"


def _ensure_connected() -> None:
    # has_connection 检查连接是否真实存活，比 get_connection_addr 可靠
    if not connections.has_connection("default"):
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
        )


def _doc_id_str(doc_id: uuid.UUID) -> str:
    return doc_id.hex


def _chunk_id(doc_id: uuid.UUID, chunk_index: int) -> str:
    raw = f"{doc_id.hex}_{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()


def get_or_create_collection(kb_id: uuid.UUID) -> Collection:
    _ensure_connected()
    name = _collection_name(kb_id)

    if utility.has_collection(name):
        col = Collection(name)
        col.load()
        return col

    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True, auto_id=False),
        FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="filename", dtype=DataType.VARCHAR, max_length=255),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="chunk_index", dtype=DataType.INT64),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=_VECTOR_DIM),
    ]
    schema = CollectionSchema(fields=fields, description=f"Knowledge base {kb_id}")
    col = Collection(name=name, schema=schema)

    col.create_index(
        field_name="vector",
        index_params={
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": _NLIST},
        },
    )
    col.load()
    logger.info("Milvus 集合已创建: %s", name)
    return col


def insert_chunks(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    filename: str,
    chunks: list[str],
    embeddings: list[list[float]],
) -> None:
    col = get_or_create_collection(kb_id)
    doc_id_str = _doc_id_str(doc_id)
    filename_safe = filename[:255]

    data = [
        [_chunk_id(doc_id, i) for i in range(len(chunks))],   # id
        [doc_id_str] * len(chunks),                             # doc_id
        [filename_safe] * len(chunks),                          # filename
        [c[:65535] for c in chunks],                            # content
        list(range(len(chunks))),                               # chunk_index
        embeddings,                                             # vector
    ]
    col.insert(data)
    col.flush()
    logger.info("Milvus 插入完成: kb=%s doc=%s chunks=%d", kb_id, doc_id, len(chunks))


def query_doc_chunks(kb_id: uuid.UUID, doc_id: uuid.UUID) -> list[dict]:
    """按 doc_id 标量过滤查询该文档的所有切块（不含向量），按 chunk_index 排序。"""
    _ensure_connected()
    name = _collection_name(kb_id)
    if not utility.has_collection(name):
        return []
    col = Collection(name)
    col.load()
    doc_id_str = _doc_id_str(doc_id)
    results = col.query(
        expr=f'doc_id == "{doc_id_str}"',
        output_fields=["chunk_index", "content"],
        limit=16384,   # 单文档切块数不会超过此上限
    )
    return sorted(results, key=lambda r: r["chunk_index"])


def delete_doc_chunks(kb_id: uuid.UUID, doc_id: uuid.UUID) -> None:
    _ensure_connected()
    name = _collection_name(kb_id)
    if not utility.has_collection(name):
        return
    col = Collection(name)
    doc_id_str = _doc_id_str(doc_id)
    col.delete(expr=f'doc_id == "{doc_id_str}"')
    col.flush()
    logger.info("Milvus 删除文档向量: kb=%s doc=%s", kb_id, doc_id)


def drop_collection(kb_id: uuid.UUID) -> None:
    _ensure_connected()
    name = _collection_name(kb_id)
    if utility.has_collection(name):
        utility.drop_collection(name)
        logger.info("Milvus 集合已删除: %s", name)
