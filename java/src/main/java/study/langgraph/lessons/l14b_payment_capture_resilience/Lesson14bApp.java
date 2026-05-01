package study.langgraph.lessons.l14b_payment_capture_resilience;

import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 14b：支付请款（Capture）韧性编排（对照 {@code 14b_payment_capture_resilience_graph.py}）。
 * <p>
 * 用 PSP 503/拒付等业务可读子串模拟分类；拓扑与第 14 课 {@code Lesson14App} 一致。
 */
public final class Lesson14bApp {

    private Lesson14bApp() {
    }

    private static final Logger LOG = Logger.getLogger(Lesson14bApp.class.getName());

    /** 与 Python：前两次见「瞬时症状」则重试 */
    private static final int MAX_TRANSIENT_ATTEMPT = 2;
    private static final double BACKOFF_CAP_S = 0.35;
    private static final double BACKOFF_BASE_S = 0.04;

    /** 与 Python `_is_transient_symptom` 同语义 */
    private static boolean isTransientSymptom(String lowered) {
        String[] markers = {"503", "502", "504", "rate_limit", "timeout", "transient", "gw_busy", "temporarily_unavailable"};
        for (String m : markers) {
            if (lowered.contains(m)) {
                return true;
            }
        }
        return false;
    }

    /** 与 Python `_is_hard_decline` 同语义 */
    private static boolean isHardDecline(String lowered) {
        String[] markers = {"declined", "fraud", "invalid_merchant", "hard_fail", "chargeback_hold", "do_not_retry"};
        for (String m : markers) {
            if (lowered.contains(m)) {
                return true;
            }
        }
        return false;
    }

    static String routeAfterPsp(L14bState state) {
        String status = state.riskStatus();
        if ("ok".equals(status)) {
            return "post_capture_audit_ok";
        }
        if ("retry".equals(status)) {
            return "backoff_before_redial";
        }
        if ("degraded".equals(status)) {
            return "degraded_finance_notice";
        }
        LOG.severe(() -> "[route_after_psp] unexpected risk_status=" + status);
        return "degraded_finance_notice";
    }

    static StateGraph<L14bState> buildGraph() throws GraphStateException {
        Map<String, String> routes = Map.of(
                "post_capture_audit_ok", "post_capture_audit_ok",
                "backoff_before_redial", "backoff_before_redial",
                "degraded_finance_notice", "degraded_finance_notice"
        );

        // 节点 invoke_psp_capture：模拟 RPC 分类，不向图外抛未捕获检查异常
        return new StateGraph<>(L14bState.SCHEMA, L14bState::new)
                .addNode("invoke_psp_capture", node_async((NodeAction<L14bState>) state -> {
                    String cid = state.correlationId();
                    String pl = state.capturePayload().trim();
                    int attempt = state.pspAttempt();
                    LOG.info(() -> "[invoke_psp_capture] correlation_id=" + cid + " psp_attempt=" + attempt + " len=" + pl.length());

                    if (pl.isEmpty()) {
                        LOG.warning(() -> "capture_payload empty");
                        return Map.of(
                                L14bState.RISK_STATUS, "degraded",
                                L14bState.SETTLEMENT_SUMMARY, "【结算降级】请款报文为空，未调用 PSP",
                                L14bState.OPERATIONS_LOG, List.of("psp:validation_empty_payload"));
                    }

                    String low = pl.toLowerCase();
                    if (isHardDecline(low)) {
                        LOG.warning(() -> "PSP hard decline");
                        return Map.of(
                                L14bState.RISK_STATUS, "degraded",
                                L14bState.SETTLEMENT_SUMMARY, "【结算降级】PSP 拒绝请款（风控/商户状态等，禁止自动重试）",
                                L14bState.OPERATIONS_LOG, List.of("psp:hard_decline"));
                    }

                    if (isTransientSymptom(low)) {
                        if (attempt < Lesson14bApp.MAX_TRANSIENT_ATTEMPT) {
                            LOG.info(() -> "PSP transient → retry psp_attempt=" + attempt);
                            return Map.of(
                                    L14bState.RISK_STATUS, "retry",
                                    L14bState.OPERATIONS_LOG, List.of("psp:transient_symptom psp_attempt=" + attempt));
                        }
                        String head = pl.length() > 48 ? pl.substring(0, 48) + "…" : pl;
                        LOG.info(() -> "PSP recovered (teaching)");
                        return Map.of(
                                L14bState.RISK_STATUS, "ok",
                                L14bState.SETTLEMENT_SUMMARY,
                                "请款成功：第 " + attempt + " 次重 dial 后确认；payload 摘要：" + head,
                                L14bState.OPERATIONS_LOG, List.of("psp:recovered_after_backoff"));
                    }

                    String head = pl.length() > 48 ? pl.substring(0, 48) + "…" : pl;
                    return Map.of(
                            L14bState.RISK_STATUS, "ok",
                            L14bState.SETTLEMENT_SUMMARY, "请款成功：一次到账；摘要：" + head,
                            L14bState.OPERATIONS_LOG, List.of("psp:ok_first_call"));
                }))
                // 退避：与 Python time.sleep 对齐的教学演示
                .addNode("backoff_before_redial", node_async((NodeAction<L14bState>) state -> {
                    String cid = state.correlationId();
                    int attempt = state.pspAttempt();
                    double delay = Math.min(BACKOFF_CAP_S, BACKOFF_BASE_S * Math.pow(2, attempt));
                    LOG.info(() -> String.format(
                            "[backoff_before_redial] correlation_id=%s sleep=%.3fs next=%s",
                            cid, delay, attempt + 1));
                    try {
                        Thread.sleep(Math.max(1, Math.round(delay * 1000)));
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return Map.of(
                                L14bState.PSP_ATTEMPT, attempt + 1,
                                L14bState.OPERATIONS_LOG, List.of("backoff:interrupted next_psp_attempt=" + (attempt + 1)));
                    }
                    return Map.of(
                            L14bState.PSP_ATTEMPT, attempt + 1,
                            L14bState.OPERATIONS_LOG, List.of(
                                    String.format("backoff:slept=%.3fs next_psp_attempt=%s", delay, attempt + 1)));
                }))
                .addNode("post_capture_audit_ok", node_async((NodeAction<L14bState>) state -> {
                    LOG.info(() -> "[post_capture_audit_ok] " + state.correlationId());
                    return Map.of(L14bState.OPERATIONS_LOG, List.of("audit:capture_posted_ok"));
                }))
                .addNode("degraded_finance_notice", node_async((NodeAction<L14bState>) state -> {
                    LOG.warning(() -> "[degraded_finance_notice] " + state.correlationId());
                    return Map.of(L14bState.OPERATIONS_LOG, List.of("finance:manual_followup_required"));
                }))
                .addEdge(START, "invoke_psp_capture")
                .addConditionalEdges("invoke_psp_capture", edge_async(Lesson14bApp::routeAfterPsp), routes)
                .addEdge("backoff_before_redial", "invoke_psp_capture")
                .addEdge("post_capture_audit_ok", END)
                .addEdge("degraded_finance_notice", END);
    }

