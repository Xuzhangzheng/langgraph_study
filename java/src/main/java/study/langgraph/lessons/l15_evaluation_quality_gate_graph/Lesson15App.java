package study.langgraph.lessons.l15_evaluation_quality_gate_graph;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第十五课：评测体系与质量门禁（对照 {@code 15_evaluation_quality_gate_graph.py}）。
 * <p>
 * <b>本课学习目标（与 Python 文件头一致，便于双端对照）：</b>
 * <ul>
 *   <li><b>黄金用例</b>：对 {@code invoke} 终态做 intent / reply 断言，扩展路线可加 LLM-as-judge。</li>
 *   <li><b>黑盒评测</b>：不依赖节点实现细节，只依赖状态契约（字段名与语义）。</li>
 *   <li><b>质量门禁</b>：通过率低于 {@code MIN_PASS_RATIO} 时 {@code main} 以非零退出码结束，模拟 CI。</li>
 *   <li><b>薄编排图</b>：{@code bootstrap_run → regression_worker → gate_finalize}，worker 内循环调用 SUT，
 *       生产中可替换为队列 worker（注释与 Python 同源思想）。</li>
 * </ul>
 * <p>
 * <b>说明：</b>Python 侧 {@code RunnableConfig.configurable.thread_id} 的完整能力以 Python 脚本为准；
 * 本类 {@code invoke} 仅传入初始 Map，与仓库现有 LangGraph4j 示例风格一致。
 */
public final class Lesson15App {

    private Lesson15App() {
    }

    private static final Logger LOG = Logger.getLogger(Lesson15App.class.getName());

    /** 与 Python {@code MIN_PASS_RATIO} 一致：1.0 表示套件必须全绿 */
    private static final double MIN_PASS_RATIO = 1.0;

    /** 与 Python {@code EVIL_CASE} 一致：改为 {@code true} 可演示门禁失败 */
    private static final boolean EVIL_CASE = false;

    /**
     * 单条黄金用例：字段语义与 Python {@code GoldenCase} 一致。
     *
     * @param caseId       稳定 ID
     * @param userMessage  用户输入
     * @param expectIntent 对 {@link L15SutState#INTENT} 的精确期望
     * @param replyNeedles {@code reply} 须全部包含的子串；可为空数组表示不检查子串
     * @param label        人类可读标签（日志用）
     */
    record GoldenCase(
            String caseId,
            String userMessage,
            String expectIntent,
            String[] replyNeedles,
            String label
    ) {
    }

    record CaseResult(String caseId, boolean passed, String detail, Map<String, Object> actual) {
        Map<String, Object> toReportRow() {
            return Map.of(
                    "case_id", caseId,
                    "passed", passed,
                    "detail", detail,
                    "actual", actual
            );
        }
    }

    static List<GoldenCase> defaultGoldenSuite() {
        return List.of(
                new GoldenCase("gc-001", "我要申请退款，订单 123", "refund", new String[]{"退款"}, "退款意图"),
                new GoldenCase("gc-002", "帮查一下快递物流到哪里了", "shipping", new String[]{"物流"}, "物流意图"),
                new GoldenCase("gc-003", "你好，随便问问", "general", new String[]{"咨询"}, "闲聊/泛化"),
                new GoldenCase("gc-004", "   ", "invalid", new String[]{"请先"}, "空输入"),
                new GoldenCase(
                        "gc-005",
                        "force_evaluator_crash",
                        "invalid",
                        new String[]{},
                        "强制失败桩：仅校验 intent"
                )
        );
    }

    static List<GoldenCase> maybeEvilSuite(List<GoldenCase> suite) {
        if (!EVIL_CASE || suite.isEmpty()) {
            return suite;
        }
        ArrayList<GoldenCase> copy = new ArrayList<>(suite);
        GoldenCase last = copy.get(copy.size() - 1);
        copy.set(
                copy.size() - 1,
                new GoldenCase(
                        last.caseId() + "-evil",
                        last.userMessage(),
                        "refund",
                        last.replyNeedles(),
                        last.label() + "（evil）"));
        return copy;
    }

    static Map<String, Object> configPlaceholder(String caseId) {
        /* Python：RunnableConfig + thread_id；Java 侧仅占位说明，避免虚构 API */
        return Map.of(
                "note", "lesson-15-eval-" + caseId,
                "python_parity", "configurable.thread_id=lesson-15-eval-" + caseId
        );
    }

