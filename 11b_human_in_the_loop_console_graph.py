"""
11b：第十一课「控制台真人操作」练手（可与脚本化版对照）

与 `11_human_in_the_loop_graph.py` 的图结构、状态、`interrupt()` / `Command(resume)` **完全一致**；
本文件仅从磁盘加载该课模块，用 **while 循环 + input()** 在终端里根据你的输入决定 `resume` 载荷，
而不是写死若干种 `Command(resume=...)`。

用法：在仓库根目录执行 `python 11b_human_in_the_loop_console_graph.py`（需已安装大纲版 `langgraph`）。

说明：Windows 控制台若中文乱码，可先执行 `chcp 65001` 或使用 UTF-8 终端。
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any

from langgraph.types import Command

# 模块名不能以数字开头，用 importlib 从同目录加载第 11 课脚本
_L11_PATH = Path(__file__).resolve().parent / "11_human_in_the_loop_graph.py"


def _load_l11():
    spec = importlib.util.spec_from_file_location("lesson11_hitl_impl", _L11_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载: {_L11_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _print_interrupt_summary(interrupts: list[Any]) -> None:
    for i, item in enumerate(interrupts, start=1):
        val = getattr(item, "value", item)
        print(f"\n── 挂起 #{i}（请将下列内容视作业面待审批项）──")
        if isinstance(val, dict):
            for k, v in val.items():
                preview = str(v)
                if len(preview) > 600:
                    preview = preview[:600] + "…"
                print(f"  {k}: {preview}")
        else:
            print(f"  {val!r}")


def _prompt_resume() -> dict[str, Any] | bool:
    """在控制台收集人工决策，返回将作为 `Command(resume=...)` 传入。"""
    print("\n请选择操作：")
    print("  [1] 通过 (approved)")
    print("  [2] 驳回 (rejected)")
    print("  [3] 修改并回流 agent (edit，需输入新草案)")
    print("  [q] 退出程序（图会停在当前中断点，下次可用同 thread_id 继续）")
    choice = input("输入 1 / 2 / 3 / q: ").strip().lower()

    if choice in ("q", "quit", "exit"):
        print("已退出；保留 checkpoint 需记下本次使用的 thread_id。")
        sys.exit(0)

    if choice == "1" or choice in ("a", "approve", "y"):
        return {"decision": "approved"}
    if choice == "2" or choice in ("r", "reject", "n"):
        return {"decision": "rejected"}
    if choice == "3" or choice in ("e", "edit"):
        print("请输入修改后的草案正文（**单行**；若要分段请先合成一行或多次用 edit）：")
        line = input("> ").strip()
        if not line:
            print("（空内容将仍视为 edit，沿用当前草案文本）")
        return {"decision": "edit", "edited_proposal": line}

    print("未识别选项，按 **驳回** 处理。")
    return {"decision": "rejected"}


def main() -> None:
    l11 = _load_l11()
    build_hitl_graph = l11.build_hitl_graph
    HitlState = l11.HitlState
    export_graph_png = l11.export_graph_png

    graph = build_hitl_graph()

    print("=" * 72)
    print("11b：人机协同 — 控制台交互（图逻辑同第 11 课）")
    print("=" * 72)

    default_tid = f"console-{uuid.uuid4().hex[:8]}"
    tid_in = input(f"thread_id（回车使用 {default_tid}）: ").strip()
    thread_id = tid_in or default_tid
    config = {"configurable": {"thread_id": thread_id}}

    topic = input("业务 topic（回车默认「控制台交互演示」）: ").strip() or "控制台交互演示"

    initial: HitlState = {
        "topic": topic,
        "proposal": "",
        "revision_count": 0,
        "human_decision": "",
        "final_output": "",
    }

    print("\n── 首次运行图（直至第一次 interrupt）──")
    result = graph.invoke(initial, config)

    while True:
        inter = result.get("__interrupt__")
        if inter:
            _print_interrupt_summary(list(inter))
            resume = _prompt_resume()
            print(f"\n… 使用 Command(resume={resume!r}) 恢复 …\n")
            result = graph.invoke(Command(resume=resume), config)
            continue

        print("\n" + "=" * 72)
        print("图已结束（当前线程无待处理 interrupt）")
        print("=" * 72)
        print("  topic:", result.get("topic", ""))
        print("  revision_count:", result.get("revision_count", ""))
        print("  human_decision:", result.get("human_decision", ""))
        fo = result.get("final_output", "")
        print("  final_output:")
        print(fo if fo else "（空）")
        break

    try:
        want_png = input("\n是否导出 PNG 到 11b_human_in_the_loop_console_graph.png？[y/N]: ").strip().lower()
    except EOFError:
        want_png = ""
    if want_png in ("y", "yes", "1"):
        export_graph_png(graph, "11b_human_in_the_loop_console_graph.png")


if __name__ == "__main__":
    main()
