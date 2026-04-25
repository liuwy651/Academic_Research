"""MCP (Model Context Protocol) 同步 stdio 客户端。

通过子进程 stdin/stdout 与 MCP Server 通信（JSON-RPC 2.0），线程安全。
适用于本地 MCP Server（如 filesystem、sqlite、自定义工具等）。

生命周期：
    client = MCPStdioClient(["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
    client.connect()          # 启动进程 + 握手
    tools = client.list_tools()
    result = client.call_tool("read_file", {"path": "/tmp/foo.txt"})
    client.close()
"""

import json
import logging
import os
import subprocess
import threading
from typing import Any

logger = logging.getLogger(__name__)

_PROTOCOL_VERSION = "2024-11-05"


class MCPError(Exception):
    """MCP 通信或协议错误。"""


class MCPStdioClient:
    """同步 stdio 传输的 MCP 客户端，线程安全。"""

    def __init__(self, command: list[str], env: dict[str, str] | None = None):
        """
        Args:
            command: 启动 MCP Server 的命令，例如 ["npx", "-y", "@modelcontextprotocol/server-sqlite", "db.sqlite"]
            env:     额外注入的环境变量（叠加到当前进程 env 之上）
        """
        self._command = command
        self._extra_env = env or {}
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._req_id = 0
        self._connected = False
        self.server_info: dict = {}

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def connect(self) -> None:
        """启动 Server 进程并完成 MCP 握手（幂等，重复调用安全）。"""
        with self._lock:
            if self._connected:
                return
            self._start_process()
            self._initialize()
            self._connected = True
            logger.info("MCP server connected: %s (server=%s)", " ".join(self._command), self.server_info.get("name", "?"))

    def close(self) -> None:
        """终止 Server 进程并清理状态。"""
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            self._process = None
            self._connected = False

    def is_alive(self) -> bool:
        """进程是否仍在运行。"""
        return self._connected and self._process is not None and self._process.poll() is None

    # ── MCP API ───────────────────────────────────────────────────────────

    def list_tools(self) -> list[dict]:
        """获取 Server 暴露的工具列表（原始 MCP 格式）。"""
        with self._lock:
            self._ensure_alive()
            result = self._rpc("tools/list")
            return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> str:
        """调用工具，返回文本结果字符串。"""
        with self._lock:
            self._ensure_alive()
            result = self._rpc("tools/call", {"name": name, "arguments": arguments})
            is_error = result.get("isError", False)
            content: list[dict] = result.get("content", [])
            parts = [item["text"] for item in content if item.get("type") == "text"]
            output = "\n".join(parts) if parts else "(工具无文本输出)"
            if is_error:
                return f"[MCP 工具错误] {output}"
            return output

    # ── 内部实现 ──────────────────────────────────────────────────────────

    def _start_process(self) -> None:
        env = {**os.environ, **self._extra_env}
        try:
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                bufsize=1,  # 行缓冲
            )
        except FileNotFoundError as e:
            raise MCPError(f"无法启动 MCP Server，命令不存在: {self._command[0]}") from e

    def _initialize(self) -> None:
        req_id = self._send("initialize", {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "agent-backend", "version": "0.1.0"},
        })
        result = self._recv(req_id)
        self.server_info = result.get("serverInfo", {})
        # 发送 initialized 通知（无需响应）
        self._notify("notifications/initialized")

    def _rpc(self, method: str, params: Any = None) -> dict:
        req_id = self._send(method, params)
        return self._recv(req_id)

    def _send(self, method: str, params: Any = None) -> int:
        self._req_id += 1
        req_id = self._req_id
        msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        line = json.dumps(msg, ensure_ascii=False) + "\n"
        assert self._process and self._process.stdin
        self._process.stdin.write(line)
        self._process.stdin.flush()
        return req_id

    def _notify(self, method: str, params: Any = None) -> None:
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        assert self._process and self._process.stdin
        self._process.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self._process.stdin.flush()

    def _recv(self, expected_id: int) -> dict:
        """阻塞读取 stdout，直到收到匹配 id 的 JSON-RPC 响应。"""
        assert self._process and self._process.stdout
        while True:
            line = self._process.stdout.readline()
            if not line:
                stderr_out = ""
                if self._process.stderr:
                    try:
                        stderr_out = self._process.stderr.read(500)
                    except Exception:
                        pass
                raise MCPError(f"MCP Server 提前关闭（stdout EOF）。stderr: {stderr_out!r}")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("MCP: 忽略非 JSON 行: %s", line[:120])
                continue
            if msg.get("id") != expected_id:
                # 可能是服务端主动推送的通知，跳过
                continue
            if "error" in msg:
                err = msg["error"]
                raise MCPError(f"JSON-RPC 错误 {err.get('code')}: {err.get('message')}")
            return msg.get("result") or {}

    def _ensure_alive(self) -> None:
        if not self._connected or not self.is_alive():
            raise MCPError("MCP Client 未连接或进程已退出，请先调用 connect()。")
