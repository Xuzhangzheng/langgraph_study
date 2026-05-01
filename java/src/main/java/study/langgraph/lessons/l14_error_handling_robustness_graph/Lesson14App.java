package study.langgraph.lessons.l14_error_handling_robustness_graph;

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

// END / START：LangGraph4j 约定入口与出口锚点
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第十四课：错误处理与鲁棒性（对照 {@code 14_error_handling_robustness_graph.py}）。
 * <p>
 * <b>主线程路：</b>{@code risky_call} 根据输入子串写入 {@link L14State#RISK_STATUS}，
 * 再由条件边分发到成功收口、退避环或降级收口。
 * <p>
 * Python 若以 {@code stream_mode} 观察每一步，本类仍建议以 Python 脚本为准；Java 侧聚焦
 * 「同拓扑 + 同状态键」的对照运行。
 */
public final class Lesson14App {

    private Lesson14App() {
    }

    private static final Logger LOG = Logger.getLogger(Lesson14App.class.getName());

    /** 与 Python {@code MAX_TRANSIENT_ATTEMPT} 一致：attempt 0,1 仍触发 retry */
    private static final int MAX_TRANSIENT_ATTEMPT = 2;
    /** 与 Python 退避 cap / 基座一致，避免演示 sleep 过长 */
    private static final double BACKOFF_CAP_S = 0.35;
    private static final double BACKOFF_BASE_S = 0.04;

    /**
     * 条件边函数：返回值必须是 {@code routes} Map 中的键，否则运行期路由失败。
     * 未知状态统一降级，防御脏数据。
     */
    static String routeAfterRisky(L14State state) {
        String status = state.riskStatus();
        if ("ok".equals(status)) {
            return "finalize_success";
        }
        if ("retry".equals(status)) {
            return "backoff_then_retry";
        }
        if ("degraded".equals(status)) {
            return "degraded_finish";
        }
        LOG.severe(() -> "[route_after_risky] unexpected risk_status=" + status + " → degraded_finish");
        return "degraded_finish";
    }

    /**
     * 构建与 Python 完全同构的无 checkpoint 编译前图（compile() 时再封装运行器）。
     */
    static StateGraph<L14State> buildGraph() throws GraphStateException {
        Map<String, String> routes = Map.of(
                "finalize_success", "finalize_success",
                "backoff_then_retry", "backoff_then_retry",
                "degraded_finish", "degraded_finish"
        );

        return new StateGraph<>(L14State.SCHEMA, L14State::new)
                // risky_call：模拟外部调用分类，全程 Map 返回，不向图引擎抛异常
                .addNode("risky_call", node_async((NodeAction<L14State>) state -> {
                    String rid = state.requestId();
                    String text = state.inputText().trim();
                    int attempt = state.attempt();
                    LOG.info(() -> "[risky_call] request_id=" + rid + " attempt=" + attempt + " length=" + text.length());

                    if (text.isEmpty()) {
                        LOG.warning(() -> "[risky_call] empty input");
                        return Map.of(
                                L14State.RISK_STATUS, "degraded",
                                L14State.RESULT_SUMMARY, "【降级】空输入，拒绝执行",
                                L14State.DIAGNOSTICS, List.of("risky:validation_empty"));
                    }

                    String lowered = text.toLowerCase();
                    if (lowered.contains("fatal") || lowered.contains("boom")) {
                        LOG.warning(() -> "[risky_call] unrecoverable keyword");
                        return Map.of(
                                L14State.RISK_STATUS, "degraded",
                                L14State.RESULT_SUMMARY, "【降级】不可恢复错误（fatal/boom）",
                                L14State.DIAGNOSTICS, List.of("risky:unrecoverable"));
                    }

                    if (lowered.contains("flaky")) {
                        if (attempt < MAX_TRANSIENT_ATTEMPT) {
                            LOG.info(() -> "[risky_call] transient flaky attempt=" + attempt + " → retry");
                            return Map.of(
                                    L14State.RISK_STATUS, "retry",
                                    L14State.DIAGNOSTICS, List.of("risky:transient_flaky attempt=" + attempt));
                        }
                        String head = text.length() > 48 ? text.substring(0, 48) + "…" : text;
                        String summary = "已恢复：在 attempt=" + attempt + " 后完成（输入前 48 字：" + head + "）";
                        LOG.info(() -> "[risky_call] flaky recovered");
                        return Map.of(
                                L14State.RISK_STATUS, "ok",
                                L14State.RESULT_SUMMARY, summary,
                                L14State.DIAGNOSTICS, List.of("risky:recovered_after_backoff"));
                    }

                    String shortText = text.length() > 48 ? text.substring(0, 48) + "…" : text;
                    return Map.of(
                            L14State.RISK_STATUS, "ok",
                            L14State.RESULT_SUMMARY, "主路径成功：" + shortText,
                            L14State.DIAGNOSTICS, List.of("risky:ok_direct"));
                }))
                // backoff_then_retry：指数退避 + 中断时仍递增 attempt，避免死循环
                .addNode("backoff_then_retry", node_async((NodeAction<L14State>) state -> {
                    String rid = state.requestId();
                    int attempt = state.attempt();
                    double delay = Math.min(BACKOFF_CAP_S, BACKOFF_BASE_S * Math.pow(2, attempt));
                    LOG.info(() -> String.format(
                            "[backoff_then_retry] request_id=%s sleep=%.3fs next_attempt=%s",
                            rid, delay, attempt + 1));
                    try {
                        Thread.sleep(Math.max(1, Math.round(delay * 1000)));
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return Map.of(
                                L14State.ATTEMPT, attempt + 1,
                                L14State.DIAGNOSTICS, List.of("backoff:interrupted next_attempt=" + (attempt + 1)));
                    }
                    return Map.of(
                            L14State.ATTEMPT, attempt + 1,
                            L14State.DIAGNOSTICS, List.of(
                                    String.format("backoff:slept=%.3fs next_attempt=%s", delay, attempt + 1)));
                }))
                .addNode("finalize_success", node_async((NodeAction<L14State>) state -> {
                    LOG.info(() -> "[finalize_success] request_id=" + state.requestId());
                    return Map.of(L14State.DIAGNOSTICS, List.of("finalize_success:done"));
                }))
                .addNode("degraded_finish", node_async((NodeAction<L14State>) state -> {
                    LOG.warning(() -> "[degraded_finish] request_id=" + state.requestId());
                    return Map.of(L14State.DIAGNOSTICS, List.of("degraded_finish:sealed"));
                }))
                .addEdge(START, "risky_call")
                .addConditionalEdges("risky_call", edge_async(Lesson14App::routeAfterRisky), routes)
                .addEdge("backoff_then_retry", "risky_call")
                .addEdge("finalize_success", END)
                .addEdge("degraded_finish", END);
    }

    /** 演示用：打印终态，字段顺序与 Python demo 接近，便于肉眼 diff */
    static void invokeCase(org.bsc.langgraph4j.CompiledGraph<L14State> g, String label, String requestId, String input)
            throws GraphStateException {
        Map<String, Object> init = new HashMap<>();
        init.put(L14State.REQUEST_ID, requestId);
        init.put(L14State.INPUT_TEXT, input);
        init.put(L14State.ATTEMPT, 0);
        init.put(L14State.RISK_STATUS, "");
        init.put(L14State.DIAGNOSTICS, new ArrayList<String>());
        init.put(L14State.RESULT_SUMMARY, "");

        System.out.println("\n" + "=".repeat(72));
        System.out.println(label);
        System.out.println("request_id=" + requestId + " input=" + (input.contains("\n") ? "..." : input));
        System.out.println("=".repeat(72));

        Object raw = g.invoke(init).orElseThrow();
        if (raw instanceof L14State) {
            L14State end = (L14State) raw;
            System.out.println("attempt: " + end.attempt());
            System.out.println("result_summary: " + end.resultSummary());
            System.out.println("diagnostics: " + end.diagnostics());
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
        System.out.println("第十四课：错误处理与鲁棒性（LangGraph4j）");
        System.out.println("=".repeat(72));
        System.out.println("对照 Python：`risk_status` 路由、退避重试与降级支路。");
        System.out.println("进阶业务叙事见：`l14b_payment_capture_resilience.Lesson14bApp`。");

        var compiled = buildGraph().compile();

        invokeCase(compiled, "Happy Path：普通输入", "req-java-ok", "正常下单请求");
        invokeCase(compiled, "Failure Path：flaky → 退避重试 → 恢复", "req-java-flaky", "这是 flaky 下游，请多试几次");
        invokeCase(compiled, "Failure Path：fatal（无重试）", "req-java-fatal", "fatal error in payload");
        invokeCase(compiled, "Failure Path：空输入", "req-java-empty", "   ");
    }
}
