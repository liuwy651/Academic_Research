# Agent 对话系统 — 项目总纲

## 项目目标

构建一个大型 **Agent 对话系统**，支持多轮对话、工具调用、多 Agent 协作、会话记忆管理等核心能力。

---

## 开发环境

| 项目 | 说明 |
|------|------|
| 本机 | MacBook M4（arm64） |
| 运行时 | 后端/前端直接运行在本地（非容器） |
| 基础服务 | PostgreSQL、Redis 等跑在 Docker（docker-compose） |
| 架构隔离 | 应用层本地热重载开发，数据层容器化隔离 |

---

## 技术栈

### 后端
- **框架**: FastAPI（异步优先）
- **ORM**: SQLAlchemy 2.x（async engine）
- **迁移**: Alembic
- **包管理**: uv
- **Python**: 3.11+
- **任务队列**: Celery + Redis（后期切片引入）
- **LLM 接入**: 通过统一 LLM Client 层（支持 OpenAI / Anthropic / 本地模型）

### 前端
- **框架**: React 18 + TypeScript
- **构建**: Vite
- **风格**: frontend-design
- **状态管理**: Zustand（轻量）
- **HTTP 客户端**: Axios + React Query
- **UI 组件**: shadcn/ui（Tailwind CSS 基础）

### 基础服务（Docker）
- **PostgreSQL 16**: 主数据库
- **Redis 7**: 缓存 + Celery Broker + 会话状态

---

## 目录结构规划

```
academic_research/
├── CLAUDE.md
├── docker-compose.yml          # 基础服务编排
├── .env.example                # 环境变量模板
├── backend/
│   ├── pyproject.toml
│   ├── alembic/                # 数据库迁移
│   ├── app/
│   │   ├── main.py             # FastAPI 入口
│   │   ├── core/               # 配置、数据库连接、安全
│   │   ├── models/             # SQLAlchemy ORM 模型
│   │   ├── schemas/            # Pydantic 请求/响应模型
│   │   ├── api/                # 路由层（按功能模块拆分）
│   │   ├── services/           # 业务逻辑层
│   │   ├── agents/             # Agent 核心逻辑
│   │   │   ├── base.py         # 基础 Agent 抽象
│   │   │   ├── tools/          # Tool 注册与执行
│   │   │   ├── memory/         # 会话记忆管理
│   │   │   └── orchestrator.py # 多 Agent 协调器
│   │   └── llm/                # LLM 统一客户端层
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── pages/
        ├── components/
        ├── store/              # Zustand 状态
        ├── hooks/
        └── api/                # API 调用层
```

---

## 切片法开发计划

> 每个切片是一个可独立运行的垂直功能条带（从数据库到前端 UI），按序交付。

| 切片 | 名称 | 核心内容 |
|------|------|----------|
| **S0** | 基础骨架 | docker-compose（PG+Redis）、FastAPI hello、React+Vite hello、环境变量、健康检查接口 |
| **S1** | 用户认证 | 用户模型、JWT 登录注册、前端登录页、路由守卫 |
| **S2** | 会话管理 | 会话（Conversation）模型、创建/列表/删除接口、前端会话列表 |
| **S3** | 基础对话 | 消息模型、单轮 LLM 调用、流式输出（SSE/WebSocket）、对话界面 |
| **S3.5** | 树状对话 | 树形消息结构、分支创建/切换、树状 UI 可视化 |
| **S4** | 多轮记忆 | 历史上下文拼接、Token 管理、会话持久化 |
| **S4.5** | 文档上传 | PDF 上传与解析、文件内容注入对话上下文、前端上传 UI |
| **S5** | Tool 系统 | Tool 注册机制、Function Calling 集成、工具执行沙箱 |
| **S6** | Agent 核心 | ReAct/计划-执行 Agent 循环、中间步骤展示 |
| **S7** | 多 Agent 协作 | Agent 角色定义、Orchestrator、任务分发 |
| **S8** | 知识库/RAG | 文档上传、向量化存储（pgvector）、检索增强生成 |
| **S9** | 监控与可观测 | 对话日志、Token 消耗统计、LLM 调用追踪 |

---

## 开发规范

### Git
- 主分支: `main`
- 功能分支: `feature/s{n}-{short-desc}`（每个切片一个分支）
- 提交格式: `feat(s0): add docker compose setup`

### API 设计
- 路径前缀: `/api/v1/`
- 认证: Bearer JWT（Authorization header）
- 错误响应统一格式: `{"detail": "...", "code": "ERROR_CODE"}`
- 流式响应: Server-Sent Events（SSE）优先，WebSocket 备选

### 数据库
- 所有表包含 `id`（UUID）、`created_at`、`updated_at`
- 软删除字段: `deleted_at`（nullable）
- 迁移命名: `{revision_id}_{short_description}.py`

### 环境变量
- 本地开发使用 `.env`（不提交）
- 模板维护在 `.env.example`（提交）
- 通过 pydantic `BaseSettings` 统一管理

---

## 当前状态

- [x] 目录结构初始化（`backend/`、`frontend/`）
- [x] S0: 基础骨架（docker-compose、FastAPI+健康检查、React+Vite+TS、Alembic）
- [x] S1: 用户认证（User 模型、JWT、bcrypt、register/login/me、前端登录注册页、路由守卫）
- [x] S2: 会话管理（Conversation 模型软删除、CRUD 接口、侧边栏、嵌套路由 Layout+Outlet）
- [x] S3: 基础对话（Message 模型、SSE 流式输出、Anthropic/OpenAI 双客户端、聊天 UI）
- [x] S3.5: 树状对话（树形 Message 数据结构、分支创建与切换、树状 UI 可视化、浮动/固定窗口）
- [x] S4: 多轮记忆（Token 计数估算、历史预算截断、token_count 存 DB、SSE done 事件返回统计、前端 token 状态栏）
- [ ] S4.5: 文档上传（PDF 解析、内容注入上下文）

---

## 关键约束

- Docker 只跑**基础服务**（数据库、缓存），不跑应用代码
- M4 芯片注意镜像架构：docker-compose 中指定 `platform: linux/arm64` 或使用多架构镜像
- 异步优先：SQLAlchemy 使用 `asyncpg` driver，FastAPI 路由全部 `async def`
- LLM 调用封装在 `app/llm/` 层，不直接在路由或 Agent 里 import SDK
