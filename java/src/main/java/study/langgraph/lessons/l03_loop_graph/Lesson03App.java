package study.langgraph.lessons.l03_loop_graph;

import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;

import java.util.HashMap;
import java.util.Map;

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第三课：循环（对照 {@code 03_loop_graph.py}）。
 */
public final class Lesson03App {

    private Lesson03App() {
    }

    static final class WriteOrExpandDraft implements NodeAction<L03State> {
        @Override
        public Map<String, Object> apply(L03State state) {
            String topic = state.topic();
            String draft = state.draft();
            int iteration = state.iteration();
            System.out.println("\n[write_or_expand_draft] 节点开始执行");
            System.out.println("[write_or_expand_draft] 当前 iteration: " + iteration);
            System.out.println("[write_or_expand_draft] 执行前 draft 长度: " + draft.length());
            String addition = " 第" + (iteration + 1) + "轮补充：围绕「" + topic
                    + "」，我们进一步强调核心概念、实践价值和学习建议。";
            String updated = draft + addition;
            System.out.println("[write_or_expand_draft] 执行后 draft 长度: " + updated.length());
            return Map.of(L03State.DRAFT, updated, L03State.ITERATION, iteration + 1);
        }
    }

    static final class CheckCompletion implements NodeAction<L03State> {
        @Override
        public Map<String, Object> apply(L03State state) {
            int draftLength = state.draft().length();
            int minLen = state.minLength();
            int iteration = state.iteration();
            int maxIter = state.maxIterations();
            boolean done = draftLength >= minLen || iteration >= maxIter;
            System.out.println("\n[check_completion] 节点开始执行");
            System.out.println("[check_completion] 当前 draft 长度: " + draftLength);
            System.out.println("[check_completion] 目标最小长度: " + minLen);
            System.out.println("[check_completion] 当前迭代次数: " + iteration);
            System.out.println("[check_completion] 最大迭代次数: " + maxIter);
            System.out.println("[check_completion] 是否完成 done: " + done);
            return Map.of(L03State.DONE, done);
        }
    }

    static final class FinishNode implements NodeAction<L03State> {
        @Override
        public Map<String, Object> apply(L03State state) {
            System.out.println("\n[finish_node] 节点开始执行");
            System.out.println("[finish_node] 最终 iteration: " + state.iteration());
            System.out.println("[finish_node] 最终 draft 长度: " + state.draft().length());
            return Map.of(L03State.DONE, true);
        }
    }

    public static StateGraph buildGraph() throws GraphStateException {
        Map<String, String> afterCheck = new HashMap<>();
        afterCheck.put("continue_writing", "write_or_expand_draft");
        afterCheck.put("finish", "finish_node");

        return new StateGraph<>(L03State.SCHEMA, L03State::new)
                .addNode("write_or_expand_draft", node_async(new WriteOrExpandDraft()))
                .addNode("check_completion", node_async(new CheckCompletion()))
                .addNode("finish_node", node_async(new FinishNode()))
                .addEdge(START, "write_or_expand_draft")
                .addEdge("write_or_expand_draft", "check_completion")
                .addConditionalEdges(
                        "check_completion",
                        edge_async(state -> {
                            if (state.done()) {
                                System.out.println("\n[route_after_check] 决策：finish（结束循环）");
                                return "finish";
                            }
                            System.out.println("\n[route_after_check] 决策：continue_writing（继续下一轮）");
                            return "continue_writing";
                        }),
                        afterCheck
                )
                .addEdge("finish_node", END);
    }

    public static void main(String[] args) throws GraphStateException {
        var graph = buildGraph().compile();
        Map<String, Object> initial = new HashMap<>();
        initial.put(L03State.TOPIC, "LangGraph 学习路线");
        initial.put(L03State.DRAFT, "开篇：我们正在学习如何用图来组织 LLM 应用。");
        initial.put(L03State.MIN_LENGTH, 220);
        initial.put(L03State.ITERATION, 0);
        initial.put(L03State.MAX_ITERATIONS, 3);
        initial.put(L03State.DONE, false);

        System.out.println("=".repeat(80));
        System.out.println("第三课：运行循环图（直到满足条件）");
        System.out.println("=".repeat(80));
        System.out.println("初始 state: " + initial);
        var finalState = graph.invoke(initial).orElseThrow();
        System.out.println("\n" + "=".repeat(80));
        System.out.println("图执行结束");
        System.out.println("=".repeat(80));
        System.out.println("最终 iteration: " + finalState.iteration());
        System.out.println("最终 done: " + finalState.done());
        System.out.println("最终 draft 长度: " + finalState.draft().length());
        System.out.println("最终 draft 内容:\n" + finalState.draft());
    }
}
