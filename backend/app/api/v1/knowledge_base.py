"""RAG 知识库 API 路由。"""
import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.knowledge_base import (
    DocumentListOut,
    DocumentOut,
    KnowledgeBaseCreate,
    KnowledgeBaseListOut,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from app.services import knowledge_base_service as kb_svc

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-base"])

_ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "txt"}
_MAX_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


async def _require_kb(
    kb_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await kb_svc.get_kb(db, current_user.id, kb_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ── 知识库 CRUD ──────────────────────────────────────────────────────

@router.post("", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    body: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = await kb_svc.create_kb(db, current_user.id, body.name, body.description)
    count = await kb_svc.count_documents(db, kb.id)
    return KnowledgeBaseOut(
        id=kb.id, name=kb.name, description=kb.description,
        document_count=count, created_at=kb.created_at, updated_at=kb.updated_at,
    )


@router.get("", response_model=KnowledgeBaseListOut)
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kbs = await kb_svc.list_kbs(db, current_user.id)
    items = []
    for kb in kbs:
        count = await kb_svc.count_documents(db, kb.id)
        items.append(KnowledgeBaseOut(
            id=kb.id, name=kb.name, description=kb.description,
            document_count=count, created_at=kb.created_at, updated_at=kb.updated_at,
        ))
    return KnowledgeBaseListOut(items=items, total=len(items))


@router.get("/{kb_id}", response_model=KnowledgeBaseOut)
async def get_knowledge_base(kb=Depends(_require_kb), db: AsyncSession = Depends(get_db)):
    count = await kb_svc.count_documents(db, kb.id)
    return KnowledgeBaseOut(
        id=kb.id, name=kb.name, description=kb.description,
        document_count=count, created_at=kb.created_at, updated_at=kb.updated_at,
    )


@router.patch("/{kb_id}", response_model=KnowledgeBaseOut)
async def update_knowledge_base(
    kb_id: uuid.UUID,
    body: KnowledgeBaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        kb = await kb_svc.update_kb(db, current_user.id, kb_id, body.name, body.description)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    count = await kb_svc.count_documents(db, kb.id)
    return KnowledgeBaseOut(
        id=kb.id, name=kb.name, description=kb.description,
        document_count=count, created_at=kb.created_at, updated_at=kb.updated_at,
    )


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        await kb_svc.delete_kb(db, current_user.id, kb_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ── 文档管理 ─────────────────────────────────────────────────────────

@router.post("/{kb_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 权限检查
    try:
        await kb_svc.get_kb(db, current_user.id, kb_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    filename = file.filename or "unknown"
    ext = _ext(filename)
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型 .{ext}，仅支持: {', '.join(_ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件大小超过 {settings.MAX_FILE_SIZE_MB} MB 限制",
        )

    # 保存到临时目录
    doc_id = uuid.uuid4()
    tmp_path = Path(f"/tmp/{doc_id.hex}_{filename}")
    tmp_path.write_bytes(content)

    # 创建数据库记录
    doc = await kb_svc.create_document(
        db, kb_id, filename, ext, len(content), str(tmp_path)
    )

    # 触发后台处理，不阻塞当前请求
    asyncio.create_task(
        kb_svc.process_document(doc.id, kb_id, tmp_path, filename, ext)
    )

    return DocumentOut.model_validate(doc)


@router.get("/{kb_id}/documents", response_model=DocumentListOut)
async def list_documents(kb_id: uuid.UUID, kb=Depends(_require_kb), db: AsyncSession = Depends(get_db)):
    docs = await kb_svc.list_documents(db, kb_id)
    return DocumentListOut(items=[DocumentOut.model_validate(d) for d in docs], total=len(docs))


@router.get("/{kb_id}/documents/{doc_id}", response_model=DocumentOut)
async def get_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    kb=Depends(_require_kb),
    db: AsyncSession = Depends(get_db),
):
    try:
        doc = await kb_svc.get_document(db, kb_id, doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return DocumentOut.model_validate(doc)


@router.get("/{kb_id}/documents/{doc_id}/chunks")
async def get_document_chunks(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    kb=Depends(_require_kb),
    db: AsyncSession = Depends(get_db),
):
    """返回文档切块预览。优先返回 parent 大块，旧文档回退到 child 小块。"""
    from sqlalchemy import text

    try:
        doc = await kb_svc.get_document(db, kb_id, doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if doc.status != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文档尚未处理完成")

    rows = (await db.execute(
        text("SELECT parent_index, content FROM kb_parent_chunks WHERE doc_id = :doc_id ORDER BY parent_index"),
        {"doc_id": doc.id.hex},
    )).mappings().all()

    if rows:
        chunks = [{"index": r["parent_index"], "content": r["content"]} for r in rows]
        return {"total": len(chunks), "chunks": chunks, "level": "parent"}

    # 旧文档：回退到 Milvus child 小块
    from app.services import milvus_service
    raw = await asyncio.to_thread(milvus_service.query_doc_chunks, kb_id, doc_id)
    chunks = [{"index": r["chunk_index"], "content": r["content"]} for r in raw]
    return {"total": len(chunks), "chunks": chunks, "level": "child"}


@router.delete("/{kb_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        await kb_svc.delete_document(db, current_user.id, kb_id, doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
