"""
04d：Reducer 合并策略示例（除 `operator.add` 以外）

本课前提（与 04b / 04c 一致）：
----------------------------
- 多个分支在**同一 superstep** 里对**同一个** state key 提交更新时，
  必须为该 key 声明 `Annotated[类型, reducer]`。
- `reducer(old, new) -> merged`：引擎按实现方式把多次更新两两归并。

本文件演示多种**二元合并函数**（不限于列表拼接）。

关于「`add_edge([w_a,w_b,w_c], join)` 是不是 reducer？」：
--------------------------------------------------------
- **不是**。那句的意思是：**Join / 屏障**——要等 `w_a、w_b、w_c` 都跑完，才允许执行 `join`。
- **Reducer**只出现在 **TypedDict 里 `Annotated[..., 你的函数]`**，用来定义**同一个 key 多次写入怎么合成一个值**。

下面每个 `demo_*` 都是：START 静态三分支并行 → 写同一个带 reducer 的字段 → 汇合后打印最终 state。

输出顺序提示：join 节点可能在并行调度/线程里执行，`print` 默认带缓冲。
在非交互终端里若不加 `flush=True`，上一 demo 的 join 输出可能拖到下一 demo 标题之后才出现（看起来像「4）里混入了 3）的内容」）。因此图内回调里的演示用 `print` 一律 `flush=True`。
"""

from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph


# ---------------------------------------------------------------------------
# 1) 集合：并集 —— 标准库 `operator.or_`（对 set 即 `|` 并集）
# ---------------------------------------------------------------------------
class SetUnionState(TypedDict):
    tags: Annotated[set[str], operator.or_]


def su_a(_: SetUnionState) -> dict:
    return {"tags": {"from_a"}}


def su_b(_: SetUnionState) -> dict:
    return {"tags": {"from_b", "shared"}}


def su_c(_: SetUnionState) -> dict:
    return {"tags": {"from_c", "shared"}}


def su_join(s: SetUnionState) -> dict:
    print(f"  [set_union] 合并后 tags = {sorted(s['tags'])}", flush=True)
    return {}


def demo_set_union() -> None:
    print("\n" + "=" * 72)
    print("1) Annotated[set[str], operator.or_]   并集（注意 shared 只出现一次）")
    print("=" * 72)
    b = StateGraph(SetUnionState)
    for name, fn in (("su_a", su_a), ("su_b", su_b), ("su_c", su_c)):
        b.add_node(name, fn)
    b.add_node("join", su_join)
    b.add_edge(START, "su_a")
    b.add_edge(START, "su_b")
    b.add_edge(START, "su_c")
    b.add_edge(["su_a", "su_b", "su_c"], "join")
    b.add_edge("join", END)
    g = b.compile()
    out = g.invoke({"tags": set()})
    print("  最终:", out)


# ---------------------------------------------------------------------------
# 2) 数值：并行分支各报一个候选，取**最大值**
# ---------------------------------------------------------------------------
def reducer_max(a: int, b: int) -> int:
    """内置 max 无 inspect 签名，LangGraph 无法直接当作 reducer，需包一层。"""
    return a if a > b else b


class MaxScoreState(TypedDict):
    best: Annotated[int, reducer_max]


def mx_a(_: MaxScoreState) -> dict:
    return {"best": 3}


def mx_b(_: MaxScoreState) -> dict:
    return {"best": 9}


def mx_c(_: MaxScoreState) -> dict:
    return {"best": 5}


def mx_join(s: MaxScoreState) -> dict:
    print(f"  [max] 合并后 best = {s['best']}", flush=True)
    return {}


def demo_max_int() -> None:
    print("\n" + "=" * 72)
    print("2) Annotated[int, reducer_max]   并行上报分数，保留最大（内置 max 需包装，见 reducer_max）")
    print("=" * 72)
    b = StateGraph(MaxScoreState)
    for name, fn in (("mx_a", mx_a), ("mx_b", mx_b), ("mx_c", mx_c)):
        b.add_node(name, fn)
    b.add_node("join", mx_join)
    b.add_edge(START, "mx_a")
    b.add_edge(START, "mx_b")
    b.add_edge(START, "mx_c")
    b.add_edge(["mx_a", "mx_b", "mx_c"], "join")
    b.add_edge("join", END)
    g = b.compile()
    out = g.invoke({"best": 0})
    print("  最终:", out)


