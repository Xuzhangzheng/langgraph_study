package study.langgraph.lessons.l01_hello_langgraph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.Map;

/**
 * 与 Python {@code 01_hello_langgraph.py} 中 {@code LessonState} 字段对齐：message、step_count。
 */
public final class L01LessonState extends AgentState {

    public static final String MESSAGE = "message";
    public static final String STEP_COUNT = "step_count";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            MESSAGE, Channels.base(() -> ""),
            STEP_COUNT, Channels.base(() -> 0)
    );

    public L01LessonState(Map<String, Object> initData) {
        super(initData);
    }

    public String message() {
        return value(MESSAGE).map(Object::toString).orElse("");
    }

    public int stepCount() {
        return value(STEP_COUNT).map(v -> ((Number) v).intValue()).orElse(0);
    }
}
