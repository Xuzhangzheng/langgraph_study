"""
第 1～19 课索引：与 `LangGraph_课程大纲.md` 对齐，供复盘脚本与 Mermaid 生成器消费。

单一数据源：新增课时只改本表，避免散落魔法字符串。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LessonRow:
    """单课元数据：不落盘图时也用于「还缺哪一课」的自检。"""

    no: int
    title: str
    artifact: str  # 主交付：单文件 `.py` 或包目录前缀 `lesson19_support_desk/`
    keywords: tuple[str, ...]  # 复盘关键词（脑图节点）


# 主路径课 1～19；插学 04b、09b、11b、14b、18 等在大纲有说明，此处可在 keywords 点名。
LESSONS: tuple[LessonRow, ...] = (
    LessonRow(1, "Hello LangGraph", "01_hello_langgraph.py", ("StateGraph", "invoke", "START/END")),
    LessonRow(2, "条件分支", "02_branching_graph.py", ("add_conditional_edges", "路由函数")),
    LessonRow(3, "循环与重试", "03_loop_graph.py", ("回边", "max_iterations")),
    LessonRow(4, "Mini-Agent", "04_mini_agent_graph.py", ("生成-评估-重试", "attempt")),
    LessonRow(5, "工具节点", "05_tool_call_graph.py", ("Tool", "finalize_result")),
    LessonRow(6, "LLM 接入", "06_llm_integration_graph.py", ("ChatOpenAI", "Ark", "分层提示词")),
    LessonRow(7, "消息与上下文", "07_messages_context_graph.py", ("add_messages", "history")),
    LessonRow(8, "多工具路由", "08_multi_tool_routing_graph.py", ("优先级", "fan-in")),
    LessonRow(9, "子图模块化", "09_subgraph_modular_graph.py", ("子图 compile", "嵌套")),
    LessonRow(10, "并行与聚合", "10_parallel_fanin_graph.py", ("fan-out", "reducer", "barrier")),
    LessonRow(11, "人机协同 HITL", "11_human_in_the_loop_graph.py", ("interrupt", "Command.resume")),
    LessonRow(12, "Checkpoint", "12_checkpoint_memory_graph.py", ("InMemorySaver", "thread_id", "get_state")),
    LessonRow(13, "可观测性", "13_observability_debug_graph.py", ("stream_mode", "logging")),
    LessonRow(14, "容错", "14_error_handling_robustness_graph.py", ("risk_status", "退避重试")),
    LessonRow(15, "评测与门禁", "15_evaluation_quality_gate_graph.py", ("GoldenCase", "MIN_PASS_RATIO")),
    LessonRow(16, "RAG 整合", "16_rag_langgraph_graph.py", ("retrieve", "citations")),
    LessonRow(17, "多 Agent 协作", "17_multi_agent_collaboration_graph.py", ("Planner", "Critic", "max_iterations")),
    LessonRow(18, "发布治理", "18_production_governance_graph.py", ("契约", "REPO_DEPS_PIN", "preflight")),
    LessonRow(19, "Capstone 应用", "lesson19_support_desk", ("多包分层", "InMemorySaver", "regression")),
)