    static void invokeCase(org.bsc.langgraph4j.CompiledGraph<L14bState> g, String label, String correlationId, String payload)
            throws GraphStateException {
        Map<String, Object> init = new HashMap<>();
        init.put(L14bState.CORRELATION_ID, correlationId);
        init.put(L14bState.CAPTURE_PAYLOAD, payload);
        init.put(L14bState.PSP_ATTEMPT, 0);
        init.put(L14bState.RISK_STATUS, "");
        init.put(L14bState.OPERATIONS_LOG, new ArrayList<String>());
        init.put(L14bState.SETTLEMENT_SUMMARY, "");

        System.out.println("\n" + "=".repeat(72));
        System.out.println(label);
        System.out.println("correlation_id=" + correlationId);
        System.out.println("=".repeat(72));

        Object raw = g.invoke(init).orElseThrow();
        if (raw instanceof L14bState) {
            L14bState end = (L14bState) raw;
            System.out.println("psp_attempt: " + end.pspAttempt());
            System.out.println("settlement_summary: " + end.settlementSummary());
            System.out.println("operations_log: " + end.operationsLog());
        } else {
            System.out.println("unexpected state type: " + raw.getClass());
        }
    }

    public static void main(String[] args) throws GraphStateException {
        Logger root = Logger.getLogger("");
        root.setLevel(Level.INFO);
        for (var h : root.getHandlers()) {
            h.setLevel(Level.INFO);
        }
        LOG.setLevel(Level.INFO);

        System.out.println("=".repeat(72));
        System.out.println("14b：支付请款韧性（LangGraph4j）");
        System.out.println("=".repeat(72));
        System.out.println("对照 Python：`14b_payment_capture_resilience_graph.py`。");

        var compiled = buildGraph().compile();

        invokeCase(compiled, "Happy Path", "java-cap-happy",
                "order_id=SO-9001 intent=pi_abc amount_cents=50000 merchant=MID-01");
        invokeCase(compiled, "503 瞬时故障 → 重试", "java-cap-503",
                "order_id=SO-9002 PSP_error=503 Service Unavailable (simulated)");
        invokeCase(compiled, "硬拒绝", "java-cap-decline",
                "order_id=SO-9003 PSP=fraud blocked transaction declined");
        invokeCase(compiled, "空报文", "java-cap-empty", "   ");
    }
}
