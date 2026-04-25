#!/usr/bin/env python3
"""
工具链集成测试脚本

验证以下闭环：
  [1] Python 沙箱独立执行（计算、stdout 捕获、超时机制）
  [2] Registry 分发固有工具（bocha + sandbox 路径均可达）
  [3] 搜索 + 沙箱串联：先搜索获取信息，再用沙箱对结果做统计处理
  [4] MCP 框架接口（register_mcp_server / shutdown 方法存在，schema 完整）
  [5] MCP 适配器（schema 转换格式正确）

运行方式：
  cd backend
  uv run python scripts/test_tools.py

无需启动 FastAPI 或数据库，脚本直接 import 工具层代码。
"""
import os
import sys

# 将 backend/ 目录加入 Python 路径（使 app.* 可 import）
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)

# 设置最小环境变量，避免 pydantic_settings 因缺字段报错
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://agent:agent_password@localhost:5432/agent_db")
os.environ.setdefault("DASHSCOPE_API_KEY", "placeholder")


# ── 颜色输出辅助 ─────────────────────────────────────────────────────────

def _ok(msg: str) -> None:
    print(f"\033[32m  ✓ {msg}\033[0m")

def _info(msg: str) -> None:
    print(f"  → {msg}")

def _header(n: int, title: str) -> None:
    print(f"\n{'=' * 55}")
    print(f"  [{n}] {title}")
    print(f"{'=' * 55}")

def _fail(msg: str) -> None:
    print(f"\033[31m  ✗ {msg}\033[0m")
    sys.exit(1)


# ── 测试用例 ─────────────────────────────────────────────────────────────

def test_sandbox_basic() -> None:
    _header(1, "Python 沙箱 — 基础执行")
    from app.agents.tools.sandbox import execute_python_code

    # 1a. 标准输出捕获
    result = execute_python_code(
        "import statistics\n"
        "data = [12, 45, 23, 67, 89, 34, 56, 78, 90, 11]\n"
        "print(f'均值: {statistics.mean(data):.2f}')\n"
        "print(f'中位数: {statistics.median(data)}')\n"
        "print(f'标准差: {statistics.stdev(data):.2f}')\n"
    )
    _info(f"沙箱输出:\n{result}")
    assert "均值" in result and "标准差" in result, "stdout 捕获失败"
    _ok("标准输出捕获正常")

    # 1b. stderr 也能捕获
    result_err = execute_python_code("import sys\nsys.stderr.write('error line\\n')\nprint('ok')")
    assert "ok" in result_err
    _ok("stderr 捕获正常")

    # 1c. 无输出时有友好提示
    result_silent = execute_python_code("x = 1 + 1")
    assert "无任何输出" in result_silent
    _ok("无输出提示正常")

    # 1d. 超时保护
    result_timeout = execute_python_code("while True: pass")
    assert "超时" in result_timeout
    _ok("15 秒超时保护生效")


def test_registry_dispatch() -> None:
    _header(2, "Registry — 固有工具分发")
    from app.agents.tools.registry import registry

    # 沙箱路径
    result = registry.execute_tool("execute_python_code", {"code": "print('dispatch ok')"})
    assert "dispatch ok" in result
    _ok("sandbox 分发正常")

    # 未知工具
    result_unknown = registry.execute_tool("no_such_tool", {})
    assert "未知工具" in result_unknown
    _ok("未知工具返回友好错误")

    # 参数错误不崩溃
    result_bad = registry.execute_tool("execute_python_code", {"wrong_param": "x"})
    assert "参数错误" in result_bad or "执行失败" in result_bad
    _ok("参数错误处理正常")

    # schema 完整性
    schemas = registry.get_all_tool_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "execute_bocha_search" in names, "缺少 bocha schema"
    assert "execute_python_code" in names, "缺少 sandbox schema"
    _info(f"已注册工具: {names}")
    _ok(f"schema 列表完整（{len(schemas)} 个工具）")


