# Academic Research 的Agent多轮对话系统

一个支持树状多轮对话、工具调用、多 Agent 协作、知识库检索的全栈 AI 对话平台。

## 功能特性

- **多轮对话** — 完整上下文记忆，支持树状分支对话
- **多 Agent 协作** — PrimaryRouter + 专业 Worker Agent（CS 研究、数学分析）
- **工具调用** — Function Calling 集成，支持代码执行、数学计算等工具
- **知识库 / RAG** — 文档上传解析（PDF）、向量化存储（Milvus）、检索增强生成
- **流式输出** — SSE 实时推流，支持 Chain-of-Thought 过程展示
- **用户认证** — JWT 登录注册，路由守卫

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI · SQLAlchemy 2.x (async) · Alembic · LangGraph |
| 前端 | React 19 · TypeScript · Vite · Tailwind CSS · Zustand |
| 数据库 | PostgreSQL 16 · Redis 7 |
| 向量库 | Milvus 2.4 (standalone) |
| LLM | 阿里云 DashScope（Qwen / DeepSeek-R1） |
| 文档解析 | 阿里云 DocMind |
| 包管理 | uv (后端) · npm (前端) |

## 目录结构

```
academic_research/
├── docker-compose.yml      # 基础服务（PG / Redis / Milvus）
├── .env.example            # 环境变量模板
├── backend/
│   ├── pyproject.toml
│   ├── alembic/            # 数据库迁移
│   └── app/
│       ├── main.py
│       ├── core/           # 配置、DB 连接、安全
│       ├── models/         # SQLAlchemy ORM
│       ├── schemas/        # Pydantic 模型
│       ├── api/            # 路由层
│       ├── services/       # 业务逻辑
│       ├── agents/         # Agent 核心（LangGraph）
│       └── llm/            # LLM 统一客户端
└── frontend/
    └── src/
        ├── pages/
        ├── components/
        ├── store/          # Zustand 状态
        └── api/            # API 调用层
```

## 快速启动

### 前置依赖

- Docker & Docker Compose
- Python 3.11+（推荐用 [uv](https://docs.astral.sh/uv/) 管理）
- Node.js 20+
- 阿里云 DashScope API Key（LLM 调用）

### 1. 克隆 & 配置环境变量

```bash
git clone <repo-url>
cd academic_research

cp .env.example .env
```

编辑 `.env`，至少填写：

```env
DASHSCOPE_API_KEY=sk-xxxx          # 必填：阿里云 DashScope
DOCMIND_ACCESS_KEY_ID=             # 可选：PDF 解析（不填则跳过文档功能）
DOCMIND_ACCESS_KEY_SECRET=
```

其他字段保持默认即可用于本地开发。

### 2. 启动基础服务（Docker）

```bash
docker compose up -d
```

等待所有服务 healthy（约 60s，Milvus 启动较慢）：

```bash
docker compose ps
```

### 3. 启动后端

```bash
cd backend

# 安装依赖
uv sync

# 运行数据库迁移
uv run alembic upgrade head

# 启动开发服务器
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端运行于 http://localhost:8000  
API 文档：http://localhost:8000/docs

### 4. 启动前端

```bash
cd frontend

npm install
npm run dev
```

前端运行于 http://localhost:5173

---

## 常用命令

### 后端

```bash
# 新建迁移（修改 ORM 模型后）
uv run alembic revision --autogenerate -m "your description"

# 查看迁移历史
uv run alembic history

# 回滚一步
uv run alembic downgrade -1

# 运行测试
uv run pytest
```

### Docker 服务

```bash
# 查看日志
docker compose logs -f postgres
docker compose logs -f milvus

# 停止并保留数据
docker compose stop

# 停止并清除所有数据（谨慎）
docker compose down -v
```

---

## 开发模式 vs 全容器模式

| 模式 | 说明 |
|---|---|
| **本地开发（推荐）** | 后端/前端直接运行在本机，享受热重载；PG / Redis / Milvus 跑在 Docker |
| **全容器** | `docker compose up -d`（含 `backend` 服务），适合验收或生产部署 |

全容器模式下，`docker-compose.yml` 中的 `environment` 块会自动将 `localhost` 地址覆盖为容器服务名（`postgres`、`redis`、`milvus`），无需修改 `.env`。

---

## 环境变量说明

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://agent:agent_password@localhost:5432/agent_db` | PostgreSQL 连接串 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |
| `MILVUS_HOST` | `localhost` | Milvus 主机 |
| `MILVUS_PORT` | `19530` | Milvus 端口 |
| `DASHSCOPE_API_KEY` | — | **必填**，阿里云 DashScope |
| `DOCMIND_ACCESS_KEY_ID` | — | 可选，阿里云文档解析 |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | 允许的前端来源 |
| `DEBUG` | `true` | 开启调试模式 |

---

## 当前切片进度

| 切片 | 名称 | 状态 |
|---|---|---|
| S0 | 基础骨架 | ✅ |
| S1 | 用户认证 | ✅ |
| S2 | 会话管理 | ✅ |
| S3 | 基础对话 + 流式输出 | ✅ |
| S3.5 | 树状对话 | ✅ |
| S4 | 多轮记忆 | ✅ |
| S4.5 | 文档上传 | ✅ |
| S5 | Tool 系统 | ✅ |
| S6 | Agent 核心 | ✅ |
| S7 | 多 Agent 协作 | ✅ |
| S8 | 知识库 / RAG | ✅ |
| S9 | 监控与可观测 | 🔲 |

---

## API 约定

- 路径前缀：`/api/v1/`
- 认证：`Authorization: Bearer <jwt_token>`
- 错误格式：`{"detail": "...", "code": "ERROR_CODE"}`
- 流式响应：Server-Sent Events（SSE）

## Git 规范

- 主分支：`main`
- 功能分支：`feature/s{n}-{short-desc}`
- 提交格式：`feat(s0): add docker compose setup`
