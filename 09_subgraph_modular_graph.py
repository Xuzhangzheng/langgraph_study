"""
第九课：子图（Subgraph）与模块化编排

目标：
1) 把一大段流程拆成独立的 `StateGraph`，`compile()` 后主图用 `add_node(name, compiled_sub)` 嵌进去
2) 主图与子图约定**同一份** `TypedDict`（本课为教学简单）；生产向「父状态超集 + 子集子图 / `input_schema`」见 **`09b_order_subgraph_input_schema_graph.py`**
3) 主图仍负责「门禁、串联、最终汇总」；子图内部可独立演进、单测、复用

图结构（逻辑）：

    START → gate_input ──route──→ sub_alpha（子图：normalize→brief）→ sub_beta（子图：elaborate）→ assemble_final → END
                        └──→ bad_input → END

子图在代码里是两个 `StateGraph`，各自 `compile()` 后作为节点挂到主图——运行时先完整跑完子图内所有节点，再回到主图下一节点。

自本课起：正文尽量「每行代码旁附注释」；Java 对照见 `java/.../l09_subgraph_modular_graph/`。
"""

from __future__ import annotations  # 注解前向引用

from pathlib import Path  # 导出 PNG

from typing import Literal, TypedDict  # 路由返回值、状态 schema

from langgraph.graph import END, START, StateGraph  # 图 API


class PipelineState(TypedDict, total=False):
    """
    主图与子图共用的状态（本课刻意相同，减少心智负担）。
    error_note：非空表示门禁失败，主图短路到 bad_input。
    """

    raw_input: str  # 外部传入的原始文本
    normalized: str  # 子图 α：清洗后小写去空白
    section_a_summary: str  # 子图 α：短摘要
    section_b_detail: str  # 子图 β：基于摘要的扩写
    final_report: str  # 主图：拼装给调用方的最终输出
    error_note: str  # 门禁错误码或说明；空串表示正常
    step_count: int  # 跨图计数（仅主图节点递增，子图内不改，避免合并歧义）


def _inc_step(state: PipelineState, delta: int = 1) -> int:  # 读取并递增 step_count 的小工具
    return int(state.get("step_count") or 0) + delta


def normalize_for_alpha(state: PipelineState) -> dict:  # 子图 α 节点1：归一化
    text = (state.get("raw_input") or "").strip().lower()  # 去边空白并小写
    print(f"  [sub_α.normalize] -> {text!r}")
    return {"normalized": text}  # 不写 step_count，交给主图维护


def brief_summary(state: PipelineState) -> dict:  # 子图 α 节点2：生成短摘要
    base = state.get("normalized") or ""  # 依赖上一节点
    summary = f"[α-摘要] 主题片段: {base[:48]}" + ("…" if len(base) > 48 else "")  # 截断展示
    print(f"  [sub_α.brief] {summary}")
    return {"section_a_summary": summary}


def build_subgraph_alpha() -> StateGraph:  # 工厂：只关心「清洗 + 短摘要」
    g = StateGraph(PipelineState)  # 与主图同类状态
    g.add_node("normalize", normalize_for_alpha)  # 对内节点名可独立命名
    g.add_node("brief", brief_summary)
    g.add_edge(START, "normalize")  # 子图入口
    g.add_edge("normalize", "brief")  # 线性
    g.add_edge("brief", END)  # 子图出口
    return g  # 返回未编译 builder，由调用方 compile


def elaborate_beta(state: PipelineState) -> dict:  # 子图 β 单节点：扩写
    summary = state.get("section_a_summary") or ""  # 读子图 α 产物
    norm = state.get("normalized") or ""
    detail = (
        f"[β-扩写] 基于归一化文本({len(norm)} 字) 与 摘要，生成说明性段落。\n"
        f"（教学占位：真实场景可接 LLM / 模板库 / RAG。）\n"
        f"----\n摘要回顾：{summary}"
    )
    print("  [sub_β.elaborate] 完成扩写占位")
    return {"section_b_detail": detail}


def build_subgraph_beta() -> StateGraph:  # 工厂：只关心「扩写」
    g = StateGraph(PipelineState)
    g.add_node("elaborate", elaborate_beta)
    g.add_edge(START, "elaborate")
    g.add_edge("elaborate", END)
    return g


