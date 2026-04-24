import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

def execute_bocha_search(query: str, count: int = 5) -> str:
    """
    实际执行博查网络搜索的 Python 函数
    """
    api_key = settings.BOCHA_API_KEY
    if not api_key:
        error_msg = "搜索失败：未配置 BOCHA_API_KEY 环境变量。"
        logger.error(error_msg)
        return error_msg

    url = "https://api.bochaai.com/v1/web-search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "count": count,
        "freshness": "noLimit",
        "summary": True,
    }

    try:
        with httpx.Client(timeout=15) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        web_pages = data.get("data", {}).get("webPages", {}).get("value", [])
        if not web_pages:
            return f"博查搜索已执行，但未找到关于 '{query}' 的结果。"

        results = []
        for idx, page in enumerate(web_pages):
            title = page.get("name", "无标题")
            snippet = page.get("snippet", "无摘要")
            site_name = page.get("siteName", "未知来源")
            results.append(f"[{idx+1}] 来源: {site_name} | 标题: {title}\n摘要: {snippet}")

        return "\n\n---\n\n".join(results)

    except httpx.HTTPError as e:
        logger.error(f"博查 API 网络异常: {e}")
        return "搜索工具网络超时或请求失败。"
    except Exception as e:
        logger.error(f"解析博查数据失败: {e}")
        return "提取搜索结果时发生未知错误。"

# ==========================================
# 下面是注册给大模型看的 Tool Schema (OpenAI/通用 Function Calling 标准格式)
# ==========================================
BOCHA_SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "execute_bocha_search",
        "description": "强大的网络搜索引擎。当你需要获取最新实时信息、验证客观事实、或查找你知识库中没有的知识时，必须调用此工具。传入精准的搜索关键词。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "需要搜索的关键词。为了获得更好的结果，请提取核心概念，避免输入完整的疑问句。"
                },
                "count": {
                    "type": "integer",
                    "description": "希望获取的搜索结果数量。默认 5，建议不要超过 10 以节省上下文 Token。",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
}