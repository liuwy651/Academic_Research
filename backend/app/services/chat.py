import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message


async def get_messages(db: AsyncSession, conv_id: uuid.UUID) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


async def create_message(
    db: AsyncSession, conv_id: uuid.UUID, role: str, content: str
) -> Message:
    msg = Message(conversation_id=conv_id, role=role, content=content)
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


async def touch_conversation(db: AsyncSession, conv_id: uuid.UUID) -> None:
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conv_id)
        .values(updated_at=datetime.now(timezone.utc))
    )