def gate_input(state: PipelineState) -> dict:  # 主图入口：参数校验
    raw = state.get("raw_input") or ""
    print("\n[gate_input] 检查 raw_input")
    if not raw.strip():  # 空输入短路
        print("  -> 空输入，标记 error_note")
        return {
            "error_note": "empty_input",
            "step_count": _inc_step(state),
        }
    return {
        "error_note": "",
        "step_count": _inc_step(state),
    }


def route_after_gate(state: PipelineState) -> Literal["sub_alpha", "bad_input"]:  # 门禁后路由
    return "bad_input" if state.get("error_note") == "empty_input" else "sub_alpha"


def bad_input(state: PipelineState) -> dict:  # 失败收尾：不跑子图
    print("\n[bad_input] 短路分支")
    return {
        "final_report": "【拒绝执行】raw_input 为空。请传入非空字符串后再 invoke。",
        "step_count": _inc_step(state),
    }


def assemble_final(state: PipelineState) -> dict:  # 主图出口：拼装子图产物
    print("\n[assemble_final] 拼装最终报告")
    block = (
        "======== 最终报告 ========\n"
        f"归一化: {state.get('normalized', '')}\n\n"
        f"{state.get('section_a_summary', '')}\n\n"
        f"{state.get('section_b_detail', '')}\n"
        "=========================="
    )
    return {
        "final_report": block,
        "step_count": _inc_step(state),
    }


def build_main_graph() -> StateGraph:  # 主图：串联子图（compiled）与收尾
    sub_a = build_subgraph_alpha().compile()  # 子图 α 先编译
    sub_b = build_subgraph_beta().compile()  # 子图 β 先编译

    main = StateGraph(PipelineState)  # 主图 builder
    main.add_node("gate_input", gate_input)  # 门禁
    main.add_node("bad_input", bad_input)  # 异常收尾
    main.add_node("sub_alpha", sub_a)  # 核心：compiled 子图当作「单节点」嵌入
    main.add_node("sub_beta", sub_b)  # 第二个子图同理
    main.add_node("assemble_final", assemble_final)  # 汇总

    main.add_edge(START, "gate_input")  # 主入口
    main.add_conditional_edges(
        "gate_input",
        route_after_gate,
        {
            "sub_alpha": "sub_alpha",
            "bad_input": "bad_input",
        },
    )
    main.add_edge("sub_alpha", "sub_beta")  # 子图 α 跑完后跑子图 β
    main.add_edge("sub_beta", "assemble_final")  # 再拼装
    main.add_edge("assemble_final", END)  # 正常结束
    main.add_edge("bad_input", END)  # 异常结束
    return main


def export_graph_image(graph) -> None:  # 与前几课相同
    go = graph.get_graph()
    png = Path(__file__).with_name("09_subgraph_modular_graph.png")
    mmd = Path(__file__).with_name("09_subgraph_modular_graph.mmd")
    try:
        png.write_bytes(go.draw_mermaid_png())
        print(f"[图导出] {png}")
    except Exception as exc:  # noqa: BLE001
        mmd.write_text(go.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mmd}")


def _initial(raw: str) -> PipelineState:  # 构造初始 state，其余字段由图填充
    return {
        "raw_input": raw,
        "normalized": "",
        "section_a_summary": "",
        "section_b_detail": "",
        "final_report": "",
        "error_note": "",
        "step_count": 0,
    }


def demo() -> None:  # 教学用例
    g = build_main_graph().compile()  # 主图编译
    export_graph_image(g)

    print("=" * 72)
    print("1) Happy Path：子图 α → 子图 β → 汇总")
    print("=" * 72)
    out_ok = g.invoke(_initial("  LangGraph 子图演示  "))
    print(out_ok["final_report"])
    print("step_count:", out_ok.get("step_count"))

    print("\n" + "=" * 72)
    print("2) Failure Path：空输入，门禁短路，不进入子图")
    print("=" * 72)
    out_bad = g.invoke(_initial("   "))
    print(out_bad["final_report"])
    print("step_count:", out_bad.get("step_count"))

    print("\n本课 DoD：")
    print("- 主路径：两段子图串行 + 最终 assemble")
    print("- 故障：gate 拦截空输入")
    print("- 回归：python 09_subgraph_modular_graph.py")
    print("- Java：Lesson09App（CompiledGraph.invoke 包装子图）")


if __name__ == "__main__":
    demo()
