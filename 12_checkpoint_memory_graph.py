"""
第十二课：持久化与记忆（Checkpoint / Memory）

与第 11 课关系：
----------------
- 第 11 课已用 **`InMemorySaver`** + **`thread_id`** 支撑 `interrupt()` / `Command(resume)`。
- 本课把 checkpoint 当成**一等概念**：多读一眼 **`get_state` / `get_state_history`**，并区分
  **「图内短期状态（checkpoint 里）」** 与 **「长期记忆（图外存储）」** 的边界。

短期 vs 长期（工程心智模型）：
-----------------------------
- **短期（本课核心）**：每个 `thread_id` 一条 checkpoint 链——多轮 `invoke`、HITL resume、
  同会话第二次从入口再跑时，都会在**同一条链**上继续落盘（见 demo ③）。
- **长期**：用户画像、知识库、跨会话摘要等多存在 **向量库 / SQL / OSS**，由你在节点内读写；
  LangGraph checkpoint **不负责**替你托管这类数据。

持久化介质：
-----------
- 本课仍用 **`InMemorySaver`**（仓库 `langgraph==1.1.10` 自带），进程退出即失。
- **生产**可选用官方扩展包中的 **SQLite / Postgres** 等 checkpointer（本脚本不新增依赖，
  大纲正文仅点名；安装后把 `compile(checkpointer=...)` 换成对应 `Saver` 即可）。

自第 7 课起：关键步骤附简短行内注释。
"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


class SessionState(TypedDict):
    """会话内状态：演示 checkpoint 如何随节点推进而快照。"""

    user_text: str  # 用户或上游注入的文本；二次 invoke 时会被输入合并覆盖
    step_count: int  # 累计节点步数（教学计数）
    trace: Annotated[list[str], operator.add]  # 每节点追加一条，便于看历史


def normalize(state: SessionState) -> dict:
    t = (state.get("user_text") or "").strip()
    print(f"  [normalize] 收到 user_text={t!r}")
    return {"step_count": int(state.get("step_count") or 0) + 1, "trace": [f"normalize:{t[:24]}"]}


def enrich(state: SessionState) -> dict:
    base = (state.get("user_text") or "").strip()
    print(f"  [enrich] step_count={state.get('step_count')}")
    return {"step_count": int(state.get("step_count") or 0) + 1, "trace": [f"enrich:len={len(base)}"]}


def summarize(state: SessionState) -> dict:
    tr = state.get("trace") or []
    print(f"  [summarize] 当前 trace 条数={len(tr)}")
    return {"step_count": int(state.get("step_count") or 0) + 1, "trace": [f"summarize:done"]}


def build_session_graph(checkpointer: InMemorySaver | None = None):
    """
    线性三节点，便于在 `get_state_history` 里看到多帧快照。

    图：START → normalize → enrich → summarize → END
    """
    cp = checkpointer if checkpointer is not None else InMemorySaver()
    g = StateGraph[SessionState, None, SessionState, SessionState](SessionState)
    g.add_node("normalize", normalize)
    g.add_node("enrich", enrich)
    g.add_node("summarize", summarize)
    g.add_edge(START, "normalize")
    g.add_edge("normalize", "enrich")
    g.add_edge("enrich", "summarize")
    g.add_edge("summarize", END)
    return g.compile(checkpointer=cp), cp


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
    saver = InMemorySaver()  # 显式持有同一实例，便于理解「所有 thread 存在这一个 saver 里」
    graph, _ = build_session_graph(saver)

    cfg_alice: dict = {"configurable": {"thread_id": "lesson-12-alice"}}
    cfg_bob: dict = {"configurable": {"thread_id": "lesson-12-bob"}}

    init: SessionState = {"user_text": "", "step_count": 0, "trace": []}

    print("=" * 72)
    print("① 两个 thread_id：同构图、不同会话，checkpoint 互不覆盖")
    print("=" * 72)
    out_a = graph.invoke({**init, "user_text": "Alice 问：退款流程？"}, cfg_alice)
    out_b = graph.invoke({**init, "user_text": "Bob 问：发票抬头？"}, cfg_bob)
    print("  Alice 终态 trace:", out_a.get("trace"))
    print("  Bob   终态 trace:", out_b.get("trace"))

    print("\n" + "=" * 72)
    print("② get_state：读取某 thread 当前「最新快照」（含 values / next / metadata）")
    print("=" * 72)
    snap_a = graph.get_state(cfg_alice)
    print("  Alice values:", snap_a.values)
    print("  Alice next（空元组通常表示已跑完当前步）:", snap_a.next)

    print("\n" + "=" * 72)
    print("③ get_state_history：倒序遍历 checkpoint 链（可观测「可重放」轨迹）")
    print("=" * 72)
    hist = list(graph.get_state_history(cfg_alice, limit=8))
    print(f"  Alice 最近 {len(hist)} 帧（新 → 旧）：")
    for i, s in enumerate(hist):
        ts = s.created_at or "?"
        keys = list(s.values.keys()) if isinstance(s.values, dict) else type(s.values)
        print(f"    #{i+1} ts={ts} values_keys={keys}")

    print("\n" + "=" * 72)
    print("④ 同一 thread 第二次 invoke：输入合并进 checkpoint，图从 START 再跑一轮")
    print("=" * 72)
    out_a2 = graph.invoke({"user_text": "Alice 追问：要多久？"}, cfg_alice)
    print("  Alice 第二轮后 trace 长度:", len(out_a2.get("trace") or []))
    print("  user_text 现为:", repr(out_a2.get("user_text")))

        
    print("\n" + "=" * 72)
    print("⑤ update_state（可选）：不跑节点，直接往状态里打补丁（调试/人工纠错）")
    print("=" * 72)
    new_cfg = graph.update_state(
        cfg_alice,
        {"user_text": "[人工订正] 由 update_state 写入"},
        as_node="summarize",
    )
    after_patch = graph.get_state(new_cfg)
    print("  patch 后 user_text:", after_patch.values.get("user_text"))

    print("\n" + "=" * 72)
    print("③ get_state_history：倒序遍历 checkpoint 链（可观测「可重放」轨迹）")
    print("=" * 72)
    hist = list(graph.get_state_history(cfg_alice, limit=18))
    print(f"  Alice 最近 {len(hist)} 帧（新 → 旧）：")
    for i, s in enumerate(hist):
        ts = s.created_at or "?"
        keys = list(s.values.keys()) if isinstance(s.values, dict) else type(s.values)
        print(f"    #{i+1} ts={ts} values={s.values.values()}")
        
    print("\n持久化扩展：生产可换 `langgraph-checkpoint-sqlite` / `langgraph-checkpoint-postgres` 等，"
          "接口仍是 `compile(checkpointer=...)` + 同一 `thread_id` 语义。")

    export_graph_png(graph, "12_checkpoint_memory_graph.png")


if __name__ == "__main__":
    demo()
