# 多智能体系统架构详解

本文档覆盖本项目 LangGraph 多 Agent 系统的完整设计，包括拓扑结构、状态流转、节点内部机制、工具系统、流式输出集成及关键设计取舍。

---

## 1. 整体拓扑

```
用户请求（HTTP SSE）
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│                      LangGraph 图                        │
│                                                         │
│   START ──► PrimaryRouter ◄──────────────────────────┐  │
│                  │                                   │  │
│         ┌────────┴─────────────┐                     │  │
│         │                     │                     │  │
│    route("CS")          route("Math")   FINISH       │  │
│         │                     │           │          │  │
│         ▼                     ▼           ▼          │  │
│   CS_Researcher         Math_Analyst    END          │  │
│         │                     │                     │  │
│         └──────────┬──────────┘                     │  │
│                    │ (完成后回来)                    │  │
│                    └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

三个节点，两条回边，一个共享状态。每次用户消息最多完成一次"路由→专家→返回→结束"的循环，`recursion_limit=15` 防止意外死循环。

---

## 2. 共享状态（AgentState）

```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_node: NotRequired[str]
    sender:    NotRequired[str]
```

### messages — 累加语义

`operator.add` 是 LangGraph 的 reducer 声明。每个节点返回的 `messages` 列表不会替换旧值，而是**追加**到全局 `messages` 末尾。这意味着：

- 所有节点共享完整的对话历史
- CS_Researcher 能看到 PrimaryRouter 的推理过程
- PrimaryRouter 返回时能看到专家给出的完整回答

消息类型按时间顺序叠加：

```
[HumanMessage]                   ← 用户输入
[AIMessage(tool_calls)]          ← PrimaryRouter 调路由工具
[ToolMessage]                    ← 路由工具假结果
[AIMessage(tool_calls)]          ← CS_Researcher 调 search_knowledge_base
[ToolMessage]                    ← 知识库检索结果
[AIMessage]                      ← CS_Researcher 最终回答
```

### next_node — 路由信号

PrimaryRouter 节点通过写 `next_node` 告诉图引擎下一跳去哪里。条件边函数读这个值：

```python
def route_primary(state: AgentState) -> Literal["CS_Researcher", "Math_Analyst", "__end__"]:
    nxt = state.get("next_node", "FINISH")
    if nxt == "CS_Researcher": return "CS_Researcher"
    if nxt == "Math_Analyst":  return "Math_Analyst"
    return "__end__"
```

### sender — 完成标记

专家节点完成后把自己的名字写入 `sender`。PrimaryRouter 回来时检测到这个值，直接 FINISH，不重复推理：

```python
if state.get("sender") in {"CS_Researcher", "Math_Analyst"}:
    return {"next_node": "FINISH", "sender": "PrimaryRouter"}
```

---

## 3. PrimaryRouter 节点

**模型**：deepseek-r1（带 `<think>` 推理过程）  
**挂载工具**：`web_search`、`route_to_specialist`（虚拟工具）

### 3.1 为什么用虚拟工具而不是条件边直接路由

PrimaryRouter 需要同时具备两种能力：
- 调 `web_search` 搜索后直接回答
- 发现超出能力时路由给专家

这两种能力无法用"结构化输出"同时满足——结构化输出和工具调用是互斥的 LLM 调用模式。虚拟工具方案让 LLM 在**同一套工具调用接口**下表达两种意图，不需要切换模式。

### 3.2 route_to_specialist 的设计

```python
route_tool = StructuredTool(
    name="route_to_specialist",
    func=lambda specialist, reason="": f"routing:{specialist}",  # 从不真正执行
)
```

这个工具只是一个意图声明接口。节点代码检测到 LLM 调用它时立刻截断循环，不走 ToolNode：

```python
route_calls = [tc for tc in response.tool_calls if tc["name"] == "route_to_specialist"]
if route_calls:
    route_target = route_calls[0]["args"].get("specialist")
    # 补假 ToolMessage：LangGraph 要求每个 tool_call_id 有对应的 ToolMessage
    for rc in route_calls:
        worker_msgs.append(ToolMessage(
            content=f"已路由至 {route_target}。",
            tool_call_id=rc["id"],
        ))
    break   # 截断，不执行
