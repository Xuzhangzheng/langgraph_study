"""
意图分类：规则版（生产可换小模型 / 微服务），写入 `intent` 与算术表达式抽取。

与第 8 课「优先级路由」同构：先算术、再时间、再业务关键词。
"""

from __future__ import annotations

import re

from lesson19_support_desk.state import Intent, SupportDeskState


def classify_intent(state: SupportDeskState) -> SupportDeskState:
    text = state.get("normalized_message") or ""
    compact = re.sub(r"\s+", "", text)

    intent: Intent = "general"
    expr = ""

    if "计算" in text or any(op in compact for op in ("+", "-", "*", "/")):
        intent = "math"
        if "计算" in text:
            expr = text.split("计算", maxsplit=1)[1].strip()
        else:
            expr = text
    elif any(k in text for k in ("几点", "时间", "现在", "日期")):
        intent = "time"
    elif any(k in text for k in ("退款", "退钱")):
        intent = "refund"
    elif any(k in text for k in ("物流", "快递", "运单")):
        intent = "shipping"

    return {
        "intent": intent,
        "tool_expression": expr,
        "diagnostics": [f"classify:intent={intent}"],
    }
