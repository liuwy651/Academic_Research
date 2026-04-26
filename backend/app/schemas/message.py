import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.schemas.file import FileAttachmentInfo


class ChatRequest(BaseModel):
    content: str
    parent_id: uuid.UUID | None = None
    file_ids: list[uuid.UUID] = []
    kb_ids: list[uuid.UUID] = []    # 显式指定 KB（非空时跳过自动选库）
    auto_kb: bool = False           # True = 从用户所有 KB 中自动选库

    @field_validator("content")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Content cannot be empty")
        return v


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    parent_id: uuid.UUID | None = None
    summary: str | None = None
    context_tokens: int | None = None
    thinking: str | None = None
    tool_steps: list | None = None
    files: list[FileAttachmentInfo] = []

    model_config = {"from_attributes": True}


class TreeNodeResponse(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None = None
    role: str
    summary: str | None = None

    model_config = {"from_attributes": True}
