# Agent 对话系统 — 全链路架构文档

## 一、架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERACTION                        │
└────────┬────────────────────────────────────────────────────────┘
         │ HTTP / SSE
┌────────▼────────────────────────────────────────────────────────┐
│  Frontend  React 18 + TypeScript + Zustand + TanStack Query     │
│  Vite Dev Server  :5173  ──  Proxy /api → :8000                │
└────────┬────────────────────────────────────────────────────────┘
         │ REST / SSE
┌────────▼────────────────────────────────────────────────────────┐
│  Backend  FastAPI (async)  :8000                                │
│  ├── api/v1/  路由层                                            │
│  ├── services/  业务逻辑层                                      │
│  ├── agents/tools/  工具注册 + 执行沙箱                         │
│  └── llm/  DashScope 客户端 + Token 管理                        │
└───┬──────────────────────────────┬───────────────────────────────┘
    │ asyncpg                      │ HTTP
┌───▼──────────┐        ┌──────────▼────────────────────────────┐
│ PostgreSQL   │        │  外部服务                              │
│ :5432        │        │  ├─ DashScope (Qwen-turbo) API        │
│ messages     │        │  ├─ 博查网络搜索 API                  │
│ conversations│        │  └─ Python 沙箱 (/tmp/agent_workspace)│
│ users / files│        └────────────────────────────────────────┘
└──────────────┘
┌──────────────┐
│ Redis :6379  │  (会话缓存 / Celery Broker 预留)
└──────────────┘
```

**技术栈一览**

| 层 | 技术 |
|---|---|
| 前端框架 | React 18 + TypeScript + Vite |
| 前端状态 | Zustand（持久化 auth）+ TanStack Query（服务端缓存）|
| 前端 HTTP | Axios（REST）+ 原生 fetch（SSE）|
| UI 组件 | shadcn/ui + Tailwind CSS |
| 后端框架 | FastAPI（async）|
| ORM | SQLAlchemy 2.x async + asyncpg |
| 迁移 | Alembic |
| LLM 接入 | OpenAI 兼容客户端 → 阿里云 DashScope |
| 工具执行 | 博查搜索 API + subprocess Python 沙箱 |
| 基础设施 | Docker Compose（PostgreSQL 16 + Redis 7）|

---

## 二、前端架构

### 2.1 组件层次

```
App（路由容器）
├── /login   → LoginPage
├── /register → RegisterPage
└── PrivateRoute（JWT 守卫）
    └── Layout
        ├── ConversationSidebar（左侧：对话列表）
        └── Outlet（主区域）
            ├── /          → DashboardPage（欢迎屏）
            └── /c/:id     → ConversationPage
                ├── ConversationHeader（标题 + 树视图开关）
                ├── MessageBubble[]（消息气泡，含 Markdown 渲染）
                ├── FileChip[]（附件标签）
                └── ConversationTree（右侧：SVG 树可视化）
```

### 2.2 状态管理

**authStore.ts（Zustand + LocalStorage 持久化）**

```typescript
{
  token: string | null           // JWT Bearer Token
  user: AuthUser | null
  setAuth(token, user): void     // 登录写入
  clearAuth(): void              // 401 / 退出清空
}
```

**conversationStore.ts（Zustand 内存状态）**

```typescript
{
  activeId: string | null            // 当前对话 ID
  activeNodeId: string | null        // 对话树中选中节点
  isGenerating: boolean              // LLM 生成进行中
  abortController: AbortController   // 用于用户停止流
  startGenerating(ctrl): void
  stopGenerating(): void             // 调用 ctrl.abort()
}
```

### 2.3 API 客户端层（src/api/）

**client.ts — Axios 实例 + 拦截器**

- 请求拦截：自动附加 `Authorization: Bearer {token}`
- 响应拦截：401 时调用 `clearAuth()` 踢出登录

**各模块接口**

```typescript
// auth.ts
authApi.register(email, password, full_name) → POST /auth/register
authApi.login(email, password)               → POST /auth/login
authApi.me()                                 → GET  /auth/me

// conversations.ts
conversationsApi.list(limit)                 → GET  /conversations?limit=50
conversationsApi.create(title)               → POST /conversations
conversationsApi.get(id)                     → GET  /conversations/{id}
conversationsApi.update(id, title)           → PATCH /conversations/{id}
conversationsApi.delete(id)                  → DELETE /conversations/{id}
conversationsApi.getMessages(id, nodeId?)    → GET  /conversations/{id}/messages
conversationsApi.getTree(id)                 → GET  /conversations/{id}/tree

