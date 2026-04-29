"""Worker 节点：PrimaryRouter（网关）、CS_Researcher（文献检索）、Math_Analyst（数学分析）。"""
import json
import re
from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from app.agents.state import AgentState

_IMAGE_RE = re.compile(r'\[IMAGE_URL:[^\]]+\]')
_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL)

# ── System Prompts ────────────────────────────────────────────────────────────

_PRIMARY_ROUTER_SYSTEM = """\
你是 PrimaryRouter，用户的第一接触点，负责意图识别和智能分流。

## 重要说明

你的可用工具只有：web_search（联网搜索）和 route_to_specialist（路由给专家）。
你**没有** search_knowledge_base 工具——知识库检索由 CS_Researcher 负责，不要尝试用 web_search 替代。

## 职责

1. **直接回答**：日常闲聊、天气、新闻、常识、翻译、写作等通用问题，可调用 web_search 后直接给出完整回答，**不要提及专家或路由**。

2. **路由 → CS_Researcher**，满足以下任一条件时立即路由，不要先尝试 web_search：
   - 问题涉及特定 CS 方法、算法、模型的解释（如"XXX 是什么方法"、"XXX 如何工作"）
   - 问题涉及学术论文、研究成果、知识库文档
   - 问题中出现论文标题、专有模型名、作者信息等学术标识

3. **路由 → Math_Analyst**，满足以下任一条件时立即路由：
   - 需要编写代码求解数学公式或方程
   - 需要用代码生成数学图表或数据可视化

## 关键规则

- 天气、气候、日常信息等通用问题 → 直接回答，**绝对不路由**。
- 路由时直接调用 route_to_specialist，**不要先做 web_search**。
- route_to_specialist 只调用一次，调用后立即停止，不追加任何文字。\
"""

_CS_RESEARCHER_SYSTEM = """\
你是 CS_Researcher，资深计算机科研助理。
- **必须优先调用 search_knowledge_base** 检索用户私有知识库中的论文与文档，基于检索结果回答并注明来源文件名
- 知识库无结果或问题涉及最新动态时，调用 web_search 联网补充
- 给出严谨、有来源依据的学术解答
- 不做数学计算，不写代码\
"""

_MATH_ANALYST_SYSTEM = """\
你是 Math_Analyst，数学家与数据科学家。
- **必须使用 execute_python_code** 进行复杂数学计算或图表绘制，禁止凭直觉估算
- 代码中使用 print() 输出结果，绘图调用 plt.show() 即可
- 给出清晰的数学推导步骤和代码注释\
"""

# ── 工具名集合 ────────────────────────────────────────────────────────────────

_WEB_TOOL_NAMES = frozenset({"execute_bocha_search", "web_search"})
_CS_TOOL_NAMES = frozenset({"execute_bocha_search", "web_search", "search_knowledge_base"})


# ── 公共工具函数 ──────────────────────────────────────────────────────────────

def _clean_tool_messages(messages: list) -> list:
    """清理 ToolMessage 中的 [IMAGE_URL:...] 标记，保持发送给 LLM 的历史整洁。"""
    cleaned = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = str(msg.content)
            has_img = bool(_IMAGE_RE.search(content))
            content = _IMAGE_RE.sub("", content).strip()
            if has_img:
                content += "\n[图片已由界面自动渲染，直接分析图表内容即可]"
            cleaned.append(ToolMessage(
                content=content or "(代码执行完毕，无任何输出)",
                tool_call_id=msg.tool_call_id,
                name=getattr(msg, "name", None),
            ))
        else:
            cleaned.append(msg)
    return cleaned


def _strip_think(response: AIMessage) -> AIMessage:
    if isinstance(response.content, str) and "<think>" in response.content:
        clean = _THINK_RE.sub("", response.content).strip()
        return response.model_copy(update={"content": clean})
    return response


