package study.langgraph.lessons.l08_multi_tool_routing;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.Map;

/**
 * 第八课状态 schema（对照 {@code 08_multi_tool_routing_graph.py} 的 {@code MultiToolState}）。
 * <p>
 * 各 Channel 使用 {@code Channels.base} 声明默认值，便于 invoke 时只填 {@code user_input} 等少数字段。
 */
public final class L08State extends AgentState {

    /** 用户原始输入。 */
    public static final String USER_INPUT = "user_input";
    /** 选择器结果：calculator | time | lookup | fallback。 */
    public static final String SELECTED_TOOL = "selected_tool";
    /** 传给具体工具的参数（算术表达式、词条 key 等）。 */
    public static final String TOOL_INPUT = "tool_input";
    /** 人类可读：为何选这条路（教学观察日志）。 */
    public static final String ROUTE_NOTE = "route_note";
    /** 工具成功时的输出文本。 */
    public static final String TOOL_OUTPUT = "tool_output";
    /** 工具失败时的错误文本。 */
    public static final String TOOL_ERROR = "tool_error";
    /** 对用户展示的最终答复（finalize_result 或兜底节点写入）。 */
    public static final String FINAL_ANSWER = "final_answer";
    /** 节点执行计数（教学用）。 */
    public static final String STEP_COUNT = "step_count";

    /** LangGraph4j 要求的「字段名 -> 通道」映射表。 */
    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            USER_INPUT, Channels.base(() -> ""),
            SELECTED_TOOL, Channels.base(() -> ""),
            TOOL_INPUT, Channels.base(() -> ""),
            ROUTE_NOTE, Channels.base(() -> ""),
            TOOL_OUTPUT, Channels.base(() -> ""),
            TOOL_ERROR, Channels.base(() -> ""),
            FINAL_ANSWER, Channels.base(() -> ""),
            STEP_COUNT, Channels.base(() -> 0)
    );

    public L08State(Map<String, Object> init) {
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

    public String routeNote() {
        return value(ROUTE_NOTE).map(Object::toString).orElse("");
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
