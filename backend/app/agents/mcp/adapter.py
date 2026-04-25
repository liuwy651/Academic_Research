"""MCP Tool Schema → OpenAI Function Calling Schema 适配器。

MCP 原始格式：
    {
        "name": "read_file",
        "description": "Read file contents",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    }

OpenAI Function Calling 格式：
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    }
"""


def mcp_tool_to_openai_schema(mcp_tool: dict, name_prefix: str = "") -> dict:
    """将 MCP 工具定义转换为 OpenAI Function Calling Schema。

    Args:
        mcp_tool:    MCP 原始工具定义 dict（含 name / description / inputSchema）
        name_prefix: 可选前缀，用于区分来自不同 MCP Server 的同名工具。
                     设置后工具名变为 "{prefix}__{name}"。

    Returns:
        OpenAI 兼容的 Function Calling Schema dict。
    """
    raw_name: str = mcp_tool.get("name") or "unnamed_tool"
    name = f"{name_prefix}__{raw_name}" if name_prefix else raw_name

    input_schema: dict = mcp_tool.get("inputSchema") or {}

    # OpenAI 要求顶层 type 必须是 "object"
    if input_schema.get("type") != "object":
        input_schema = {
            "type": "object",
            "properties": {"input": input_schema} if input_schema else {},
        }

    # 移除 OpenAI 不认识的 JSON Schema 关键字（如 $schema）
    input_schema.pop("$schema", None)
    input_schema.pop("additionalProperties", None)

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": mcp_tool.get("description") or "",
            "parameters": input_schema,
        },
    }


def extract_raw_tool_name(registered_name: str, name_prefix: str) -> str:
    """从带前缀的注册名还原原始工具名。

    例：extract_raw_tool_name("filesystem__read_file", "filesystem") → "read_file"
    """
    prefix_with_sep = f"{name_prefix}__"
    if registered_name.startswith(prefix_with_sep):
        return registered_name[len(prefix_with_sep):]
    return registered_name
