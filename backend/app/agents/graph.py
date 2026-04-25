"""LangGraph Agent 核心图（S6）。

拓扑：START → agent ──tool_calls?→ tools → agent (loop) → END
                    └──no tools──────────────────────────→ END
"""
import asyncio
import logging
import re
from typing import Any, Literal, Optional

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import Field, create_model

from app.agents.state import AgentState
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────────────────────────

MCP_FS_AUTH = """\
## 工具调用授权

你运行在受信任的本地开发环境中，已获得以下授权：
- 使用 fs__ 前缀工具（fs__read_file、fs__write_file、fs__list_directory 等）访问 \
/Users/liuwy/ 及其所有子目录
- 当用户提供本地文件路径时，**必须直接调用相应的 fs__ 工具**，严禁以"安全原因"\
"权限不足"或"无法访问本地文件"为由拒绝
- 若工具返回权限错误，如实将错误内容反馈给用户，并指导用户如何将该路径加入白名单"""

_MCP_PERM_KWS = ("EACCES", "permission", "Permission", "denied", "Denied", "not allowed")
_MCP_PERM_NOTE = (
    "\n\n[权限引导] 该路径未在 MCP filesystem server 的授权目录中。"
    "请告知用户：可在后端配置 MCP_FILESYSTEM_PATHS 环境变量（逗号分隔）添加目标路径，"
    "然后重启服务使配置生效。"
)

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
    """将 OpenAI function parameters JSON Schema 转为 Pydantic 模型。"""
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
            # 非必填且无默认值 → Optional[T] = None
            opt_type: Any = Optional[ftype] if default is None else ftype
            fields[fname] = (opt_type, Field(default=default, description=desc))

    return create_model(f"_{tool_name}_Args", **fields)


def _make_sync_fn(tool_name: str, reg) -> Any:
    def fn(**kwargs: Any) -> str:
        result: str = reg.execute_tool(tool_name, dict(kwargs))
        if result.startswith("[MCP 工具错误]") and any(kw in result for kw in _MCP_PERM_KWS):
            result += _MCP_PERM_NOTE
        return result
    fn.__name__ = tool_name
    return fn


def _make_async_fn(tool_name: str, reg) -> Any:
    async def fn(**kwargs: Any) -> str:
        result: str = await asyncio.to_thread(reg.execute_tool, tool_name, dict(kwargs))
        if result.startswith("[MCP 工具错误]") and any(kw in result for kw in _MCP_PERM_KWS):
            result += _MCP_PERM_NOTE
        return result
    fn.__name__ = tool_name
    return fn


def _registry_to_lc_tools(reg) -> list[StructuredTool]:
    """将 ToolRegistry 中所有工具转换为 LangChain StructuredTool 列表。"""
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

# ── 图构建 ────────────────────────────────────────────────────────────────────

_IMAGE_RE = re.compile(r'\[IMAGE_URL:[^\]]+\]')
_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL)


def _build_graph():
    from app.agents.tools.registry import registry

    lc_tools = _registry_to_lc_tools(registry)
    logger.info("构建 Agent 图，工具数量: %d", len(lc_tools))

    from app.agents.thinking_chat import ChatWithThinking

    llm = ChatWithThinking(
        model=settings.LLM_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        streaming=True,
    )
    llm_with_tools = llm.bind_tools(lc_tools)
    tool_node = ToolNode(lc_tools)

    async def agent_node(state: AgentState) -> dict:
        """调用 LLM，预处理 ToolMessage 以清除图片标记。"""
        messages = list(state["messages"])

        # 清理 ToolMessage 中的 [IMAGE_URL:...] 标记，向 LLM 发送整洁的工具结果
        cleaned = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                content = str(msg.content)
                has_img = bool(_IMAGE_RE.search(content))
                content = _IMAGE_RE.sub("", content).strip()
                if has_img:
                    content += (
                        "\n[图片已由界面自动渲染，请勿在回复中描述图片的保存或展示过程，"
                        "直接分析图表内容即可]"
                    )
                cleaned.append(ToolMessage(
                    content=content or "(代码执行完毕，无任何输出)",
                    tool_call_id=msg.tool_call_id,
                    name=getattr(msg, "name", None),
                ))
            else:
                cleaned.append(msg)

        response = await llm_with_tools.ainvoke(cleaned)

        # 剥离 <think> 块，避免思考内容污染后续 LLM 调用的历史
        if isinstance(response.content, str) and "<think>" in response.content:
            clean_content = _THINK_RE.sub("", response.content).strip()
            response = response.model_copy(update={"content": clean_content})

        return {"messages": [response]}

    def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return "__end__"

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.set_entry_point("agent")
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "agent")

    return builder.compile()


_graph_instance = None


def get_agent_graph():
    """获取（懒构建+缓存）Agent 图实例。应在所有工具注册完毕后首次调用。"""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = _build_graph()
    return _graph_instance


def reset_agent_graph() -> None:
    """强制重建图（用于测试或工具注册变更后刷新）。"""
    global _graph_instance
    _graph_instance = None
