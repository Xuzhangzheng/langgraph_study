package study.langgraph.lessons.l05_tool_call_graph;

import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;

import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第五课：工具调用（对照 {@code 05_tool_call_graph.py}）。
 */
public final class Lesson05App {

    private Lesson05App() {
    }

    private static final Set<String> CALC_ALLOWED = Set.of(
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
            "+", "-", "*", "/", "%", ".", "(", ")", " "
    );

    static double evalExpression(String expression) throws Exception {
        ScriptEngineManager mgr = new ScriptEngineManager();
        ScriptEngine eng = mgr.getEngineByName("nashorn");
        if (eng == null) {
            eng = mgr.getEngineByName("JavaScript");
        }
        if (eng == null) {
            throw new IllegalStateException("未找到 Nashorn/JavaScript 引擎（请确认依赖 nashorn-core）");
        }
        Object raw = eng.eval(expression);
        if (raw instanceof Number n) {
            return n.doubleValue();
        }
        return Double.parseDouble(raw.toString());
    }

    static final class DecideTool implements NodeAction<L05State> {
        @Override
        public Map<String, Object> apply(L05State state) {
            String userInput = state.userInput();
            String normalized = userInput.replace(" ", "");
            System.out.println("\n[decide_tool] 节点开始执行");
            System.out.println("[decide_tool] user_input: " + userInput);
            String selectedTool;
            String toolInput;
            if (userInput.contains("几点") || userInput.contains("时间") || userInput.contains("现在")) {
                selectedTool = "time";
                toolInput = "";
            } else if (userInput.contains("计算")
                    || normalized.contains("+") || normalized.contains("-")
                    || normalized.contains("*") || normalized.contains("/")) {
                selectedTool = "calculator";
                if (userInput.contains("计算")) {
                    int idx = userInput.indexOf("计算");
                    toolInput = userInput.substring(idx + "计算".length()).trim();
                } else {
                    toolInput = userInput;
                }
            } else {
                selectedTool = "no_tool";
                toolInput = "";
            }
            System.out.println("[decide_tool] selected_tool: " + selectedTool);
            System.out.println("[decide_tool] tool_input: " + toolInput);
            return Map.of(
                    L05State.SELECTED_TOOL, selectedTool,
                    L05State.TOOL_INPUT, toolInput,
                    L05State.STEP_COUNT, state.stepCount() + 1,
                    L05State.TOOL_OUTPUT, "",
                    L05State.TOOL_ERROR, ""
            );
        }
    }

    static final class CalculatorTool implements NodeAction<L05State> {
        @Override
        public Map<String, Object> apply(L05State state) {
            String expression = state.toolInput();
            System.out.println("\n[calculator_tool] 节点开始执行");
            System.out.println("[calculator_tool] expression: " + expression);
            if (expression.isEmpty()) {
                return Map.of(
                        L05State.TOOL_ERROR, "未找到可计算表达式，请在「计算」后提供表达式，例如：计算 12 * (3 + 5)",
                        L05State.STEP_COUNT, state.stepCount() + 1
                );
            }
            for (int i = 0; i < expression.length(); i++) {
                String ch = expression.substring(i, i + 1);
                if (!CALC_ALLOWED.contains(ch)) {
                    return Map.of(
                            L05State.TOOL_ERROR, "表达式包含非法字符，当前仅支持数字与 +-*/%()",
                            L05State.STEP_COUNT, state.stepCount() + 1
                    );
                }
            }
            try {
                double result = evalExpression(expression);
                return Map.of(
                        L05State.TOOL_OUTPUT, expression + " = " + result,
                        L05State.STEP_COUNT, state.stepCount() + 1
                );
            } catch (Exception e) {
                return Map.of(
                        L05State.TOOL_ERROR, "计算失败：" + e.getMessage(),
                        L05State.STEP_COUNT, state.stepCount() + 1
                );
            }
        }
    }

