"""
收口节点：统一写 `final_reply`——工具链与 LLM 链在此 **产品化对齐**。
"""

from __future__ import annotations

from lesson19_support_desk.state import SupportDeskState


def finalize_reply(state: SupportDeskState) -> SupportDeskState:
    if state.get("message_gate") == "invalid":
        out = "【系统】未收到有效问题描述，请重新输入。"
        return {"final_reply": out, "diagnostics": ["finalize:invalid_input"]}

    intent = state.get("intent")
    if intent in ("math", "time"):
        text = (state.get("draft_reply") or "").strip() or (state.get("tool_output") or "")
        return {
            "final_reply": text,
            "diagnostics": [f"finalize:tool:{intent}"],
        }

    text = (state.get("draft_reply") or "").strip() or "【系统】暂无答复。"
    if not state.get("quality_passed"):
        text = text + "\n（备注：自动质检未完全通过，建议人工复核。）"
    return {
        "final_reply": text,
        "diagnostics": ["finalize:llm_path"],
    }
