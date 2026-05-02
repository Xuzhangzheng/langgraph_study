package study.langgraph.lessons.l20_course_review;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

/**
 * 第二十课：与 Python {@code lesson20_course_review/catalog.py} 同构的课表明细。
 */
public final class CourseCatalog {

    private CourseCatalog() {
    }

    public record LessonRow(int no, String title, String artifact, List<String> keywords) {
    }

    public static List<LessonRow> lessons() {
        return List.of(
                new LessonRow(1, "Hello LangGraph", "01_hello_langgraph.py", List.of("StateGraph", "invoke")),
                new LessonRow(2, "条件分支", "02_branching_graph.py", List.of("add_conditional_edges", "路由")),
                new LessonRow(3, "循环与重试", "03_loop_graph.py", List.of("回边", "max_iterations")),
                new LessonRow(4, "Mini-Agent", "04_mini_agent_graph.py", List.of("生成-评估", "attempt")),
                new LessonRow(5, "工具节点", "05_tool_call_graph.py", List.of("Tool", "finalize")),
                new LessonRow(6, "LLM 接入", "06_llm_integration_graph.py", List.of("OpenAI", "Ark")),
                new LessonRow(7, "消息与上下文", "07_messages_context_graph.py", List.of("add_messages", "history")),
                new LessonRow(8, "多工具路由", "08_multi_tool_routing_graph.py", List.of("优先级", "fan-in")),
                new LessonRow(9, "子图模块化", "09_subgraph_modular_graph.py", List.of("子图", "compile")),
                new LessonRow(10, "并行与聚合", "10_parallel_fanin_graph.py", List.of("fan-out", "reducer")),
                new LessonRow(11, "人机协同", "11_human_in_the_loop_graph.py", List.of("interrupt", "resume")),
                new LessonRow(12, "Checkpoint", "12_checkpoint_memory_graph.py", List.of("Saver", "thread_id")),
                new LessonRow(13, "可观测性", "13_observability_debug_graph.py", List.of("stream_mode", "logging")),
                new LessonRow(14, "容错", "14_error_handling_robustness_graph.py", List.of("risk_status", "退避")),
                new LessonRow(15, "评测与门禁", "15_evaluation_quality_gate_graph.py", List.of("GoldenCase", "门禁")),
                new LessonRow(16, "RAG 整合", "16_rag_langgraph_graph.py", List.of("retrieve", "citations")),
                new LessonRow(17, "多 Agent 协作", "17_multi_agent_collaboration_graph.py", List.of("Planner", "Critic")),
                new LessonRow(18, "发布治理", "18_production_governance_graph.py", List.of("契约", "preflight")),
                new LessonRow(19, "Capstone 应用", "lesson19_support_desk", List.of("多包", "regression"))
        );
    }
}