    static final class TimeTool implements NodeAction<L05State> {
        @Override
        public Map<String, Object> apply(L05State state) {
            String now = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
            System.out.println("\n[time_tool] 节点开始执行");
            System.out.println("[time_tool] now: " + now);
            return Map.of(
                    L05State.TOOL_OUTPUT, "当前本地时间是：" + now,
                    L05State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    static final class NoToolNode implements NodeAction<L05State> {
        @Override
        public Map<String, Object> apply(L05State state) {
            System.out.println("\n[no_tool_node] 节点开始执行");
            return Map.of(
                    L05State.TOOL_OUTPUT, "当前请求不需要工具，走直接回复逻辑。",
                    L05State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    static final class FinalizeResult implements NodeAction<L05State> {
        @Override
        public Map<String, Object> apply(L05State state) {
            System.out.println("\n[finalize_result] 节点开始执行");
            String finalAnswer;
            if (!state.toolError().isEmpty()) {
                finalAnswer = "工具 `" + state.selectedTool() + "` 执行失败。\n"
                        + "错误信息：" + state.toolError() + "\n"
                        + "建议：请调整输入后重试。";
            } else if ("no_tool".equals(state.selectedTool())) {
                finalAnswer = "这是直接回复分支：\n当前输入未命中工具调用条件。";
            } else {
                finalAnswer = "工具 `" + state.selectedTool() + "` 执行成功。\n"
                        + "结果：" + state.toolOutput();
            }
            return Map.of(
                    L05State.FINAL_ANSWER, finalAnswer,
                    L05State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    public static StateGraph buildGraph() throws GraphStateException {
        Map<String, String> routeTool = new HashMap<>();
        routeTool.put("calculator_tool", "calculator_tool");
        routeTool.put("time_tool", "time_tool");
        routeTool.put("no_tool_node", "no_tool_node");

        return new StateGraph<>(L05State.SCHEMA, L05State::new)
                .addNode("decide_tool", node_async(new DecideTool()))
                .addNode("calculator_tool", node_async(new CalculatorTool()))
                .addNode("time_tool", node_async(new TimeTool()))
                .addNode("no_tool_node", node_async(new NoToolNode()))
                .addNode("finalize_result", node_async(new FinalizeResult()))
                .addEdge(START, "decide_tool")
                .addConditionalEdges(
                        "decide_tool",
                        edge_async(state -> {
                            System.out.println("\n[route_tool] 路由函数开始执行");
                            String t = state.selectedTool();
                            System.out.println("[route_tool] selected_tool: " + t);
                            if ("calculator".equals(t)) {
                                return "calculator_tool";
                            }
                            if ("time".equals(t)) {
                                return "time_tool";
                            }
                            return "no_tool_node";
                        }),
                        routeTool

                )
                .addEdge("calculator_tool", "finalize_result")
                .addEdge("time_tool", "finalize_result")
                .addEdge("no_tool_node", "finalize_result")
                .addEdge("finalize_result", END);
    }

    static void runCase(org.bsc.langgraph4j.CompiledGraph<?> graph, String userInput) throws GraphStateException {
        Map<String, Object> initial = new HashMap<>();
        initial.put(L05State.USER_INPUT, userInput);
        initial.put(L05State.SELECTED_TOOL, "");
        initial.put(L05State.TOOL_INPUT, "");
        initial.put(L05State.TOOL_OUTPUT, "");
        initial.put(L05State.TOOL_ERROR, "");
        initial.put(L05State.FINAL_ANSWER, "");
        initial.put(L05State.STEP_COUNT, 0);
        System.out.println("\n" + "=".repeat(80));
        System.out.println("开始案例：" + userInput);
        System.out.println("=".repeat(80));
        var fs = graph.invoke(initial).orElseThrow();
        if (fs instanceof L05State s) {
            System.out.println("\n[案例结束]");
            System.out.println("selected_tool: " + s.selectedTool());
            System.out.println("step_count: " + s.stepCount());
            System.out.println("final_answer:");
            System.out.println(s.value(L05State.FINAL_ANSWER).orElse(""));
        }
    }

    public static void main(String[] args) throws GraphStateException {
        var g = buildGraph().compile();
        runCase(g, "请帮我计算 12 * (3 + 5)");
        runCase(g, "现在几点了？");
        runCase(g, "你好，简单介绍一下 LangGraph。");
    }
}
