package study.langgraph.lessons.l08_multi_tool_routing;

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
 * 第八课：多工具路由与工具选择策略（对照 {@code 08_multi_tool_routing_graph.py}）。
 * <p>
 * 图拓扑：START {@code ->} select_tools {@code ->} 条件边 {@code ->} calculator / time / lookup /
 * fallback；前三者 {@code ->} finalize_result {@code ->} END，兜底 {@code ->} END。
 * <p>
 * 与 Python 的差异仅在运行时栈（此处为 LangGraph4j + JDK）；选择策略与词典数据与脚本保持一致便于对照。
 * <p>
 * 注意：每轮只执行<strong>一个</strong>工具分支；{@code finalize_result} 只排版<strong>该工具</strong>的单次输出，不是多工具结果的归并。
 */
public final class Lesson08App {

    private Lesson08App() {
    }

    /** 计算器允许的字符集（与第五课 Java 示例一致，防注入）。 */
    private static final Set<String> CALC_ALLOWED = Set.of(
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
            "+", "-", "*", "/", "%", ".", "(", ")", " "
    );

    /** 内置词条（key 小写）；lookup 工具只读该表。 */
    private static final Map<String, String> GLOSSARY = Map.of(
            "langgraph", "LangGraph：面向多步骤、有状态的 LLM 应用编排库，常与 LangChain 生态配合。",
            "langchain", "LangChain：构建 LLM 应用的框架，提供模型抽象、链、工具与数据连接器。"
    );

    /**
     * 使用 Nashorn（或通用 JavaScript）引擎求算术表达式数值。
     */
    static double evalExpression(String expression) throws Exception {
        ScriptEngineManager mgr = new ScriptEngineManager();
        ScriptEngine eng = mgr.getEngineByName("nashorn");
        if (eng == null) {
            eng = mgr.getEngineByName("JavaScript");
        }
        if (eng == null) {
            throw new IllegalStateException("未找到 Nashorn/JavaScript 引擎");
        }
        Object raw = eng.eval(expression);
        if (raw instanceof Number n) {
            return n.doubleValue();
        }
        return Double.parseDouble(raw.toString());
    }

