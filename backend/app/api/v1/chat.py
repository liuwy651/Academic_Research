import asyncio
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.llm.client import get_llm_client
from app.llm.token import count_messages_tokens, estimate_tokens, trim_to_budget
from app.models.user import User
from app.schemas.message import ChatRequest, MessageResponse, TreeNodeResponse
from app.services.chat import (
    create_message,
    get_messages_path,
    get_tree,
    resolve_node_id,
    touch_conversation,
)
from app.services.conversation import get_conversation, set_title_by_id
from app.schemas.file import FileAttachmentInfo
from app.services.file import attach_files_to_message, get_files_by_message_ids, get_files_text

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

    msg_ids = [uuid.UUID(str(r["id"])) for r in rows]
    files_map = await get_files_by_message_ids(db, msg_ids)

    responses = []
    for r in rows:
        data = dict(r)
        mid = uuid.UUID(str(data["id"]))
        data["files"] = [FileAttachmentInfo.model_validate(f) for f in files_map.get(mid, [])]
        responses.append(MessageResponse.model_validate(data))
    return responses


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
        raw_history = [{"role": r["role"], "content": r["content"]} for r in history_rows]
    else:
        raw_history = []

    # Fetch and format attached file content
    files_text = await get_files_text(db, payload.file_ids, conv_id)
    if files_text:
        user_content_for_llm = f"{files_text}\n\n---\n{payload.content}"
    else:
        user_content_for_llm = payload.content

    # With files: budget against the full context window so file tokens don't
    # get double-counted (trim_to_budget already deducts user_content tokens internally).
    # Without files: use the conservative history budget.
    if files_text:
        effective_budget = max(0, settings.LLM_CONTEXT_WINDOW - settings.LLM_RESPONSE_RESERVE)
    else:
        effective_budget = settings.LLM_HISTORY_BUDGET

    # Apply token budget — trim oldest messages to fit within effective budget
    trimmed_history, context_truncated = trim_to_budget(
        raw_history, user_content_for_llm, effective_budget
    )

    messages_for_llm = trimmed_history + [{"role": "user", "content": user_content_for_llm}]
    prompt_tokens = count_messages_tokens(messages_for_llm)

    # Save user message; track whether this is the first exchange for title generation
    user_token_count = estimate_tokens(payload.content)
    is_first_message = conv.title == "New Conversation" and conv.current_node_id is None
    user_msg = await create_message(
        db, conv_id, "user", payload.content,
        parent_id=user_parent_id, token_count=user_token_count,
    )
    user_msg_id = user_msg.id

    if payload.file_ids:
        await attach_files_to_message(db, payload.file_ids, user_msg_id, conv_id)

    await db.commit()

    async def generate():
        full_content = ""
        try:
            async for chunk in llm.stream_chat(messages_for_llm):
                full_content += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            new_title: str | None = None

            completion_tokens = estimate_tokens(full_content)

            async with AsyncSessionLocal() as save_db:
                asst_msg = await create_message(
                    save_db, conv_id, "assistant", full_content,
                    parent_id=user_msg_id, token_count=completion_tokens,
                    context_tokens=prompt_tokens,
                )
                await touch_conversation(save_db, conv_id, current_node_id=asst_msg.id)

                # Generate LLM title for the first exchange
                if is_first_message:
                    try:
                        snippet = full_content[:400]
                        title_messages = [
                            {
                                "role": "user",
                                "content": (
                                    f"请根据以下对话内容，生成一个5到15个字的简洁标题，"
                                    f"只输出标题文字，不要任何解释、标点符号或引号。\n\n"
                                    f"用户：{payload.content}\n"
                                    f"助手：{snippet}"
                                ),
                            }
                        ]
                        raw = await llm.chat(
                            title_messages,
                            system="你是对话标题生成助手，只输出简洁标题，不超过15个字。",
                        )
                        # Strip surrounding punctuation/quotes LLM might add
                        cleaned = raw.strip().strip('《》「」【】""\'\'""。，.').strip()
                        if cleaned:
                            new_title = cleaned[:20]
                            await set_title_by_id(save_db, conv_id, new_title)
                    except Exception:
                        pass  # title generation is non-critical

                await save_db.commit()

            yield f"data: {json.dumps({'type': 'done', 'message_id': str(asst_msg.id), 'title': new_title, 'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'context_truncated': context_truncated})}\n\n"

        except asyncio.CancelledError:
            return  # client disconnected — clean exit, nothing to yield
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
