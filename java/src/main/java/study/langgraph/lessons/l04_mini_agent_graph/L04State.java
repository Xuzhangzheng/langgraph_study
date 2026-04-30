package study.langgraph.lessons.l04_mini_agent_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.Map;

public final class L04State extends AgentState {

    public static final String USER_INPUT = "user_input";
    public static final String TASK_TYPE = "task_type";
    public static final String ATTEMPT = "attempt";
    public static final String MAX_ATTEMPTS = "max_attempts";
    public static final String CANDIDATE_ANSWER = "candidate_answer";
    public static final String QUALITY_SCORE = "quality_score";
    public static final String PASS_THRESHOLD = "pass_threshold";
    public static final String PASSED = "passed";
    public static final String FEEDBACK = "feedback";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            USER_INPUT, Channels.base(() -> ""),
            TASK_TYPE, Channels.base(() -> ""),
            ATTEMPT, Channels.base(() -> 0),
            MAX_ATTEMPTS, Channels.base(() -> 0),
            CANDIDATE_ANSWER, Channels.base(() -> ""),
            QUALITY_SCORE, Channels.base(() -> 0),
            PASS_THRESHOLD, Channels.base(() -> 0),
            PASSED, Channels.base(() -> false),
            FEEDBACK, Channels.base(() -> "")
    );

    public L04State(Map<String, Object> init) {
        super(init);
    }

    public String userInput() {
        return value(USER_INPUT).map(Object::toString).orElse("");
    }

    public String taskType() {
        return value(TASK_TYPE).map(Object::toString).orElse("");
    }

    public int attempt() {
        return value(ATTEMPT).map(v -> ((Number) v).intValue()).orElse(0);
    }

    public int maxAttempts() {
        return value(MAX_ATTEMPTS).map(v -> ((Number) v).intValue()).orElse(0);
    }

    public String candidateAnswer() {
        return value(CANDIDATE_ANSWER).map(Object::toString).orElse("");
    }

    public int qualityScore() {
        return value(QUALITY_SCORE).map(v -> ((Number) v).intValue()).orElse(0);
    }

    public int passThreshold() {
        return value(PASS_THRESHOLD).map(v -> ((Number) v).intValue()).orElse(0);
    }

    public boolean passed() {
        return value(PASSED).map(v -> Boolean.TRUE.equals(v) || Boolean.parseBoolean(v.toString())).orElse(false);
    }

    public String feedback() {
        return value(FEEDBACK).map(Object::toString).orElse("");
    }
}
