from typing import AsyncGenerator

from app.core.config import settings


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
    if prompt:
        return [{"role": "system", "content": prompt}, *messages]
    return messages


def get_llm_client() -> DashScopeClient:
    if not settings.DASHSCOPE_API_KEY:
        raise ValueError("DASHSCOPE_API_KEY is not configured")
    return DashScopeClient()
