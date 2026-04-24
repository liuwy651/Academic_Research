import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message


def generate_summary(content: str) -> str:
    cleaned = re.sub(r'[#*_~`\[\]()>|]', '', content)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:10]


async def get_messages(db: AsyncSession, conv_id: uuid.UUID) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


_CTE_PATH_SQL = text("""
WITH RECURSIVE path AS (
  SELECT id, parent_id, role, content, created_at, conversation_id, summary
  FROM messages
  WHERE id = :node_id AND conversation_id = :conv_id
  UNION ALL
  SELECT m.id, m.parent_id, m.role, m.content, m.created_at, m.conversation_id, m.summary
  FROM messages m
  JOIN path p ON m.id = p.parent_id
  WHERE m.conversation_id = :conv_id
)
SELECT * FROM path ORDER BY created_at ASC
""")


async def get_messages_path(
    db: AsyncSession, conv_id: uuid.UUID, node_id: uuid.UUID
) -> list[Any]:
    result = await db.execute(
        _CTE_PATH_SQL,
        {"node_id": str(node_id), "conv_id": str(conv_id)},
    )
    return result.mappings().all()


async def resolve_node_id(
    db: AsyncSession,
    conv_id: uuid.UUID,
    node_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if node_id is not None:
        return node_id

    conv = await db.get(Conversation, conv_id)
    if conv is None:
        raise ValueError(f"Conversation {conv_id} not found")

    if conv.current_node_id is not None:
        return conv.current_node_id

    result = await db.execute(
        select(Message.id)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_tree(db: AsyncSession, conv_id: uuid.UUID) -> list[Any]:
    result = await db.execute(
        select(Message.id, Message.parent_id, Message.role, Message.summary)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
    )
    return result.mappings().all()


async def create_message(
    db: AsyncSession,
    conv_id: uuid.UUID,
    role: str,
    content: str,
    parent_id: uuid.UUID | None = None,
) -> Message:
    msg = Message(
        conversation_id=conv_id,
        role=role,
        content=content,
        parent_id=parent_id,
        summary=generate_summary(content),
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


async def touch_conversation(
    db: AsyncSession,
    conv_id: uuid.UUID,
    current_node_id: uuid.UUID | None = None,
) -> None:
    values: dict = {"updated_at": datetime.now(timezone.utc)}
    if current_node_id is not None:
        values["current_node_id"] = current_node_id
    await db.execute(
        update(Conversation).where(Conversation.id == conv_id).values(**values)
    )