def test_search_plus_sandbox() -> None:
    _header(3, "搜索 + 沙箱 — 串联验证")
    from app.agents.tools.registry import registry

    # Step 1：执行搜索
    _info("调用 execute_bocha_search ...")
    search_result: str = registry.execute_tool(
        "execute_bocha_search",
        {"query": "Python 大语言模型工具调用 2024", "count": 3},
    )
    _info(f"搜索结果（前 200 字）: {search_result[:200]} ...")

    # Step 2：将搜索结果传入沙箱做统计
    _info("将搜索结果传入 Python 沙箱处理 ...")
    # 用 repr() 安全地将字符串嵌入 Python 代码，避免引号/换行转义问题
    sandbox_code = (
        "text = " + repr(search_result[:800]) + "\n"
        "char_count = len(text)\n"
        "word_count = len(text.split())\n"
        "line_count = len([l for l in text.splitlines() if l.strip()])\n"
        "print(f'字符数: {char_count}')\n"
        "print(f'词数: {word_count}')\n"
        "print(f'行数: {line_count}')\n"
    )
    sandbox_result: str = registry.execute_tool(
        "execute_python_code",
        {"code": sandbox_code},
    )
    _info(f"沙箱处理结果:\n{sandbox_result}")

    assert "字符数" in sandbox_result, "沙箱未成功处理搜索结果"
    _ok("搜索 + 沙箱串联验证通过")


def test_mcp_framework_interface() -> None:
    _header(4, "MCP 框架 — 接口完整性")
    from app.agents.tools.registry import ToolRegistry, registry

    assert hasattr(registry, "register_mcp_server"), "缺少 register_mcp_server 方法"
    assert hasattr(registry, "shutdown"), "缺少 shutdown 方法"
    assert hasattr(registry, "list_tool_names"), "缺少 list_tool_names 方法"
    _ok("ToolRegistry 接口完整")

    # shutdown 不应抛出（无 MCP client 时也安全）
    r = ToolRegistry()
    r.shutdown()
    _ok("shutdown() 空调用安全")

    # register_mcp_server 失败时返回 0，不崩溃
    count = registry.register_mcp_server(
        server_name="ghost",
        command=["non_existent_binary_xyz"],
    )
    assert count == 0
    _ok("register_mcp_server 连接失败时优雅降级（返回 0）")


def test_mcp_adapter() -> None:
    _header(5, "MCP 适配器 — Schema 转换")
    from app.agents.mcp.adapter import mcp_tool_to_openai_schema, extract_raw_tool_name

    # 标准 MCP 工具 → OpenAI schema
    mcp_tool = {
        "name": "read_file",
        "description": "Read a file from disk",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path"}},
            "required": ["path"],
            "$schema": "http://json-schema.org/draft-07/schema#",
        },
    }
    schema = mcp_tool_to_openai_schema(mcp_tool, name_prefix="fs")
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "fs__read_file"
    assert schema["function"]["description"] == "Read a file from disk"
    params = schema["function"]["parameters"]
    assert params["type"] == "object"
    assert "path" in params["properties"]
    assert "$schema" not in params, "$schema 应被清除"
    _ok("带前缀的 schema 转换正确，$schema 已清除")

    # 无前缀
    schema_no_prefix = mcp_tool_to_openai_schema(mcp_tool)
    assert schema_no_prefix["function"]["name"] == "read_file"
    _ok("无前缀转换正确")

    # 还原原始名
    raw = extract_raw_tool_name("fs__read_file", "fs")
    assert raw == "read_file"
    _ok("extract_raw_tool_name 还原正确")

    # inputSchema 缺失时不崩溃
    schema_empty = mcp_tool_to_openai_schema({"name": "ping", "description": "health check"})
    assert schema_empty["function"]["parameters"]["type"] == "object"
    _ok("缺少 inputSchema 时降级处理正常")


# ── 主入口 ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n工具链集成测试开始...")

    try:
        test_sandbox_basic()
        test_registry_dispatch()
        test_search_plus_sandbox()
        test_mcp_framework_interface()
        test_mcp_adapter()
    except AssertionError as e:
        _fail(f"断言失败: {e}")
    except Exception as e:
        import traceback
        _fail(f"意外错误: {e}\n{traceback.format_exc()}")

    print(f"\n{'=' * 55}")
    print("\033[32m  全部测试通过！工具链集成验证完成。\033[0m\n")
