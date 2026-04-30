"""
04c：静态 Fan-out（固定拆边）与 04b 动态 Send 的对照

04b（动态 fan-out）回顾：
------------------------
- 在 **START 的条件边** 上挂 `fan_out_sends()`，**运行时**根据 `state["topics"]`
  生成 `list[Send]`，并行次数和内容都随输入变化。

04c（静态 fan-out）本课要点：
---------------------------
- **不**在路由函数里造 Send 列表，而是在建图时 **显式添加多条边**，例如：
    `add_edge("dosth", "w_a")`、`add_edge("dosth", "w_b")`、`add_edge("dosth", "w_c")`
- 图结构在代码里是**写死的**：每次运行都是这三分支并行（除非改代码）。
- **依赖**会拆 superstep：例如 `A→B→C` 链路上，`B` 必须等 `A` 写完状态后才会就绪，
  因而 `B` 与 `A` **不可能**在同一 superstep 里与 `A` 并列执行（与「同父多子无彼此依赖」的并行相反）。
- LangGraph 约束：若同一 **superstep** 里多个节点都往**同一个** state 字段写，
  该字段仍需要 **Annotated + reducer**（与 04b 相同道理）。

合并（join）：
-------------
- `add_edge(["w_a", "w_b", "w_c"], "join")` 表示：**三个上游都结束后**才执行 `join`。
  这是「等全员到齐再汇总」的静态写法。

本脚本：
1. 演示静态 fan-out + Annotated reducer 的正确用法
2. 演示去掉 reducer 时与 04b 相同的 InvalidUpdateError（对照）
3. **依赖链对照**：`step_1 → step_2 → step_3` 全串行——后一等前驱结束，无法与前一节点同一 superstep
4. **fan-out 图** `stream(stream_mode="updates")`（与 §3 对照）+ 导出图 PNG

前置：04b_reducer_graph.py
"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph


class StaticFanoutState(TypedDict):
    """
    seed：仅便于节点里打印/演示，静态三分支与 seed 无必然关系。
    notes：并行分支都往这里追加；必须带 reducer。
    """

    seed: str
    notes: Annotated[list[str], operator.add]


class BrokenStaticFanoutState(TypedDict):
    """与上相同，但 notes 无 reducer，用于复现并行冲突。"""

    seed: str
    notes: list[str]


def worker_dosth(state: StaticFanoutState) -> dict:
    print("  [worker_dosth] 静态边 START→Dosth")
    return {"notes": [f"Dosth: 收到 seed={state['seed']!r}"]}

def worker_a(state: StaticFanoutState) -> dict:
    print("  [worker_a] 静态边 dosth→w_a")
    return {"notes": [f"A: 收到 seed={state['seed']!r}"]}


def worker_b(state: StaticFanoutState) -> dict:
    print("  [worker_b] 静态边 dosth→w_b")
    return {"notes": [f"B: 收到 seed={state['seed']!r}"]}


def worker_c(state: StaticFanoutState) -> dict:
    print("  [worker_c] 静态边 dosth→w_c")
    return {"notes": [f"C: 收到 seed={state['seed']!r}"]}


def worker_a_broken(state: BrokenStaticFanoutState) -> dict:
    print("  [worker_a_broken]")
    return {"notes": ["a"]}


def worker_b_broken(state: BrokenStaticFanoutState) -> dict:
    print("  [worker_b_broken]")
    return {"notes": ["b"]}


def worker_c_broken(state: BrokenStaticFanoutState) -> dict:
    print("  [worker_c_broken]")
    return {"notes": ["c"]}


def join_all(state: StaticFanoutState) -> dict:
    """
    汇合节点：仅在 w_a、w_b、w_c 全部完成后被调用。
    这里只做汇总打印，不必须再写 notes。
    """
    print("\n[join_all] 三分支已完成，当前 notes：")
    for line in state["notes"]:
        print(f"    - {line}")
    return {}


def join_all_broken(state: BrokenStaticFanoutState) -> dict:
    print("\n[join_all_broken]（不应在无 reducer 成功场景下跑到这里）")
    return {}


def build_graph_with_reducer():
    """
    静态 fan-out + join：

        START → dosth ─┬─→ w_a ──┐
                       ├─→ w_b ─┼─→ join_all → END
                       └─→ w_c ──┘
    """
    b = StateGraph(StaticFanoutState)
    b.add_node("dosth", worker_dosth)
    b.add_node("w_a", worker_a)
    b.add_node("w_b", worker_b)
    b.add_node("w_c", worker_c)
    b.add_node("join_all", join_all)

    # 静态 fan-out：同一起点三条边，无需 Send、无需路由函数返回值。
    b.add_edge(START, "dosth")
    b.add_edge("dosth", "w_a")
    b.add_edge("dosth", "w_b")
    b.add_edge("dosth", "w_c")

    # 静态 join：列齐所有上游后进入 join_all
    b.add_edge(["w_a", "w_b", "w_c"], "join_all")
    b.add_edge("join_all", END)
    return b.compile()


# ---------------------------------------------------------------------------
# 依赖链：后继依赖前驱 → 必须占用后续 superstep，无法「并到前驱那一拍」
# ---------------------------------------------------------------------------
class ChainDemoState(TypedDict):
    seed: str
    notes: Annotated[list[str], operator.add]


def chain_step_1(_: ChainDemoState) -> dict:
    print("  [step_1] 无前驱，第一拍即可运行")
    return {"notes": ["step_1 done"]}


def chain_step_2(state: ChainDemoState) -> dict:
    print("  [step_2] 依赖 step_1：只有前驱已写入 notes 才可能就绪")
    n = len(state["notes"])
    return {"notes": [f"step_2 (运行至此已有 {n} 条 notes)"]}


def chain_step_3(state: ChainDemoState) -> dict:
    print("  [step_3] 依赖 step_2：链式最后一环")
    n = len(state["notes"])
    return {"notes": [f"step_3 (运行至此已有 {n} 条 notes)"]}


def build_linear_dependency_graph():
    """
    START → step_1 → step_2 → step_3 → END

    与「dosth 同时扇出 w_a/w_b/w_c」对比：这里每一步都是下一步的**唯一前驱**，
    整段在调度上是串行多拍；`step_2` 不可能与 `step_1` 同一 superstep。
    """
    b = StateGraph(ChainDemoState)
    b.add_node("step_1", chain_step_1)
    b.add_node("step_2", chain_step_2)
    b.add_node("step_3", chain_step_3)
    b.add_edge(START, "step_1")
    b.add_edge("step_1", "step_2")
    b.add_edge("step_2", "step_3")
    b.add_edge("step_3", END)
    return b.compile()


def build_graph_without_reducer():
    """拓扑相同，notes 用 LastValue → 并行三写应报错。"""
    b = StateGraph(BrokenStaticFanoutState)
    b.add_node("w_a", worker_a_broken)
    b.add_node("w_b", worker_b_broken)
    b.add_node("w_c", worker_c_broken)
    b.add_node("join_all", join_all_broken)

    b.add_edge(START, "w_a")
    b.add_edge(START, "w_b")
    b.add_edge(START, "w_c")
    b.add_edge(["w_a", "w_b", "w_c"], "join_all")
    b.add_edge("join_all", END)
    return b.compile()


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
    initial = {"seed": "hello-static-fanout", "notes": []}

    print("=" * 72)
    print("1) 无 reducer：静态三分支并行写 notes，预期 InvalidUpdateError")
    print("=" * 72)
    bad = build_graph_without_reducer()
    try:
        bad.invoke(initial)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        print(f"捕获到异常（符合预期）：\n  {type(exc).__name__}: {exc}\n")

    print("=" * 72)
    print("2) 有 reducer：静态 fan-out → 合并 notes → join_all")
    print("=" * 72)
    good = build_graph_with_reducer()
    final = good.invoke(initial)  # type: ignore[arg-type]
    print("\n最终 state：")
    for k, v in final.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 72)
    print("3) 依赖链：step_1 → step_2 → step_3（后继不能与前驱同一 superstep）")
    print("=" * 72)
    print(
        "  拓扑里没有「兄弟并行」：`step_2` 的唯一入边来自 `step_1`，引擎必须在后续拍里才允许 `step_2`。\n"
        "  下面 `stream` 中你会看到 step_1 / step_2 / step_3 分属不同更新档（与 §4 fan-out 对照）。\n"
        "  注：流式 chunk 与 superstep 不必一一对应，但「有边 A->B 则 B 不能早于 A」始终成立。\n"
    )
    chain_initial: ChainDemoState = {"seed": "linear-chain", "notes": []}
    chain_g = build_linear_dependency_graph()
    chain_final = chain_g.invoke(chain_initial)
    print("  最终 state notes：", chain_final["notes"])
    print("  stream(stream_mode=\"updates\"):")
    for i, chunk in enumerate(
        chain_g.stream(chain_initial, stream_mode="updates"),  # type: ignore[arg-type]
        start=1,
    ):
        print(f"  --- chunk #{i} ---")
        for node_name, delta in chunk.items():
            print(f"  [{node_name}] {delta}")

    print("\n" + "=" * 72)
    print('4) fan-out 图 stream(stream_mode="updates")（对照 §3）')
    print("=" * 72)
    for i, chunk in enumerate(
        good.stream(initial, stream_mode="updates"),  # type: ignore[arg-type]
        start=1,
    ):
        print(f"  --- chunk #{i} ---")
        for node_name, delta in chunk.items():
            print(f"  [{node_name}] {delta}")

    export_graph_png(good, "04c_static_fanout_graph.png")

    print("\n与 04b 对比记忆：")
    print("- 04b：条数/内容由 state 决定，return list[Send]")
    print("- 04c：条数写死在 add_edge 里，固定三分支 + join 列表")


if __name__ == "__main__":
    demo()
