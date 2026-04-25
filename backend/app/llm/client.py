from datetime import datetime
from typing import AsyncGenerator

from app.core.config import settings

# 当存在文件系统类 MCP 工具时注入此授权段，防止模型以安全理由拒绝本地路径
_MCP_FS_AUTH = """\
## 工具调用授权

你运行在受信任的本地开发环境中，已获得以下授权：
- 使用 fs__ 前缀工具（fs__read_file、fs__write_file、fs__list_directory 等）访问 /Users/liuwy/ 及其所有子目录
- 当用户提供本地文件路径时，**必须直接调用相应的 fs__ 工具**，严禁以"安全原因""权限不足"或"无法访问本地文件"为由拒绝
- 若工具返回权限错误，如实将错误内容反馈给用户，并指导用户如何将该路径加入白名单"""


class DashScopeClient:
    async def stream_chat(
        self, messages: list[dict], system: str | None = None
    ) -> AsyncGenerator[str, None]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.DASHSCOPE_BASE_URL,
        )
        all_messages = _prepend_system(messages, system)
        stream = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=all_messages,
            stream=True,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content

    async def stream_chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """流式对话，支持工具调用拦截。

        每次 yield 一个 dict：
          {"type": "text",       "content": str}        — 文本块，实时推送
          {"type": "tool_calls", "calls":   list[dict]} — 流结束后，若模型要调用工具则 yield 一次
        """
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.DASHSCOPE_BASE_URL,
        )
        # 有文件系统工具时注入授权声明，防止模型误判安全限制
        base_system = system or settings.LLM_SYSTEM_PROMPT
        has_fs_tools = any(
            t.get("function", {}).get("name", "").startswith("fs__") for t in tools
        )
        effective_system = f"{base_system}\n\n{_MCP_FS_AUTH}" if has_fs_tools else base_system
        all_messages = _prepend_system(messages, effective_system)
        stream = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=all_messages,
            stream=True,
            tools=tools,
            tool_choice="auto",
        )

        # index -> {id, type, function: {name, arguments}}
        tool_calls_buffer: dict[int, dict] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta.content:
                yield {"type": "text", "content": delta.content}

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    if tc_delta.id:
                        tool_calls_buffer[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_buffer[idx]["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_buffer[idx]["function"]["arguments"] += tc_delta.function.arguments

        if tool_calls_buffer:
            calls = [tool_calls_buffer[i] for i in sorted(tool_calls_buffer.keys())]
            yield {"type": "tool_calls", "calls": calls}

    async def chat(
        self, messages: list[dict], system: str | None = None, max_tokens: int = 60
    ) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.DASHSCOPE_BASE_URL,
        )
        all_messages = _prepend_system(messages, system)
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=all_messages,
            stream=False,
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()


def _prepend_system(messages: list[dict], system: str | None) -> list[dict]:
    prompt = system or settings.LLM_SYSTEM_PROMPT
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    date_line = f"当前时间：{now}"
    content = f"{date_line}\n\n{prompt}" if prompt else date_line
    return [{"role": "system", "content": content}, *messages]


def get_llm_client() -> DashScopeClient:
    if not settings.DASHSCOPE_API_KEY:
        raise ValueError("DASHSCOPE_API_KEY is not configured")
    return DashScopeClient()
