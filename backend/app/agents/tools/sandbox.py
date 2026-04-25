import logging
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_WORKSPACE = Path("/tmp/agent_workspace")
_PLOTS_DIR = Path(__file__).parents[2] / "static" / "plots"

# Marker format embedded in tool result so chat.py can extract the URL
_IMAGE_MARKER_PREFIX = "[IMAGE_URL:"
_IMAGE_MARKER_SUFFIX = "]"


def _build_preamble(plot_path: Path) -> str:
    """Return Python source injected before user code to capture matplotlib output."""
    return f"""\
try:
    import matplotlib as _mpl
    _mpl.use('Agg')
    import matplotlib.pyplot as _plt_mod
    _PLOT_OUTPUT = {str(plot_path)!r}
    _orig_show = _plt_mod.show
    def _auto_show(*_a, **_k):
        if _plt_mod.get_fignums():
            _plt_mod.savefig(_PLOT_OUTPUT, dpi=150, bbox_inches='tight')
        _orig_show(*_a, **_k)
    _plt_mod.show = _auto_show
except ImportError:
    pass
"""


def execute_python_code(code: str) -> str:
    """在受限子进程中执行 Python 代码，返回 stdout / stderr 输出。
    若代码生成了 matplotlib 图表，结果中会附带图片 URL 标记。
    """
    _WORKSPACE.mkdir(parents=True, exist_ok=True)
    _PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    plot_name = f"{uuid.uuid4().hex}.png"
    plot_path = _PLOTS_DIR / plot_name
    plot_url = f"/static/plots/{plot_name}"

    augmented_code = _build_preamble(plot_path) + "\n" + code

    with tempfile.NamedTemporaryFile(
        dir=_WORKSPACE, suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(augmented_code)
        script_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(_WORKSPACE),
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "MPLBACKEND": "Agg"},
        )
        output_parts = []
        if result.stdout.strip():
            output_parts.append(f"[stdout]\n{result.stdout.strip()}")
        if result.stderr.strip():
            output_parts.append(f"[stderr]\n{result.stderr.strip()}")

        if plot_path.exists():
            output_parts.append(f"{_IMAGE_MARKER_PREFIX}{plot_url}{_IMAGE_MARKER_SUFFIX}")

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
            "支持 matplotlib 绘图：调用 plt.show() 即可将图表自动保存并展示给用户，"
            "无需指定保存路径。"
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
                        "绘图时调用 plt.show() 即可，图片会自动保存并展示。"
                    ),
                }
            },
            "required": ["code"],
        },
    },
}
