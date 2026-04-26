import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("知识库名称不能为空")
        return v


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class KnowledgeBaseOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    document_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeBaseListOut(BaseModel):
    items: list[KnowledgeBaseOut]
    total: int


class DocumentOut(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    filename: str
    file_type: str
    file_size: int
    chunk_count: int | None
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int
