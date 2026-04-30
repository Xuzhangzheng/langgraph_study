package study.langgraph.lessons.l02_branching_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.Map;

/** 与 Python {@code BranchingState} 字段对齐。 */
public final class L02State extends AgentState {

    public static final String USER_INPUT = "user_input";
    public static final String ROUTE = "route";
    public static final String ANSWER = "answer";
    public static final String STEP_COUNT = "step_count";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            USER_INPUT, Channels.base(() -> ""),
            ROUTE, Channels.base(() -> ""),
            ANSWER, Channels.base(() -> ""),
            STEP_COUNT, Channels.base(() -> 0)
    );

    public L02State(Map<String, Object> init) {
        super(init);
    }

    public String userInput() {
        return value(USER_INPUT).map(Object::toString).orElse("");
    }

    public String route() {
        return value(ROUTE).map(Object::toString).orElse("");
    }

    public int stepCount() {
        return value(STEP_COUNT).map(v -> ((Number) v).intValue()).orElse(0);
    }

    public String answer() {
        return value(ANSWER).map(Object::toString).orElse("");
    }
}
