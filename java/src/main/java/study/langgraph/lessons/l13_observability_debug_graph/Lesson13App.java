package study.langgraph.lessons.l13_observability_debug_graph;

import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第十三课：可观测性与调试（对照 {@code 13_observability_debug_graph.py}）。
 * <p>
 * Python 侧的 {@code stream_mode} / checkpoints 流式事件为本仓库<strong>主推</strong>实操；
 * 此处用 {@code java.util.logging} + {@link org.bsc.langgraph4j.CompiledGraph#stream(Map)} 的 chunk
 * 演示「节点级 stderr 日志」与「按步快照」两件事可分开做但仍应对照阅读。
 */
public final class Lesson13App {

    private Lesson13App() {
    }

    private static final Logger LOG = Logger.getLogger(Lesson13App.class.getName());

    static String routeAfterGate(L13State state) {
        String text = state.inputText().trim();
        if (text.isEmpty()) {
            return "stub_error";
        }
        if (text.toLowerCase().contains("boom")) {
            return "stub_error";
        }
        return "process";
    }

    static StateGraph<L13State> buildGraph() throws GraphStateException {
        Map<String, String> routes = Map.of(
                "process", "process",
                "stub_error", "stub_error"
        );

        return new StateGraph<>(L13State.SCHEMA, L13State::new)
                .addNode("gate", node_async((NodeAction<L13State>) state -> {
                    String rid = state.requestId();
                    String text = state.inputText().trim();
                    LOG.info(() -> "[gate] request_id=" + rid + " inputLen=" + text.length());
                    return Map.of(L13State.DIAGNOSTICS, java.util.List.of(
                            "gate:seen request_id=" + rid + " len=" + text.length()));
                }))
                .addNode("process", node_async((NodeAction<L13State>) state -> {
                    String rid = state.requestId();
                    String text = state.inputText().trim();
                    LOG.info(() -> "[process] request_id=" + rid);
                    String summary = text.length() > 48 ? text.substring(0, 48) + "…" : text;
                    return Map.of(
                            L13State.DIAGNOSTICS, java.util.List.of("process:ok"),
                            L13State.RESULT_SUMMARY, "已处理：" + summary);
                }))
                .addNode("finalize", node_async((NodeAction<L13State>) state -> {
                    String rid = state.requestId();
                    LOG.info(() -> "[finalize] request_id=" + rid);
                    return Map.of(L13State.DIAGNOSTICS, java.util.List.of("finalize:done"));
                }))
                .addNode("stub_error", node_async((NodeAction<L13State>) state -> {
                    String rid = state.requestId();
                    String text = state.inputText().trim();
                    boolean empty = text.isEmpty();
                    boolean boom = text.toLowerCase().contains("boom");
                    LOG.warning(() -> "[stub_error] request_id=" + rid + " empty=" + empty + " boom=" + boom);
                    String reason = empty ? "empty_input" : "keyword_boom";
                    return Map.of(
                            L13State.DIAGNOSTICS, java.util.List.of("stub_error:" + reason),
                            L13State.RESULT_SUMMARY, "【故障路径】" + reason);
                }))
                .addEdge(START, "gate")
                .addConditionalEdges("gate", edge_async(Lesson13App::routeAfterGate), routes)
                .addEdge("process", "finalize")
                .addEdge("finalize", END)
                .addEdge("stub_error", END);
    }

    static void invokeCase(org.bsc.langgraph4j.CompiledGraph<L13State> g, String requestId, String input)
            throws GraphStateException {
        Map<String, Object> init = new HashMap<>();
        init.put(L13State.REQUEST_ID, requestId);
        init.put(L13State.INPUT_TEXT, input);
        init.put(L13State.DIAGNOSTICS, new ArrayList<String>());
        init.put(L13State.RESULT_SUMMARY, "");

        System.out.println("\n" + "=".repeat(72));
        System.out.println("invoke: request_id=" + requestId + " input=" + (input.contains("\n") ? "..." : input));
        System.out.println("=".repeat(72));

        Object raw = g.invoke(init).orElseThrow();
        if (raw instanceof L13State) {
            L13State end = (L13State) raw;
            System.out.println("result_summary: " + end.resultSummary());
            System.out.println("diagnostics: " + end.diagnostics());
        } else {
            System.out.println("unexpected state type: " + raw.getClass());
        }
    }

    public static void main(String[] args) throws GraphStateException {
        Logger root = Logger.getLogger("");
        root.setLevel(Level.INFO);
        for (var h : root.getHandlers()) {
            h.setLevel(Level.INFO);
        }
        LOG.setLevel(Level.INFO);

        System.out.println("=".repeat(72));
        System.out.println("第十三课：可观测性与调试（LangGraph4j）");
        System.out.println("=".repeat(72));
        System.out.println("对照 Python：`stream_mode` / `RunnableConfig.tags` / `checkpoints` 以 py 脚本为准。");

        var compiled = buildGraph().compile();

        invokeCase(compiled, "req-java-happy", "查询订单 OG-9001 状态");
        invokeCase(compiled, "req-java-boom", "trigger boom please");
        invokeCase(compiled, "req-java-empty", "   ");

        System.out.println("\n" + "=".repeat(72));
        System.out.println("stream（LangGraph4j chunk 迭代，对照 Python updates/values）");
        System.out.println("=".repeat(72));
        Map<String, Object> init = new HashMap<>();
        init.put(L13State.REQUEST_ID, "req-java-stream");
        init.put(L13State.INPUT_TEXT, "chunk 迭代示例");
        init.put(L13State.DIAGNOSTICS, new ArrayList<String>());
        init.put(L13State.RESULT_SUMMARY, "");
        int i = 0;
        for (var chunk : compiled.stream(init)) {
            i++;
            System.out.println("  --- chunk #" + i + " ---");
            System.out.println("  " + chunk);
        }
    }
}
