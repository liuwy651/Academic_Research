"""知识库业务逻辑：CRUD + 后台文档处理流水线。"""
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KBDocument, KnowledgeBase

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"pdf", "docx", "xlsx", "txt"}


# ── 文本切块 ─────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """按句子边界切分文本，保留相邻块重叠。"""
    # 按中英文句子边界断句
    sentences = re.split(r'(?<=[。！？.!?])\s*', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) <= chunk_size:
            current = current + sentence if not current else current + " " + sentence
        else:
            if current:
                chunks.append(current)
                # 保留 overlap：从当前块尾部截取
                current = current[-overlap:] + " " + sentence if overlap else sentence
            else:
                # 单句超长，强制截断
                for start in range(0, len(sentence), chunk_size - overlap):
                    chunks.append(sentence[start : start + chunk_size])
                current = ""

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]


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
    # 删除 Milvus 集合（在线程池中执行同步 pymilvus 调用）
    import asyncio
    from app.services import milvus_service
    await asyncio.to_thread(milvus_service.drop_collection, kb.id)
    # 软删除 KB（级联删除 kb_documents 记录）
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
    """后台文档处理流水线：DocMind → 切块 → 向量化 → Milvus。"""
    import asyncio
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

        # ── 切块 ──────────────────────────────────────────────────────
        chunks = chunk_text(markdown)
        if not chunks:
            raise ValueError("文档切块结果为空")
        logger.info("文档切块完成: doc_id=%s chunks=%d", doc_id, len(chunks))

        # ── 向量化 ────────────────────────────────────────────────────
        embeddings = await embedding_service.encode_batch(chunks)
        logger.info("向量化完成: doc_id=%s vectors=%d", doc_id, len(embeddings))

        # ── 写入 Milvus ───────────────────────────────────────────────
        await asyncio.to_thread(
            milvus_service.insert_chunks,
            kb_id, doc_id, filename, chunks, embeddings,
        )

        await _update_doc_status(doc_id, "completed", chunk_count=len(chunks))
        logger.info("文档处理完成: doc_id=%s", doc_id)

    except Exception as exc:
        logger.exception("文档处理失败: doc_id=%s error=%s", doc_id, exc)
        await _update_doc_status(doc_id, "failed", error_message=str(exc))
    finally:
        # 清理临时文件
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass
