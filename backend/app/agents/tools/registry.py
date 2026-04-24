from typing import Callable

from app.agents.tools.bocha import BOCHA_SEARCH_TOOL_SCHEMA, execute_bocha_search
from app.agents.tools.sandbox import PYTHON_SANDBOX_TOOL_SCHEMA, execute_python_code


class ToolRegistry:
    def __init__(self) -> None:
        self._schemas: list[dict] = []
        self._handlers: dict[str, Callable[..., str]] = {}

    def register(self, schema: dict, handler: Callable[..., str]) -> None:
        name: str = schema["function"]["name"]
        self._schemas.append(schema)
        self._handlers[name] = handler

    def get_all_tool_schemas(self) -> list[dict]:
        return list(self._schemas)

    def execute_tool(self, name: str, args: dict) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            return f"未知工具：{name}"
        return handler(**args)


# 全局单例 —— 在模块加载时完成注册
registry = ToolRegistry()
registry.register(BOCHA_SEARCH_TOOL_SCHEMA, execute_bocha_search)
registry.register(PYTHON_SANDBOX_TOOL_SCHEMA, execute_python_code)
