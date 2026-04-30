package study.langgraph.lessons.l03_loop_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.Map;

public final class L03State extends AgentState {

    public static final String TOPIC = "topic";
    public static final String DRAFT = "draft";
    public static final String MIN_LENGTH = "min_length";
    public static final String ITERATION = "iteration";
    public static final String MAX_ITERATIONS = "max_iterations";
    public static final String DONE = "done";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            TOPIC, Channels.base(() -> ""),
            DRAFT, Channels.base(() -> ""),
            MIN_LENGTH, Channels.base(() -> 0),
            ITERATION, Channels.base(() -> 0),
            MAX_ITERATIONS, Channels.base(() -> 0),
            DONE, Channels.base(() -> false)
    );

    public L03State(Map<String, Object> init) {
        super(init);
    }

    public String topic() {
        return value(TOPIC).map(Object::toString).orElse("");
    }

    public String draft() {
        return value(DRAFT).map(Object::toString).orElse("");
    }

    public int minLength() {
        return value(MIN_LENGTH).map(v -> ((Number) v).intValue()).orElse(0);
    }

    public int iteration() {
        return value(ITERATION).map(v -> ((Number) v).intValue()).orElse(0);
    }

    public int maxIterations() {
        return value(MAX_ITERATIONS).map(v -> ((Number) v).intValue()).orElse(0);
    }

    public boolean done() {
        return value(DONE).map(v -> Boolean.TRUE.equals(v) || Boolean.parseBoolean(v.toString())).orElse(false);
    }
}
