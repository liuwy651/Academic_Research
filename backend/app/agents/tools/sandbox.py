import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_WORKSPACE = Path("/tmp/agent_workspace")


def execute_python_code(code: str) -> str:
    """在受限子进程中执行 Python 代码，返回 stdout / stderr 输出。"""
    _WORKSPACE.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        dir=_WORKSPACE, suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        script_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(_WORKSPACE),
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        output_parts = []
        if result.stdout.strip():
            output_parts.append(f"[stdout]\n{result.stdout.strip()}")
        if result.stderr.strip():
            output_parts.append(f"[stderr]\n{result.stderr.strip()}")
        if not output_parts:
            return "(代码执行完毕，无任何输出)"
        return "\n\n".join(output_parts)
    except subprocess.TimeoutExpired:
        return "执行超时（15 秒限制）。请检查代码是否存在死循环或长时间阻塞操作。"
    except Exception as e:
        logger.error("sandbox execute_python_code 异常: %s", e)
        return f"沙箱执行失败：{e}"
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


PYTHON_SANDBOX_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "execute_python_code",
        "description": (
            "在本地 Python 沙箱中执行任意 Python 代码，并返回 stdout/stderr 输出。"
            "当你需要进行复杂数学计算、数据处理、统计分析、验证算法逻辑，"
            "或任何需要精确计算而非估算的任务时，必须调用此工具。"
            "代码应当是完整可运行的脚本，使用 print() 输出结果。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "完整的 Python 代码字符串。"
                        "必须通过 print() 输出结果，否则将看不到任何返回值。"
                        "可以使用标准库，但不要依赖未预装的第三方包。"
                    ),
                }
            },
            "required": ["code"],
        },
    },
}