    static Map<String, Object> initialSut(GoldenCase c) {
        Map<String, Object> m = new HashMap<>();
        m.put(L15SutState.REQUEST_ID, c.caseId());
        m.put(L15SutState.USER_MESSAGE, c.userMessage());
        m.put(L15SutState.INTENT, "");
        m.put(L15SutState.REPLY, "");
        m.put(L15SutState.DIAGNOSTICS, new ArrayList<String>());
        return m;
    }

    /** 条件边：返回值必须是 {@code routes} 的键 */
    static String routeAfterClassify(L15SutState state) {
        String intent = state.intent();
        if ("refund".equals(intent)) {
            return "draft_refund";
        }
        if ("shipping".equals(intent)) {
            return "draft_shipping";
        }
        if ("general".equals(intent)) {
            return "draft_general";
        }
        if ("invalid".equals(intent)) {
            return "draft_invalid";
        }
        LOG.severe(() -> "[route_after_classify] unknown intent=" + intent + " → draft_invalid");
        return "draft_invalid";
    }

    static StateGraph<L15SutState> buildSutGraph() throws GraphStateException {
        Map<String, String> routes = Map.of(
                "draft_refund", "draft_refund",
                "draft_shipping", "draft_shipping",
                "draft_general", "draft_general",
                "draft_invalid", "draft_invalid"
        );

        return new StateGraph<>(L15SutState.SCHEMA, L15SutState::new)
                .addNode("normalize_message", node_async((NodeAction<L15SutState>) state -> {
                    String raw = state.userMessage();
                    String cleaned = raw.strip();
                    LOG.info(() -> String.format(
                            "[normalize_message] request_id=%s len_in=%s len_out=%s",
                            state.requestId(), raw.length(), cleaned.length()));
                    return Map.of(
                            L15SutState.USER_MESSAGE, cleaned,
                            L15SutState.DIAGNOSTICS, List.of("normalize:stripped"));
                }))
                .addNode("classify_intent", node_async((NodeAction<L15SutState>) state -> {
                    String msg = state.userMessage().strip();
                    String rid = state.requestId();
                    if (msg.isEmpty()) {
                        LOG.warning(() -> "[classify_intent] empty after normalize request_id=" + rid);
                        return Map.of(
                                L15SutState.INTENT, "invalid",
                                L15SutState.DIAGNOSTICS, List.of("classify:empty"));
                    }
                    if (msg.contains("force_evaluator_crash")) {
                        LOG.warning(() -> "[classify_intent] force token request_id=" + rid);
                        return Map.of(
                                L15SutState.INTENT, "invalid",
                                L15SutState.REPLY, "【测试桩】检测到强制失败标记。",
                                L15SutState.DIAGNOSTICS, List.of("classify:force_evaluator_crash"));
                    }
                    String lowered = msg.toLowerCase();
                    if (msg.contains("退款") || msg.contains("退货") || lowered.contains("refund")) {
                        return Map.of(
                                L15SutState.INTENT, "refund",
                                L15SutState.DIAGNOSTICS, List.of("classify:refund"));
                    }
                    if (msg.contains("物流") || msg.contains("快递") || lowered.contains("shipping")
                            || msg.contains("查单") || lowered.contains("track")) {
                        return Map.of(
                                L15SutState.INTENT, "shipping",
                                L15SutState.DIAGNOSTICS, List.of("classify:shipping"));
                    }
                    return Map.of(
                            L15SutState.INTENT, "general",
                            L15SutState.DIAGNOSTICS, List.of("classify:general"));
                }))
                .addNode("draft_refund", node_async((NodeAction<L15SutState>) state -> Map.of(
                        L15SutState.REPLY, "已记录您的退款诉求，将在 1 个工作日内处理。",
                        L15SutState.DIAGNOSTICS, List.of("draft:refund"))))
                .addNode("draft_shipping", node_async((NodeAction<L15SutState>) state -> Map.of(
                        L15SutState.REPLY, "正在为您查询物流状态，请稍候刷新订单详情页。",
                        L15SutState.DIAGNOSTICS, List.of("draft:shipping"))))
                .addNode("draft_general", node_async((NodeAction<L15SutState>) state -> Map.of(
                        L15SutState.REPLY, "感谢您的咨询，我们已收到，将由人工坐席跟进。",
                        L15SutState.DIAGNOSTICS, List.of("draft:general"))))
                .addNode("draft_invalid", node_async((NodeAction<L15SutState>) state -> {
                    String existing = state.reply();
                    if (!existing.isEmpty()) {
                        return Map.of(L15SutState.DIAGNOSTICS, List.of("draft:invalid_passthrough"));
                    }
                    return Map.of(
                            L15SutState.REPLY, "请先描述您的问题，以便为您分流到对应坐席。",
                            L15SutState.DIAGNOSTICS, List.of("draft:invalid_default"));
                }))
                .addNode("seal_response", node_async((NodeAction<L15SutState>) state -> {
                    LOG.info(() -> "[seal_response] request_id=" + state.requestId() + " intent=" + state.intent());
                    return Map.of(L15SutState.DIAGNOSTICS, List.of("seal:ok"));
                }))
                .addEdge(START, "normalize_message")
                .addEdge("normalize_message", "classify_intent")
                .addConditionalEdges("classify_intent", org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async(Lesson15App::routeAfterClassify), routes)
                .addEdge("draft_refund", "seal_response")
                .addEdge("draft_shipping", "seal_response")
                .addEdge("draft_general", "seal_response")
                .addEdge("draft_invalid", "seal_response")
                .addEdge("seal_response", END);
    }

