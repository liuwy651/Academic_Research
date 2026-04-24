import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.file import FileResponse
from app.services.conversation import get_conversation
from app.services.file import delete_file, get_file, list_files, save_upload

router = APIRouter(prefix="/conversations", tags=["files"])


@router.post("/{conv_id}/files", response_model=FileResponse, status_code=201)
async def upload_file(
    conv_id: uuid.UUID,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await get_conversation(db, conv_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        db_file = await save_upload(db, file, conv_id, current_user.id)
        await db.commit()
        await db.refresh(db_file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FileResponse.model_validate(db_file)


@router.get("/{conv_id}/files", response_model=list[FileResponse])
async def get_files(
    conv_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await get_conversation(db, conv_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    files = await list_files(db, conv_id)
    return [FileResponse.model_validate(f) for f in files]


@router.delete("/{conv_id}/files/{file_id}", status_code=204)
async def remove_file(
    conv_id: uuid.UUID,
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await get_conversation(db, conv_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db_file = await get_file(db, file_id, conv_id)
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    await delete_file(db, db_file)
    await db.commit()
