package study.langgraph.lessons.l04_mini_agent_graph;

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
 * 第四课：Mini-Agent（对照 {@code 04_mini_agent_graph.py}）。
 */
public final class Lesson04App {

    private Lesson04App() {
    }

    static final class ClassifyTask implements NodeAction<L04State> {
        @Override
        public Map<String, Object> apply(L04State state) {
            String userInput = state.userInput();
            System.out.println("\n[classify_task] 节点开始执行");
            System.out.println("[classify_task] user_input: " + userInput);
            String taskType;
            if (userInput.contains("改写") || userInput.contains("润色") || userInput.contains("重写")) {
                taskType = "rewrite";
            } else {
                taskType = "qa";
            }
            System.out.println("[classify_task] 识别 task_type: " + taskType);
            return Map.of(L04State.TASK_TYPE, taskType);
        }
    }

    static final class QaPrepare implements NodeAction<L04State> {
        @Override
        public Map<String, Object> apply(L04State state) {
            System.out.println("\n[qa_prepare] 节点开始执行");
            return Map.of(L04State.FEEDBACK, "目标：给出结构清晰、要点完整的回答。");
        }
    }

    static final class RewritePrepare implements NodeAction<L04State> {
        @Override
        public Map<String, Object> apply(L04State state) {
            System.out.println("\n[rewrite_prepare] 节点开始执行");
            return Map.of(L04State.FEEDBACK, "目标：保留原意，表达更自然、更精炼。");
        }
    }

    static final class GenerateAnswer implements NodeAction<L04State> {
        @Override
        public Map<String, Object> apply(L04State state) {
            String userInput = state.userInput();
            String taskType = state.taskType();
            int attempt = state.attempt() + 1;
            String feedback = state.feedback();
            System.out.println("\n[generate_answer] 节点开始执行");
            System.out.println("[generate_answer] task_type: " + taskType);
            System.out.println("[generate_answer] 当前 attempt: " + attempt);
            System.out.println("[generate_answer] 使用反馈: " + feedback);
            String candidate;
            if ("rewrite".equals(taskType)) {
                candidate = "第" + attempt + "版改写：\n"
                        + "- 原句：" + userInput + "\n"
                        + "- 改写：这个内容可以表达为「" + userInput + "」，语气更自然。\n"
                        + "- 改进说明：" + feedback;
            } else {
                candidate = "第" + attempt + "版回答：\n"
                        + "- 问题：" + userInput + "\n"
                        + "- 回答要点：先定义概念，再给步骤，最后给注意事项。\n"
                        + "- 改进说明：" + feedback;
            }
            System.out.println("[generate_answer] candidate: " + candidate);
            return Map.of(L04State.ATTEMPT, attempt, L04State.CANDIDATE_ANSWER, candidate);
        }
    }

    static final class EvaluateAnswer implements NodeAction<L04State> {
        @Override
        public Map<String, Object> apply(L04State state) {
            int attempt = state.attempt();
            String answer = state.candidateAnswer();
            int passThreshold = state.passThreshold();
            int maxAttempts = state.maxAttempts();
            System.out.println("\n[evaluate_answer] 节点开始执行");
            System.out.println("[evaluate_answer] 当前 attempt: " + attempt);
            System.out.println("[evaluate_answer] candidate 长度: " + answer.length());
            int score = attempt * 25;
            if (answer.length() > 120) {
                score += 10;
            }
            score = Math.min(score, 100);
            boolean passedByScore = score >= passThreshold;
            boolean reachedMax = attempt >= maxAttempts;
            boolean passed = passedByScore || reachedMax;
            String feedback;
            if (passedByScore) {
                feedback = "评估通过：质量已达到阈值。";
            } else if (reachedMax) {
                feedback = "达到最大尝试次数，停止循环（这是安全退出，不代表最佳质量）。";
            } else {
                feedback = "评估未通过：请增加结构化说明，并补充更具体的细节。";
            }
            System.out.println("[evaluate_answer] score: " + score);
            System.out.println("[evaluate_answer] pass_threshold: " + passThreshold);
            System.out.println("[evaluate_answer] passed: " + passed);
            System.out.println("[evaluate_answer] feedback: " + feedback);
            return Map.of(
                    L04State.QUALITY_SCORE, score,
                    L04State.PASSED, passed,
                    L04State.FEEDBACK, feedback
            );
        }
    }

