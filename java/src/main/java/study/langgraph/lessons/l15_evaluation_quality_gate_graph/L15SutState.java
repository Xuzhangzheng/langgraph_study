package study.langgraph.lessons.l15_evaluation_quality_gate_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 第十五课：被测业务图（SUT）状态，与 Python {@code SutState} / {@code TypedDict} 键名一致。
 * <p>
 * <b>本课契约要点：</b>评测脚本与对外 API 只依赖这些字段名；改名即破坏「接口不变」约束，
 * 应先在黄金用例与兼容性清单中显式评审。
 */
public final class L15SutState extends AgentState {

    /** 用例或请求 ID；评测时与 {@code thread_id} 后缀对齐便于排查 */
    public static final String REQUEST_ID = "request_id";
    /** 用户原始消息；{@code normalize_message} 节点负责 trim */
    public static final String USER_MESSAGE = "user_message";
    /**
     * 分类结果：{@code classify_intent} 写入；条件边 {@code route_after_classify} 的唯一路由键。
     * 取值：{@code refund} | {@code shipping} | {@code general} | {@code invalid} | 空串（初值）
     */
    public static final String INTENT = "intent";
    /** 坐席草稿回复；各 {@code draft_*} 节点写入 */
    public static final String REPLY = "reply";
    /** 追加型审计痕迹，与 Python {@code Annotated[list, operator.add]} 同目的 */
    public static final String DIAGNOSTICS = "diagnostics";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            REQUEST_ID, Channels.base(() -> ""),
            USER_MESSAGE, Channels.base(() -> ""),
            INTENT, Channels.base(() -> ""),
            REPLY, Channels.base(() -> ""),
            DIAGNOSTICS, Channels.appender(ArrayList::new)
    );

    public L15SutState(Map<String, Object> init) {
        super(init);
    }

    public String requestId() {
        return value(REQUEST_ID).map(Object::toString).orElse("");
    }

    public String userMessage() {
        return value(USER_MESSAGE).map(Object::toString).orElse("");
    }

    public String intent() {
        return value(INTENT).map(Object::toString).orElse("");
    }

    public String reply() {
        return value(REPLY).map(Object::toString).orElse("");
    }

    @SuppressWarnings("unchecked")
    public List<String> diagnostics() {
        return value(DIAGNOSTICS).map(v -> (List<String>) v).orElseGet(List::of);
    }
}
