package study.langgraph.lessons.l17_multi_agent_collaboration;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 第十七课状态：对照 Python {@code AgentCollabState}（{@code 17_multi_agent_collaboration_graph.py}）。
 * <p>
 * {@link #ITERATION} 只在 Critic 裁定为非 {@code pass} 时递增，与 {@link #MAX_ITERATIONS}
 * 比较决定走修订回路还是 {@code finalize_abort}。
 */
public final class L17State extends AgentState {

    /** 链路追踪 ID：与前几课一致的审计习惯 */
    public static final String REQUEST_ID = "request_id";
    /** 经门禁 trim 的业务目标正文 */
    public static final String USER_GOAL = "user_goal";
    /** {@code llm}：尝试远端模型；{@code fallback}：与 Python 离线规则对齐 */
    public static final String MODE = "mode";
    /** {@code pending}｜{@code ok}｜{@code invalid} */
    public static final String GOAL_GATE = "goal_gate";
    /** Planner 输出：可读步骤表 */
    public static final String PLAN_OUTLINE = "plan_outline";
    /** Executor 当前草案（可能被多轮重写） */
    public static final String DRAFT_ANSWER = "draft_answer";
    /** 对用户暴露的最终收口——通过或 abort 节点的产物 */
    public static final String FINAL_ANSWER = "final_answer";
    /** Critic 最近一次裁定 */
    public static final String CRITIC_VERDICT = "critic_verdict";
    /** 供下一轮 Planner/Executor 消化的短评——状态即协议 */
    public static final String CRITIC_FEEDBACK = "critic_feedback";
    /** 已发生的「非通过」计数（由 Critic 节点维护） */
    public static final String ITERATION = "iteration";
    /** 允许的修理轮上限：超限即 {@code finalize_abort} */
    public static final String MAX_ITERATIONS = "max_iterations";
    /** 追加型诊断字段 */
    public static final String DIAGNOSTICS = "diagnostics";

    /**
     * 通道语义：{@code base} 表示整字段覆盖；{@code appender} 等价 Python {@code Annotated[list, operator.add]}。
     * 字段多于 {@link Map#of} 允许的 10 对上限时使用 {@link Map#ofEntries}。
     */
    public static final Map<String, Channel<?>> SCHEMA = Map.ofEntries(
            Map.entry(REQUEST_ID, Channels.base(() -> "")),
            Map.entry(USER_GOAL, Channels.base(() -> "")),
            Map.entry(MODE, Channels.base(() -> "fallback")),
            Map.entry(GOAL_GATE, Channels.base(() -> "pending")),
            Map.entry(PLAN_OUTLINE, Channels.base(() -> "")),
            Map.entry(DRAFT_ANSWER, Channels.base(() -> "")),
            Map.entry(FINAL_ANSWER, Channels.base(() -> "")),
            Map.entry(CRITIC_VERDICT, Channels.base(() -> "pending")),
            Map.entry(CRITIC_FEEDBACK, Channels.base(() -> "")),
            Map.entry(ITERATION, Channels.base(() -> 0)),
            Map.entry(MAX_ITERATIONS, Channels.base(() -> 3)),
            Map.entry(DIAGNOSTICS, Channels.appender(ArrayList::new))
    );

    public L17State(Map<String, Object> init) {
        super(init);
    }

    /** 读出 request_id，若无则回落空串，避免 NPE */
    public String requestId() {
        return value(REQUEST_ID).map(Object::toString).orElse("");
    }

    public String userGoal() {
        return value(USER_GOAL).map(Object::toString).orElse("");
    }

    public String mode() {
        return value(MODE).map(Object::toString).orElse("fallback");
    }

    public String goalGate() {
        return value(GOAL_GATE).map(Object::toString).orElse("pending");
    }

    public String planOutline() {
        return value(PLAN_OUTLINE).map(Object::toString).orElse("");
    }

    public String draftAnswer() {
        return value(DRAFT_ANSWER).map(Object::toString).orElse("");
    }

    public String finalAnswer() {
        return value(FINAL_ANSWER).map(Object::toString).orElse("");
    }

    public String criticVerdict() {
        return value(CRITIC_VERDICT).map(Object::toString).orElse("pending");
    }

    public String criticFeedback() {
        return value(CRITIC_FEEDBACK).map(Object::toString).orElse("");
    }

    public int iteration() {
        return value(ITERATION)
                .map(v -> v instanceof Number ? ((Number) v).intValue() : Integer.parseInt(v.toString()))
                .orElse(0);
    }

    public int maxIterations() {
        return value(MAX_ITERATIONS)
                .map(v -> v instanceof Number ? ((Number) v).intValue() : Integer.parseInt(v.toString()))
                .orElse(3);
    }

    @SuppressWarnings("unchecked")
    public List<String> diagnostics() {
        return value(DIAGNOSTICS).map(v -> (List<String>) v).orElseGet(List::of);
    }
}
