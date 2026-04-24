import uuid
from datetime import datetime

from pydantic import BaseModel


class FileResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID | None = None
    original_filename: str
    file_type: str
    file_size: int
    token_estimate: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
