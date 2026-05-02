package study.langgraph.lessons.l19_support_desk;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 第十九课 Capstone 状态：与 Python {@code lesson19_support_desk.state.SupportDeskState} 对齐。
 */
public final class L19State extends AgentState {

    public static final String REQUEST_ID = "request_id";
    public static final String USER_MESSAGE = "user_message";
    public static final String NORMALIZED_MESSAGE = "normalized_message";
    public static final String MESSAGE_GATE = "message_gate";
    public static final String INTENT = "intent";
    public static final String TOOL_EXPRESSION = "tool_expression";
    public static final String TOOL_OUTPUT = "tool_output";
    public static final String TOOL_ERROR = "tool_error";
    public static final String DRAFT_REPLY = "draft_reply";
    public static final String FINAL_REPLY = "final_reply";
    public static final String QUALITY_SCORE = "quality_score";
    public static final String QUALITY_PASSED = "quality_passed";
    public static final String FEEDBACK_FOR_GENERATION = "feedback_for_generation";
    public static final String ATTEMPT = "attempt";
    public static final String MAX_ATTEMPTS = "max_attempts";
    public static final String MODE = "mode";
    public static final String DIAGNOSTICS = "diagnostics";

    public static final Map<String, Channel<?>> SCHEMA = Map.ofEntries(
            Map.entry(REQUEST_ID, Channels.base(() -> "")),
            Map.entry(USER_MESSAGE, Channels.base(() -> "")),
            Map.entry(NORMALIZED_MESSAGE, Channels.base(() -> "")),
            Map.entry(MESSAGE_GATE, Channels.base(() -> "pending")),
            Map.entry(INTENT, Channels.base(() -> "pending")),
            Map.entry(TOOL_EXPRESSION, Channels.base(() -> "")),
            Map.entry(TOOL_OUTPUT, Channels.base(() -> "")),
            Map.entry(TOOL_ERROR, Channels.base(() -> "")),
            Map.entry(DRAFT_REPLY, Channels.base(() -> "")),
            Map.entry(FINAL_REPLY, Channels.base(() -> "")),
            Map.entry(QUALITY_SCORE, Channels.base(() -> 0)),
            Map.entry(QUALITY_PASSED, Channels.base(() -> false)),
            Map.entry(FEEDBACK_FOR_GENERATION, Channels.base(() -> "")),
            Map.entry(ATTEMPT, Channels.base(() -> 0)),
            Map.entry(MAX_ATTEMPTS, Channels.base(() -> 2)),
            Map.entry(MODE, Channels.base(() -> "fallback")),
            Map.entry(DIAGNOSTICS, Channels.appender(ArrayList::new))
    );

    public L19State(Map<String, Object> init) {
        super(init);
    }

    public String normalizedMessage() {
        return value(NORMALIZED_MESSAGE).map(Object::toString).orElse("");
    }

    public String messageGate() {
        return value(MESSAGE_GATE).map(Object::toString).orElse("pending");
    }

    public String intent() {
        return value(INTENT).map(Object::toString).orElse("pending");
    }

    public String toolExpression() {
        return value(TOOL_EXPRESSION).map(Object::toString).orElse("");
    }

    public String draftReply() {
        return value(DRAFT_REPLY).map(Object::toString).orElse("");
    }

    public int attempt() {
        return value(ATTEMPT)
                .map(v -> v instanceof Number ? ((Number) v).intValue() : Integer.parseInt(v.toString()))
                .orElse(0);
    }

    public int maxAttempts() {
        return value(MAX_ATTEMPTS)
                .map(v -> v instanceof Number ? ((Number) v).intValue() : Integer.parseInt(v.toString()))
                .orElse(2);
    }

    public boolean qualityPassed() {
        return value(QUALITY_PASSED)
                .map(v -> v instanceof Boolean ? (Boolean) v : Boolean.parseBoolean(String.valueOf(v)))
                .orElse(false);
    }

    public String finalReply() {
        return value(FINAL_REPLY).map(Object::toString).orElse("");
    }

    @SuppressWarnings("unchecked")
    public List<String> diagnostics() {
        return value(DIAGNOSTICS).map(v -> (List<String>) v).orElseGet(List::of);
    }

    public String mode() {
        return value(MODE).map(Object::toString).orElse("fallback");
    }

    public String userMessage() {
        return value(USER_MESSAGE).map(Object::toString).orElse("");
    }

    public String toolOutput() {
        return value(TOOL_OUTPUT).map(Object::toString).orElse("");
    }
}
