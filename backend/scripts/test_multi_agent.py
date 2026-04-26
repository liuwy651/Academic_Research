"""快速验证多 Agent Supervisor 图是否正常工作。"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from langchain_core.messages import HumanMessage, SystemMessage


async def test_routing(label: str, user_msg: str):
    """发送一条消息，打印路由决策和最终回复摘要。"""
    from app.agents.graph import get_agent_graph, reset_agent_graph

    reset_agent_graph()
    graph = get_agent_graph()

    messages = [
        SystemMessage(content="当前时间：2026年04月26日"),
        HumanMessage(content=user_msg),
    ]

    print(f"\n{'='*60}")
    print(f"[{label}] 用户: {user_msg}")
    print("-" * 60)

    sender_trace = []
    final_content = ""

    async for event in graph.astream_events(
        {"messages": messages},
        version="v2",
        config={"recursion_limit": 15},
    ):
        etype = event["event"]
        ename = event.get("name", "")
        data = event.get("data", {})

        if etype == "on_chain_start" and ename in ("Supervisor", "Researcher", "Coder"):
            print(f"  >> 节点启动: {ename}")

        if etype == "on_chain_end" and ename in ("Supervisor", "Researcher", "Coder"):
            output = data.get("output", {})
            if isinstance(output, dict):
                next_node = output.get("next_node", "")
                sender = output.get("sender", "")
                if next_node:
                    print(f"  << Supervisor 路由 → {next_node}")
                if sender and sender != "Supervisor":
                    sender_trace.append(sender)

        if etype == "on_tool_start":
            print(f"  🔧 工具调用: {ename}  args={data.get('input', {})}")

        if etype == "on_tool_end":
            output = data.get("output")
            text = output.content if hasattr(output, "content") else str(output)
            print(f"  ✅ 工具完成: {ename}  result={text[:80]}...")

        if etype == "on_chat_model_stream":
            chunk = data.get("chunk")
            if chunk and chunk.content:
                content = chunk.content if isinstance(chunk.content, str) else ""
                final_content += content

    print(f"\n  Workers 执行顺序: {sender_trace}")
    preview = final_content.replace("\n", " ")[:200]
    print(f"  最终回复预览: {preview}")
    print(f"{'='*60}")


async def main():
    print("=== 多 Agent Supervisor 验证 ===\n")

    # Case 1: 纯检索 → 应路由到 Researcher
    await test_routing(
        "检索任务",
        "帮我搜索一下 LangGraph 多 Agent 模式的核心概念，用中文总结。"
    )

    # Case 2: 纯代码 → 应路由到 Coder
    await test_routing(
        "代码任务",
        "用 Python 计算 1 到 100 的平方和，并打印结果。"
    )


if __name__ == "__main__":
    asyncio.run(main())
