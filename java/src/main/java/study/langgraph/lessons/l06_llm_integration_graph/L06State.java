package study.langgraph.lessons.l06_llm_integration_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.Map;

public final class L06State extends AgentState {

    public static final String USER_INPUT = "user_input";
    public static final String TASK_TYPE = "task_type";
    public static final String MODE = "mode";
    public static final String PROVIDER = "provider";
    public static final String SYSTEM_PROMPT = "system_prompt";
    public static final String TASK_PROMPT = "task_prompt";
    public static final String ANSWER = "answer";
    public static final String ERROR = "error";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            USER_INPUT, Channels.base(() -> ""),
            TASK_TYPE, Channels.base(() -> ""),
            MODE, Channels.base(() -> "fallback"),
            PROVIDER, Channels.base(() -> ""),
            SYSTEM_PROMPT, Channels.base(() -> ""),
            TASK_PROMPT, Channels.base(() -> ""),
            ANSWER, Channels.base(() -> ""),
            ERROR, Channels.base(() -> "")
    );

    public L06State(Map<String, Object> init) {
        super(init);
    }

    public String userInput() {
        return value(USER_INPUT).map(Object::toString).orElse("");
    }

    public String taskType() {
        return value(TASK_TYPE).map(Object::toString).orElse("");
    }

    public String mode() {
        return value(MODE).map(Object::toString).orElse("fallback");
    }

    public String provider() {
        return value(PROVIDER).map(Object::toString).orElse("");
    }

    public String systemPrompt() {
        return value(SYSTEM_PROMPT).map(Object::toString).orElse("");
    }

    public String taskPrompt() {
        return value(TASK_PROMPT).map(Object::toString).orElse("");
    }

    public String error() {
        return value(ERROR).map(Object::toString).orElse("");
    }
}
