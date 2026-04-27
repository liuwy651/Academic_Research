"""知识库业务逻辑：CRUD + 后台文档处理流水线。"""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KBChunk, KBDocument, KBParentChunk, KnowledgeBase

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"pdf", "docx", "xlsx", "txt"}


# ── 分层文本切块 ──────────────────────────────────────────────────────

# Markdown 分隔符优先级：标题 → 段落 → 换行 → 中英文句子 → 标点 → 字符
_MARKDOWN_SEPARATORS = [
    "\n## ", "\n### ", "\n#### ",
    "\n\n",
    "\n",
    "。", "！", "？",
    ". ", "! ", "? ",
    "；", ";",
    "，", ", ",
    " ", "",
]

_parent_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=150,
    separators=_MARKDOWN_SEPARATORS,
    keep_separator=True,
    is_separator_regex=False,
)

_child_splitter = RecursiveCharacterTextSplitter(
    chunk_size=300,
    chunk_overlap=30,
    separators=_MARKDOWN_SEPARATORS,
    keep_separator=True,
    is_separator_regex=False,
)


def chunk_text_hierarchical(text: str) -> tuple[list[str], list[tuple[int, str]]]:
    """两段切块：先切 parent(1500)，再对每个 parent 切 child(300)。

    Returns:
        parents: parent chunk 文本列表（按 parent_index 顺序）
        children: [(parent_index, child_text), ...] 全局有序列表
    """
    parent_docs = _parent_splitter.create_documents([text])
    parents = [d.page_content for d in parent_docs if d.page_content.strip()]

    children: list[tuple[int, str]] = []
    for p_idx, parent_text in enumerate(parents):
        child_docs = _child_splitter.create_documents([parent_text])
        for child_doc in child_docs:
            child_text = child_doc.page_content
            if child_text.strip():
                children.append((p_idx, child_text))

    return parents, children


# ── 知识库 CRUD ──────────────────────────────────────────────────────

async def create_kb(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    description: str | None = None,
) -> KnowledgeBase:
    kb = KnowledgeBase(user_id=user_id, name=name, description=description)
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return kb


async def list_kbs(db: AsyncSession, user_id: uuid.UUID) -> list[KnowledgeBase]:
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.user_id == user_id, KnowledgeBase.deleted_at.is_(None))
        .order_by(KnowledgeBase.created_at.desc())
    )
    return list(result.scalars().all())


async def get_kb(db: AsyncSession, user_id: uuid.UUID, kb_id: uuid.UUID) -> KnowledgeBase:
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None or kb.deleted_at is not None or kb.user_id != user_id:
        raise ValueError("知识库不存在或无权限")
    return kb


async def update_kb(
    db: AsyncSession,
    user_id: uuid.UUID,
    kb_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
) -> KnowledgeBase:
    kb = await get_kb(db, user_id, kb_id)
    if name is not None:
        kb.name = name
    if description is not None:
        kb.description = description
    kb.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(kb)
    return kb


async def delete_kb(db: AsyncSession, user_id: uuid.UUID, kb_id: uuid.UUID) -> None:
    kb = await get_kb(db, user_id, kb_id)
    import asyncio
    from app.services import milvus_service
    await asyncio.to_thread(milvus_service.drop_collection, kb.id)
    await db.execute(delete(KBChunk).where(KBChunk.kb_id == kb_id))
    await db.execute(delete(KBParentChunk).where(KBParentChunk.kb_id == kb_id))
    kb.deleted_at = datetime.now(timezone.utc)
    await db.commit()


async def count_documents(db: AsyncSession, kb_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).where(KBDocument.knowledge_base_id == kb_id)
    )
    return result.scalar_one()


# ── 文档 CRUD ────────────────────────────────────────────────────────

