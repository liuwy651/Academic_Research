import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation

DEFAULT_TITLE = "New Conversation"


def generate_title(content: str) -> str:
    text = re.sub(r'[#*_~`\[\]()>|]', '', content)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return DEFAULT_TITLE
    if len(text) <= 20:
        return text
    chunk = text[:20]
    # Only cut at sentence-ending punctuation (not commas)
    for sep in ('。', '？', '！', '?', '!', '.'):
        idx = chunk.rfind(sep)
        if idx > 5:
            return chunk[:idx + 1].strip()
    # For English: cut at last space to avoid mid-word truncation
    idx = chunk.rfind(' ')
    if idx > 8:
        return chunk[:idx].strip()
    return chunk.strip()


async def get_conversations(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 50
) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id, Conversation.deleted_at.is_(None))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def count_conversations(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(Conversation).where(
            Conversation.user_id == user_id, Conversation.deleted_at.is_(None)
        )
    )
    return result.scalar_one()


async def get_conversation(
    db: AsyncSession, conv_id: uuid.UUID, user_id: uuid.UUID
) -> Conversation | None:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_conversation(
    db: AsyncSession, user_id: uuid.UUID, title: str = "New Conversation"
) -> Conversation:
    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


async def update_conversation_title(
    db: AsyncSession, conv: Conversation, title: str
) -> Conversation:
    conv.title = title
    await db.flush()
    await db.refresh(conv)
    return conv


async def soft_delete_conversation(db: AsyncSession, conv: Conversation) -> None:
    conv.deleted_at = datetime.now(timezone.utc)
    await db.flush()


async def auto_title_conversation(
    db: AsyncSession, conv: Conversation, content: str
) -> bool:
    """Set title from first message content if still at default. Returns True if updated."""
    if conv.title != DEFAULT_TITLE:
        return False
    title = generate_title(content)
    conv.title = title
    await db.flush()
    return True


async def set_title_by_id(db: AsyncSession, conv_id: uuid.UUID, title: str) -> None:
    """Update conversation title directly by ID (for use inside streaming sessions)."""
    await db.execute(
        update(Conversation).where(Conversation.id == conv_id).values(title=title)
    )
