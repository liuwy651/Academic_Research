import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import AsyncSessionLocal, get_db
from app.llm.client import get_llm_client
from app.models.user import User
from app.schemas.message import ChatRequest, MessageResponse
from app.services.chat import create_message, get_messages, touch_conversation
from app.services.conversation import get_conversation

router = APIRouter(prefix="/conversations", tags=["chat"])


@router.get("/{conv_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conv_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await get_conversation(db, conv_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return await get_messages(db, conv_id)


@router.post("/{conv_id}/chat")
async def chat_stream(
    conv_id: uuid.UUID,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await get_conversation(db, conv_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Validate LLM is configured before saving anything
    try:
        llm = get_llm_client()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Save user message and load history (all in one transaction)
    await create_message(db, conv_id, "user", payload.content)
    history = await get_messages(db, conv_id)
    messages_for_llm = [{"role": m.role, "content": m.content} for m in history]

    # Commit user message before streaming starts
    await db.commit()

    async def generate():
        full_content = ""
        try:
            async for chunk in llm.stream_chat(messages_for_llm):
                full_content += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            # Persist assistant message + update conversation timestamp
            async with AsyncSessionLocal() as save_db:
                msg = await create_message(save_db, conv_id, "assistant", full_content)
                await touch_conversation(save_db, conv_id)
                await save_db.commit()

            yield f"data: {json.dumps({'type': 'done', 'message_id': str(msg.id)})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
