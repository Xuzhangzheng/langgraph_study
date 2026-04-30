package study.langgraph.lessons.l01_hello_langgraph;

import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;

import java.util.Map;

import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第一课：最小线性图（START → prepare_message → summarize_result → END）。
 * 逻辑对齐仓库根目录 {@code 01_hello_langgraph.py}，便于对照阅读。
 */
public final class Lesson01App {

    private Lesson01App() {
    }

    static final class PrepareMessage implements NodeAction<L01LessonState> {
        @Override
        public Map<String, Object> apply(L01LessonState state) {
            String original = state.message();
            String prepared = "Hello, LangGraph! 原始输入是：" + original;
            System.out.println("\n[prepare_message] 节点开始执行");
            System.out.println("[prepare_message] message=" + original + ", step_count=" + state.stepCount());
            System.out.println("[prepare_message] 生成的新 message: " + prepared);
            return Map.of(
                    L01LessonState.MESSAGE, prepared,
                    L01LessonState.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    static final class SummarizeResult implements NodeAction<L01LessonState> {
        @Override
        public Map<String, Object> apply(L01LessonState state) {
            String currentMessage = state.message();
            int currentStep = state.stepCount();
            String finalMessage = currentMessage + " | 图执行完成，总共经过 " + (currentStep + 1) + " 个节点。";
            System.out.println("\n[summarize_result] 节点开始执行");
            System.out.println("[summarize_result] message=" + currentMessage + ", step_count=" + currentStep);
            System.out.println("[summarize_result] 生成的最终 message: " + finalMessage);
            return Map.of(
                    L01LessonState.MESSAGE, finalMessage,
                    L01LessonState.STEP_COUNT, currentStep + 1
            );
        }
    }

    public static void main(String[] args) throws GraphStateException {
        var graph = new StateGraph<>(L01LessonState.SCHEMA, L01LessonState::new)
                .addNode("prepare_message", node_async(new PrepareMessage()))
                .addNode("summarize_result", node_async(new SummarizeResult()))
                .addEdge(START, "prepare_message")
                .addEdge("prepare_message", "summarize_result")
                .addEdge("summarize_result", END)
                .compile();

        Map<String, Object> initial = Map.of(
                L01LessonState.MESSAGE, "这是我学习 LangGraph 的第一天",
                L01LessonState.STEP_COUNT, 0
        );

        System.out.println("=".repeat(80));
        System.out.println("第一课：运行一个最小 LangGraph（Java / LangGraph4j）");
        System.out.println("=".repeat(80));
        System.out.println("初始 state: " + initial);

        var finalState = graph.invoke(initial)
                .orElseThrow(() -> new IllegalStateException("图未产生最终状态"));

        System.out.println("\n" + "=".repeat(80));
        System.out.println("图执行结束");
        System.out.println("=".repeat(80));
        System.out.println("最终 state: " + finalState);
    }
}
