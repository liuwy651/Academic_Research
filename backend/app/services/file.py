import io
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.token import estimate_tokens
from app.models.file import File

# 聊天时上传的文件仅支持 pdf 和 markdown 格式。
ALLOWED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "text/markdown": "markdown",
    "text/x-markdown": "markdown",
    "text/plain": "markdown",  # .md files sometimes come as text/plain
}

ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown"}


def _detect_file_type(filename: str, content_type: str) -> str | None:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".md", ".markdown"}:
        return "markdown"
    return ALLOWED_CONTENT_TYPES.get(content_type)


def _extract_pdf_text(data: bytes) -> str:
    import fitz  # PyMuPDF
    
    # 直接从二进制内存流加载 PDF，不需要先写到硬盘
    doc = fitz.open(stream=data, filetype="pdf")
    text_blocks = []
    
    for page in doc:
        # 获取当前页的所有文本块 (blocks)
        # 每个 block 包含坐标信息：(x0, y0, x1, y1, "text", block_no, block_type)
        blocks = page.get_text("blocks")
        
        # 核心逻辑：先按 Y 坐标（垂直方向）排序，再按 X 坐标（水平方向）排序
        # 这能最大程度解决双栏论文被“跨栏横读”的问题
        blocks.sort(key=lambda b: (b[1], b[0]))
        
        for b in blocks:
            text = b[4].strip()
            if text:
                text_blocks.append(text)
                
    return "\n\n".join(text_blocks)


def _extract_markdown_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _truncate_to_budget(text: str, budget: int) -> tuple[str, bool]:
    tokens = estimate_tokens(text)
    if tokens <= budget:
        return text, False
    # Binary-search a safe cut point (characters, not tokens)
    lo, hi = 0, len(text)
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if estimate_tokens(text[:mid]) <= budget:
            lo = mid
        else:
            hi = mid
    return text[:lo] + "\n\n[内容已截断，仅展示前部分]", True


def _storage_path(conv_id: uuid.UUID, file_id: uuid.UUID, filename: str) -> Path:
    safe_name = Path(filename).name  # strip any path traversal
    return Path(settings.UPLOAD_DIR) / str(conv_id) / f"{file_id}_{safe_name}"


async def save_upload(
    db: AsyncSession,
    upload: UploadFile,
    conv_id: uuid.UUID,
    user_id: uuid.UUID,
) -> File:
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"文件超过 {settings.MAX_FILE_SIZE_MB} MB 限制")

    file_type = _detect_file_type(upload.filename or "", upload.content_type or "")
    if file_type is None:
        raise ValueError("不支持的文件类型，仅支持 PDF 和 Markdown")

    if file_type == "pdf":
        raw_text = _extract_pdf_text(data)
    else:
        raw_text = _extract_markdown_text(data)

    extracted_text, _ = _truncate_to_budget(raw_text, settings.FILE_TOKEN_BUDGET)
    token_estimate = estimate_tokens(extracted_text)

    file_id = uuid.uuid4()
    rel_path = _storage_path(conv_id, file_id, upload.filename or "file")
    abs_path = Path(rel_path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(data)

    db_file = File(
        id=file_id,
        conversation_id=conv_id,
        uploader_id=user_id,
        original_filename=upload.filename or "file",
        file_type=file_type,
        file_size=len(data),
        storage_path=str(rel_path),
        extracted_text=extracted_text,
        token_estimate=token_estimate,
    )
    db.add(db_file)
    await db.flush()
    return db_file


async def get_file(db: AsyncSession, file_id: uuid.UUID, conv_id: uuid.UUID) -> File | None:
    result = await db.execute(
        select(File).where(File.id == file_id, File.conversation_id == conv_id)
    )
    return result.scalar_one_or_none()


async def list_files(db: AsyncSession, conv_id: uuid.UUID) -> list[File]:
    result = await db.execute(
        select(File)
        .where(File.conversation_id == conv_id)
        .order_by(File.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_file(db: AsyncSession, db_file: File) -> None:
    path = Path(db_file.storage_path)
    if path.exists():
        path.unlink(missing_ok=True)
    await db.delete(db_file)


async def attach_files_to_message(
    db: AsyncSession, file_ids: list[uuid.UUID], message_id: uuid.UUID, conv_id: uuid.UUID
) -> None:
    if not file_ids:
        return
    result = await db.execute(
        select(File).where(File.id.in_(file_ids), File.conversation_id == conv_id)
    )
    for db_file in result.scalars().all():
        db_file.message_id = message_id


async def get_files_by_message_ids(
    db: AsyncSession, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[File]]:
    """Batch-fetch files keyed by message_id."""
    if not message_ids:
        return {}
    result = await db.execute(
        select(File).where(File.message_id.in_(message_ids))
    )
    grouped: dict[uuid.UUID, list[File]] = {}
    for f in result.scalars().all():
        grouped.setdefault(f.message_id, []).append(f)
    return grouped


async def get_files_text(
    db: AsyncSession, file_ids: list[uuid.UUID], conv_id: uuid.UUID
) -> str:
    """Return concatenated formatted text for all requested files."""
    if not file_ids:
        return ""
    result = await db.execute(
        select(File).where(File.id.in_(file_ids), File.conversation_id == conv_id)
    )
    files = result.scalars().all()
    parts = []
    for f in files:
        if f.extracted_text:
            parts.append(f"[Attachment: {f.original_filename}]\n{f.extracted_text}")
    return "\n\n".join(parts)