    static final class Finish implements NodeAction<L04State> {
        @Override
        public Map<String, Object> apply(L04State state) {
            System.out.println("\n[finish] 节点开始执行");
            System.out.println("[finish] 最终 attempt: " + state.attempt());
            System.out.println("[finish] 最终 score: " + state.qualityScore());
            return Map.of(L04State.PASSED, true);
        }
    }

    public static StateGraph buildGraph() throws GraphStateException {
        Map<String, String> routeTask = Map.of(
                "qa_prepare", "qa_prepare",
                "rewrite_prepare", "rewrite_prepare"
        );
        Map<String, String> afterEval = Map.of(
                "finish", "finish",
                "retry_generate", "generate_answer"
        );

        return new StateGraph<>(L04State.SCHEMA, L04State::new)
                .addNode("classify_task", node_async(new ClassifyTask()))
                .addNode("qa_prepare", node_async(new QaPrepare()))
                .addNode("rewrite_prepare", node_async(new RewritePrepare()))
                .addNode("generate_answer", node_async(new GenerateAnswer()))
                .addNode("evaluate_answer", node_async(new EvaluateAnswer()))
                .addNode("finish", node_async(new Finish()))
                .addEdge(START, "classify_task")
                .addConditionalEdges(
                        "classify_task",
                        edge_async(state -> "rewrite".equals(state.taskType()) ? "rewrite_prepare" : "qa_prepare"),
                        routeTask
                )
                .addEdge("qa_prepare", "generate_answer")
                .addEdge("rewrite_prepare", "generate_answer")
                .addEdge("generate_answer", "evaluate_answer")
                .addConditionalEdges(
                        "evaluate_answer",
                        edge_async(state -> {
                            if (state.passed()) {
                                System.out.println("\n[route_after_evaluation] 决策：finish");
                                return "finish";
                            }
                            System.out.println("\n[route_after_evaluation] 决策：retry_generate");
                            return "retry_generate";
                        }),
                        afterEval
                )
                .addEdge("finish", END);
    }

    static void runCase(org.bsc.langgraph4j.CompiledGraph<?> graph, String userInput) throws GraphStateException {
        Map<String, Object> initial = new HashMap<>();
        initial.put(L04State.USER_INPUT, userInput);
        initial.put(L04State.TASK_TYPE, "");
        initial.put(L04State.ATTEMPT, 0);
        initial.put(L04State.MAX_ATTEMPTS, 2);
        initial.put(L04State.CANDIDATE_ANSWER, "");
        initial.put(L04State.QUALITY_SCORE, 0);
        initial.put(L04State.PASS_THRESHOLD, 70);
        initial.put(L04State.PASSED, false);
        initial.put(L04State.FEEDBACK, "初始反馈：请先生成一个可评估版本。");
        System.out.println("\n" + "=".repeat(80));
        System.out.println("开始案例：" + userInput);
        System.out.println("=".repeat(80));
        var fs = graph.invoke(initial).orElseThrow();
        if (fs instanceof L04State s) {
            System.out.println("\n[案例结束]");
            System.out.println("task_type: " + s.taskType());
            System.out.println("attempt: " + s.attempt());
            System.out.println("quality_score: " + s.qualityScore());
            System.out.println("passed: " + s.passed());
            System.out.println("final feedback: " + s.feedback());
            System.out.println("最终候选答案：");
            System.out.println(s.candidateAnswer());
        }
    }

    public static void main(String[] args) throws GraphStateException {
        var g = buildGraph().compile();
        runCase(g, "请解释一下什么是 LangGraph，以及适合哪些场景。");
        runCase(g, "请把这句话改写得更自然：我今天学习了很多新知识，感觉很充实。");
    }
}
