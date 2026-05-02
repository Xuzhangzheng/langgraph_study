"""
入站节点：规范化用户输入并设 `message_gate`。

职责边界：**不做意图判断**——那是 `node_classify` 的事。
"""

from __future__ import annotations

from lesson19_support_desk.state import MessageGate, SupportDeskState


def ingest_user_message(state: SupportDeskState) -> SupportDeskState:
    raw = (state.get("user_message") or "").strip()
    gate: MessageGate = "invalid" if not raw else "ok"
    return {
        "normalized_message": raw,
        "message_gate": gate,
        "diagnostics": [f"ingest:gate={gate}"],
    }