async def create_document(
    db: AsyncSession,
    kb_id: uuid.UUID,
    filename: str,
    file_type: str,
    file_size: int,
    storage_path: str,
) -> KBDocument:
    doc = KBDocument(
        knowledge_base_id=kb_id,
        filename=filename,
        file_type=file_type,
        file_size=file_size,
        storage_path=storage_path,
        status="pending",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def list_documents(db: AsyncSession, kb_id: uuid.UUID) -> list[KBDocument]:
    result = await db.execute(
        select(KBDocument)
        .where(KBDocument.knowledge_base_id == kb_id)
        .order_by(KBDocument.created_at.desc())
    )
    return list(result.scalars().all())


async def get_document(db: AsyncSession, kb_id: uuid.UUID, doc_id: uuid.UUID) -> KBDocument:
    doc = await db.get(KBDocument, doc_id)
    if doc is None or doc.knowledge_base_id != kb_id:
        raise ValueError("文档不存在")
    return doc


async def delete_document(
    db: AsyncSession,
    user_id: uuid.UUID,
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
) -> None:
    # 权限检查
    await get_kb(db, user_id, kb_id)
    doc = await get_document(db, kb_id, doc_id)

    import asyncio
    from app.services import milvus_service
    await asyncio.to_thread(milvus_service.delete_doc_chunks, kb_id, doc.id)
    await db.execute(delete(KBChunk).where(KBChunk.doc_id == doc.id.hex))
    await db.execute(delete(KBParentChunk).where(KBParentChunk.doc_id == doc.id.hex))

    await db.delete(doc)
    await db.commit()


# ── 后台处理流水线 ────────────────────────────────────────────────────

async def _update_doc_status(
    doc_id: uuid.UUID,
    status: str,
    task_id: str | None = None,
    chunk_count: int | None = None,
    error_message: str | None = None,
) -> None:
    """独立 DB 会话更新文档状态（后台任务中使用）。"""
    from app.core.database import AsyncSessionLocal

    values: dict = {
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    }
    if task_id is not None:
        values["docmind_task_id"] = task_id
    if chunk_count is not None:
        values["chunk_count"] = chunk_count
    if error_message is not None:
        values["error_message"] = error_message[:2000]

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(KBDocument).where(KBDocument.id == doc_id).values(**values)
        )
        await session.commit()


async def process_document(
    doc_id: uuid.UUID,
    kb_id: uuid.UUID,
    file_path: Path,
    filename: str,
    file_type: str,
) -> None:
    """后台文档处理流水线：DocMind → 分层切块 → 向量化(child) → Milvus + PostgreSQL 双写。"""
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.services import docmind_service, embedding_service, milvus_service

    logger.info("开始处理文档: doc_id=%s filename=%s", doc_id, filename)
    await _update_doc_status(doc_id, "processing")

    try:
        # ── TXT 直接读取，其他格式走 DocMind ──────────────────────────
        if file_type == "txt":
            markdown = file_path.read_text(encoding="utf-8", errors="replace")
            task_id = None
        else:
            task_id, markdown = await docmind_service.parse_document(file_path, filename, file_type)
            await _update_doc_status(doc_id, "processing", task_id=task_id)

        if not markdown.strip():
            raise ValueError("DocMind 返回空内容，请确认文件有可提取文本")

        # ── 分层切块：parent(1500) → child(300) ───────────────────────
        parents, children = chunk_text_hierarchical(markdown)
        if not children:
            raise ValueError("文档切块结果为空")
        logger.info("分层切块完成: doc_id=%s parents=%d children=%d", doc_id, len(parents), len(children))

        # child_texts 与 Milvus insert 保持全局索引对齐
        child_texts = [child_text for _, child_text in children]

        # ── 向量化（仅 child chunks）─────────────────────────────────
        embeddings = await embedding_service.encode_batch(child_texts)
        logger.info("向量化完成: doc_id=%s vectors=%d", doc_id, len(embeddings))

        # ── 写入 Milvus（child 向量）────────────────────────────────
        await asyncio.to_thread(
            milvus_service.insert_chunks,
            kb_id, doc_id, filename, child_texts, embeddings,
        )

        now = datetime.now(timezone.utc)
        doc_id_hex = doc_id.hex
        filename_safe = filename[:255]

        # ── 写入 PostgreSQL：kb_parent_chunks ─────────────────────────
        parent_rows = [
            {
                "id": hashlib.md5(f"{doc_id_hex}_p_{p_idx}".encode()).hexdigest(),
                "kb_id": kb_id,
                "doc_id": doc_id_hex,
                "filename": filename_safe,
                "parent_index": p_idx,
                "content": parent_text,
                "created_at": now,
            }
            for p_idx, parent_text in enumerate(parents)
        ]

        # ── 写入 PostgreSQL：kb_chunks（child + parent_id）────────────
        child_rows = [
            {
                "id": hashlib.md5(f"{doc_id_hex}_{c_idx}".encode()).hexdigest(),
                "kb_id": kb_id,
                "doc_id": doc_id_hex,
                "filename": filename_safe,
                "chunk_index": c_idx,
                "content": child_texts[c_idx],
                "parent_id": hashlib.md5(f"{doc_id_hex}_p_{p_idx}".encode()).hexdigest(),
                "created_at": now,
            }
            for c_idx, (p_idx, _) in enumerate(children)
        ]

        async with AsyncSessionLocal() as session:
            await session.execute(insert(KBParentChunk), parent_rows)
            await session.execute(insert(KBChunk), child_rows)
            await session.commit()
        logger.info("PostgreSQL 双写完成: doc_id=%s parents=%d children=%d", doc_id, len(parents), len(children))

        await _update_doc_status(doc_id, "completed", chunk_count=len(children))
        logger.info("文档处理完成: doc_id=%s", doc_id)

    except Exception as exc:
        logger.exception("文档处理失败: doc_id=%s error=%s", doc_id, exc)
        await _update_doc_status(doc_id, "failed", error_message=str(exc))
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass
