"""
第十三课：可观测性与调试（Observability / Debugging）

与前序课关系：
--------------
- 第 10 课已用 **`stream`** 观察并行屏障前后的 chunk；本课系统化 **`stream_mode`**
  与 **`logging`**、`RunnableConfig` 元数据，作为日常排障的组合拳。
- 第 12 课的 **`get_state` / `get_state_history`** 仍是对 checkpoint 的可观测入口；本课补全
  **「执行过程中」** 的粒度（每步 updates / checkpoints 事件等）。

本节要点（对照 `langgraph==1.1.10`）：
-----------------------------------
- **`stream_mode`**：`updates`（节点增量）、`values`（整状态快照）、`checkpoints`
  （与 checkpoint 对齐的事件）、`debug`（极尽详细，教学时少用以免刷屏）。
- **`print_mode`**：与 `stream_mode` 同枚举，仅 **打到控制台**，不改变迭代返回值。
- **`RunnableConfig`**：`tags`、`metadata` 常被 APM / 自建日志拦截器用来做运行关联。
- **`get_graph().draw_mermaid_png()`**：结构可视化仍是「这张图到底长什么样」的第一现场。

Failure Path：`input_text` 为空或包含子串 **`boom`** 时走入 `stub_error`，在 `diagnostics`
 里留下可检索的错误标记（模拟「如何把失败钉在轨迹上」）。

自第 7 课起：关键步骤附简短行内注释。
"""

from __future__ import annotations

import logging
import operator
from pathlib import Path
from typing import Annotated

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

# 本子图用标准 logging，避免与 LangGraph 内部 print 混在一起难以收敛格式。
_LOG = logging.getLogger("lesson13.obs")


class ObservabilityState(TypedDict):
    """教学最小状态：业务字段 + 可追加的诊断列表。"""

    request_id: str  # 与 config.metadata 对齐，演示「关联 ID」日志
    input_text: str
    diagnostics: Annotated[list[str], operator.add]  # 每节点可追加痕迹
    result_summary: str  # 终态可读摘要


def gate(state: ObservabilityState) -> dict:
    """入口：不写路由结果到 state（路由由条件边函数读取 state）。"""
    rid = state.get("request_id") or ""
    text = (state.get("input_text") or "").strip()
    _LOG.info("节点 gate 入参 request_id=%s input_len=%s", rid, len(text))
    return {
        "diagnostics": [f"gate:seen request_id={rid!r} len={len(text)}"],
    }


def route_after_gate(state: ObservabilityState) -> str:
    """条件边：空输入或显式故障关键字 → 诊断支路。"""
    text = (state.get("input_text") or "").strip()
    if not text:
        return "stub_error"
    if "boom" in text.lower():
        return "stub_error"
    return "process"


def process(state: ObservabilityState) -> dict:
    """主路径：模拟正常业务处理。"""
    rid = state.get("request_id") or ""
    text = (state.get("input_text") or "").strip()
    _LOG.info("节点 process 处理 request_id=%s", rid)
    summary = f"已处理：{text[:48]}{'…' if len(text) > 48 else ''}"
    return {
        "diagnostics": [f"process:ok"],
        "result_summary": summary,
    }


def stub_error(state: ObservabilityState) -> dict:
    """故障/边界：不打真实异常栈，只写可观测诊断（便于 stream 里对齐）。"""
    rid = state.get("request_id") or ""
    text = (state.get("input_text") or "").strip()
    _LOG.warning("节点 stub_error request_id=%s empty=%s boom=%s", rid, not text, "boom" in text.lower())
    reason = "empty_input" if not text else "keyword_boom"
    return {
        "diagnostics": [f"stub_error:{reason}"],
        "result_summary": f"【故障路径】{reason}",
    }


def finalize(state: ObservabilityState) -> dict:
    """主路径收尾：统一写一条结束诊断（与 stub_error 支路互斥，不共用此节点亦可；为省节点合并）。"""
    rid = state.get("request_id") or ""
    _LOG.info("节点 finalize request_id=%s", rid)
    return {"diagnostics": ["finalize:done"]}


def build_observability_graph():
    """
    START → gate ──route──→ process → finalize → END
                      └──→ stub_error → END
    """
    g = StateGraph(ObservabilityState)
    g.add_node("gate", gate)
    g.add_node("process", process)
    g.add_node("finalize", finalize)
    g.add_node("stub_error", stub_error)
    g.add_edge(START, "gate")
    g.add_conditional_edges(
        "gate",
        route_after_gate,
        {"process": "process", "stub_error": "stub_error"},
    )
    g.add_edge("process", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("stub_error", END)
    saver = InMemorySaver()
    return g.compile(checkpointer=saver), saver


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


def _demo_stream_updates(graph, init: dict, cfg: dict) -> None:
    print("\n--- stream_mode=['updates']：每步只看节点返回的增量 ---")
    for chunk in graph.stream(init, cfg, stream_mode=["updates"]):
        # list[str] stream_mode → (mode, data)
        payload = chunk[1] if isinstance(chunk, tuple) and len(chunk) >= 2 else chunk
        print(f"  updates chunk: {payload!r}")


def _demo_stream_values(graph, init: dict, cfg: dict) -> None:
    print("\n--- stream_mode=['values']：每步后的全状态（截断 diagnostics 显示）---")
    for i, chunk in enumerate(graph.stream(init, cfg, stream_mode=["values"])):
        payload = chunk[1] if isinstance(chunk, tuple) and len(chunk) >= 2 else chunk
        if not isinstance(payload, dict):
            print(f"  values #{i+1}: {payload!r}")
            continue
        diag = payload.get("diagnostics")
        slim = {k: v for k, v in payload.items() }
        slim["diagnostics_len"] = len(diag or [])
        print(f"  values #{i+1}: {slim!r}")


def _demo_stream_checkpoints(graph, init: dict, cfg: dict) -> None:
    print("\n--- stream_mode=['checkpoints']：与 checkpoint 落盘节拍对齐的事件（摘要打印）---")
    for i, chunk in enumerate(graph.stream(init, cfg, stream_mode=["checkpoints"])):
        # list[str] stream_mode → (mode, dict|StateSnapshot)，1.1.10 侧多为映射结构。
        payload = chunk[1] if isinstance(chunk, tuple) and len(chunk) >= 2 else chunk
        if hasattr(payload, "id"):
            sid = getattr(payload, "id", "?")
            ts = getattr(payload, "created_at", None)
            nxt = getattr(payload, "next", ())
            vals = getattr(payload, "values", {}) or {}
        elif isinstance(payload, dict):
            conf = payload.get("config") or {}
            cid = (
                conf.get("configurable", {}).get("checkpoint_id")
                if isinstance(conf.get("configurable"), dict)
                else None
            )
            sid = cid or payload.get("id") or "?"
            ts = payload.get("created_at")
            meta = payload.get("metadata") or {}
            if ts is None and isinstance(meta, dict):
                ts = meta.get("step")
            nxt = payload.get("next", ())
            vals = payload.get("values") or {}
        else:
            sid, ts, nxt, vals = "?", None, (), {}
        keys = tuple(vals.keys()) if isinstance(vals, dict) else ()
        print(f"  checkpoints #{i+1}: checkpoint_id_suffix={str(sid)[-8:]} ts_or_step={ts} next={nxt} value_keys={keys}")


def demo() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    graph, _ = build_observability_graph()

    base_cfg = {
        "tags": ["lesson-13", "obs-demo"],
        "metadata": {"course": "langgraph-study", "lesson": "13"},
        "configurable": {"thread_id": "lesson-13-obs"},
    }

    print("=" * 72)
    print("① RunnableConfig：tags / metadata（本 demo 仅占位打印，真实环境可由中间件抓取）")
    print("=" * 72)
    print(f"  tags={base_cfg['tags']} metadata={base_cfg['metadata']}")

    happy_init: ObservabilityState = {
        "request_id": "req-happy-1",
        "input_text": "查询订单 OG-9001 状态",
        "diagnostics": [],
        "result_summary": "",
    }
    bad_init: ObservabilityState = {
        "request_id": "req-boom-1",
        "input_text": "trigger boom please",
        "diagnostics": [],
        "result_summary": "",
    }
    empty_init: ObservabilityState = {
        "request_id": "req-empty-1",
        "input_text": "   ",
        "diagnostics": [],
        "result_summary": "",
    }

    print("\n" + "=" * 72)
    print("② invoke 主路径（Happy Path）")
    print("=" * 72)
    out = graph.invoke(happy_init, base_cfg)
    print("  result_summary:", repr(out.get("result_summary")))
    print("  diagnostics:", out.get("diagnostics"))

    print("\n" + "=" * 72)
    print("③ Failure Path：boom / 空输入")
    print("=" * 72)
    out_boom = graph.invoke(bad_init, {**base_cfg, "configurable": {"thread_id": "lesson-13-boom"}})
    print("  boom →", out_boom.get("diagnostics"), out_boom.get("result_summary"))
    out_empty = graph.invoke(empty_init, {**base_cfg, "configurable": {"thread_id": "lesson-13-empty"}})
    print("  empty →", out_empty.get("diagnostics"), out_empty.get("result_summary"))

    cfg_stream = {**base_cfg, "configurable": {"thread_id": "lesson-13-stream"}}
    stream_init: ObservabilityState = {
        "request_id": "req-stream-1",
        "input_text": "stream 演示输入",
        "diagnostics": [],
        "result_summary": "",
    }
    print("\n" + "=" * 72)
    print("④ stream：多 stream_mode（同一新 thread，避免与前序 invokes 混在一起）")
    print("=" * 72)
    # _demo_stream_updates(graph, dict(stream_init), cfg_stream)
    _demo_stream_updates(graph, happy_init, cfg_stream)

    cfg_vals = {**base_cfg, "configurable": {"thread_id": "lesson-13-values"}}
    _demo_stream_values(
        graph,
        happy_init,
        # {
        #     "request_id": "req-values-1",
        #     "input_text": "values 快照",
        #     "diagnostics": [],
        #     "result_summary": "",
        # },
        cfg_vals,
    )

    cfg_cp = {**base_cfg, "configurable": {"thread_id": "lesson-13-cpstream"}}
    _demo_stream_checkpoints(
        graph,
        happy_init,
        # {
        #     "request_id": "req-cp-1",
        #     "input_text": "checkpoint 事件",
        #     "diagnostics": [],
        #     "result_summary": "",
        # },
        cfg_cp,
    )

    print("\n" + "=" * 72)
    print("⑤ print_mode：仅控制台镜像 stream（返回值仍是一份 updates）")
    print("=" * 72)
    print("[print_mode 镜像行开始]")
    for _ in graph.stream(
        {"request_id": "x", "input_text": "short", "diagnostics": [], "result_summary": ""},
        {**base_cfg, "configurable": {"thread_id": "lesson-13-printmode"}},
        stream_mode=["updates"],
        print_mode=["updates"],
    ):
        pass
    print("[print_mode 镜像行结束]")

    export_graph_png(graph, "13_observability_debug_graph.png")


if __name__ == "__main__":
    demo()
