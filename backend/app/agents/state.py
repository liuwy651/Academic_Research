import operator
from typing import Annotated, Sequence

from langchain_core.messages import BaseMessage
from typing_extensions import NotRequired, TypedDict


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_node: NotRequired[str]   # 路由目标："Researcher" | "Coder" | "FINISH"
    sender: NotRequired[str]      # 刚刚完成任务的 Agent 名（供前端追踪展示）
