package study.langgraph.lessons.l10_parallel_fanin_graph;

import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第十课：并行 fan-out / fan-in 与单点聚合（对照 {@code 10_parallel_fanin_graph.py}）。
 * <p>
 * 与 04c 分工：04c 侧重静态多分边 + appender + 无 reducer 异常对照；本课侧重分支写 {@code fragments}、
 * {@code aggregate} 单写 {@code final_report} 的工程模式。
 * <p>
 * 与 Python 差异：动态条数 fan-out（{@code Send}）在 Java 侧仍建议以静态边或引擎扩展实现，参见 l04b 类注释。
 */
public final class Lesson10App {

    private Lesson10App() {
    }

    public static final class L10State extends AgentState {
        public static final String REQUEST_ID = "request_id";
        public static final String TASK_HINT = "task_hint";
        public static final String FRAGMENTS = "fragments";
        public static final String FINAL_REPORT = "final_report";

        public static final Map<String, Channel<?>> SCHEMA = Map.of(
                REQUEST_ID, Channels.base(() -> ""),
                TASK_HINT, Channels.base(() -> ""),
                FRAGMENTS, Channels.appender(ArrayList::new),
                FINAL_REPORT, Channels.base(() -> "")
        );

        public L10State(Map<String, Object> init) {
            super(init);
        }

        public String requestId() {
            return value(REQUEST_ID).map(Object::toString).orElse("");
        }

        public String taskHint() {
            return value(TASK_HINT).map(Object::toString).orElse("");
        }

        @SuppressWarnings("unchecked")
        public List<String> fragments() {
            return value(FRAGMENTS).map(v -> (List<String>) v).orElseGet(List::of);
        }

        public String finalReport() {
            return value(FINAL_REPORT).map(Object::toString).orElse("");
        }
    }

    static StateGraph<L10State> buildGraph() throws GraphStateException {
        return new StateGraph<>(L10State.SCHEMA, L10State::new)
                .addNode("fan_out", node_async((NodeAction<L10State>) state -> {
                    String rid = state.requestId();
                    System.out.println("  [fan_out] 为 request_id=" + rid + " 准备三路并行分支");
                    return Map.of(L10State.TASK_HINT, "scope:" + rid);
                }))
                .addNode("branch_1", node_async((NodeAction<L10State>) state -> {
                    String hint = state.taskHint();
                    System.out.println("  [branch_1] 模拟 IO/子任务 A，hint=" + hint);
                    return Map.of(L10State.FRAGMENTS, List.of("branch_1: 完成 A · " + hint));
                }))
                .addNode("branch_2", node_async((NodeAction<L10State>) state -> {
                    String hint = state.taskHint();
                    System.out.println("  [branch_2] 模拟 IO/子任务 B，hint=" + hint);
                    return Map.of(L10State.FRAGMENTS, List.of("branch_2: 完成 B · " + hint));
                }))
                .addNode("branch_3", node_async((NodeAction<L10State>) state -> {
                    String hint = state.taskHint();
                    System.out.println("  [branch_3] 模拟 IO/子任务 C，hint=" + hint);
                    return Map.of(L10State.FRAGMENTS, List.of("branch_3: 完成 C · " + hint));
                }))
                .addNode("aggregate", node_async((NodeAction<L10State>) state -> {
                    List<String> frags = state.fragments();
                    String body = frags.stream().sorted().collect(Collectors.joining("\n"));
                    String report = "=== 并行汇总 ===\n" + body + "\n=== 共 " + frags.size() + " 条分支产出 ===\n";
                    System.out.println("\n[aggregate] 单点写入 final_report（多分支不写此键）");
                    return Map.of(L10State.FINAL_REPORT, report);
                }))
                .addEdge(START, "fan_out")
                .addEdge("fan_out", "branch_1")
                .addEdge("fan_out", "branch_2")
                .addEdge("fan_out", "branch_3")
                .addEdge("branch_1", "aggregate")
                .addEdge("branch_2", "aggregate")
                .addEdge("branch_3", "aggregate")
                .addEdge("aggregate", END);
    }

    public static void main(String[] args) throws GraphStateException {
        Map<String, Object> initial = new HashMap<>();
        initial.put(L10State.REQUEST_ID, "REQ-10-demo");
        initial.put(L10State.TASK_HINT, "");
        initial.put(L10State.FRAGMENTS, new ArrayList<String>());
        initial.put(L10State.FINAL_REPORT, "");

        System.out.println("=".repeat(72));
        System.out.println("第十课：并行 fan-out / fan-in（LangGraph4j）");
        System.out.println("=".repeat(72));

        var compiled = buildGraph().compile();
        var fin = compiled.invoke(initial).orElseThrow();
        if (fin instanceof L10State) {
            L10State s = (L10State) fin;
            System.out.println("\n最终 final_report:\n");
            System.out.println(s.finalReport());
        }

        System.out.println("\n" + "=".repeat(72));
        System.out.println("stream");
        System.out.println("=".repeat(72));
        int i = 0;
        for (var chunk : compiled.stream(initial)) {
            i++;
            System.out.println("  --- chunk #" + i + " ---");
            System.out.println("  " + chunk);
        }
    }
}
