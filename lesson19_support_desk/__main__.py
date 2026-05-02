"""
入口：`python -m lesson19_support_desk`（工作目录为仓库根目录 `langgraph_study/`）。

子命令风格：默认 demo；`--regression` 跑黄金套件；`--export` 写拓扑图。
"""

from __future__ import annotations

import argparse
import json
import sys

from lesson19_support_desk.application import SupportDeskApplication, build_initial_state
from lesson19_support_desk.regression import run_suite
from lesson19_support_desk.workflow import export_workflow_diagram


def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson19 Capstone — 支持台应用")
    parser.add_argument("--regression", action="store_true", help="运行离线黄金套件（fallback）")
    parser.add_argument("--export", action="store_true", help="导出 workflow PNG/Mermaid")
    args = parser.parse_args()

    if args.regression:
        ok, total = run_suite(use_checkpointer=False)
        print(f"[regression] {ok}/{total} passed")
        sys.exit(0 if ok == total else 1)

    app = SupportDeskApplication(use_checkpointer=True)

    if args.export:
        export_workflow_diagram(app.compiled, "lesson19_support_desk_workflow.png")
        return

    demos = [
        ("d1", "计算 3*(4+5)", "demo-thread-1"),
        ("d2", "帮我查物流 单号 SF123", "demo-thread-2"),
        ("d3", "   ", "demo-thread-invalid"),
        ("d4", "今天是星期几", "demo-thread-4"),
    ]

    for request_id, message, thread_id in demos:
        st = build_initial_state(request_id=request_id, user_message=message, mode="llm")
        out = app.handle(st, thread_id=thread_id)
        print(json.dumps({"request_id": request_id, "final": out.get("final_reply"), "diag": out.get("diagnostics")}, ensure_ascii=False))
    export_workflow_diagram(app.compiled, "lesson19_support_desk_workflow.png")


if __name__ == "__main__":
    main()