```

### 3.3 完整 ReAct 循环

```
┌──────────────────────────────────────────────────────────────┐
│ PrimaryRouter 内部 while 循环                                 │
│                                                              │
│  ┌─► [Reason] LLM 推理（可能有 <think> 段）                  │
│  │       │                                                   │
│  │   有 tool_calls？                                         │
│  │       │                                                   │
│  │   ┌───┴──────────────────────────┐                        │
│  │   │                             │                        │
│  │  route_to_specialist        web_search                   │
│  │   │                             │                        │
│  │  截断，break              [Act] 真正执行工具              │
│  │   │                             │                        │
│  │  写 next_node               拿到搜索结果                  │
│  │                               └─► 回到 Reason ──────────┘│
│  │                                                          │
│  └── 无 tool_calls → 直接文本回答 → break，next_node=FINISH  │
└──────────────────────────────────────────────────────────────┘
```

### 3.4 deepseek-r1 兼容处理

deepseek-r1 不支持原生 function calling，工具调用以 JSON markdown 块输出：

```
```json
[{"name": "route_to_specialist", "arguments": {"specialist": "CS_Researcher"}}]
```
```

`_heal_tool_calls` 检测并解析这种格式，注入标准 `tool_calls` 字段：

```python
def _heal_tool_calls(response: AIMessage) -> AIMessage:
    if response.tool_calls:          # 已有标准格式，跳过
        return response
    match = _JSON_BLOCK_RE.search(str(response.content))
    if not match:
        return response
    # 解析 JSON，构造 tool_calls 列表，注入 response
    ...
```

`_strip_think` 把 `<think>...</think>` 从消息内容中剥除，避免思考过程污染消息历史：

```python
def _strip_think(response: AIMessage) -> AIMessage:
    if "<think>" in str(response.content):
        clean = _THINK_RE.sub("", response.content).strip()
        return response.model_copy(update={"content": clean})
    return response
```

---

## 4. CS_Researcher / Math_Analyst 节点

两者共用 `_make_worker_node` 工厂，结构完全相同，只有系统提示和挂载工具不同。

**模型**：qwen-plus（不带思考，执行效率优先）

| 节点 | 挂载工具 |
|---|---|
| CS_Researcher | `search_knowledge_base`、`web_search` |
| Math_Analyst | `execute_python_code` |

### 4.1 标准 ReAct 循环

```
┌──────────────────────────────────────────────────────────────┐
│ Worker 内部 while 循环                                        │
│                                                              │
│  ┌─► [Reason] LLM 看完整历史 + 系统提示，决定下一步          │
│  │       │                                                   │
│  │   有 tool_calls？                                         │
│  │       │ 是                        │ 否                    │
│  │       ▼                           ▼                       │
│  │  [Act] ToolNode 执行         输出最终回答 → break         │
│  │       │                                                   │
│  │  拿到 ToolMessage                                         │
│  └───────┘ 追加到 worker_msgs，继续循环                      │
│                                                              │
│  return {"messages": worker_msgs, "sender": role}            │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 CS_Researcher 典型调用序列

```
用户：请介绍 RAG 方法的核心思路

[Reason] 判断需要检索 → tool_call: search_knowledge_base("RAG 核心思路")
[Act]    向量检索 + 关键词检索 + RRF 融合 + Cross-Encoder 重排 → 返回 5 个 chunk
[Reason] 知识库有结果，内容充分 → 直接输出结构化回答（引用来源文件名）
→ break
```

若知识库无结果：

```
[Reason] → tool_call: search_knowledge_base("RAG")
[Act]    → 返回空
[Reason] → 知识库无结果，改为 tool_call: web_search("RAG retrieval augmented generation")
[Act]    → 返回网页摘要
[Reason] → 内容足够 → 输出回答，注明来自网络
→ break
```

