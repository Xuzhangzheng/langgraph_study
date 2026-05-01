package study.langgraph.lessons.l13_observability_debug_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 第十三课状态（对照 {@code 13_observability_debug_graph.py} 的 {@code ObservabilityState}）。
 */
public final class L13State extends AgentState {

    public static final String REQUEST_ID = "request_id";
    public static final String INPUT_TEXT = "input_text";
    public static final String DIAGNOSTICS = "diagnostics";
    public static final String RESULT_SUMMARY = "result_summary";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            REQUEST_ID, Channels.base(() -> ""),
            INPUT_TEXT, Channels.base(() -> ""),
            DIAGNOSTICS, Channels.appender(ArrayList::new),
            RESULT_SUMMARY, Channels.base(() -> "")
    );

    public L13State(Map<String, Object> init) {
        super(init);
    }

    public String requestId() {
        return value(REQUEST_ID).map(Object::toString).orElse("");
    }

    public String inputText() {
        return value(INPUT_TEXT).map(Object::toString).orElse("");
    }

    @SuppressWarnings("unchecked")
    public List<String> diagnostics() {
        return value(DIAGNOSTICS).map(v -> (List<String>) v).orElseGet(List::of);
    }

    public String resultSummary() {
        return value(RESULT_SUMMARY).map(Object::toString).orElse("");
    }
}