    static CaseResult runSingleCase(CompiledGraph<L15SutState> sut, GoldenCase c) throws GraphStateException {
        /* configPlaceholder：与 Python RunnableConfig 说明对齐，运行时不传入图 API */
        LOG.fine(() -> "eval config parity: " + configPlaceholder(c.caseId()));
        L15SutState fin = sut.invoke(initialSut(c)).orElseThrow();
        String intent = fin.intent();
        String reply = fin.reply();

        if (!c.expectIntent().equals(intent)) {
            return new CaseResult(
                    c.caseId(),
                    false,
                    "intent 期望 " + c.expectIntent() + " 实际 " + intent,
                    Map.of("intent", intent, "reply", reply));
        }
        for (String needle : c.replyNeedles()) {
            if (!reply.contains(needle)) {
                return new CaseResult(
                        c.caseId(),
                        false,
                        "reply 缺少子串 " + needle + ": " + reply,
                        Map.of("intent", intent, "reply", reply));
            }
        }
        return new CaseResult(c.caseId(), true, "ok", Map.of("intent", intent, "reply", reply));
    }

    record SuiteSummary(List<CaseResult> results, double passRatio) {
    }

    static SuiteSummary runGoldenSuite(CompiledGraph<L15SutState> sut, List<GoldenCase> cases)
            throws GraphStateException {
        List<CaseResult> results = new ArrayList<>();
        for (GoldenCase c : cases) {
            results.add(runSingleCase(sut, c));
        }
        int n = results.size();
        long passed = results.stream().filter(CaseResult::passed).count();
        double ratio = n == 0 ? 1.0 : (double) passed / (double) n;
        return new SuiteSummary(results, ratio);
    }

    static String evaluateGate(double passRatio) {
        boolean ok = passRatio + 1e-9 >= MIN_PASS_RATIO;
        return String.format("pass_ratio=%.3f min_required=%.3f → %s", passRatio, MIN_PASS_RATIO, ok ? "PASS" : "FAIL");
    }

    static StateGraph<L15OrchestrationState> buildOrchestrationGraph(
            CompiledGraph<L15SutState> sut,
            List<GoldenCase> cases) throws GraphStateException {

        return new StateGraph<>(L15OrchestrationState.SCHEMA, L15OrchestrationState::new)
                .addNode("bootstrap_run", node_async((NodeAction<L15OrchestrationState>) state -> {
                    LOG.info(() -> "[bootstrap_run] run_id=" + state.runId());
                    return Map.of(
                            L15OrchestrationState.EVAL_REPORTS, new ArrayList<Map<String, Object>>(),
                            L15OrchestrationState.PASS_COUNT, 0,
                            L15OrchestrationState.FAIL_COUNT, 0,
                            L15OrchestrationState.GATE_OK, false,
                            L15OrchestrationState.GATE_DETAIL, "");
                }))
                .addNode("regression_worker", node_async((NodeAction<L15OrchestrationState>) state -> {
                    SuiteSummary summary = runGoldenSuite(sut, cases);
                    List<Map<String, Object>> reports = new ArrayList<>();
                    for (CaseResult r : summary.results()) {
                        reports.add(r.toReportRow());
                    }
                    long pass = summary.results().stream().filter(CaseResult::passed).count();
                    int fail = summary.results().size() - (int) pass;
                    String gateDetail = evaluateGate(summary.passRatio());
                    boolean gateOk = summary.passRatio() + 1e-9 >= MIN_PASS_RATIO;
                    LOG.info(() -> String.format(
                            "[regression_worker] run_id=%s pass=%s fail=%s ratio=%.3f gate=%s",
                            state.runId(), pass, fail, summary.passRatio(), gateOk));
                    return Map.of(
                            L15OrchestrationState.EVAL_REPORTS, reports,
                            L15OrchestrationState.PASS_COUNT, (int) pass,
                            L15OrchestrationState.FAIL_COUNT, fail,
                            L15OrchestrationState.GATE_OK, gateOk,
                            L15OrchestrationState.GATE_DETAIL, gateDetail);
                }))
                .addNode("gate_finalize", node_async((NodeAction<L15OrchestrationState>) state -> Map.of()))
                .addEdge(START, "bootstrap_run")
                .addEdge("bootstrap_run", "regression_worker")
                .addEdge("regression_worker", "gate_finalize")
                .addEdge("gate_finalize", END);
    }

