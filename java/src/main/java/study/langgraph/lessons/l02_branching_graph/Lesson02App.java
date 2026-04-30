package study.langgraph.lessons.l02_branching_graph;

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
 * 第二课：条件分支（对照 {@code 02_branching_graph.py}）。
 */
public final class Lesson02App {

    private Lesson02App() {
    }

    static final class AnalyzeInput implements NodeAction<L02State> {
        @Override
        public Map<String, Object> apply(L02State state) {
            String userInput = state.userInput();
            System.out.println("\n[analyze_input] 节点开始执行");
            System.out.println("[analyze_input] user_input=" + userInput + ", step_count=" + state.stepCount());
            String route;
            if (userInput.contains("天气")) {
                route = "weather";
            } else if (userInput.contains("计算") || userInput.contains("+")) {
                route = "math";
            } else {
                route = "chat";
            }
            System.out.println("[analyze_input] 判断得到 route: " + route);
            return Map.of(
                    L02State.ROUTE, route,
                    L02State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    static final class WeatherNode implements NodeAction<L02State> {
        @Override
        public Map<String, Object> apply(L02State state) {
            System.out.println("\n[weather_node] 节点开始执行");
            System.out.println("[weather_node] step_count=" + state.stepCount());
            String answer =
                    "这是天气分支给出的模拟回复：你当前的问题被识别为天气相关，后续可以在这里接入真实天气 API。";
            return Map.of(
                    L02State.ANSWER, answer,
                    L02State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    static final class MathNode implements NodeAction<L02State> {
        @Override
        public Map<String, Object> apply(L02State state) {
            System.out.println("\n[math_node] 节点开始执行");
            System.out.println("[math_node] step_count=" + state.stepCount());
            String answer =
                    "这是数学分支给出的模拟回复：你的问题被识别为计算相关，后续可以在这里接入计算工具。";
            return Map.of(
                    L02State.ANSWER, answer,
                    L02State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    static final class ChatNode implements NodeAction<L02State> {
        @Override
        public Map<String, Object> apply(L02State state) {
            System.out.println("\n[chat_node] 节点开始执行");
            System.out.println("[chat_node] step_count=" + state.stepCount());
            String answer =
                    "这是普通聊天分支给出的模拟回复：当前输入没有命中特定业务路由，所以进入默认聊天处理。";
            return Map.of(
                    L02State.ANSWER, answer,
                    L02State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    private static Map<String, String> routeMapping() {
        Map<String, String> m = new HashMap<>();
        m.put("weather_node", "weather_node");
        m.put("math_node", "math_node");
        m.put("chat_node", "chat_node");
        return m;
    }

    public static StateGraph buildGraph() throws GraphStateException {
        return new StateGraph<>(L02State.SCHEMA, L02State::new)
                .addNode("analyze_input", node_async(new AnalyzeInput()))
                .addNode("weather_node", node_async(new WeatherNode()))
                .addNode("math_node", node_async(new MathNode()))
                .addNode("chat_node", node_async(new ChatNode()))
                .addEdge(START, "analyze_input")
                .addConditionalEdges(
                        "analyze_input",
                        edge_async(state -> {
                            String route = state.route();
                            System.out.println("\n[route_next_step] 路由函数开始执行");
                            System.out.println("[route_next_step] 当前 route: " + route);
                            if ("weather".equals(route)) {
                                return "weather_node";
                            }
                            if ("math".equals(route)) {
                                return "math_node";
                            }
                            return "chat_node";
                        }),
                        routeMapping()
                )
                .addEdge("weather_node", END)
                .addEdge("math_node", END)
                .addEdge("chat_node", END);
    }

    static void runCase(org.bsc.langgraph4j.CompiledGraph<L02State> graph, String userInput) throws GraphStateException {
        Map<String, Object> initial = new HashMap<>();
        initial.put(L02State.USER_INPUT, userInput);
        initial.put(L02State.ROUTE, "");
        initial.put(L02State.ANSWER, "");
        initial.put(L02State.STEP_COUNT, 0);
        System.out.println("\n" + "=".repeat(80));
        System.out.println("开始运行案例，用户输入：" + userInput);
        System.out.println("=".repeat(80));
        System.out.println("初始 state: " + initial);
        var finalState = graph.invoke(initial).orElseThrow();
        System.out.println("\n[案例执行完成]");
        System.out.println("最终 state: route=" + finalState.route() + ", answer=" + finalState.answer());
    }

    public static void main(String[] args) throws GraphStateException {
        var graph = buildGraph().compile();
        runCase(graph, "今天北京天气怎么样？");
        runCase(graph, "请帮我计算 3 + 5");
        runCase(graph, "你好，给我介绍一下 LangGraph");
    }
}
