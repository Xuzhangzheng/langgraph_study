package study.langgraph.lessons.l14_error_handling_robustness_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 第十四课状态（对照 {@code 14_error_handling_robustness_graph.py} 的 {@code RobustnessState}）。
 * <p>
 * 各常量字符串须与 Python TypedDict 键名一致，便于双端对照 demo 输出。
 */
public final class L14State extends AgentState {

    /** 请求标识，用于把日志行串起来（类似业务 trace id） */
    public static final String REQUEST_ID = "request_id";
    /**
     * 教学用输入串；Python 侧用子串 flaky / fatal / boom 模拟三类下游行为，
     * 真实项目可替换为序列化后的 API 负载摘要。
     */
    public static final String INPUT_TEXT = "input_text";
    /** 当前重试轮次；仅 {@code backoff_then_retry} 节点递增，供瞬时故障分支读取 */
    public static final String ATTEMPT = "attempt";
    /**
     * 条件边路由键：ok → finalize_success；retry → backoff；degraded → degraded_finish。
     * 空字符串表示尚未经过 {@code risky_call} 写入，正常 invoke 流程中很快会被覆盖。
     */
    public static final String RISK_STATUS = "risk_status";
    /** 追加型通道：各节点可独立追加一条审计/排障字符串 */
    public static final String DIAGNOSTICS = "diagnostics";
    /** 终态给人读的摘要（成功或降级文案都由 risky_call / stub 风格节点写入） */
    public static final String RESULT_SUMMARY = "result_summary";

    /**
     * LangGraph4j Channel 定义：标量用 base，列表合并用 appender（与 Python Annotated+add 同目的）。
     */
    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            REQUEST_ID, Channels.base(() -> ""),
            INPUT_TEXT, Channels.base(() -> ""),
            ATTEMPT, Channels.base(() -> 0),
            RISK_STATUS, Channels.base(() -> ""),
            DIAGNOSTICS, Channels.appender(ArrayList::new),
            RESULT_SUMMARY, Channels.base(() -> "")
    );

    public L14State(Map<String, Object> init) {
        super(init);
    }

    public String requestId() {
        return value(REQUEST_ID).map(Object::toString).orElse("");
    }

    public String inputText() {
        return value(INPUT_TEXT).map(Object::toString).orElse("");
    }

    public int attempt() {
        return value(ATTEMPT)
                .map(v -> v instanceof Number ? ((Number) v).intValue() : Integer.parseInt(v.toString()))
                .orElse(0);
    }

    public String riskStatus() {
        return value(RISK_STATUS).map(Object::toString).orElse("");
    }

    @SuppressWarnings("unchecked")
    public List<String> diagnostics() {
        return value(DIAGNOSTICS).map(v -> (List<String>) v).orElseGet(List::of);
    }

    public String resultSummary() {
        return value(RESULT_SUMMARY).map(Object::toString).orElse("");
    }
}