### 4.3 Math_Analyst 典型调用序列

```
用户：画一个 sin(x) 在 0~2π 的图

[Reason] 需要绘图 → tool_call: execute_python_code("""
import numpy as np
import matplotlib.pyplot as plt
x = np.linspace(0, 2*np.pi, 300)
plt.plot(x, np.sin(x))
plt.title('sin(x)')
plt.show()
""")
[Act]    沙箱执行代码 → 返回图片 URL + 执行输出
[Reason] 代码成功执行 → 输出解释文字
→ break
```

---

## 5. 工具系统

### 5.1 工具注册机制

全局 `registry` 维护工具的 schema（JSON Function Calling 格式）和 handler 映射：

```
registry
├── schemas: [{"type": "function", "function": {...}}, ...]
└── handlers: {"web_search": fn, "execute_python_code": fn, ...}
```

per-request 的额外工具（如 RAG 工具）通过 `_MergedRegistry` 合并，不修改全局注册表：

```python
class _MergedRegistry:
    def __init__(self, schemas: list[dict], handlers: dict):
        self._schemas = schemas    # 全局 + 额外，额外优先
        self._handlers = handlers
```

### 5.2 工具转换为 LangChain StructuredTool

图中的工具需要是 LangChain `StructuredTool` 格式，`_registry_to_lc_tools` 做这个转换：

```
JSON Schema（"type": "string", "integer"...）
    → Pydantic 动态模型（args_schema）
    → StructuredTool（name, description, args_schema, func, coroutine）
```

同步和异步版本都会生成（`func` + `coroutine`），ToolNode 会自动选择合适的版本。

### 5.3 各工具功能

| 工具 | 节点 | 实现 |
|---|---|---|
| `web_search` | PrimaryRouter、CS_Researcher | 博查 API，网页搜索 |
| `route_to_specialist` | PrimaryRouter | 虚拟工具，仅用于路由信号 |
| `search_knowledge_base` | CS_Researcher | 向量+关键词混合检索→Cross-Encoder重排 |
| `execute_python_code` | Math_Analyst | Python 沙箱，支持 matplotlib 图表 |

---

## 6. RAG 工具的 per-request 注入

RAG 工具需要绑定当前用户的 `user_id`，不能是全局单例。每次请求时动态生成：

```python
# chat.py
if user_has_knowledge_bases:
    rag_handler = make_rag_handler(user_id=current_user.id)
    extra_schemas = [KB_RAG_SEARCH_TOOL_SCHEMA]
    extra_handlers = {"search_knowledge_base": rag_handler}
    graph = get_agent_graph(extra_schemas, extra_handlers)
else:
    graph = get_agent_graph()   # 返回缓存图，无 RAG 工具
```

有 RAG 工具时每次重建图（不缓存），无 RAG 工具时复用全局缓存图。

RAG handler 的跨线程调用：ToolNode 在 `asyncio.to_thread` 线程中执行同步 handler，但 RAG 需要 async DB 操作，通过 `run_coroutine_threadsafe` 将协程提交回主事件循环：

```python
future = asyncio.run_coroutine_threadsafe(_run(), main_loop)
results = future.result(timeout=30)
```

---

## 7. 流式输出与 SSE 集成

LangGraph 的 `astream_events(version="v2")` 产生细粒度事件，chat.py 把它们翻译成前端 SSE。

### 7.1 事件类型处理

| LangGraph 事件 | 含义 | 处理方式 |
|---|---|---|
| `on_chat_model_stream` | LLM 流式输出块 | 分发到缓冲或直接 yield |
| `on_chat_model_end` | 一轮 LLM 结束 | flush 字符缓冲区 |
| `on_chain_end(PrimaryRouter)` | 路由节点完成 | 决定冲刷或丢弃 SSE 缓冲 |
| `on_tool_start` | 工具开始执行 | yield `tool_start` 事件 |
| `on_tool_end` | 工具执行完毕 | yield `tool_end` 事件 |

### 7.2 PrimaryRouter 的双缓冲设计

