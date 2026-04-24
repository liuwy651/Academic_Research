import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import AsyncSessionLocal, get_db
from app.llm.client import get_llm_client
from app.models.user import User
from app.schemas.message import ChatRequest, MessageResponse, TreeNodeResponse
from app.services.chat import (
    create_message,
    get_messages_path,
    get_tree,
    resolve_node_id,
    touch_conversation,
)
from app.services.conversation import get_conversation

router = APIRouter(prefix="/conversations", tags=["chat"])


@router.get("/{conv_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conv_id: uuid.UUID,
    node_id: Optional[uuid.UUID] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await get_conversation(db, conv_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        resolved = await resolve_node_id(db, conv_id, node_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if resolved is None:
        return []

    rows = await get_messages_path(db, conv_id, resolved)
    return [MessageResponse.model_validate(dict(r)) for r in rows]


@router.get("/{conv_id}/tree", response_model=list[TreeNodeResponse])
async def get_conversation_tree(
    conv_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await get_conversation(db, conv_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    rows = await get_tree(db, conv_id)
    return [TreeNodeResponse.model_validate(dict(r)) for r in rows]


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

    try:
        llm = get_llm_client()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Determine parent for new user message
    if payload.parent_id is not None:
        user_parent_id = payload.parent_id
    else:
        user_parent_id = conv.current_node_id  # may be None for first message

    # Build LLM history from the linear path up to user_parent_id
    if user_parent_id is not None:
        history_rows = await get_messages_path(db, conv_id, user_parent_id)
        messages_for_llm = [{"role": r["role"], "content": r["content"]} for r in history_rows]
    else:
        messages_for_llm = []

    messages_for_llm.append({"role": "user", "content": payload.content})

    # Save user message
    user_msg = await create_message(db, conv_id, "user", payload.content, parent_id=user_parent_id)
    user_msg_id = user_msg.id

    await db.commit()

    async def generate():
        full_content = ""
        try:
            async for chunk in llm.stream_chat(messages_for_llm):
                full_content += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            async with AsyncSessionLocal() as save_db:
                asst_msg = await create_message(
                    save_db, conv_id, "assistant", full_content, parent_id=user_msg_id
                )
                await touch_conversation(save_db, conv_id, current_node_id=asst_msg.id)
                await save_db.commit()

            yield f"data: {json.dumps({'type': 'done', 'message_id': str(asst_msg.id)})}\n\n"

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
