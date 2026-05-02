"""
纯路由函数：无任何 I/O，便于单元测试与表驱动验收。

`workflow.py` 在注册 `add_conditional_edges` 时只引用这里的符号，保持「图 = 声明式接线」。
"""

from __future__ import annotations

from typing import Literal

from lesson19_support_desk.state import SupportDeskState


def route_after_ingest(state: SupportDeskState) -> Literal["ok", "invalid"]:
    """入参不合法时直达 finalize，避免后续节点读到脏数据。"""

    return "invalid" if state.get("message_gate") == "invalid" else "ok"


def route_after_classify(
    state: SupportDeskState,
) -> Literal["tool_calculator", "tool_time", "generate_reply"]:
    """`classify` 之后分流：计算/时间走工具，其余走可自我修订的生成链。"""

    intent = state.get("intent") or "pending"
    if intent == "math":
        return "tool_calculator"
    if intent == "time":
        return "tool_time"
    return "generate_reply"


def route_after_evaluate(state: SupportDeskState) -> Literal["retry_generate", "finalize_reply"]:
    """评估未通过且未达 `max_attempts` 时回到生成；否则收口。"""

    if state.get("quality_passed"):
        return "finalize_reply"
    if int(state.get("attempt") or 0) >= int(state.get("max_attempts") or 1):
        return "finalize_reply"
    return "retry_generate"
