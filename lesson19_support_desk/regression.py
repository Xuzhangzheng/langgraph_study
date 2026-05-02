"""
离线回归：黑盒调用 `SupportDeskApplication`，只断言 `final_reply` / `intent`（与第 15 课精神一致）。

不依赖节点实现细节——**字段契约**在 `state.py`。
"""

from __future__ import annotations

from dataclasses import dataclass

from lesson19_support_desk.application import SupportDeskApplication, build_initial_state


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    user_message: str
    reply_needle: str  # final_reply 应包含的子串
    expect_intent_substr: str  # diagnostics 或状态难以直接读 intent 时的弱断言——此处验 `final_reply` 即可


def default_suite() -> list[GoldenCase]:
    return [
        GoldenCase("gc-calc", "计算 19+23", "计算结果：", ""),
        GoldenCase("gc-time", "现在几点", "当前本机时间", ""),
        GoldenCase("gc-week", "今天是星期几", "今天是星期", ""),
        GoldenCase("gc-refund", "我要退款", "退款", ""),
        GoldenCase("gc-empty", "", "未收到有效", ""),
    ]


def run_suite(*, use_checkpointer: bool = False) -> tuple[int, int]:
    """返回 (通过数, 总数)；用于 `sys.exit` 模拟 CI。"""

    app = SupportDeskApplication(use_checkpointer=use_checkpointer)
    suite = default_suite()
    passed = 0
    for c in suite:
        tid = f"reg-{c.case_id}"
        st = build_initial_state(request_id=c.case_id, user_message=c.user_message, mode="llm")
        out = app.handle(st, thread_id=tid)
        fr = (out.get("final_reply") or "").strip()
        ok = c.reply_needle in fr if c.reply_needle else False
        if ok:
            passed += 1
        print(f"[regression] {c.case_id} {'PASS' if ok else 'FAIL'} final_reply_head={fr[:60]!r}")
    return passed, len(suite)