PrimaryRouter 的输出有两种命运：路由时丢弃，FINISH 时推送。因此设计了 SSE 缓冲区：

```
_pr_sse     : SSE 字符串列表（路由 JSON 等正文内容）
_pr_content : 纯文本列表（用于数据库存储）
_pr_thinking: 思考内容列表（已实时推送，此处备份用于 DB 存储）
```

思考内容（`reasoning_content`）**不进缓冲，直接 yield**：

```python
if is_router:
    _pr_thinking.append(rc)
    yield sse          # 思考实时推送，不管路由还是 FINISH 都让用户看到
else:
    _pr_sse.append(sse)   # 正文进缓冲，等待路由决策
    _pr_content.append(text)
```

`on_chain_end(PrimaryRouter)` 时的决策：

```python
if next_node == "FINISH" and _pr_sse:
    # 路由器直接回答：把缓冲的正文 SSE 全部推送给前端
    full_content_parts.extend(_pr_content)
    for sse in _pr_sse:
        yield sse
# 路由到专家：丢弃缓冲（路由 JSON 不该给用户看）
_pr_sse.clear()
_pr_content.clear()
_pr_thinking.clear()
```

### 7.3 这个设计防止了什么 Bug

不做缓冲的早期版本中，PrimaryRouter 的路由 JSON（`route_to_specialist` 工具调用的 JSON 文本）会直接 yield 给前端，表现为前端看到一段奇怪的 JSON 文字作为"回复"。这段 JSON 随后被保存进数据库，下轮对话带入上下文，路由器看到自己的 JSON 输出当作历史消息，产生重复路由，形成伪死循环。缓冲设计截断了这条路径。

---

## 8. 模型分工

| 节点 | 模型 | 原因 |
|---|---|---|
| PrimaryRouter | deepseek-r1 | 意图理解需要推理能力，`<think>` 过程有助于准确路由 |
| CS_Researcher | qwen-plus | 工具调用执行任务，推理过程不暴露，效率优先 |
| Math_Analyst | qwen-plus | 同上，代码生成稳定性优先 |

deepseek-r1 不支持 native function calling，由 `_heal_tool_calls` 补丁解决。  
qwen-plus 支持 native function calling，无需补丁。

---

## 9. 图的生命周期

```python
def get_agent_graph(extra_schemas=None, extra_handlers=None):
    if extra_schemas:
        return _build_graph(extra_schemas, extra_handlers)  # 每次重建（有 RAG 工具）
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = _build_graph()                    # 首次构建后缓存
    return _graph_instance
```

无 RAG 工具的图是无状态的（所有状态在 `AgentState` 里，不在图对象里），全局缓存安全。有 RAG 工具时每次请求都需要绑定不同 `user_id`，不能缓存。

---

## 10. 数据流全景（一次完整请求）

```
前端发送消息
    │
    ▼
chat.py 构建 lc_msgs（历史消息转 LangChain 格式）
    │
    ▼
get_agent_graph() → 获取/构建图
    │
    ▼
graph.astream_events({"messages": lc_msgs}, recursion_limit=15)
    │
    ├── on_chat_model_stream (PrimaryRouter thinking) → yield thinking_chunk SSE
    ├── on_chat_model_stream (PrimaryRouter content)  → 进 _pr_sse 缓冲
    ├── on_chain_end(PrimaryRouter)
    │       ├── next_node=CS_Researcher → 丢弃缓冲，图跳转
    │       └── next_node=FINISH       → flush 缓冲，yield 给前端
    │
    ├── on_tool_start(search_knowledge_base) → yield tool_start SSE
    ├── on_tool_end(search_knowledge_base)   → yield tool_end SSE
    │
    ├── on_chat_model_stream (CS_Researcher) → yield chunk SSE（实时）
    └── on_chain_end(CS_Researcher)
            │
            ▼
        PrimaryRouter 检测 sender → FINISH → END
            │
            ▼
    保存 AI 消息到数据库
    yield done SSE
    关闭 SSE 流
```