_JSON_BLOCK_RE = re.compile(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```')


def _heal_tool_calls(response: AIMessage) -> AIMessage:
    """Deepseek-R1 等不支持 native function calling 的模型会把工具调用输出为 JSON markdown 块。
    检测到这种情况时，提取 JSON 并注入 tool_calls，使后续 ToolNode / 路由逻辑正常工作。
    """
    if response.tool_calls:
        return response

    content = str(response.content) if response.content else ""
    match = _JSON_BLOCK_RE.search(content)
    if not match:
        return response

    try:
        calls_raw = json.loads(match.group(1))
        tool_calls = []
        for i, call in enumerate(calls_raw):
            if not isinstance(call, dict):
                continue
            # 兼容多种字段名：name/function, arguments/parameters/args
            tool_name = call.get("name") or call.get("function")
            if not tool_name:
                continue
            args = call.get("arguments") or call.get("parameters") or call.get("args") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            tool_calls.append({
                "name": tool_name,
                "args": args if isinstance(args, dict) else {},
                "id": f"synthetic_{i}_{tool_name}",
                "type": "tool_call",
            })
        if tool_calls:
            clean_content = content[:match.start()].rstrip()
            return response.model_copy(update={"content": clean_content, "tool_calls": tool_calls})
    except Exception:
        pass

    return response


# ── PrimaryRouter ─────────────────────────────────────────────────────────────

class _RouteArgs(BaseModel):
    specialist: Literal["CS_Researcher", "Math_Analyst"] = Field(
        description="CS_Researcher：计算机科研文献；Math_Analyst：复杂数学计算/图表"
    )
    reason: str = Field(default="", description="路由原因（可选）")


def make_primary_router_node(lc_tools: list[StructuredTool]):
    """PrimaryRouter：意图识别 → 直接回答（可用 web_search）或路由给专家。

    核心设计：给 LLM 挂载一个虚拟工具 route_to_specialist。
    - LLM 调用 route_to_specialist → 截断循环，设置 next_node = specialist
    - LLM 不调用 / 直接输出文本 → 视为最终回答，next_node = "FINISH"
    """
    from app.agents.thinking_chat import ChatWithThinking
    from app.core.config import settings

    web_tools = [t for t in lc_tools if t.name in _WEB_TOOL_NAMES]

    route_tool = StructuredTool(
        name="route_to_specialist",
        description=(
            "将任务路由给专家 Agent 处理。"
            "仅当问题明确超出你能力范围时调用（CS文献 → CS_Researcher；数学计算 → Math_Analyst）。"
        ),
        args_schema=_RouteArgs,
        func=lambda specialist, reason="": f"routing:{specialist}",
    )

    all_tools = web_tools + [route_tool]
    llm = ChatWithThinking(
        model=settings.AGENT_ROUTER_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        streaming=True,
    )
    llm_with_tools = llm.bind_tools(all_tools)
    web_tool_node = ToolNode(web_tools) if web_tools else None

    _SPECIALIST_NAMES = {"CS_Researcher", "Math_Analyst"}

    async def node(state: AgentState) -> dict:
        # 专家刚完成任务后返回此处：其回答已完整，直接 FINISH，不再复述
        if state.get("sender") in _SPECIALIST_NAMES:
            return {"next_node": "FINISH", "sender": "PrimaryRouter"}

        base_messages = list(state["messages"])
        worker_msgs: list = []
        route_target: str | None = None

        while True:
            full = [SystemMessage(content=_PRIMARY_ROUTER_SYSTEM)] + base_messages + worker_msgs
            cleaned = _clean_tool_messages(full)
            response = await llm_with_tools.ainvoke(cleaned)
            response = _strip_think(response)
            response = _heal_tool_calls(response)
            worker_msgs.append(response)

            if not (isinstance(response, AIMessage) and response.tool_calls):
                break  # 直接回答，next_node = FINISH

            # 路由工具优先检测：截断循环，不进入 ToolNode
            route_calls = [tc for tc in response.tool_calls if tc["name"] == "route_to_specialist"]
            if route_calls:
                route_target = route_calls[0]["args"].get("specialist")
                # 补充 ToolMessage 维持消息结构完整性（LangGraph 要求每个 tool_call 有对应结果）
                for rc in route_calls:
                    worker_msgs.append(ToolMessage(
                        content=f"已路由至 {route_target}。",
                        tool_call_id=rc["id"],
                        name="route_to_specialist",
                    ))
                break

            # 执行普通工具（web_search）
            if web_tool_node is None:
                break
            tool_result = await web_tool_node.ainvoke({"messages": base_messages + worker_msgs})
            worker_msgs.extend(tool_result["messages"])

        return {
            "messages": worker_msgs,
            "sender": "PrimaryRouter",
            "next_node": route_target or "FINISH",
        }

    node.__name__ = "PrimaryRouter"
    return node


# ── 通用专家 Worker 工厂 ──────────────────────────────────────────────────────

def _make_worker_node(role: str, system_prompt: str, tools: list[StructuredTool]):
    """创建含内部 ReAct 循环的专家 Worker 节点。"""
    from app.agents.thinking_chat import ChatWithThinking
    from app.core.config import settings

    llm = ChatWithThinking(
        model=settings.AGENT_WORKER_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        streaming=True,
    )
    llm_with_tools = llm.bind_tools(tools) if tools else llm
    tool_node = ToolNode(tools) if tools else None

    async def node(state: AgentState) -> dict:
        base_messages = list(state["messages"])
        worker_msgs: list = []

        while True:
            full = [SystemMessage(content=system_prompt)] + base_messages + worker_msgs
            cleaned = _clean_tool_messages(full)
            response = await llm_with_tools.ainvoke(cleaned)
            response = _strip_think(response)
            response = _heal_tool_calls(response)
            worker_msgs.append(response)

            if not (isinstance(response, AIMessage) and response.tool_calls):
                break
            if tool_node is None:
                break

            tool_result = await tool_node.ainvoke({"messages": base_messages + worker_msgs})
            worker_msgs.extend(tool_result["messages"])

        return {"messages": worker_msgs, "sender": role}

    node.__name__ = role
    return node


def make_cs_researcher_node(lc_tools: list[StructuredTool]):
    """CS_Researcher：文献检索专家，挂载 search_knowledge_base + web_search。"""
    tools = [t for t in lc_tools if t.name in _CS_TOOL_NAMES]
    return _make_worker_node("CS_Researcher", _CS_RESEARCHER_SYSTEM, tools)


def make_math_analyst_node(lc_tools: list[StructuredTool]):
    """Math_Analyst：数学分析专家，只挂载 execute_python_code。"""
    tools = [t for t in lc_tools if t.name == "execute_python_code"]
    return _make_worker_node("Math_Analyst", _MATH_ANALYST_SYSTEM, tools)
