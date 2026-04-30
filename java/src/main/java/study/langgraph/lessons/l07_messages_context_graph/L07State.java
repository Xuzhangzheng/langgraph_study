package study.langgraph.lessons.l07_messages_context_graph;

import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.data.message.ChatMessage;
import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class L07State extends AgentState {

    public static final String MESSAGES = "messages";
    public static final String PENDING_USER_TEXT = "pending_user_text";
    public static final String MODE = "mode";
    public static final String MAX_MESSAGES_TO_KEEP = "max_messages_to_keep";
    public static final String INPUT_VALID = "input_valid";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            MESSAGES, Channels.base(() -> new ArrayList<ChatMessage>()),
            PENDING_USER_TEXT, Channels.base(() -> ""),
            MODE, Channels.base(() -> "fallback"),
            MAX_MESSAGES_TO_KEEP, Channels.base(() -> 0),
            INPUT_VALID, Channels.base(() -> false)
    );

    public L07State(Map<String, Object> init) {
        super(init);
    }

    @SuppressWarnings("unchecked")
    public List<ChatMessage> messages() {
        return value(MESSAGES)
                .map(v -> (List<ChatMessage>) v)
                .orElseGet(ArrayList::new);
    }

    public String pendingUserText() {
        return value(PENDING_USER_TEXT).map(Object::toString).orElse("");
    }

    public String mode() {
        return value(MODE).map(Object::toString).orElse("fallback");
    }

    public int maxMessagesToKeep() {
        return value(MAX_MESSAGES_TO_KEEP).map(v -> ((Number) v).intValue()).orElse(0);
    }

    public boolean inputValid() {
        return value(INPUT_VALID).map(v -> Boolean.TRUE.equals(v) || Boolean.parseBoolean(v.toString())).orElse(false);
    }
}
