"""RAG 知识库检索工具，供 Agent 主动调用。"""
import asyncio
import logging
import uuid

logger = logging.getLogger(__name__)


KB_RAG_SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": (
            "在用户的私有知识库中检索相关内容。"
            "当用户问题涉及其上传的文档、专属知识、内部资料时，必须调用此工具。"
            "工具使用语义向量检索 + 关键词匹配混合方式，能理解语义相近的表达。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "检索查询文本。直接使用用户问题的核心语义，"
                        "保留实体名、专有词，不要过度简化。"
                        "例：'深度学习中梯度消失问题如何解决'"
                    ),
                },
                "top_n": {
                    "type": "integer",
                    "description": "返回的最相关片段数量，默认 5，最大 10。",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


def make_rag_handler(
    user_id: uuid.UUID,
    override_kb_ids: list[uuid.UUID] | None = None,
):
    """工厂函数：创建 RAG 检索 handler 闭包。

    在 async 请求上下文中调用本函数，会捕获当前事件循环引用。
    handler 本身是同步函数，由 ToolNode 经 asyncio.to_thread 在线程中调用，
    线程内无 running loop，因此需要通过 run_coroutine_threadsafe 提交回主循环。
    """
    # 在创建时（async 请求上下文）捕获主事件循环，供线程内回调使用
    try:
        _main_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        _main_loop = None

    def handler(query: str, top_n: int | None = 5) -> str:
        from app.core.database import AsyncSessionLocal
        from app.services import rag_service

        top_n = max(1, min(top_n or 5, 10))

        async def _run():
            async with AsyncSessionLocal() as db:
                if override_kb_ids:
                    kb_ids = override_kb_ids
                    qvec = None
                else:
                    from app.services.embedding_service import encode_batch
                    vectors = await encode_batch([query])
                    qvec = vectors[0]
                    kb_ids = await rag_service.select_relevant_kbs(
                        db=db,
                        user_id=user_id,
                        query_vector=qvec,
                    )
                    if not kb_ids:
                        return []

                return await rag_service.retrieve(
                    db=db,
                    kb_ids=kb_ids,
                    query=query,
                    top_n=top_n,
                    query_vector=qvec,
                )

        try:
            loop = _main_loop
            if loop is None or not loop.is_running():
                # 无主循环引用时（如单元测试），直接新建循环运行
                results = asyncio.run(_run())
            else:
                # 运行于 asyncio.to_thread 线程中：提交协程回主循环
                future = asyncio.run_coroutine_threadsafe(_run(), loop)
                results = future.result(timeout=30)
        except Exception as exc:
            logger.error("RAG 检索失败: %s", exc, exc_info=True)
            return f"知识库检索失败：{exc}"

        return _format_results(query, results)

    handler.__name__ = "search_knowledge_base"
    return handler


def _format_results(query: str, results) -> str:
    """将 ChunkResult 列表格式化为 LLM 友好的 Markdown 文本。"""
    if not results:
        return f'知识库检索未找到与"{query}"相关的内容。'

    lines = [f"## 知识库检索结果（查询：{query}）\n"]
    for i, chunk in enumerate(results, 1):
        context = chunk.parent_content if chunk.parent_content else chunk.content
        lines.append(
            f"### 片段 {i}（来源：{chunk.filename}，第 {chunk.chunk_index + 1} 块）\n"
            f"{context}\n"
        )
    return "\n".join(lines)
