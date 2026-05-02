"""
工具节点：调用 `tools_runtime` 并把结果写入 `draft_reply` / `tool_error`。

单个文件承载 **两个** 工具节点函数，避免「一函数一文件」过度碎裂；
若企业规范要求一工具一文件，再拆子包即可。
"""

from __future__ import annotations

from lesson19_support_desk.state import SupportDeskState
from lesson19_support_desk.tools_runtime import now_local_iso, safe_eval_arithmetic


def tool_calculator(state: SupportDeskState) -> SupportDeskState:
    expr = (state.get("tool_expression") or "").strip() or (state.get("normalized_message") or "")
    try:
        val = safe_eval_arithmetic(expr)
        out = f"计算结果：{val}"
        return {
            "tool_output": out,
            "tool_error": "",
            "draft_reply": out,
            "diagnostics": ["tool:calc_ok"],
        }
    except Exception as exc:  # noqa: BLE001
        err = f"算术失败：{type(exc).__name__}: {exc}"
        return {
            "tool_output": "",
            "tool_error": err,
            "draft_reply": "暂时无法安全计算该表达式，请换用纯数字四则运算。",
            "diagnostics": ["tool:calc_fail"],
        }


def tool_time(state: SupportDeskState) -> SupportDeskState:
    stamp = now_local_iso()
    line = f"当前本机时间（ISO）：{stamp}"
    return {
        "tool_output": line,
        "tool_error": "",
        "draft_reply": line,
        "diagnostics": ["tool:time_ok"],
    }
