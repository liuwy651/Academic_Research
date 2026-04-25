import asyncio
import json
import logging
import re
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.registry import registry
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
            # ── 第一次请求：带工具定义，实时推送文本，拦截 tool_calls ──────────
            pending_tool_calls: list[dict] = []

            logger.info("Starting first LLM request with tools for conv %s", conv_id)
            async for event in llm.stream_chat_with_tools(
                messages_for_llm, tools=registry.get_all_tool_schemas()
            ):
                if event["type"] == "text":
                    full_content += event["content"]
                    yield f"data: {json.dumps({'type': 'chunk', 'content': event['content']})}\n\n"
                elif event["type"] == "tool_calls":
                    pending_tool_calls = event["calls"]
                    logger.info("Intercepted tool_calls: %s", pending_tool_calls)

            # ── 如果模型决定调用工具：执行 → 二次请求 ────────────────────────
            if pending_tool_calls:
                logger.info("Tool calls triggered: %s", [tc["function"]["name"] for tc in pending_tool_calls])

                # 组装带工具调用记录的 messages（OpenAI 标准格式）
                # 不设置 content 键（而非 None），以兼容更多 LLM 后端
                asst_tool_msg: dict = {
                    "role": "assistant",
                    "tool_calls": pending_tool_calls,
                }
                if full_content:
                    asst_tool_msg["content"] = full_content

                messages_augmented: list[dict] = list(messages_for_llm) + [asst_tool_msg]
                image_mds: list[str] = []

                for tc in pending_tool_calls:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except (json.JSONDecodeError, KeyError):
                        args = {}

                    # 通知前端正在调用哪个工具
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': name, 'args': args})}\n\n"

                    # 同步函数用 to_thread 防止阻塞事件循环
                    result: str = await asyncio.to_thread(registry.execute_tool, name, args)

                    # 检测 MCP 权限错误，追加引导说明供模型理解
                    if result.startswith("[MCP 工具错误]") and any(
                        kw in result for kw in ("EACCES", "permission", "Permission", "denied", "Denied", "not allowed")
                    ):
                        result += (
                            "\n\n[权限引导] 该路径未在 MCP filesystem server 的授权目录中。"
                            "请告知用户：可在后端配置 MCP_FILESYSTEM_PATHS 环境变量（逗号分隔）添加目标路径，"
                            "然后重启服务使配置生效。"
                        )

                    # 通知前端工具返回结果（内容截断避免 SSE 报文过大）
                    yield f"data: {json.dumps({'type': 'tool_result', 'name': name, 'content': result[:800]})}\n\n"

                    # 如果沙箱生成了图片，以 markdown 图片语法注入 content 流
                    # chunk 在工具执行后立刻发出，图片自然出现在对话中间位置
                    image_match = re.search(r'\[IMAGE_URL:(/static/plots/[^\]]+)\]', result)
                    if image_match:
                        image_md = f"\n\n![]({image_match.group(1)})\n\n"
                        image_mds.append(image_md)
                        yield f"data: {json.dumps({'type': 'chunk', 'content': image_md})}\n\n"

                    # 剥除内部图片标记再送入 LLM，避免模型在回复中重复输出图片 URL
                    llm_result = re.sub(r'\n*\[IMAGE_URL:[^\]]+\]', '', result).strip()
                    if image_match:
                        llm_result += "\n[图片已由界面自动渲染，请勿在回复中用任何文字描述图片的保存或展示过程，直接分析图表内容即可]"
                    messages_augmented.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": llm_result or "(代码执行完毕，无任何输出)",
                    })

                # 二次请求：保留工具调用前的文字，拼接图片 markdown，再追加模型文字
                # 图片 markdown 已作为 chunk 发出，无需重发
                full_content += "".join(image_mds)
                async for chunk in llm.stream_chat(messages_augmented):
                    full_content += chunk
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            # ── 保存助手消息 & done 事件（与原有逻辑完全一致）───────────────
            new_title: str | None = None
            completion_tokens = estimate_tokens(full_content)

            async with AsyncSessionLocal() as save_db:
                asst_msg = await create_message(
                    save_db, conv_id, "assistant", full_content,
                    parent_id=user_msg_id, token_count=completion_tokens,
                    context_tokens=prompt_tokens,
                )
                await touch_conversation(save_db, conv_id, current_node_id=asst_msg.id)

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
                        cleaned = raw.strip().strip('《》「」【】""\'\'""。，.').strip()
                        if cleaned:
                            new_title = cleaned[:20]
                            await set_title_by_id(save_db, conv_id, new_title)
                    except Exception:
                        pass

                await save_db.commit()

            yield f"data: {json.dumps({'type': 'done', 'message_id': str(asst_msg.id), 'title': new_title, 'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'context_truncated': context_truncated})}\n\n"

        except asyncio.CancelledError:
            return
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
