"""
生成节点：调用 `llm_client`，把本轮 `attempt` 递增（与第 4 课 attempt 计数对齐）。
"""

from __future__ import annotations

from lesson19_support_desk.llm_client import generate_reply_text
from lesson19_support_desk.state import SupportDeskState


def generate_reply(state: SupportDeskState) -> SupportDeskState:
    prev = int(state.get("attempt") or 0)
    mode = state.get("mode") or "fallback"
    intent = state.get("intent") or "general"
    body, tag = generate_reply_text(
        mode=mode,  # type: ignore[arg-type]
        intent=str(intent),
        user_message=state.get("normalized_message") or "",
        feedback=state.get("feedback_for_generation") or "",
    )
    return {
        "attempt": prev + 1,
        "draft_reply": body,
        "diagnostics": [f"generate:{tag}"],
    }
