package study.langgraph.lessons.l14b_payment_capture_resilience;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 14b 支付请款编排状态（对照 {@code 14b_payment_capture_resilience_graph.py} 的 {@code PaymentCaptureState}）。
 * <p>
 * 字段命名贴近业务，便于与第 14 课抽象版 {@link study.langgraph.lessons.l14_error_handling_robustness_graph.L14State}
 * 对照：correlation_id / capture_payload / psp_attempt / operations_log / settlement_summary。
 */
public final class L14bState extends AgentState {

    /** 全链路追踪号（可对齐日志/审计） */
    public static final String CORRELATION_ID = "correlation_id";
    /** 教学用请款报文摘要一行；生产为结构化报文 + 签名 */
    public static final String CAPTURE_PAYLOAD = "capture_payload";
    /** 已对 PSP 发起次数；仅退避节点递增 */
    public static final String PSP_ATTEMPT = "psp_attempt";
    /** 与第 14 课相同：条件边路由键 ok | retry | degraded */
    public static final String RISK_STATUS = "risk_status";
    /** 各节点追加的运营/账务排障痕迹（appender） */
    public static final String OPERATIONS_LOG = "operations_log";
    /** 给订单/财务读的终态摘要 */
    public static final String SETTLEMENT_SUMMARY = "settlement_summary";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            CORRELATION_ID, Channels.base(() -> ""),
            CAPTURE_PAYLOAD, Channels.base(() -> ""),
            PSP_ATTEMPT, Channels.base(() -> 0),
            RISK_STATUS, Channels.base(() -> ""),
            OPERATIONS_LOG, Channels.appender(ArrayList::new),
            SETTLEMENT_SUMMARY, Channels.base(() -> "")
    );

    public L14bState(Map<String, Object> init) {
        super(init);
    }

    public String correlationId() {
        return value(CORRELATION_ID).map(Object::toString).orElse("");
    }

    public String capturePayload() {
        return value(CAPTURE_PAYLOAD).map(Object::toString).orElse("");
    }

    public int pspAttempt() {
        return value(PSP_ATTEMPT)
                .map(v -> v instanceof Number ? ((Number) v).intValue() : Integer.parseInt(v.toString()))
                .orElse(0);
    }

    public String riskStatus() {
        return value(RISK_STATUS).map(Object::toString).orElse("");
    }

    @SuppressWarnings("unchecked")
    public List<String> operationsLog() {
        return value(OPERATIONS_LOG).map(v -> (List<String>) v).orElseGet(List::of);
    }

    public String settlementSummary() {
        return value(SETTLEMENT_SUMMARY).map(Object::toString).orElse("");
    }
}
