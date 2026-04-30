"""
专题（插学）：状态模型与合并机制（Reducer）

为什么会有这一课？
-----------------
在 LangGraph 里，绝大多数状态字段默认是「单值通道」：同一个 step 内只允许写入一次。
当你用「并行」方式（例如多个 Send 同时跑）让两个子节点都去更新同一个 key 时，
如果没有声明「如何把多个更新合并成一个」，运行时会直接报错：

    InvalidUpdateError: At key 'xxx': Can receive only one value per step.
    Use an Annotated key to handle multiple values.

本脚本做四件事：
1. 用最小并行图 **复现** 上述错误（无 reducer）
2. 用 `typing.Annotated` + `operator.add` **修复**（列表按步合并为拼接）
3. 用 **`stream(stream_mode="updates")`** 打印每一档输出，便于对照「一步」长什么样
4. 对比「同一 key、同一步、多次写入」在有/无 reducer 时的行为差异

前置知识：请先完成第 1～4 课，理解 StateGraph、节点返回值、invoke。
"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated, NotRequired

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send


# ---------------------------------------------------------------------------
# 关于 reducer 可写哪些「二元函数」
# ---------------------------------------------------------------------------
# LangGraph 要求 Annotated 上的 reducer 形如 (accumulated, update) -> new_accumulated。
# - `operator.add` 对 list 即列表拼接，所以本课用它做「合并多条并行说明」最自然。
#
# 常见误区（与你的终端报错对应）：
# 1) `operator.or_`：在 Python 里会对两个操作数做「按位或 / __or__」。
#    两个 list 没有定义 `|`，故运行时报：TypeError: unsupported operand type(s) for |: 'list' and 'list'
# 2) `operator.first` / `operator.last`：标准库 operator **根本没有**这两个名字，
#    故在解析 TypedDict 时就报：AttributeError: module 'operator' has no attribute 'first'
#
# 若要「只保留先到的」或「只保留最后合并到的」一类语义，请自己写函数，例如：
#   def take_last(_left: list[str], right: list[str]) -> list[str]:
#       return right
#   def take_first(left: list[str], _right: list[str]) -> list[str]:
#       return left
# 注意：并行任务两两 fold 时顺序通常**不稳定**，first/last 的语义在工程上要自己确认是否可接受。
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 状态 schema
# ---------------------------------------------------------------------------
# topics:  fan-out 前要处理的条目列表（本例由初始 invoke 传入）
# notes:   各并行 worker 都会往这个字段里「追加」说明文字
# topic:   只在 Send 派生子调用时使用（父状态里没有也没关系）
#
# 重点：notes 必须带 reducer，否则并行 worker 同一步都写 notes 会冲突。
class MapReduceState(TypedDict):
    topics: list[str]
    notes: Annotated[list[str], operator.add]
    topic: NotRequired[str]


# 故意做成「无 reducer 的列表字段」用于对照实验
class BrokenParallelState(TypedDict):
    topics: list[str]
    notes: list[str]  # 没有 Annotated → 默认 LastValue，同一步只能接受一个更新
    topic: NotRequired[str]


def fan_out_sends(state: MapReduceState | BrokenParallelState) -> list[Send]:
    """
    条件边路由函数：不返回下一个节点名，而是返回一批 Send。

    LangGraph 会为每个 Send 启动一次并行子执行，各自进入目标节点。
    这就是官方文档里 map-reduce / fan-out 的标准写法。
    """
    return [Send("annotate_topic", {"topic": t}) for t in state["topics"]]


def annotate_topic(state: MapReduceState) -> dict:
    """
    并行 worker：根据当前子状态里的 topic 写一条说明，往 notes 里「追加」一条。

    注意返回值里 notes 是「长度为 1 的列表」。
    有了 operator.add 后，多个这样的列表会在本 step 内被拼成一个大列表。
    """
    topic = state.get("topic", "?")
    line = f"[{topic}] 这是并行节点生成的一行说明。"
    print(f"  [annotate_topic] topic={topic!r} -> 追加 1 条 notes")
    return {"notes": [line]}


def annotate_topic_broken(state: BrokenParallelState) -> dict:
    """与 annotate_topic 相同逻辑，但配合 BrokenParallelState 使用（会触发冲突）。"""
    topic = state.get("topic", "?")
    line = f"[{topic}] 说明。"
    print(f"  [annotate_topic_broken] topic={topic!r}")
    return {"notes": [line]}


def build_graph_with_reducer():
    """
    正确示例：notes 使用 Annotated[list, operator.add]，支持同一步多次追加。

    图结构：
        START --(Send 列表)--> annotate_topic（并行多次）--> END
    """
    builder = StateGraph(MapReduceState)
    builder.add_node("annotate_topic", annotate_topic)
    builder.add_conditional_edges(START, fan_out_sends)
    builder.add_edge("annotate_topic", END)
    return builder.compile()


def build_graph_without_reducer():
    """
    对照示例：notes 为普通 list 字段 → 同一步内只允许写入一次。

    与 build_graph_with_reducer topology 相同，仅 state schema 不同。
    """
    builder = StateGraph(BrokenParallelState)
    builder.add_node("annotate_topic", annotate_topic_broken)
    builder.add_conditional_edges(START, fan_out_sends)
    builder.add_edge("annotate_topic", END)
    return builder.compile()


def demo_stream_updates(compiled_graph, initial: dict) -> None:
    """
    用 stream 观察「对外的一格格输出」。

    stream_mode=\"updates\" 时，每次 yield 的大致形状是：
    { 节点名: 该节点本次返回的 state 更新片段 }

    重要：**stream 的一个 chunk 不必等于引擎内部的「一个 superstep」**。
    在本机 LangGraph 版本中，三个并行 annotate_topic 往往会出现 **连续 3 个 chunk**，
    每个 chunk 里 `notes` 仍是一条；**reducer 在引擎把多次写入合并进完整 state 时**才拼成最终长列表。
    因此观察 stream 时：把 chunk 当作「有一次节点写回暴露了」，不要强行和「一步」划等号。
    """
    print("=" * 72)
    print('3) stream(stream_mode="updates")：观察每一档更新')
    print("=" * 72)
    chunk_idx = 0
    for chunk in compiled_graph.stream(initial, stream_mode="updates"):  # type: ignore[arg-type]
        chunk_idx += 1
        print(f"  --- chunk #{chunk_idx} ---")
        if not chunk:
            print("  (空)")
            continue
        for node_name, delta in chunk.items():
            print(f"  [{node_name}] {delta}")
    print()


def export_graph_png(compiled_graph, filename: str) -> None:
    """运行后导出图 PNG（失败则写 mermaid，与第六课一致）。"""
    graph_obj = compiled_graph.get_graph()
    png_path = Path(__file__).with_name(filename)
    mermaid_path = Path(__file__).with_name(filename.replace(".png", ".mmd"))
    try:
        png_path.write_bytes(graph_obj.draw_mermaid_png())
        print(f"[图导出] {png_path}")
    except Exception as exc:  # noqa: BLE001
        mermaid_path.write_text(graph_obj.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mermaid_path}")


def demo_broken_then_fixed():
    initial = {
        "topics": ["A", "B", "C"],
        "notes": [],
    }

    print("=" * 72)
    print("1) 无 reducer：并行写入同一字段，预期报错")
    print("=" * 72)
    bad = build_graph_without_reducer()
    try:
        bad.invoke(initial)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        print(f"捕获到异常（符合预期）：\n  {type(exc).__name__}: {exc}\n")
    else:
        print("未报错：若你看到这行，请检查 LangGraph 版本或并行语义是否变化。\n")

    print("=" * 72)
    print("2) 有 reducer（Annotated + operator.add）：并行结果合并为一条列表")
    print("=" * 72)
    good = build_graph_with_reducer()
    out = good.invoke(initial)  # type: ignore[arg-type]
    print("最终 state：")
    for k, v in out.items():
        print(f"  {k}: {v}")

    demo_stream_updates(good, initial)  # type: ignore[arg-type]

    export_graph_png(good, "04b_reducer_graph.png")

    print("\n学习要点：")
    print("- 并行（多 Send）同一步写同一 key → 需要 reducer 或改用不同 key 再汇总")
    print("- `Annotated[list[str], operator.add]` 表示：本步内多个列表更新按 + 合并")
    print("- `stream(updates)` 的 chunk 数未必等于 superstep 数；以打印为准，最终 state 以 invoke 结果为准")
    print("- 自定义合并可写 `(old, new) -> merged` 函数，签名参见 StateGraph 文档")


if __name__ == "__main__":
    demo_broken_then_fixed()