// files.ts
filesApi.upload(convId, file)                → POST /conversations/{id}/files
filesApi.list(convId)                        → GET  /conversations/{id}/files
filesApi.delete(convId, fileId)              → DELETE /conversations/{id}/files/{fid}
```

### 2.4 SSE 流式接收（ConversationPage.tsx）

前端不使用 EventSource，改用 `fetch + ReadableStream` 以支持 POST + AbortController：

```typescript
const response = await fetch(`/api/v1/conversations/${id}/chat`, {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ content, parent_id: activeNodeId, file_ids }),
  signal: abortController.signal
})

const reader = response.body.getReader()
let buffer = ''

while (true) {
  const { done, value } = await reader.read()
  if (done) break
  buffer += decoder.decode(value, { stream: true })
  const parts = buffer.split('\n\n')
  buffer = parts.pop() ?? ''

  for (const part of parts) {
    const ev = JSON.parse(part.replace(/^data: /, ''))
    // 按 ev.type 分支处理（见下节）
  }
}
```

**SSE 事件类型**

| `ev.type` | 触发时机 | 前端行为 |
|---|---|---|
| `chunk` | LLM 返回文本片段 | 追加到占位符 assistant 消息 |
| `tool_start` | 工具调用开始 | 显示工具 badge（含工具名 + 参数） |
| `done` | 流结束 | 替换临时 ID、更新 Token 统计、刷新对话树 |
| `error` | 后端异常 | 在消息气泡中显示错误提示 |

用户点击停止 → `abortController.abort()` → 前端 catch `AbortError` → 保留已有内容，`streaming: false`

### 2.5 对话树可视化（ConversationTree.tsx）

- 数据：平铺 TreeNode[]（id, parent_id, role, summary）→ 递归构建树
- 布局：自底向上计算子树宽度（NW=90px, 水平间距 26px），Top-down 分配坐标
- 渲染：SVG canvas，支持鼠标拖拽 pan
- 节点配色：深度 0 红色 / 深度 1 绿色 / 深度 ≥2 黄色；当前激活节点 violet 边框
- 交互：点击节点 → `setActiveNodeId(id)` → 重新加载该分支路径

---

## 三、后端架构

### 3.1 FastAPI 路由总表

所有接口前缀 `/api/v1/`，认证接口除外。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查（DB + Redis） |
| POST | `/auth/register` | 注册（201） |
| POST | `/auth/login` | 登录，返回 JWT |
| GET | `/auth/me` | 获取当前用户 |
| GET | `/conversations` | 列出对话（limit=50） |
| POST | `/conversations` | 创建对话（201） |
| GET | `/conversations/{id}` | 获取对话详情 |
| PATCH | `/conversations/{id}` | 重命名对话 |
| DELETE | `/conversations/{id}` | 软删除（204） |
| GET | `/conversations/{id}/messages` | 获取消息路径（支持 node_id） |
| GET | `/conversations/{id}/tree` | 获取对话树（所有节点） |
| **POST** | **`/conversations/{id}/chat`** | **SSE 流式聊天（核心接口）** |
| POST | `/conversations/{id}/files` | 上传文件（201） |
| GET | `/conversations/{id}/files` | 列出文件 |
| DELETE | `/conversations/{id}/files/{fid}` | 删除文件 |

### 3.2 数据库模型

**users 表**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | uuid4 |
| email | str UNIQUE | 唯一索引 |
| hashed_password | str | bcrypt |
| full_name | str\|None | |
| is_active | bool | default True |
| created_at / updated_at | datetime | server_default + onupdate |

**conversations 表**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK→users | INDEX，CASCADE |
| title | str | default "New Conversation" |
| current_node_id | UUID FK→messages\|None | 指向当前分支最新消息 |
| created_at / updated_at | datetime | |
| deleted_at | datetime\|None | 软删除标记 |

**messages 表**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| conversation_id | UUID FK→conversations | INDEX，CASCADE |
| parent_id | UUID FK→messages\|None | 树结构链接，INDEX |
| role | str | user / assistant / system |
| content | Text | |
| summary | str\|None | 前 10 字（用于树节点标签） |
| token_count | int\|None | 本条消息 token 数 |
| context_tokens | int\|None | 仅 assistant：提示词总 token |
| created_at | datetime | |

**files 表**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| conversation_id | UUID FK→conversations | |
| message_id | UUID FK→messages\|None | 关联到用户消息（上传后写入） |
| uploader_id | UUID FK→users | |
| original_filename | str | |
| file_type | str | pdf / markdown |
| file_size | int | bytes |
| storage_path | str | 本地路径 uploads/{conv_id}/{id}_{name} |
| extracted_text | str\|None | 提取的纯文本 |
| token_estimate | int\|None | 预估 token 数 |
| created_at | datetime | |

### 3.3 Service 层

**services/user.py**
- `create_user(email, password, full_name)` — bcrypt 哈希，INSERT
- `authenticate_user(email, password)` — 验证 hash，失败返回 None

**services/conversation.py**
- `get_conversations(user_id, limit)` — 过滤 `deleted_at IS NULL`，按 `updated_at DESC`
- `soft_delete_conversation(conv)` — 设置 `deleted_at = now()`
- `set_title_by_id(conv_id, title)` — 标题自动生成后的无锁 UPDATE

**services/chat.py**
- `get_messages_path(db, conv_id, node_id)` — **递归 CTE**：从 node_id 向上追溯到根，返回有序路径
- `resolve_node_id(db, conv_id, node_id?)` — 优先用传入值，次用 `conv.current_node_id`，最后查最新消息
- `create_message(...)` — 自动填充 summary（前 10 字）
- `touch_conversation(db, conv_id, current_node_id?)` — 更新 `updated_at` 并可选推进树指针

**services/file.py**
- `_extract_pdf_text(data)` — PyMuPDF，按 Y→X 坐标排序（解决双栏论文横读问题）
- `_truncate_to_budget(text, budget)` — 二分查找截断点，保证 ≤ budget tokens
- `save_upload(upload, conv_id, user_id)` — 检查大小 → 提取文本 → 截断 → 存磁盘 → INSERT File
- `get_files_text(db, file_ids, conv_id)` — 拼接 `[Attachment: {name}]\n{text}` 注入上下文

---

## 四、LLM 层

### 4.1 DashScopeClient（llm/client.py）

所有方法通过 OpenAI 兼容客户端调用阿里云 DashScope，自动注入系统时间：

```python
def _prepend_system(messages, system?) → list[dict]:
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    content = f"当前时间：{now}\n\n{system_prompt}"
    return [{"role": "system", "content": content}, *messages]
