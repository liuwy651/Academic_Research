"""阿里云 DocMind 文档解析服务。

支持 PDF / DOCX / XLSX / TXT，异步提交任务并轮询结果。
SDK 为同步，全部通过 asyncio.to_thread() 在线程池中运行。

GetDocParserResult 是分页 API，必须传 layout_num（起始索引）和 layout_step_size（每批大小）。
总 layout 数来自 QueryDocParserStatus 响应的 paragraph_count 字段。
"""
import asyncio
import logging
import time
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5    # 轮询间隔秒数
_MAX_WAIT = 300       # 最长等待秒数
_PAGE_SIZE = 200      # 每次获取的 layout 数量


def _make_client():
    from alibabacloud_docmind_api20220711.client import Client
    from alibabacloud_tea_openapi import models as open_api_models

    config = open_api_models.Config(
        access_key_id=settings.DOCMIND_ACCESS_KEY_ID,
        access_key_secret=settings.DOCMIND_ACCESS_KEY_SECRET,
    )
    config.endpoint = settings.DOCMIND_ENDPOINT
    return Client(config)


def _submit_sync(file_path: Path, filename: str, file_type: str) -> str:
    """同步提交解析任务，返回 task_id。"""
    from alibabacloud_docmind_api20220711 import models as dm_models
    from alibabacloud_tea_util import models as util_models

    client = _make_client()
    runtime = util_models.RuntimeOptions()

    with open(file_path, "rb") as f:
        request = dm_models.SubmitDocParserJobAdvanceRequest(
            file_url_object=f,
            file_name=filename,
            file_name_extension=file_type.lower().lstrip("."),
        )
        response = client.submit_doc_parser_job_advance(request, runtime)

    task_id: str = response.body.data.id
    logger.info("DocMind 任务已提交: task_id=%s filename=%s", task_id, filename)
    return task_id


def _poll_and_fetch_sync(task_id: str) -> str:
    """同步轮询状态，完成后分页取全部结果，返回拼接后的文本。"""
    from alibabacloud_docmind_api20220711 import models as dm_models

    client = _make_client()
    start = time.monotonic()
    total_layouts = 0

    # ── 第一阶段：轮询状态，拿到 paragraph_count ──────────────────────
    while True:
        elapsed = time.monotonic() - start
        if elapsed > _MAX_WAIT:
            raise TimeoutError(f"DocMind 解析超时（>{_MAX_WAIT}s）: task_id={task_id}")

        status_req = dm_models.QueryDocParserStatusRequest(id=task_id)
        status_resp = client.query_doc_parser_status(status_req)
        data = status_resp.body.data
        status: str = (data.status or "").strip().lower()

        logger.debug("DocMind 轮询中: task_id=%s status=%s elapsed=%.1fs", task_id, status, elapsed)

        if status == "success":
            # paragraph_count 即 layout 总数
            total_layouts = data.paragraph_count or 0
            logger.info("DocMind 解析完成: task_id=%s total_layouts=%d", task_id, total_layouts)
            break
        if status in ("failed", "error"):
            raise RuntimeError(f"DocMind 解析失败: task_id={task_id} status={status}")

        time.sleep(_POLL_INTERVAL)

    # ── 第二阶段：分页拉取全部 layout ────────────────────────────────
    # layout_num 是本次取结果的起始索引（0-based），layout_step_size 是每批大小
    all_parts: list[str] = []
    fetched = 0

    # 若 paragraph_count 为 0（API 未返回），至少取一次
    fetch_count = max(total_layouts, 1)

    while fetched < fetch_count:
        result_req = dm_models.GetDocParserResultRequest(
            id=task_id,
            layout_num=fetched,
            layout_step_size=_PAGE_SIZE,
        )
        result_resp = client.get_doc_parser_result(result_req)

        body = result_resp.body
        if body.code and body.code != "Success":
            raise RuntimeError(f"GetDocParserResult 错误: code={body.code} message={body.message}")

        data: dict = body.data or {}
        page_parts = _extract_page(data)
        all_parts.extend(page_parts)

        returned = len(page_parts)
        fetched += _PAGE_SIZE

        logger.debug("DocMind 取结果: layout_num=%d returned=%d", fetched - _PAGE_SIZE, returned)

        # 若本批返回数量 < 页大小，说明已到末尾
        if returned < _PAGE_SIZE:
            break

    markdown = "\n\n".join(all_parts)
    logger.info("DocMind 全部内容获取完毕: task_id=%s chars=%d parts=%d", task_id, len(markdown), len(all_parts))
    return markdown


# DocMind layout subType 中属于图片/公式等非文本内容，提取文本时跳过
_NON_TEXT_SUBTYPES = {"figure", "image", "picture", "formula", "seal", "barcode", "qrcode"}


def _extract_page(data: dict) -> list[str]:
    """从单次 GetDocParserResult 的 data 字典中提取文本片段列表。

    实测 layout 字段优先级（以 PDF 为例）：
      markdownContent > markdownText > markdown_text > text

    图片/公式类 layout（subType in _NON_TEXT_SUBTYPES）直接跳过，避免乱码写入向量库。
    """
    parts: list[str] = []

    # 优先取顶层 markdown 字段
    top_md = data.get("markdown") or data.get("markdownContent") or data.get("markdownText")
    if isinstance(top_md, str) and top_md.strip():
        parts.append(top_md.strip())
        return parts

    # 从 layouts 列表逐块提取，跳过非文本 block
    layouts: list[dict] = data.get("layouts") or []
    for layout in layouts:
        sub_type = (layout.get("subType") or layout.get("type") or "").lower()
        if sub_type in _NON_TEXT_SUBTYPES:
            logger.debug("跳过非文本 layout: subType=%s", sub_type)
            continue

        text = (
            layout.get("markdownContent")
            or layout.get("markdownText")
            or layout.get("markdown_text")
            or layout.get("text")
            or ""
        )
        if text.strip():
            parts.append(text.strip())

    return parts


async def parse_document(file_path: Path, filename: str, file_type: str) -> tuple[str, str]:
    """提交并等待 DocMind 解析完成。

    Returns:
        (task_id, markdown_text)
    """
    task_id = await asyncio.to_thread(_submit_sync, file_path, filename, file_type)
    markdown = await asyncio.to_thread(_poll_and_fetch_sync, task_id)
    return task_id, markdown
