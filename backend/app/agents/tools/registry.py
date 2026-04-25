import logging
from typing import Callable

from app.agents.tools.bocha import BOCHA_SEARCH_TOOL_SCHEMA, execute_bocha_search
from app.agents.tools.sandbox import PYTHON_SANDBOX_TOOL_SCHEMA, execute_python_code

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表，统一管理固有工具与动态加载的 MCP 工具。

    固有工具（bocha 搜索、Python 沙箱）在模块加载时注册。
    MCP 工具通过 register_mcp_server() 动态注册：连接 Server →
    拉取工具列表 → 转换 Schema → 注入注册表。

    execute_tool() 是统一分发入口，调用方无需感知工具来源。
    chat.py 通过 asyncio.to_thread(registry.execute_tool, name, args) 调用，
    因此本类所有方法保持同步。
    """

    def __init__(self) -> None:
        self._schemas: list[dict] = []
        self._handlers: dict[str, Callable[..., str]] = {}
        # server_name → MCPStdioClient，用于生命周期管理
        self._mcp_clients: dict[str, object] = {}

    # ── 固有工具注册 ──────────────────────────────────────────────────────

    def register(self, schema: dict, handler: Callable[..., str]) -> None:
        """注册一个固有工具（schema + handler）。"""
        name: str = schema["function"]["name"]
        self._schemas.append(schema)
        self._handlers[name] = handler
        logger.debug("注册固有工具: %s", name)

    # ── MCP Server 动态注册 ────────────────────────────────────────────────

    def register_mcp_server(
        self,
        server_name: str,
        command: list[str],
        env: dict[str, str] | None = None,
    ) -> int:
        """连接 MCP Server，将其所有工具动态注入注册表。

        Args:
            server_name: 逻辑名称，用作工具名前缀（避免同名冲突）。
                         例：server_name="fs" → 工具名变为 "fs__read_file"。
            command:     启动 MCP Server 的命令列表。
                         例：["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
            env:         额外注入的环境变量。

        Returns:
            成功注册的工具数量；连接/列工具失败时返回 0。
        """
        from app.agents.mcp.client import MCPError, MCPStdioClient
        from app.agents.mcp.adapter import mcp_tool_to_openai_schema

        try:
            client = MCPStdioClient(command, env)
            client.connect()
            mcp_tools = client.list_tools()
        except MCPError as e:
            logger.error("无法连接 MCP Server '%s': %s", server_name, e)
            return 0
        except Exception as e:
            logger.error("注册 MCP Server '%s' 时发生意外错误: %s", server_name, e)
            return 0

        registered = 0
        for mcp_tool in mcp_tools:
            schema = mcp_tool_to_openai_schema(mcp_tool, name_prefix=server_name)
            tool_name = schema["function"]["name"]
            raw_name: str = mcp_tool.get("name", tool_name)

            # 通过闭包捕获 client 和 raw_name，避免循环变量陷阱
            handler = _make_mcp_handler(client, raw_name)
            self._schemas.append(schema)
            self._handlers[tool_name] = handler
            registered += 1
            logger.info("注册 MCP 工具: %s (来自 server: %s)", tool_name, server_name)

        self._mcp_clients[server_name] = client
        logger.info("MCP Server '%s' 注册完成，共 %d 个工具", server_name, registered)
        return registered

    # ── 工具查询与执行 ────────────────────────────────────────────────────

    def get_all_tool_schemas(self) -> list[dict]:
        """返回所有已注册工具的 OpenAI Function Calling Schema 列表。

        包含：固有工具（bocha + sandbox）+ 所有已注册 MCP Server 的工具。
        """
        return list(self._schemas)

    def execute_tool(self, name: str, args: dict) -> str:
        """统一工具执行入口，根据工具名分发至对应处理器。

        固有工具与 MCP 工具使用相同接口，调用方无感知。
        """
        handler = self._handlers.get(name)
        if handler is None:
            logger.warning("尝试调用未知工具: %s", name)
            return f"未知工具：{name}"
        try:
            return handler(**args)
        except TypeError as e:
            logger.error("工具 '%s' 参数错误: %s，args=%s", name, e, args)
            return f"工具参数错误：{e}"
        except Exception as e:
            logger.error("工具 '%s' 执行异常: %s", name, e, exc_info=True)
            return f"工具执行失败：{e}"

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """关闭所有 MCP Server 连接，释放子进程资源。

        建议在应用关闭时（FastAPI shutdown 事件）调用。
        """
        for name, client in list(self._mcp_clients.items()):
            try:
                client.close()  # type: ignore[attr-defined]
                logger.info("已关闭 MCP Server 连接: %s", name)
            except Exception as e:
                logger.warning("关闭 MCP Server '%s' 时出错: %s", name, e)
        self._mcp_clients.clear()

    # ── 调试辅助 ──────────────────────────────────────────────────────────

    def list_tool_names(self) -> list[str]:
        """返回所有已注册工具名称（调试用）。"""
        return [s["function"]["name"] for s in self._schemas]


def _make_mcp_handler(client: object, raw_name: str) -> Callable[..., str]:
    """构造 MCP 工具处理器闭包，捕获 client 与 raw_name。"""
    def handler(**kwargs: object) -> str:
        return client.call_tool(raw_name, kwargs)  # type: ignore[attr-defined]
    handler.__name__ = raw_name
    return handler


# ── 全局单例，模块加载时注册固有工具 ─────────────────────────────────────
registry = ToolRegistry()
registry.register(BOCHA_SEARCH_TOOL_SCHEMA, execute_bocha_search)
registry.register(PYTHON_SANDBOX_TOOL_SCHEMA, execute_python_code)