```

**三个方法**

| 方法 | stream | tools | 用途 |
|---|---|---|---|
| `stream_chat(messages, system?)` | ✓ | ✗ | 工具结果后的第二轮回复 |
| `stream_chat_with_tools(messages, tools, system?)` | ✓ | ✓ | 第一轮请求，拦截 tool_calls |
| `chat(messages, system?, max_tokens=60)` | ✗ | ✗ | 标题自动生成（非流式） |

`stream_chat_with_tools` 累积工具调用方式：

```python
# delta.tool_calls 可能跨多个 chunk 分片到达
tool_calls_buffer: dict[int, dict] = {}   # index → 累积结构
# 流结束后整体 yield {"type": "tool_calls", "calls": [...]}
```

### 4.2 Token 管理（llm/token.py）

**`estimate_tokens(text)`** — 混合 CJK/英文估算（保守策略）
- CJK 字符：1 字符 = 1 token
- ASCII：4 字符 = 1 token

**`trim_to_budget(history, user_content, budget)`**
- 从最新消息向旧消息扫描，累积直到超出预算为止
- 返回 `(trimmed_history, was_truncated)`

**Token 预算分配**

| 场景 | 历史预算 |
|---|---|
| 无附件 | `LLM_HISTORY_BUDGET = 4000` tokens |
| 有附件 | `LLM_CONTEXT_WINDOW - LLM_RESPONSE_RESERVE = 29952` tokens |

---

## 五、工具系统

### 5.1 ToolRegistry（agents/tools/registry.py）

```python
registry.register(schema: dict, handler: Callable[..., str])
registry.get_all_tool_schemas() → list[dict]   # 传给 LLM tools 参数
registry.execute_tool(name, args) → str        # 调用 handler，捕获异常
```

启动时注册两个工具：

```python
registry.register(BOCHA_SEARCH_TOOL_SCHEMA, execute_bocha_search)
registry.register(PYTHON_SANDBOX_TOOL_SCHEMA, execute_python_code)
```

### 5.2 博查网络搜索（agents/tools/bocha.py）

```
函数签名：execute_bocha_search(query: str, count: int = 5) → str

调用：POST https://api.bochaai.com/v1/web-search
      body: {query, count, freshness, summary: true}