    /**
     * 选择器节点：按固定优先级决定 {@code selected_tool}，并写 {@code route_note} 便于对照策略。
     */
    static final class SelectTools implements NodeAction<L08State> {
        @Override
        public Map<String, Object> apply(L08State state) {
            String userInput = state.userInput();
            String normalized = userInput.replace(" ", "");
            System.out.println("\n[select_tools] 节点开始执行");
            System.out.println("[select_tools] user_input=" + userInput);

            String selectedTool = "fallback";
            String toolInput = "";
            String routeNote = "未命中专用工具关键词，将走 fallback_reply。";

            if (userInput.contains("计算")
                    || normalized.contains("+") || normalized.contains("-")
                    || normalized.contains("*") || normalized.contains("/")) {
                selectedTool = "calculator";
                if (userInput.contains("计算")) {
                    int idx = userInput.indexOf("计算");
                    toolInput = userInput.substring(idx + "计算".length()).trim();
                } else {
                    toolInput = userInput;
                }
                routeNote = "优先级1：检测到算术相关关键词或运算符，选 calculator。";
            } else if (userInput.contains("几点") || userInput.contains("时间") || userInput.contains("现在")) {
                selectedTool = "time";
                toolInput = "";
                routeNote = "优先级2：检测到时间相关关键词，选 time。";
            } else if (userInput.contains("是什么")) {
                int idx = userInput.indexOf("是什么");
                String term = userInput.substring(0, idx).trim().toLowerCase();
                if (GLOSSARY.containsKey(term)) {
                    selectedTool = "lookup";
                    toolInput = term;
                    routeNote = "优先级3：「是什么」句型且词条在内置词典中，选 lookup。";
                } else {
                    routeNote = "优先级3：虽有「是什么」，但词条「" + term + "」不在词典，最终兜底。";
                }
            } else {
                String whole = userInput.trim().toLowerCase();
                if (GLOSSARY.containsKey(whole)) {
                    selectedTool = "lookup";
                    toolInput = whole;
                    routeNote = "优先级3：整句即为词典 key，选 lookup。";
                }
            }

            System.out.println("[select_tools] selected_tool=" + selectedTool + " tool_input=" + toolInput);
            System.out.println("[select_tools] route_note=" + routeNote);

            return Map.of(
                    L08State.SELECTED_TOOL, selectedTool,
                    L08State.TOOL_INPUT, toolInput,
                    L08State.ROUTE_NOTE, routeNote,
                    L08State.TOOL_OUTPUT, "",
                    L08State.TOOL_ERROR, "",
                    L08State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    /** 计算器工具：白名单校验 + 脚本求值。 */
    static final class CalculatorTool implements NodeAction<L08State> {
        @Override
        public Map<String, Object> apply(L08State state) {
            String expression = state.toolInput();
            System.out.println("\n[calculator_tool] expression=" + expression);
            if (expression.isEmpty()) {
                return Map.of(
                        L08State.TOOL_ERROR, "未找到可计算表达式。",
                        L08State.STEP_COUNT, state.stepCount() + 1
                );
            }
            for (int i = 0; i < expression.length(); i++) {
                String ch = expression.substring(i, i + 1);
                if (!CALC_ALLOWED.contains(ch)) {
                    return Map.of(
                            L08State.TOOL_ERROR, "表达式包含非法字符（仅允许数字与 +-*/%() 与空格）。",
                            L08State.STEP_COUNT, state.stepCount() + 1
                    );
                }
            }
            try {
                double r = evalExpression(expression);
                return Map.of(
                        L08State.TOOL_OUTPUT, expression + " = " + r,
                        L08State.STEP_COUNT, state.stepCount() + 1
                );
            } catch (Exception e) {
                return Map.of(
                        L08State.TOOL_ERROR, "计算失败：" + e.getMessage(),
                        L08State.STEP_COUNT, state.stepCount() + 1
                );
            }
        }
    }

    /** 时间工具：本地时钟。 */
    static final class TimeTool implements NodeAction<L08State> {
        @Override
        public Map<String, Object> apply(L08State state) {
            String now = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
            System.out.println("\n[time_tool] now=" + now);
            return Map.of(
                    L08State.TOOL_OUTPUT, "当前本地时间：" + now,
                    L08State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    /** 词典工具：静态 Map 查询。 */
    static final class LookupTool implements NodeAction<L08State> {
        @Override
        public Map<String, Object> apply(L08State state) {
            String key = state.toolInput().trim().toLowerCase();
            System.out.println("\n[lookup_tool] key=" + key);
            String body = GLOSSARY.get(key);
            if (body == null) {
                return Map.of(
                        L08State.TOOL_ERROR, "词典未收录：" + key,
                        L08State.STEP_COUNT, state.stepCount() + 1
                );
            }
            return Map.of(
                    L08State.TOOL_OUTPUT, body,
                    L08State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    /** 工具支路统一收尾：把<strong>本轮已执行的那一个</strong>工具的成功/失败排版进 final_answer（与第 5 课 finalize 同义，非多工具合并）。 */
    static final class FinalizeResult implements NodeAction<L08State> {
        @Override
        public Map<String, Object> apply(L08State state) {
            System.out.println("\n[finalize_result] 格式化本轮单工具输出");
            String finalText;
            if (!state.toolError().isEmpty()) {
                finalText = "工具 `" + state.selectedTool() + "` 执行失败。\n"
                        + "错误：" + state.toolError() + "\n"
                        + "路由说明：" + state.routeNote();
            } else {
                finalText = "工具 `" + state.selectedTool() + "` 执行成功。\n"
                        + "结果：" + state.toolOutput() + "\n"
                        + "路由说明：" + state.routeNote();
            }
            return Map.of(
                    L08State.FINAL_ANSWER, finalText,
                    L08State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    /** 未命中专用工具时的兜底节点。 */
    static final class FallbackReply implements NodeAction<L08State> {
        @Override
        public Map<String, Object> apply(L08State state) {
            System.out.println("\n[fallback_reply] 兜底");
            String text = "【兜底】当前输入未命中 calculator / time / lookup 的选取规则。\n"
                    + "你可以尝试：\n"
                    + "  - 算术：「计算 3*(2+1)」或直接「3*(2+1)」\n"
                    + "  - 时间：「现在几点」\n"
                    + "  - 词条：「LangGraph是什么」或单独发送「langgraph」\n"
                    + "\n原始输入：" + state.userInput() + "\n"
                    + "策略说明：" + state.routeNote();
            return Map.of(
                    L08State.FINAL_ANSWER, text,
                    L08State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    /**
     * 构建编译前的 StateGraph（与 Python {@code build_graph} 等价）。
     */
    public static StateGraph<L08State> buildGraph() throws GraphStateException {
        Map<String, String> routes = new HashMap<>();
        routes.put("calculator_tool", "calculator_tool");
        routes.put("time_tool", "time_tool");
        routes.put("lookup_tool", "lookup_tool");
        routes.put("fallback_reply", "fallback_reply");

        return new StateGraph<>(L08State.SCHEMA, L08State::new)
                .addNode("select_tools", node_async(new SelectTools()))
                .addNode("calculator_tool", node_async(new CalculatorTool()))
                .addNode("time_tool", node_async(new TimeTool()))
                .addNode("lookup_tool", node_async(new LookupTool()))
                .addNode("finalize_result", node_async(new FinalizeResult()))
                .addNode("fallback_reply", node_async(new FallbackReply()))
                .addEdge(START, "select_tools")
                .addConditionalEdges(
                        "select_tools",
                        edge_async(s -> {
                            System.out.println("\n[route_tools] -> " + s.selectedTool());
                            return switch (s.selectedTool()) {
                                case "calculator" -> "calculator_tool";
                                case "time" -> "time_tool";
                                case "lookup" -> "lookup_tool";
                                default -> "fallback_reply";
                            };
                        }),
                        routes
                )
                .addEdge("calculator_tool", "finalize_result")
                .addEdge("time_tool", "finalize_result")
                .addEdge("lookup_tool", "finalize_result")
                .addEdge("finalize_result", END)
                .addEdge("fallback_reply", END);
    }

    /** 与 Python run_case 对等的单次调用。 */
    static void runCase(org.bsc.langgraph4j.CompiledGraph<?> g, String userInput) throws GraphStateException {
        Map<String, Object> init = new HashMap<>();
        init.put(L08State.USER_INPUT, userInput);
        init.put(L08State.SELECTED_TOOL, "");
        init.put(L08State.TOOL_INPUT, "");
        init.put(L08State.ROUTE_NOTE, "");
        init.put(L08State.TOOL_OUTPUT, "");
        init.put(L08State.TOOL_ERROR, "");
        init.put(L08State.FINAL_ANSWER, "");
        init.put(L08State.STEP_COUNT, 0);
        System.out.println("\n" + "=".repeat(80));
        System.out.println("案例：" + userInput);
        System.out.println("=".repeat(80));
        var fs = g.invoke(init).orElseThrow();
        if (fs instanceof L08State s) {
            System.out.println("\n[结束] selected_tool = " + s.selectedTool());
            System.out.println("final_answer:\n" + s.value(L08State.FINAL_ANSWER).orElse(""));
        }
    }

    /** 入口：多案例覆盖主路径 / 兜底 / 计算器故障。 */
    public static void main(String[] args) throws GraphStateException {
        var g = buildGraph().compile();
        runCase(g, "计算 20 + 22");
        runCase(g, "现在几点");
        runCase(g, "LangGraph是什么");
        runCase(g, "langchain");
        runCase(g, "你好，随便聊聊");
        runCase(g, "计算 1 + )");
    }
}
