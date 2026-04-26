"""LangGraph Agent 核心图（全能网关 + 双专家模式）。

拓扑：
  START → PrimaryRouter
  PrimaryRouter --CS_Researcher--> CS_Researcher → PrimaryRouter
  PrimaryRouter --Math_Analyst---> Math_Analyst  → PrimaryRouter
  PrimaryRouter --FINISH---------> END
"""
import asyncio
import logging
from typing import Any, Literal, Optional

from langchain_core.tools import StructuredTool
from langgraph.graph import END, StateGraph
from pydantic import Field, create_model

from app.agents.state import AgentState
from app.core.config import settings

logger = logging.getLogger(__name__)

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}

# ── 工具构建辅助 ──────────────────────────────────────────────────────────────

def _build_args_schema(fn_schema: dict, tool_name: str):
    params = fn_schema.get("parameters", {})
    props: dict[str, dict] = params.get("properties", {})
    required: set[str] = set(params.get("required", []))

    fields: dict[str, Any] = {}
    for fname, fschema in props.items():
        ftype = _TYPE_MAP.get(fschema.get("type", "string"), str)
        desc = fschema.get("description", "")
        if fname in required:
            fields[fname] = (ftype, Field(..., description=desc))
        else:
            default = fschema.get("default")
            opt_type: Any = Optional[ftype] if default is None else ftype
            fields[fname] = (opt_type, Field(default=default, description=desc))

    return create_model(f"_{tool_name}_Args", **fields)


def _make_sync_fn(tool_name: str, reg) -> Any:
    def fn(**kwargs: Any) -> str:
        return reg.execute_tool(tool_name, dict(kwargs))
    fn.__name__ = tool_name
    return fn


def _make_async_fn(tool_name: str, reg) -> Any:
    async def fn(**kwargs: Any) -> str:
        return await asyncio.to_thread(reg.execute_tool, tool_name, dict(kwargs))
    fn.__name__ = tool_name
    return fn


def _registry_to_lc_tools(reg) -> list[StructuredTool]:
    tools: list[StructuredTool] = []
    for schema in reg.get_all_tool_schemas():
        fn_def = schema["function"]
        name: str = fn_def["name"]
        args_schema = _build_args_schema(fn_def, name)
        tools.append(StructuredTool(
            name=name,
            description=fn_def.get("description", ""),
            args_schema=args_schema,
            func=_make_sync_fn(name, reg),
            coroutine=_make_async_fn(name, reg),
            handle_tool_error=True,
        ))
    return tools


# ── 合并注册表视图 ─────────────────────────────────────────────────────────────

class _MergedRegistry:
    """合并全局 registry 与 per-request 额外工具（如 RAG Tool），不修改全局状态。"""

    def __init__(self, schemas: list[dict], handlers: dict) -> None:
        self._schemas = schemas
        self._handlers = handlers

    def get_all_tool_schemas(self) -> list[dict]:
        return list(self._schemas)

    def execute_tool(self, name: str, args: dict) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            return f"未知工具：{name}"
        try:
            return handler(**args)
        except TypeError as e:
            return f"工具参数错误：{e}"
        except Exception as e:
            logger.error("工具 '%s' 执行异常: %s", name, e, exc_info=True)
            return f"工具执行失败：{e}"


# ── 图构建 ────────────────────────────────────────────────────────────────────

def _build_graph(
    extra_schemas: list[dict] | None = None,
    extra_handlers: dict | None = None,
):
    from app.agents.tools.registry import registry
    from app.agents.workers import (
        make_primary_router_node,
        make_cs_researcher_node,
        make_math_analyst_node,
    )

    # 合并全局 registry 与 per-request 额外工具（额外工具优先）
    schemas = list(registry.get_all_tool_schemas())
    handlers: dict = dict(registry._handlers)
    if extra_schemas:
        extra_names = {s["function"]["name"] for s in extra_schemas}
        schemas = [s for s in schemas if s["function"]["name"] not in extra_names]
        schemas.extend(extra_schemas)
    if extra_handlers:
        handlers.update(extra_handlers)

    merged = _MergedRegistry(schemas, handlers)
    lc_tools = _registry_to_lc_tools(merged)
    logger.info("构建 Agent 图，工具数量: %d  %s", len(lc_tools), [t.name for t in lc_tools])

    primary_router = make_primary_router_node(lc_tools)
    cs_researcher  = make_cs_researcher_node(lc_tools)
    math_analyst   = make_math_analyst_node(lc_tools)

    def route_primary(state: AgentState) -> Literal["CS_Researcher", "Math_Analyst", "__end__"]:
        nxt = state.get("next_node", "FINISH")
        if nxt == "CS_Researcher":
            return "CS_Researcher"
        if nxt == "Math_Analyst":
            return "Math_Analyst"
        return "__end__"

    builder = StateGraph(AgentState)
    builder.add_node("PrimaryRouter", primary_router)
    builder.add_node("CS_Researcher", cs_researcher)
    builder.add_node("Math_Analyst",  math_analyst)
    builder.set_entry_point("PrimaryRouter")
    builder.add_conditional_edges(
        "PrimaryRouter",
        route_primary,
        {"CS_Researcher": "CS_Researcher", "Math_Analyst": "Math_Analyst", "__end__": END},
    )
    builder.add_edge("CS_Researcher", "PrimaryRouter")
    builder.add_edge("Math_Analyst",  "PrimaryRouter")

    return builder.compile()


_graph_instance = None


def get_agent_graph(
    extra_schemas: list[dict] | None = None,
    extra_handlers: dict | None = None,
):
    """获取 Agent 图。有额外工具（RAG）时每次重建，否则返回缓存图。"""
    if extra_schemas:
        return _build_graph(extra_schemas, extra_handlers)
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = _build_graph()
    return _graph_instance


def reset_agent_graph() -> None:
    global _graph_instance
    _graph_instance = None
