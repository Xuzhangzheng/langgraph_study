"""
第十一课：人机协同（Human-in-the-loop，HITL）

目标：
1) 在关键节点用 `interrupt()` **挂起**执行，把待审批内容交给外层（UI / 审批系统）
2) 使用 **checkpointer**（本课 `InMemorySaver`）+ **同一 `thread_id`** 恢复图状态
3) 用 `Command(resume=...)` 把人工决策**喂回** `interrupt()` 的返回值，继续执行
4) **审批 / 驳回 / 要求修改并回流** 三种路径（修改回流到 `agent_step` 再送审）

图结构（与大纲一致）：

    START → agent_step → human_review ──→ continue_flow → END
                                ├──→ end_rejected → END
                                └──→ agent_step（回流，再进入 human_review）

**注意**：恢复执行时，含 `interrupt()` 的节点会**从节点开头再跑一遍**；因此节点内 `interrupt()` 之前的代码应具备
可重入/幂等（官方文档「Resuming interrupts」一节）。

前置：第 3 课条件边与循环；第 12 课将展开更持久的 Checkpoint 存储。


本课依赖：`langgraph` 提供的 `interrupt`、`Command`、`InMemorySaver`（与大纲 `langgraph==1.1.10` 一致）。

Java 对照见 `java/.../l11_human_in_the_loop_graph/`（队列模拟人工输入，见该类 JavaDoc）。

**交互练手**：希望在终端里自己按键选择通过/驳回/修改时，请运行 `11b_human_in_the_loop_console_graph.py`（与本课共用同一张图）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class HitlState(TypedDict):
    """人机协同演示状态：草案 + 人工决策 + 终稿。"""

    topic: str  # 业务主题
    proposal: str  # 当前待审草案（agent 写；edit 时人工可改此字段）
    revision_count: int  # agent 轮次计数
    human_decision: str  # human_review 根据 resume 写入：approved / rejected / edit
    final_output: str  # continue_flow 或 end_rejected 写入


def agent_step(state: HitlState) -> dict:
    """模拟「智能体产出草案」：每进入一次就递增修订序号并生成一版 proposal。"""
    n = int(state.get("revision_count") or 0) + 1  # 新一轮修订
    topic = state.get("topic") or ""
    prev = (state.get("proposal") or "").strip()
    if prev:
        body = prev  # 若上一跳是 edit，proposal 已被人工改过，在此基础上再打标记   
    else:
        body = f"自动生成的首版要点（topic={topic!r}）"
    text = f"[修订 {n}] {body}"
    print(f"  [agent_step] -> {text[:72]}{'…' if len(text) > 72 else ''}")
    return {"revision_count": n, "proposal": text}


def human_review(state: HitlState) -> dict:
    """
    在节点内调用 interrupt：引擎落 checkpoint 并把 payload 暴露给调用方（如 `__interrupt__`）。
    `Command(resume=...)` 传入的值会成为此处 `interrupt()` 的返回值。
    """
    payload = {
        "待审批草案": state.get("proposal", ""),
        "当前修订轮次": state.get("revision_count", 0),
        "说明": "resume 请传 dict：{decision: approved|rejected|edit, edited_proposal?: str}",
    }
    # 恢复执行时本节点从开头重跑：会再次打印；随后 interrupt 将直接返回 resume 而非二次挂起
    print("  [human_review] interrupt(payload) …")
    raw = interrupt(payload)  # 挂起点；恢复后本节点从头执行，此处返回 resume 值
    decision = ""
    if isinstance(raw, dict):
        decision = str(raw.get("decision", "rejected")).strip().lower()
    elif raw is True:  # 兼容最小审批：resume True 视为通过
        decision = "approved"
    elif raw is False:
        decision = "rejected"
    out: dict = {"human_decision": decision}
    if decision == "edit":
        edited = raw.get("edited_proposal") if isinstance(raw, dict) else None
        out["proposal"] = str(edited if edited is not None else state.get("proposal", ""))
        print(f"  [human_review] 人工要求修改，已写回 proposal（len={len(out['proposal'])}）")
    else:
        print(f"  [human_review] 人工决策：{decision!r}")
    return out


def route_after_human(state: HitlState) -> Literal["continue_flow", "agent_step", "end_rejected"]:
    """根据 human_review 写入的 human_decision 分流。"""
    d = (state.get("human_decision") or "").lower()
    if d == "approved":
        return "continue_flow"
    if d == "edit":
        return "agent_step"
    return "end_rejected"


def continue_flow(state: HitlState) -> dict:
    """通过：把当前 proposal 定为终稿。"""
    print("  [continue_flow] 审批通过，写入 final_output")
    return {"final_output": state.get("proposal", "")}


def end_rejected(state: HitlState) -> dict:
    """驳回：不回流，给出说明。"""
    print("  [end_rejected] 已驳回")
    note = f"驳回（草案摘要）：{state.get('proposal', '')[:80]}"
    return {"final_output": note}


def build_hitl_graph():
    """编译带 checkpointer 的 HITL 图（必须 compile(checkpointer=...) 才能 interrupt）。"""
    g = StateGraph(HitlState)
    g.add_node("agent_step", agent_step)
    g.add_node("human_review", human_review)
    g.add_node("continue_flow", continue_flow)
    g.add_node("end_rejected", end_rejected)

    g.add_edge(START, "agent_step")
    g.add_edge("agent_step", "human_review")
    g.add_conditional_edges(
        "human_review",
        route_after_human,
        {
            "continue_flow": "continue_flow",
            "agent_step": "agent_step",
            "end_rejected": "end_rejected",
        },
    )
    g.add_edge("continue_flow", END)
    g.add_edge("end_rejected", END)
    return g.compile(checkpointer=InMemorySaver())  # 教学用内存 checkpoint；生产换持久化实现


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
    config = {"configurable": {"thread_id": "lesson-11-hitl-demo"}}  # 恢复时必须相同
    graph = build_hitl_graph()

    initial: HitlState = {
        "topic": "上线前风控策略变更",
        "proposal": "",
        "revision_count": 0,
        "human_decision": "",
        "final_output": "",
    }

    print("=" * 72)
    print("1) 首次 invoke：跑到 human_review 的 interrupt 后暂停")
    print("=" * 72)
    r1 = graph.invoke(initial, config)
    inter = r1.get("__interrupt__")
    print(f"  __interrupt__ 条数: {len(inter) if inter else 0}")
    if inter:
        print(f"  首条 payload 键: {list(inter[0].value.keys()) if isinstance(inter[0].value, dict) else type(inter[0].value)}")

    print("\n" + "=" * 72)
    print("2) resume：要求 edit（人工改稿）→ agent 再产出一版 → 再次 interrupt")
    print("=" * 72)
    r2 = graph.invoke(
        Command(resume={"decision": "edit", "edited_proposal": "【人工】加强审计日志保留期说明"}),
        config,
    )
    inter2 = r2.get("__interrupt__")
    print(f"  第二轮 __interrupt__ 条数: {len(inter2) if inter2 else 0}")

    print("\n" + "=" * 72)
    print("3) resume：approved → continue_flow → END")
    print("=" * 72)
    r3 = graph.invoke(Command(resume={"decision": "approved"}), config)
    print("  终态 final_output 前 200 字：")
    out = r3.get("final_output", "")
    print("  " + (out[:200] + "…") if len(out) > 200 else out)

    print("\n" + "=" * 72)
    print("4) 独立 thread：演示 rejected 短路到 end_rejected")
    print("=" * 72)
    cfg2 = {"configurable": {"thread_id": "lesson-11-reject-branch"}}
    graph.invoke(initial, cfg2)
    rj = graph.invoke(Command(resume={"decision": "rejected"}), cfg2)
    print(f"  final_output: {rj.get('final_output', '')[:120]}…")

    export_graph_png(graph, "11_human_in_the_loop_graph.png")

    print("\n要点：`interrupt()` 需 checkpointer + `thread_id`；`Command(resume=...)` 为恢复用入参。")


if __name__ == "__main__":
    demo()
