"""ChatOpenAI 子类，从流式 chunk 中提取 reasoning_content（DeepSeek-R1 / Qwen3 等思维模型）。

LangChain 的 _convert_delta_to_message_chunk 只处理标准 OpenAI 字段，
DashScope 返回的 reasoning_content 存在 delta.model_extra 中，model_dump() 后
出现在 delta dict 里但被忽略。本类 override _convert_chunk_to_generation_chunk，
把 reasoning_content 注入 AIMessageChunk.additional_kwargs，
chat.py 的流式循环即可通过 chunk.additional_kwargs["reasoning_content"] 读取。
"""
from typing import Any

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI


class ChatWithThinking(ChatOpenAI):
    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        gen_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen_chunk is None:
            return None

        choices = chunk.get("choices") or []
        if choices and isinstance(gen_chunk.message, AIMessageChunk):
            rc: str = choices[0].get("delta", {}).get("reasoning_content") or ""
            if rc:
                gen_chunk.message.additional_kwargs["reasoning_content"] = rc

        return gen_chunk
