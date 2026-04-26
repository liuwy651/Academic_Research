"""临时调试脚本：测试 DocMind 分页取结果。

用法：
  uv run python scripts/debug_docmind.py /path/to/file.pdf
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.core.config import settings
from alibabacloud_docmind_api20220711.client import Client
from alibabacloud_docmind_api20220711 import models as dm
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

_PAGE_SIZE = 200


def make_client():
    config = open_api_models.Config(
        access_key_id=settings.DOCMIND_ACCESS_KEY_ID,
        access_key_secret=settings.DOCMIND_ACCESS_KEY_SECRET,
    )
    config.endpoint = settings.DOCMIND_ENDPOINT
    return Client(config)


def main():
    file_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not file_path or not file_path.exists():
        print("用法: uv run python scripts/debug_docmind.py /path/to/file.pdf")
        sys.exit(1)

    ext = file_path.suffix.lstrip(".")
    client = make_client()
    runtime = util_models.RuntimeOptions()

    # ── 1. 提交 ───────────────────────────────────────────────────────
    print(f"\n[1] 提交文件: {file_path.name}  ext={ext}")
    with open(file_path, "rb") as f:
        req = dm.SubmitDocParserJobAdvanceRequest(
            file_url_object=f,
            file_name=file_path.name,
            file_name_extension=ext,
        )
        resp = client.submit_doc_parser_job_advance(req, runtime)

    task_id = resp.body.data.id
    print(f"    task_id = {task_id}")

    # ── 2. 轮询状态 ───────────────────────────────────────────────────
    print(f"\n[2] 轮询状态...")
    start = time.monotonic()
    total_layouts = 0
    while True:
        s_req = dm.QueryDocParserStatusRequest(id=task_id)
        s_resp = client.query_doc_parser_status(s_req)
        data = s_resp.body.data
        status = (data.status or "").lower()
        elapsed = time.monotonic() - start
        print(f"    elapsed={elapsed:.0f}s  status={status}  paragraph_count={data.paragraph_count}")
        if status == "success":
            total_layouts = data.paragraph_count or 0
            break
        if status in ("failed", "error"):
            print("    解析失败"); sys.exit(1)
        if elapsed > 300:
            print("    超时"); sys.exit(1)
        time.sleep(5)

    # ── 3. 分页取结果 ─────────────────────────────────────────────────
    print(f"\n[3] 分页取结果 total_layouts={total_layouts}")
    all_parts: list[str] = []
    fetched = 0
    fetch_count = max(total_layouts, 1)

    while fetched < fetch_count:
        r_req = dm.GetDocParserResultRequest(
            id=task_id,
            layout_num=fetched,
            layout_step_size=_PAGE_SIZE,
        )
        r_resp = client.get_doc_parser_result(r_req)
        body = r_resp.body

        print(f"    layout_num={fetched}  code={body.code}  data_type={type(body.data).__name__}")

        data = body.data or {}
        if isinstance(data, dict):
            print(f"    data keys: {list(data.keys())}")
            layouts = data.get("layouts") or []
            print(f"    layouts count: {len(layouts)}")
            if layouts:
                print(f"    first layout keys: {list(layouts[0].keys())}")
                first_text = (
                    layouts[0].get("markdownText")
                    or layouts[0].get("text")
                    or ""
                )
                print(f"    first layout text preview: {first_text[:120]!r}")

            # 提取文本
            top_md = data.get("markdown") or data.get("markdownText") or ""
            if top_md.strip():
                all_parts.append(top_md.strip())
                returned_count = 1
            else:
                page_parts = []
                for layout in layouts:
                    t = layout.get("markdownText") or layout.get("text") or ""
                    if t.strip():
                        page_parts.append(t.strip())
                all_parts.extend(page_parts)
                returned_count = len(layouts)
        else:
            returned_count = 0

        fetched += _PAGE_SIZE
        if returned_count < _PAGE_SIZE:
            break

    print(f"\n[4] 汇总")
    print(f"    总 parts 数: {len(all_parts)}")
    full_text = "\n\n".join(all_parts)
    print(f"    总字符数: {len(full_text)}")
    print(f"    前 300 字符预览:\n{full_text[:300]}")

    out = Path("/tmp/docmind_text.txt")
    out.write_text(full_text, encoding="utf-8")
    print(f"\n    完整文本已保存到 {out}")


if __name__ == "__main__":
    main()
