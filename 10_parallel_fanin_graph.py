"""
第十课：并行分支与聚合（Fan-out / Fan-in）

与第 4c 课关系：
----------------
- **04c** 用静态多分边 + `Annotated[list, operator.add]` 讲清「并行写同一槽位要 reducer」，
  并对比**依赖链串行**与**兄弟并行**的调度差异。
- **本课**假定你已理解 reducer，转而强调 **fan-in（聚合）**：分支各自追加**片段**，
  再由 **唯一**节点 `aggregate` 读全量片段、生成**单一** `final_report`（标量字段只由聚合写，
  避免多路争用）。

图结构：

    START → fan_out ─┬─→ branch_1 ──┐
                     ├─→ branch_2 ──┼─→ aggregate → END
                     └─→ branch_3 ──┘

前置：04b（reducer）、04c（静态 fan-out）；动态条数 fan-out 仍见 04b `Send`。

自第 7 课起：正文关键步骤附行内注释；Java 对照见 `java/.../l10_parallel_fanin_graph/`。
"""

from __future__ import annotations  # 注解前向引用

import operator  # list 追加型 reducer
from pathlib import Path  # 导出 PNG

from typing import Annotated  # Reducer 元数据

from typing_extensions import TypedDict  # 状态 schema

from langgraph.graph import END, START, StateGraph  # 图 API


class ParallelFanInState(TypedDict):
    """
    request_id：调用方传入的业务键（演示用）。
    task_hint：fan_out 写入，分支只读，避免分支依赖原始请求以外的隐式全局。
    fragments：并行分支都只往此列表贡献一条字符串，必须用 reducer 合并。
    final_report：仅 aggregate 写入；标量「汇总结果」由单节点产出，毋须 reducer。
    """

    request_id: str
    task_hint: str
    fragments: Annotated[list[str], operator.add]
    final_report: str


def fan_out(state: ParallelFanInState) -> dict:
    """扇出前的准备：写 hint，不写 final_report（留给聚合）。"""
    rid = state["request_id"]
    print(f"  [fan_out] 为 request_id={rid!r} 准备三路并行分支")
    return {"task_hint": f"scope:{rid}"}  # 分支将读取此字段


def branch_1(state: ParallelFanInState) -> dict:
    hint = state.get("task_hint") or ""
    print(f"  [branch_1] 模拟 IO/子任务 A，hint={hint!r}")
    return {"fragments": [f"branch_1: 完成 A · {hint}"]}  # 单元素列表，交给 operator.add


def branch_2(state: ParallelFanInState) -> dict:
    hint = state.get("task_hint") or ""
    print(f"  [branch_2] 模拟 IO/子任务 B，hint={hint!r}")
    return {"fragments": [f"branch_2: 完成 B · {hint}"]}


def branch_3(state: ParallelFanInState) -> dict:
    hint = state.get("task_hint") or ""
    print(f"  [branch_3] 模拟 IO/子任务 C，hint={hint!r}")
    return {"fragments": [f"branch_3: 完成 C · {hint}"]}


def aggregate(state: ParallelFanInState) -> dict:
    """
    Fan-in：屏障之后执行；读齐 fragments，生成最终报告。
    工程上可在此做排序、去重、冲突检测、调用下游预算裁剪等。
    """
    frags = state["fragments"]
    ordered = sorted(frags)  # 固定顺序，便于对齐验收与截图 diff
    body = "\n".join(ordered)
    report = "=== 并行汇总 ===\n" + body + f"\n=== 共 {len(frags)} 条分支产出 ===\n"
    print("\n[aggregate] 单点写入 final_report（多分支不写此键）")
    return {"final_report": report}


def build_parallel_fanin_graph():
    """
    START → fan_out ─┬─→ branch_* ─┼─→ aggregate → END

    `add_edge([...], "aggregate")`：列齐上游 = **join 屏障**，三路都完成后才进入聚合。
    """
    g = StateGraph(ParallelFanInState)
    g.add_node("fan_out", fan_out)  # 扇出前准备
    g.add_node("branch_1", branch_1)  # 并行分支 1
    g.add_node("branch_2", branch_2)
    g.add_node("branch_3", branch_3)
    g.add_node("aggregate", aggregate)  # fan-in 汇总

    g.add_edge(START, "fan_out")  # 入口
    g.add_edge("fan_out", "branch_1")  # 静态 fan-out：同一父节点三条出边
    g.add_edge("fan_out", "branch_2")
    g.add_edge("fan_out", "branch_3")
    g.add_edge(["branch_1", "branch_2", "branch_3"], "aggregate")  # 全员到齐再聚合
    g.add_edge("aggregate", END)
    return g.compile()


def export_graph_png(compiled_graph, filename: str) -> None:
    graph_obj = compiled_graph.get_graph()
    png_path = Path(__file__).with_name(filename)
    mermaid_path = Path(__file__).with_name(filename.replace(".png", ".mmd"))
    try:
        png_path.write_bytes(graph_obj.draw_mermaid_png())
        print(f"[图导出] {png_path}")
    except Exception as exc:  # noqa: BLE001
        mermaid_path.write_text(graph_obj.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mermaid_path}")


def demo() -> None:
    initial: ParallelFanInState = {
        "request_id": "REQ-10-demo",
        "task_hint": "",
        "fragments": [],
        "final_report": "",
    }

    print("=" * 72)
    print("并行 fan-out / fan-in：fragment 列表 + 单点 aggregate")
    print("=" * 72)
    app = build_parallel_fanin_graph()
    final = app.invoke(initial)  # type: ignore[arg-type]
    print("\n最终 state（节选）：")
    print("  final_report:\n")
    print(final.get("final_report", ""))

    print("\n" + "=" * 72)
    print('stream(stream_mode="updates")：观察 barrier 前多分支、后 aggregate')
    print("=" * 72)
    for i, chunk in enumerate(
        app.stream(initial, stream_mode="updates"),  # type: ignore[arg-type]
        start=1,
    ):
        print(f"  --- chunk #{i} ---")
        for node_name, delta in chunk.items():
            print(f"  [{node_name}] {delta}")

    export_graph_png(app, "10_parallel_fanin_graph.png")

    print("\n边界提示：若多分支在同一 superstep 写同一**标量**槽位且无 reducer，仍会触发")
    print("InvalidUpdateError（与 04b/04c 相同）；本课用「只写 fragments + 聚合写 report」规避。")
    print("权衡：并行度越高，aggregate 侧内存/复杂度通常越大，宜按业务切片或分层聚合。")


if __name__ == "__main__":
    demo()
