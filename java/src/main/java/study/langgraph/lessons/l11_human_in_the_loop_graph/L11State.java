package study.langgraph.lessons.l11_human_in_the_loop_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.Map;

/**
 * 第十一课状态：与 Python {@code HitlState} 字段对齐（教学用）。
 */
public final class L11State extends AgentState {

    public static final String TOPIC = "topic";
    public static final String PROPOSAL = "proposal";
    public static final String REVISION_COUNT = "revision_count";
    public static final String HUMAN_DECISION = "human_decision";
    public static final String FINAL_OUTPUT = "final_output";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            TOPIC, Channels.base(() -> ""),
            PROPOSAL, Channels.base(() -> ""),
            REVISION_COUNT, Channels.base(() -> 0),
            HUMAN_DECISION, Channels.base(() -> ""),
            FINAL_OUTPUT, Channels.base(() -> "")
    );

    public L11State(Map<String, Object> init) {
        super(init);
    }

    public String topic() {
        return value(TOPIC).map(Object::toString).orElse("");
    }

    public String proposal() {
        return value(PROPOSAL).map(Object::toString).orElse("");
    }

    public int revisionCount() {
        return value(REVISION_COUNT).map(o -> ((Number) o).intValue()).orElse(0);
    }

    public String humanDecision() {
        return value(HUMAN_DECISION).map(Object::toString).orElse("");
    }

    public String finalOutput() {
        return value(FINAL_OUTPUT).map(Object::toString).orElse("");
    }
}
