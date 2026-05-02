"""
应用门面：组装 **compile(checkpointer=...)**、统一 `invoke` 配置。

对照企业项目里的 `Application` / `Service` 层——图在 `workflow.py`，持久语义在这里注入。
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from lesson19_support_desk.settings import bootstrap_env, default_max_attempts_generate, default_run_mode
from lesson19_support_desk.state import RunMode, SupportDeskState
from lesson19_support_desk.workflow import build_support_desk_graph


def build_initial_state(
    *,
    request_id: str,
    user_message: str,
    mode: RunMode | None = None,
    max_attempts: int | None = None,
) -> SupportDeskState:
    """构造满足 `SupportDeskState` 的完整初值；`diagnostics` 必须为空列表以启用 reducer。"""

    m = mode if mode is not None else default_run_mode()  # type: ignore[assignment]
    if m not in ("llm", "fallback"):
        m = "fallback"

    mx = max_attempts if max_attempts is not None else default_max_attempts_generate()
    return {
        "request_id": request_id,
        "user_message": user_message,
        "normalized_message": "",
        "message_gate": "pending",
        "intent": "pending",
        "tool_expression": "",
        "tool_output": "",
        "tool_error": "",
        "draft_reply": "",
        "final_reply": "",
        "quality_score": 0,
        "quality_passed": False,
        "feedback_for_generation": "",
        "attempt": 0,
        "max_attempts": mx,
        "mode": m,
        "diagnostics": [],
    }


class SupportDeskApplication:
    """
    Capstone 对外主类：示例项目里 Flask/FastAPI 会持有一个单例并透传 `thread_id`。
    """

    def __init__(self, *, use_checkpointer: bool = True) -> None:
        bootstrap_env()
        builder = build_support_desk_graph()
        if use_checkpointer:
            self._compiled = builder.compile(checkpointer=InMemorySaver())  # 第 12 课同 family
        else:
            self._compiled = builder.compile()
        self._use_checkpointer = use_checkpointer

    @property
    def compiled(self) -> Any:
        """暴露给 `regression` 与运维脚本（导出图、读 `get_state`）。"""

        return self._compiled

    def handle(self, state: SupportDeskState, *, thread_id: str = "default") -> SupportDeskState:
        """一次完整问答；有 checkpointer 时必须传稳定 `thread_id` 以复现第 12 课语义。"""

        cfg = {"configurable": {"thread_id": thread_id}} if self._use_checkpointer else {}
        if self._use_checkpointer:
            return self._compiled.invoke(state, config=cfg)  # type: ignore[return-value]
        return self._compiled.invoke(state)  # type: ignore[return-value]