输出格式：
[1] 来源: {site} | 标题: {title}
摘要: {snippet}

[2] ...
```

**LLM Schema 描述**：强大的网络搜索引擎，需要最新实时信息时必须调用。

### 5.3 Python 代码沙箱（agents/tools/sandbox.py）

```
函数签名：execute_python_code(code: str) → str

执行方式：
1. 写入临时脚本 /tmp/agent_workspace/{uuid}.py
2. subprocess.run([python, script], timeout=15, capture_output=True)
3. 返回 stdout + stderr，超时或异常返回错误描述

环境：PYTHONDONTWRITEBYTECODE=1（防止 .pyc 残留）
```

**LLM Schema 描述**：在沙箱中执行 Python 代码进行计算、数据处理、统计分析，必须通过 print() 输出结果。

---

## 六、一次完整请求的数据流

以"用户发送消息，模型调用搜索工具后回复"为例：

```
1. 前端
   ├─ 输入框输入 → 点击发送
   ├─ 本地立即渲染：用户气泡 + 空白 assistant 占位符（streaming: true）
   └─ fetch POST /conversations/{id}/chat
      body: { content, parent_id, file_ids }

2. 后端 api/v1/chat.py:chat_stream()
   ├─ 验证 conv 所有权
   ├─ 递归 CTE 查询 → 当前分支的消息路径（有序历史）
   ├─ 附件处理 → 拼接文件文本
   ├─ trim_to_budget() → 截断超出预算的历史
   ├─ count_messages_tokens() → prompt_tokens
   ├─ INSERT user_msg → DB（含 token_count）
   └─ 返回 StreamingResponse(generate(), media_type="text/event-stream")

3. generate() 协程（SSE 生成器）
   │
   ├─ 第一轮 LLM 请求：llm.stream_chat_with_tools(messages, tools=[BOCHA, PYTHON])
   │   ├─ delta.content → yield SSE: {type: "chunk", content: "..."}
   │   └─ 流结束有 tool_calls → pending_tool_calls = [...]
   │
   ├─ 工具执行阶段（per tool_call）
   │   ├─ yield SSE: {type: "tool_start", name, args}
   │   └─ asyncio.to_thread(registry.execute_tool, name, args) → result
   │       ├─ execute_bocha_search → HTTP → 博查 API → 格式化摘要
   │       └─ execute_python_code → subprocess → stdout
   │
   ├─ 第二轮 LLM 请求：llm.stream_chat(messages + [asst_tool_msg] + [tool_results])
   │   └─ delta.content → yield SSE: {type: "chunk", content: "..."}
   │
   ├─ 保存 assistant 消息
   │   ├─ INSERT Message(role=assistant, content, parent_id=user_msg.id,
   │   │                  token_count, context_tokens=prompt_tokens)
   │   ├─ UPDATE Conversation(current_node_id=asst_msg.id, updated_at)
   │   └─ 首条消息：llm.chat() 生成标题 → UPDATE Conversation(title)
   │
   └─ yield SSE: {type: "done", message_id, title?, prompt_tokens, completion_tokens, context_truncated}

4. 前端 SSE 解析
   ├─ chunk     → setMessages(m.content += chunk)
   ├─ tool_start → setMessages(m.toolStatus = {name, args})  ← 动画 badge
   └─ done      → m.id = real_id, streaming = false
                  setTokenStats(...)
                  queryClient.invalidateQueries(['tree', id])
                  对话标题更新（如有）

5. 数据库最终状态
   ├─ messages: user_msg + asst_msg（parent-child 链，构成树节点）
   ├─ conversations: current_node_id = asst_msg.id, title 已更新
   └─ files: 若有附件，message_id 已关联到 user_msg
```

---

## 七、配置项速查（core/config.py）

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `LLM_MODEL` | `qwen-turbo` | DashScope 模型名 |
| `LLM_SYSTEM_PROMPT` | `You are a helpful AI assistant.` | 基础系统提示 |
| `LLM_CONTEXT_WINDOW` | `32000` | 模型总 token 窗口 |
| `LLM_HISTORY_BUDGET` | `4000` | 无文件时历史预算 |
| `LLM_RESPONSE_RESERVE` | `2048` | 保留给模型回复 |
| `FILE_TOKEN_BUDGET` | `20000` | 单文件最大 token |
| `MAX_FILE_SIZE_MB` | `50` | 上传文件大小上限 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT 有效期（24h） |
| `UPLOAD_DIR` | `uploads` | 本地文件存储目录 |
