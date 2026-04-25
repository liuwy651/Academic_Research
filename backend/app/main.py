import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.chat import router as chat_router
from app.api.v1.files import router as files_router

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_PLOTS_DIR = _STATIC_DIR / "plots"
_PLOTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(files_router, prefix="/api/v1")

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.on_event("startup")
async def startup_event() -> None:
    from app.agents.tools.registry import registry
    from app.agents.graph import get_agent_graph

    command = ["npx", "-y", "@modelcontextprotocol/server-filesystem"] + settings.MCP_FILESYSTEM_PATHS
    logger.info("正在注册 MCP filesystem server，授权目录: %s", settings.MCP_FILESYSTEM_PATHS)
    try:
        count = await asyncio.to_thread(registry.register_mcp_server, "fs", command)
        logger.info("MCP filesystem server 注册完成，共 %d 个工具", count)
    except Exception as e:
        logger.error("MCP filesystem server 注册失败（非致命，文件工具将不可用）: %s", e)

    # MCP 注册完毕后构建 Agent 图，确保所有工具都已纳入
    try:
        graph = get_agent_graph()
        logger.info("Agent 图构建完成: %s", graph)
    except Exception as e:
        logger.error("Agent 图构建失败: %s", e)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    from app.agents.tools.registry import registry

    logger.info("正在关闭所有 MCP Server 连接…")
    await asyncio.to_thread(registry.shutdown)