# ---------------------------------------------------------------------------
# 3) 字符串：多行日志拼接（自定义 reducer，避免误用会炸的 `operator.or_`）
# ---------------------------------------------------------------------------
def merge_lines(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    return f"{left}\n{right}"


class LogState(TypedDict):
    log: Annotated[str, merge_lines]


def lg_a(_: LogState) -> dict:
    return {"log": "[A] 第一条"}


def lg_b(_: LogState) -> dict:
    return {"log": "[B] 第二条"}


def lg_c(_: LogState) -> dict:
    return {"log": "[C] 第三条"}


def lg_join(s: LogState) -> dict:
    print("  [merge_lines] 合并后 log:\n" + s["log"].replace("\n", "\n    "), flush=True)
    return {}


def demo_merge_str() -> None:
    print("\n" + "=" * 72)
    print("3) Annotated[str, merge_lines]   自定义字符串按行拼接")
    print("=" * 72)
    b = StateGraph(LogState)
    for name, fn in (("lg_a", lg_a), ("lg_b", lg_b), ("lg_c", lg_c)):
        b.add_node(name, fn)
    b.add_node("join", lg_join)
    b.add_edge(START, "lg_a")
    b.add_edge(START, "lg_b")
    b.add_edge(START, "lg_c")
    b.add_edge(["lg_a", "lg_b", "lg_c"], "join")
    b.add_edge("join", END)
    g = b.compile()
    out = g.invoke({"log": ""})
    print("  最终 log 字段长度:", len(out["log"]))


# ---------------------------------------------------------------------------
# 4) 列表：只保留「当前这一轮合并里后递交的那一段」（演示用，并行顺序不稳定）
# ---------------------------------------------------------------------------
def take_last_list(_left: list[str], right: list[str]) -> list[str]:
    """归并时永远丢弃左累积，只保留 right。并行场景下最终是哪一支，取决于引擎归并顺序。"""
    return right


class LastListState(TypedDict):
    payload: Annotated[list[str], take_last_list]


def ll_a(_: LastListState) -> dict:
    return {"payload": ["branch-A"]}


def ll_b(_: LastListState) -> dict:
    return {"payload": ["branch-B"]}


def ll_c(_: LastListState) -> dict:
    return {"payload": ["branch-C"]}


def ll_join(s: LastListState) -> dict:
    print(f"  [take_last_list] 最终 payload = {s['payload']}（并行时可能不固定）", flush=True)
    return {}


def demo_take_last_list() -> None:
    print("\n" + "=" * 72)
    print("4) Annotated[list[str], take_last_list]   只保留最后一次写入的列表（顺序敏感，慎用于并行）")
    print("=" * 72)
    b = StateGraph(LastListState)
    for name, fn in (("ll_a", ll_a), ("ll_b", ll_b), ("ll_c", ll_c)):
        b.add_node(name, fn)
    b.add_node("join", ll_join)
    b.add_edge(START, "ll_a")
    b.add_edge(START, "ll_b")
    b.add_edge(START, "ll_c")
    b.add_edge(["ll_a", "ll_b", "ll_c"], "join")
    b.add_edge("join", END)
    g = b.compile()
    out = g.invoke({"payload": []})
    print("  最终:", out)


# ---------------------------------------------------------------------------
# 5) 列表：去重合并（自定义：按出现顺序拼接再 uniq）
# ---------------------------------------------------------------------------
def merge_unique_in_order(left: list[str], right: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in left + right:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


class UniqueListState(TypedDict):
    ids: Annotated[list[str], merge_unique_in_order]


def uq_a(_: UniqueListState) -> dict:
    return {"ids": ["u1", "u2"]}


def uq_b(_: UniqueListState) -> dict:
    return {"ids": ["u2", "u3"]}


def uq_c(_: UniqueListState) -> dict:
    return {"ids": ["u1", "u4"]}


def uq_join(s: UniqueListState) -> dict:
    print(f"  [merge_unique_in_order] ids = {s['ids']}", flush=True)
    return {}


def demo_unique_merge() -> None:
    print("\n" + "=" * 72)
    print("5) 自定义 merge_unique_in_order   拼接后按首次出现去重")
    print("=" * 72)
    b = StateGraph(UniqueListState)
    for name, fn in (("uq_a", uq_a), ("uq_b", uq_b), ("uq_c", uq_c)):
        b.add_node(name, fn)
    b.add_node("join", uq_join)
    b.add_edge(START, "uq_a")
    b.add_edge(START, "uq_b")
    b.add_edge(START, "uq_c")
    b.add_edge(["uq_a", "uq_b", "uq_c"], "join")
    b.add_edge("join", END)
    g = b.compile()
    out = g.invoke({"ids": []})
    print("  最终:", out)


def main() -> None:
    print(__doc__)
    demo_set_union()
    demo_max_int()
    demo_merge_str()
    demo_take_last_list()
    demo_unique_merge()
    print("\n小结：reducer = TypedDict 里 Annotated 的第二个参数；join = add_edge([...], 节点) 调度语义。")


if __name__ == "__main__":
    main()
