import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage as LCAIMessage
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage as LCToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import get_agent_graph
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

_IMAGE_RE = re.compile(r'\[IMAGE_URL:(/static/plots/[^\]]+)\]')

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

    # 验证 LLM 密钥配置（早失败，返回 503）
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

    if files_text:
        effective_budget = max(0, settings.LLM_CONTEXT_WINDOW - settings.LLM_RESPONSE_RESERVE)
    else:
        effective_budget = settings.LLM_HISTORY_BUDGET

    trimmed_history, context_truncated = trim_to_budget(
        raw_history, user_content_for_llm, effective_budget
    )

    # Save user message — token_count tracks raw user text (without injected file content)
    user_token_count = estimate_tokens(user_content_for_llm)
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
        # ── 构建 LangChain 消息列表（系统提示 + 历史 + 用户消息）──────────────
        now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        system_parts = [f"当前时间：{now}"]
        if settings.LLM_SYSTEM_PROMPT:
            system_parts.append(settings.LLM_SYSTEM_PROMPT)

        # ── RAG Tool：始终注入 search_knowledge_base，确保 Researcher 可用 ──
        # kb_ids 显式指定时精确检索；否则自动从用户所有 KB 中选库。
        # 工具始终存在，没有 KB 时工具会返回"未找到"，不影响其他功能。
        from app.agents.tools.rag_search import KB_RAG_SEARCH_TOOL_SCHEMA, make_rag_handler
        rag_handler = make_rag_handler(
            user_id=current_user.id,
            override_kb_ids=payload.kb_ids if payload.kb_ids else None,
        )
        extra_schemas: list[dict] = [KB_RAG_SEARCH_TOOL_SCHEMA]
        extra_handlers: dict = {"search_knowledge_base": rag_handler}
        # 知识库检索指引不注入全局 system prompt（避免 PrimaryRouter 看到矛盾指令）
        # CS_Researcher 的 system prompt 已内置知识库检索职责

        system_text = "\n\n".join(system_parts)
        lc_msgs: list = [SystemMessage(content=system_text)]
        for row in trimmed_history:
            role, content = row["role"], row["content"]
            if role == "user":
                lc_msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_msgs.append(LCAIMessage(content=content))
        lc_msgs.append(HumanMessage(content=user_content_for_llm))

        # Compute prompt_tokens here so it includes system prompt + tool schemas
        tool_schema_text = json.dumps(extra_schemas)
        prompt_tokens = (
            estimate_tokens(system_text) + 4
            + estimate_tokens(tool_schema_text)
            + count_messages_tokens(
                trimmed_history + [{"role": "user", "content": user_content_for_llm}]
            )
        )

        graph = get_agent_graph(extra_schemas=extra_schemas, extra_handlers=extra_handlers)
        full_content_parts: list[str] = []
        full_thinking_parts: list[str] = []
        collected_steps: list[dict] = []

        # ── <think> 标签流式解析状态机 ────────────────────────────────────
        _THINK_OPEN = "<think>"
        _THINK_CLOSE = "</think>"
        _THINK_LAG = max(len(_THINK_OPEN), len(_THINK_CLOSE))
        _think_buf: str = ""
        _in_think: bool = False

        def _process_delta(delta: str) -> list[tuple[str, str]]:
            nonlocal _think_buf, _in_think
            _think_buf += delta
            out: list[tuple[str, str]] = []
            while True:
                if not _in_think:
                    i = _think_buf.find(_THINK_OPEN)
                    if i >= 0:
                        if i > 0:
                            out.append(("chunk", _think_buf[:i]))
                        _think_buf = _think_buf[i + len(_THINK_OPEN):]
                        _in_think = True
                    elif len(_think_buf) > _THINK_LAG:
                        out.append(("chunk", _think_buf[:-_THINK_LAG]))
                        _think_buf = _think_buf[-_THINK_LAG:]
                        break
                    else:
                        break
                else:
                    i = _think_buf.find(_THINK_CLOSE)
                    if i >= 0:
                        if i > 0:
                            out.append(("thinking_chunk", _think_buf[:i]))
                        _think_buf = _think_buf[i + len(_THINK_CLOSE):]
                        _in_think = False
                    elif len(_think_buf) > _THINK_LAG:
                        out.append(("thinking_chunk", _think_buf[:-_THINK_LAG]))
                        _think_buf = _think_buf[-_THINK_LAG:]
                        break
                    else:
                        break
            return out

        def _flush_buf() -> list[tuple[str, str]]:
            nonlocal _think_buf, _in_think
            if not _think_buf:
                return []
            kind = "thinking_chunk" if _in_think else "chunk"
            result = [(kind, _think_buf)]
            _think_buf = ""
            return result

        # ── PrimaryRouter 输出缓冲 ──────────────────────────────────────
        # PrimaryRouter 路由时不应向前端输出任何内容（包括 JSON 工具调用块）。
        # 仅当 PrimaryRouter 直接回答（next_node=FINISH）时才将缓冲内容推送给前端。
        _pr_sse: list[str] = []      # 待推送的 SSE 字符串
        _pr_content: list[str] = []  # 对应的纯文本（用于保存到数据库）
        _pr_thinking: list[str] = [] # 对应的思考内容

        def _pr_node(ev: dict) -> bool:
            return ev.get("metadata", {}).get("langgraph_node") == "PrimaryRouter"

        try:
            async for event in graph.astream_events(
                {"messages": lc_msgs},
                version="v2",
                config={"recursion_limit": 15},
            ):
                etype: str = event["event"]
                ename: str = event.get("name", "")
                data: dict = event.get("data", {})

                # ── LLM 流式文本块 ────────────────────────────────────────
                if etype == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    if chunk is None:
                        continue

                    is_router = _pr_node(event)

                    # Thinking 模型：思考内容在 reasoning_content 字段
                    rc: str = (getattr(chunk, "additional_kwargs", None) or {}).get("reasoning_content") or ""
                    if rc:
                        sse = f"data: {json.dumps({'type': 'thinking_chunk', 'content': rc})}\n\n"
                        if is_router:
                            _pr_thinking.append(rc)
                            yield sse  # 思考内容实时推送，不缓冲
                        else:
                            full_thinking_parts.append(rc)
                            yield sse

                    content = chunk.content
                    deltas: list[str] = []
                    if isinstance(content, str) and content:
                        deltas.append(content)
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                t: str = block["text"]
                                if t:
                                    deltas.append(t)
                    for delta in deltas:
                        for kind, text in _process_delta(delta):
                            sse = f"data: {json.dumps({'type': kind, 'content': text})}\n\n"
                            if is_router:
                                if kind == "thinking_chunk":
                                    _pr_thinking.append(text)
                                    yield sse  # 思考内容实时推送
                                else:
                                    _pr_sse.append(sse)
                                    _pr_content.append(text)
                            else:
                                if kind == "chunk":
                                    full_content_parts.append(text)
                                else:
                                    full_thinking_parts.append(text)
                                yield sse

                # ── LLM 一轮结束，冲刷缓冲区 ─────────────────────────────
                elif etype == "on_chat_model_end":
                    is_router = _pr_node(event)
                    for kind, text in _flush_buf():
                        sse = f"data: {json.dumps({'type': kind, 'content': text})}\n\n"
                        if is_router:
                            if kind == "thinking_chunk":
                                _pr_thinking.append(text)
                                yield sse  # 思考内容实时推送
                            else:
                                _pr_sse.append(sse)
                                _pr_content.append(text)
                        else:
                            if kind == "chunk":
                                full_content_parts.append(text)
                            else:
                                full_thinking_parts.append(text)
                            yield sse

                # ── PrimaryRouter 节点结束：决定冲刷还是丢弃缓冲 ──────────
                elif etype == "on_chain_end" and ename == "PrimaryRouter":
                    node_out = data.get("output") or {}
                    if isinstance(node_out, dict) and node_out.get("next_node", "FINISH") == "FINISH" and _pr_sse:
                        full_content_parts.extend(_pr_content)
                        full_thinking_parts.extend(_pr_thinking)
                        for sse in _pr_sse:
                            yield sse
                    _pr_sse.clear()
                    _pr_content.clear()
                    _pr_thinking.clear()

                # ── 工具开始执行 ──────────────────────────────────────────
                elif etype == "on_tool_start":
                    is_router = _pr_node(event)
                    tool_input = data.get("input", {})
                    collected_steps.append({"name": ename, "args": tool_input, "status": "running"})
                    sse = f"data: {json.dumps({'type': 'tool_start', 'name': ename, 'args': tool_input})}\n\n"
                    if is_router:
                        _pr_sse.append(sse)
                    else:
                        yield sse

                # ── 工具执行完毕 ──────────────────────────────────────────
                elif etype == "on_tool_end":
                    is_router = _pr_node(event)
                    # LangGraph 1.x: output 是 ToolMessage 对象
                    output = data.get("output")
                    raw_text: str = (
                        output.content
                        if isinstance(output, LCToolMessage)
                        else str(output) if output is not None else ""
                    )

                    # 图片 URL 作为 chunk 注入（工具结果中的图片始终直接推送）
                    image_match = _IMAGE_RE.search(raw_text)
                    if image_match:
                        image_md = f"\n\n![]({image_match.group(1)})\n\n"
                        full_content_parts.append(image_md)
                        yield f"data: {json.dumps({'type': 'chunk', 'content': image_md})}\n\n"

                    clean = _IMAGE_RE.sub("", raw_text).strip()
                    for step in reversed(collected_steps):
                        if step["name"] == ename and step["status"] == "running":
                            step["result"] = clean[:800]
                            step["status"] = "done"
                            break
                    sse = f"data: {json.dumps({'type': 'tool_result', 'name': ename, 'content': clean[:800]})}\n\n"
                    if is_router:
                        _pr_sse.append(sse)
                    else:
                        yield sse

            # ── 保存助手消息 ──────────────────────────────────────────────
            full_content = "".join(full_content_parts)
            full_thinking = "".join(full_thinking_parts) or None
            new_title: str | None = None
            completion_tokens = estimate_tokens(full_content)

            async with AsyncSessionLocal() as save_db:
                asst_msg = await create_message(
                    save_db, conv_id, "assistant", full_content,
                    parent_id=user_msg_id, token_count=completion_tokens,
                    context_tokens=prompt_tokens,
                    thinking=full_thinking,
                    tool_steps=collected_steps if collected_steps else None,
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
                            max_tokens=200,
                            model=settings.LLM_TITLE_MODEL,
                        )
                        # Strip any <think>...</think> blocks that reasoning models may emit
                        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
                        cleaned_title = raw.strip('《》「」【】""\'\'""。，.').strip()
                        if cleaned_title:
                            new_title = cleaned_title[:20]
                            await set_title_by_id(save_db, conv_id, new_title)
                    except Exception:
                        pass

                await save_db.commit()

            yield f"data: {json.dumps({'type': 'done', 'message_id': str(asst_msg.id), 'title': new_title, 'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'context_truncated': context_truncated})}\n\n"

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.exception("generate() 异常: %s", e)
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
