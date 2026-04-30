package study.langgraph.lessons.l05_tool_call_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.Map;

public final class L05State extends AgentState {

    public static final String USER_INPUT = "user_input";
    public static final String SELECTED_TOOL = "selected_tool";
    public static final String TOOL_INPUT = "tool_input";
    public static final String TOOL_OUTPUT = "tool_output";
    public static final String TOOL_ERROR = "tool_error";
    public static final String FINAL_ANSWER = "final_answer";
    public static final String STEP_COUNT = "step_count";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            USER_INPUT, Channels.base(() -> ""),
            SELECTED_TOOL, Channels.base(() -> ""),
            TOOL_INPUT, Channels.base(() -> ""),
            TOOL_OUTPUT, Channels.base(() -> ""),
            TOOL_ERROR, Channels.base(() -> ""),
            FINAL_ANSWER, Channels.base(() -> ""),
            STEP_COUNT, Channels.base(() -> 0)
    );

    public L05State(Map<String, Object> init) {
        super(init);
    }

    public String userInput() {
        return value(USER_INPUT).map(Object::toString).orElse("");
    }

    public String selectedTool() {
        return value(SELECTED_TOOL).map(Object::toString).orElse("");
    }

    public String toolInput() {
        return value(TOOL_INPUT).map(Object::toString).orElse("");
    }

    public String toolOutput() {
        return value(TOOL_OUTPUT).map(Object::toString).orElse("");
    }

    public String toolError() {
        return value(TOOL_ERROR).map(Object::toString).orElse("");
    }

    public int stepCount() {
        return value(STEP_COUNT).map(v -> ((Number) v).intValue()).orElse(0);
    }
}
