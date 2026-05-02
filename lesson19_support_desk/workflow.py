"""
图装配：只负责 `StateGraph` 的节点注册与边——**不含业务计算**。

维护时优先改 `node_*.py` 或 `routing.py`，本文件保持稳定接线表。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from lesson19_support_desk.node_classify import classify_intent
from lesson19_support_desk.node_evaluate import evaluate_reply
from lesson19_support_desk.node_finalize import finalize_reply
from lesson19_support_desk.node_generate import generate_reply
from lesson19_support_desk.node_ingest import ingest_user_message
from lesson19_support_desk.node_tools import tool_calculator, tool_time
from lesson19_support_desk.routing import route_after_classify, route_after_evaluate, route_after_ingest
from lesson19_support_desk.state import SupportDeskState


def build_support_desk_graph() -> StateGraph:
    """返回 **未** `compile` 的图构建器，供应用层注入 checkpointer / 将来 subgraph。"""

    g = StateGraph(SupportDeskState)
    g.add_node("ingest", ingest_user_message)
    g.add_node("classify_intent", classify_intent)
    g.add_node("tool_calculator", tool_calculator)
    g.add_node("tool_time", tool_time)
    g.add_node("generate_reply", generate_reply)
    g.add_node("evaluate_reply", evaluate_reply)
    g.add_node("finalize_reply", finalize_reply)

    g.add_edge(START, "ingest")
    g.add_conditional_edges(
        "ingest",
        route_after_ingest,
        {"ok": "classify_intent", "invalid": "finalize_reply"},
    )
    g.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        {
            "tool_calculator": "tool_calculator",
            "tool_time": "tool_time",
            "generate_reply": "generate_reply",
        },
    )
    g.add_edge("tool_calculator", "finalize_reply")
    g.add_edge("tool_time", "finalize_reply")
    g.add_edge("generate_reply", "evaluate_reply")
    g.add_conditional_edges(
        "evaluate_reply",
        route_after_evaluate,
        {"retry_generate": "generate_reply", "finalize_reply": "finalize_reply"},
    )
    g.add_edge("finalize_reply", END)

    return g


def export_workflow_diagram(compiled: Any, png_name: str) -> None:
    """与前几课一致：尝试 PNG，失败写 `.mmd`。"""

    from pathlib import Path

    root = Path(__file__).resolve().parent
    png_path = root / png_name
    mmd_path = root / png_name.replace(".png", ".mmd")
    graph_obj = compiled.get_graph()
    try:
        png_path.write_bytes(graph_obj.draw_mermaid_png())
        print(f"[capstone] diagram → {png_path}")
    except Exception as exc:  # noqa: BLE001
        mmd_path.write_text(graph_obj.draw_mermaid(), encoding="utf-8")
        print(f"[capstone] diagram PNG failed ({exc}); wrote {mmd_path}")