    public static void main(String[] args) throws GraphStateException {
        Logger root = Logger.getLogger("");
        root.setLevel(Level.INFO);
        for (var h : root.getHandlers()) {
            h.setLevel(Level.INFO);
        }
        LOG.setLevel(Level.INFO);

        CompiledGraph<L15SutState> sut = buildSutGraph().compile();
        List<GoldenCase> suite = maybeEvilSuite(new ArrayList<>(defaultGoldenSuite()));

        System.out.println("=".repeat(72));
        System.out.println("第十五课：SUT 单次 invoke（Happy Path）");
        System.out.println("=".repeat(72));
        Map<String, Object> demoInit = new HashMap<>();
        demoInit.put(L15SutState.REQUEST_ID, "demo-1");
        demoInit.put(L15SutState.USER_MESSAGE, "我要退款");
        demoInit.put(L15SutState.INTENT, "");
        demoInit.put(L15SutState.REPLY, "");
        demoInit.put(L15SutState.DIAGNOSTICS, new ArrayList<String>());
        L15SutState one = sut.invoke(demoInit).orElseThrow();
        System.out.println("  intent: " + one.intent());
        System.out.println("  reply: " + one.reply());
        System.out.println("  diagnostics: " + one.diagnostics());

        System.out.println("\n" + "=".repeat(72));
        System.out.println("第十五课：黄金套件 + 质量门禁");
        System.out.println("=".repeat(72));
        SuiteSummary summary = runGoldenSuite(sut, suite);
        for (CaseResult r : summary.results()) {
            System.out.println("  [" + (r.passed() ? "PASS" : "FAIL") + "] " + r.caseId() + ": " + r.detail());
        }
        String gateLine = evaluateGate(summary.passRatio());
        System.out.println("\n  " + gateLine);

        System.out.println("\n" + "=".repeat(72));
        System.out.println("第十五课：评测编排图 invoke");
        System.out.println("=".repeat(72));
        CompiledGraph<L15OrchestrationState> orch = buildOrchestrationGraph(sut, suite).compile();
        Map<String, Object> orchInit = new HashMap<>();
        orchInit.put(L15OrchestrationState.RUN_ID, "ci-lesson-15-java");
        orchInit.put(L15OrchestrationState.EVAL_REPORTS, new ArrayList<Map<String, Object>>());
        orchInit.put(L15OrchestrationState.PASS_COUNT, 0);
        orchInit.put(L15OrchestrationState.FAIL_COUNT, 0);
        orchInit.put(L15OrchestrationState.GATE_OK, false);
        orchInit.put(L15OrchestrationState.GATE_DETAIL, "");
        L15OrchestrationState out = orch.invoke(orchInit).orElseThrow();
        System.out.println("  pass_count: " + out.passCount());
        System.out.println("  fail_count: " + out.failCount());
        System.out.println("  gate_ok: " + out.gateOk());
        System.out.println("  gate_detail: " + out.gateDetail());

        System.out.println("\n" + "=".repeat(72));
        System.out.println("说明：将 EVIL_CASE=true 可演示门禁失败；GoldenCase 可外置为 JSON 由 CI 加载。");
        System.out.println("=".repeat(72));

        if (!out.gateOk()) {
            System.exit(1);
        }
    }
}
