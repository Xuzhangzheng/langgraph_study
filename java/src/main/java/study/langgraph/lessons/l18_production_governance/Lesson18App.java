package study.langgraph.lessons.l18_production_governance;

import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.output.Response;
import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;
import study.langgraph.support.CourseEnv;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.regex.Pattern;

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第十八课：生产化发布治理与版本契约（LangGraph4j）。
 * <p><b>本课学习目标（与 Python 文件头对齐）：</b></p>
 * <ul>
 *   <li><b>分环境 profile</b>：{@code app_env} 驱动 flags / log_level / 期望 pin。</li>
 *   <li><b>契约版本</b>：{@link #STATE_CONTRACT_VERSION} 与环境变量
 *   {@code EXPECTED_STATE_CONTRACT_VERSION} 比对；{@code FORCE_CONTRACT_FAIL} 模拟失败。</li>
 *   <li><b>依赖锁定</b>：{@code REPO_DEPS_PIN} 与 profile；{@code FORCE_LOCK_FAIL}。</li>
 *   <li><b>预检</b>：{@code prod} 要求 {@code REQUIRE_TRACING_IN_PROD}；{@code FORCE_PREFLIGHT_FAIL}。</li>
 *   <li><b>条件边</b>：{@link StateGraph#addConditionalEdges} 返回值与 {@code Map} 键严格一致。</li>
 *   <li><b>LLM</b>：{@code LLM_PROVIDER=openai} 走 LangChain4j；{@code ark} 为占位（完整 Ark 以 Python + volcenginesdkarkruntime 为准，同第 6 课）。</li>
 * </ul>
 */
@SuppressWarnings({"SameParameterValue", "java:S1192"})
public final class Lesson18App {

    private Lesson18App() {
    }

    /** 与 Python {@code STATE_CONTRACT_VERSION} 必须保持同值，保证双端契约对齐。 */
    public static final String STATE_CONTRACT_VERSION = "2026.05.course.state.v18.v1";

    private static final Logger LOG = Logger.getLogger(Lesson18App.class.getName());

    /** 与 Python {@code route_after_normalize}：invalid 走收口节点。 */
    static String routeAfterNormalize(L18State state) {
        return "invalid".equals(state.releaseGate()) ? "invalid" : "ok";
    }

    /** 与 Python {@code route_after_gates}：任一 fail → blocked。 */
    static String routeAfterGates(L18State state) {
        if ("fail".equals(state.contractCheck())) {
            return "blocked";
        }
        if ("fail".equals(state.dependencyLockCheck())) {
            return "blocked";
        }
        if ("fail".equals(state.preflightCheck())) {
            return "blocked";
        }
        return "continue";
    }

    /** OpenAI 兼容单次调用；空 Optional 表示回落模板（与 L17 同模式）。 */
    static Optional<String> tryOpenAiLlm(String system, String human) {
        String apiKey = CourseEnv.get("OPENAI_API_KEY", "");
        String baseUrl = CourseEnv.get("OPENAI_BASE_URL", "https://api.openai.com/v1");
        String model = CourseEnv.get("OPENAI_MODEL", "gpt-4o-mini");
        if (apiKey.isBlank() || baseUrl.isBlank() || model.isBlank()) {
            return Optional.empty();
        }
        try {
            ChatLanguageModel llm = OpenAiChatModel.builder()
                    .apiKey(apiKey)
                    .baseUrl(baseUrl)
                    .modelName(model)
                    .temperature(0.1)
                    .build();
            Response<AiMessage> resp = llm.generate(
                    SystemMessage.from(system),
                    UserMessage.from(human)
            );
            return Optional.of(resp.content().text().trim());
        } catch (Exception e) {
            LOG.log(Level.WARNING, "OpenAI risk assessment failed → stub", e);
            return Optional.empty();
        }
    }

    /**
     * Ark 路径占位：若 {@code ARK_API_KEY} 与 {@code ARK_MODEL} 非空则返回对齐第 6 课提示的占位块；
     * 真实 {@code responses.create(model, input)} 以 Python 为准。
     */
    static String arkRiskStub(String system, String human, String stubFallback) {
        String apiKey = CourseEnv.get("ARK_API_KEY", "");
        String model = CourseEnv.get("ARK_MODEL", "");
        if (!apiKey.isBlank() && !model.isBlank()) {
            String head = human.length() > 160 ? human.substring(0, 160) + "…" : human;
            return "【Java-Ark占位】Lesson18 risk；请以 Python18 + Ark SDK 调用 client.responses.create。\n"
                    + "model=" + model + "\n"
                    + "system_head=" + (system.length() > 80 ? system.substring(0, 80) + "…" : system) + "\n"
                    + "human_head=\n" + head;
        }
        return stubFallback;
    }

    /** Fallback 模板：与 Python {@code _invoke_llm_or_template} 中 mode!=llm 文案一致。 */
    static String fallbackRiskTemplate() {
        return "【Fallback-风险评估】\n"
                + "1) 监控：请求错误率、P95 延迟、LLM 调用失败率、checkout 转化。\n"
                + "2) 回滚：保留上一镜像 tag；一键切流或按比例灰度回退。\n"
                + "3) 契约：对照 STATE_CONTRACT_VERSION 与集成测试黄金用例。\n";
    }

    static StateGraph<L18State> buildGraph() throws GraphStateException {
        Map<String, String> routesNorm = Map.of(
                "ok", "load_env_profile",
                "invalid", "seal_invalid_release"
        );
        Map<String, String> routesGates = Map.of(
                "continue", "assess_release_risk",
                "blocked", "seal_blocked"
        );

        return new StateGraph<>(L18State.SCHEMA, L18State::new)
                .addNode("normalize_release", node_async((NodeAction<L18State>) state -> {
                    String rid = state.releaseId() == null ? "" : state.releaseId().trim();
                    String notes = state.releaseNotes() == null ? "" : state.releaseNotes().trim();
                    String gate = rid.isEmpty() ? "invalid" : "ok";
                    LOG.info(() -> "[" + state.traceId() + "] normalize gate=" + gate);
                    return Map.of(
                            L18State.RELEASE_ID, rid,
                            L18State.RELEASE_NOTES, notes,
                            L18State.RELEASE_GATE, gate,
                            L18State.DIAGNOSTICS, List.of("normalize:gate=" + gate)
                    );
                }))
                .addNode("load_env_profile", node_async((NodeAction<L18State>) state -> {
                    String env = state.appEnv().toLowerCase(Locale.ROOT);
                    if (!List.of("dev", "staging", "prod").contains(env)) {
                        env = "dev";
                    }
                    String expectedPin;
                    String flags;
                    String logLevel;
                    if ("prod".equals(env)) {
                        expectedPin = "sha256:course-prod-lock-001";
                        flags = "shadow_mode=off,canary=1%";
                        logLevel = "WARN";
                    } else if ("staging".equals(env)) {
                        expectedPin = "sha256:course-staging-lock-001";
                        flags = "shadow_mode=off,canary=10%";
                        logLevel = "INFO";
                    } else {
                        expectedPin = "";
                        flags = "shadow_mode=on,canary=0%";
                        logLevel = "DEBUG";
                    }
                    String observedPin = CourseEnv.get("REPO_DEPS_PIN", "");
                    String summary = "app_env=" + env + "\n"
                            + "feature_flags=" + flags + "\n"
                            + "log_level=" + logLevel + "\n"
                            + "expected_deps_pin=" + (expectedPin.isEmpty() ? "(dev_skip)" : expectedPin) + "\n"
                            + "REPO_DEPS_PIN_env=" + (observedPin.isEmpty() ? "(empty)" : observedPin);
                    LOG.info(() -> "[" + state.traceId() + "] load_env_profile");
                    return Map.of(
                            L18State.APP_ENV, env,
                            L18State.ENV_PROFILE_SUMMARY, summary,
                            L18State.EXPECTED_DEPS_PIN, expectedPin,
                            L18State.OBSERVED_DEPS_PIN, observedPin,
                            L18State.DIAGNOSTICS, List.of("profile:loaded")
                    );
                }))
                .addNode("verify_contract_and_pins", node_async((NodeAction<L18State>) state -> {
                    String notes = state.releaseNotes() == null ? "" : state.releaseNotes();
                    String observed = STATE_CONTRACT_VERSION;
                    String expected = CourseEnv.get("EXPECTED_STATE_CONTRACT_VERSION", observed).trim();
                    final String contract = notes.contains("FORCE_CONTRACT_FAIL") || !expected.equals(observed)
                            ? "fail"
                            : "pass";
                    String envKind = state.appEnv();
                    String expPin = state.expectedDepsPin() == null ? "" : state.expectedDepsPin().trim();
                    String obsPin = state.observedDepsPin() == null ? "" : state.observedDepsPin().trim();
                    final String lock;
                    if (notes.contains("FORCE_LOCK_FAIL")) {
                        lock = "fail";
                    } else if (("staging".equals(envKind) || "prod".equals(envKind))
                            && (expPin.isEmpty() || !obsPin.equals(expPin))) {
                        lock = "fail";
                    } else {
                        lock = "pass";
                    }
                    String ctr = contract;
                    String lck = lock;
                    LOG.info(() -> "[" + state.traceId() + "] verify contract=" + ctr + " lock=" + lck);
                    return Map.of(
                            L18State.EXPECTED_CONTRACT_VERSION, expected,
                            L18State.OBSERVED_CONTRACT_VERSION, observed,
                            L18State.CONTRACT_CHECK, contract,
                            L18State.DEPENDENCY_LOCK_CHECK, lock,
                            L18State.DIAGNOSTICS, List.of("verify:contract=" + contract + ",lock=" + lock)
                    );
                }))
                .addNode("preflight_health", node_async((NodeAction<L18State>) state -> {
                    String notes = state.releaseNotes() == null ? "" : state.releaseNotes();
                    List<String> lines = new ArrayList<>();
                    lines.add("check:artifact_present=pass");
                    lines.add("check:migration_dry_run=pass");
                    final String check;
                    if (notes.contains("FORCE_PREFLIGHT_FAIL")) {
                        check = "fail";
                        lines.add("check:forced_failure=fail");
                    } else if ("prod".equals(state.appEnv())) {
                        String tracing = CourseEnv.get("REQUIRE_TRACING_IN_PROD", "").trim().toLowerCase(Locale.ROOT);
                        boolean ok = tracing.equals("1") || tracing.equals("true") || tracing.equals("yes");
                        if (!ok) {
                            check = "fail";
                            lines.add("check:tracing_required_in_prod=fail");
                        } else {
                            check = "pass";
                            lines.add("check:tracing_required_in_prod=pass");
                        }
                    } else {
                        check = "pass";
                        lines.add("check:tracing_optional_non_prod=pass");
                    }
                    String log = String.join("\n", lines);
                    String chk = check;
                    LOG.info(() -> "[" + state.traceId() + "] preflight=" + chk);
                    return Map.of(
                            L18State.PREFLIGHT_CHECK, check,
                            L18State.PREFLIGHT_LOG, log,
                            L18State.DIAGNOSTICS, List.of("preflight:" + check)
                    );
                }))
                .addNode("assess_release_risk", node_async((NodeAction<L18State>) state -> {
                    String system = "你是发布评审助手。根据给定的发布说明与环境摘要，输出简洁中文："
                            + "① 主要风险 ② 建议监控指标 ③ 回滚触发条件（各不超过 3 条短句）。"
                            + "不要编造未提供的版本号。";
                    String human = "release_id=" + state.releaseId() + "\n"
                            + "release_notes:\n" + state.releaseNotes() + "\n\n"
                            + "env_profile_summary:\n" + state.envProfileSummary() + "\n\n"
                            + "preflight_log:\n" + state.preflightLog() + "\n";
                    String body;
                    String diag;
                    if (!"llm".equals(state.mode())) {
                        body = fallbackRiskTemplate();
                        diag = "risk:mode=fallback";
                    } else {
                        String provider = CourseEnv.get("LLM_PROVIDER", "openai").toLowerCase(Locale.ROOT);
                        if ("ark".equals(provider)) {
                            body = arkRiskStub(system, human, fallbackRiskTemplate());
                            diag = body.startsWith("【Java-Ark占位】") ? "risk:llm_ok_ark_stub" : "risk:ark_placeholder";
                        } else {
                            Optional<String> opt = tryOpenAiLlm(system, human);
                            if (opt.isPresent()) {
                                body = opt.get();
                                diag = "risk:llm_ok_openai";
                            } else {
                                body = "【Fallback-风险评估】缺少 LLM 密钥或模型配置；已跳过远端推理。";
                                diag = "risk:llm_config_incomplete";
                            }
                        }
                    }
                    return Map.of(
                            L18State.RISK_NARRATIVE, body,
                            L18State.DIAGNOSTICS, List.of(diag)
                    );
                }))
                .addNode("governance_finalize", node_async((NodeAction<L18State>) state -> {
                    String notes = state.releaseNotes() == null ? "" : state.releaseNotes();
                    String risk = state.riskNarrative() == null ? "" : state.riskNarrative().trim();
                    final String decision;
                    if (notes.contains("FORCE_ROLLBACK")) {
                        decision = "rollback_recommend";
                    } else if (notes.contains("FORCE_HOLD")) {
                        decision = "hold";
                    } else if (Pattern.compile("(致命|严重事故|P0)").matcher(risk).find()) {
                        decision = "hold";
                    } else {
                        decision = "promote";
                    }
                    String report = "[" + state.traceId() + "] 发布治理结论\n"
                            + "- app_env: " + state.appEnv() + "\n"
                            + "- release_id: " + state.releaseId() + "\n"
                            + "- contract: " + state.contractCheck()
                            + " (expected=" + state.expectedContractVersion()
                            + ", observed=" + state.observedContractVersion() + ")\n"
                            + "- dependency_lock: " + state.dependencyLockCheck() + "\n"
                            + "- preflight: " + state.preflightCheck() + "\n"
                            + "- decision: " + decision + "\n\n"
                            + "风险与操作提示：\n"
                            + risk;
                    String dec = decision;
                    LOG.info(() -> "[" + state.traceId() + "] finalize decision=" + dec);
                    return Map.of(
                            L18State.GOVERNANCE_DECISION, decision,
                            L18State.FINAL_REPORT, report,
                            L18State.DIAGNOSTICS, List.of("finalize:" + decision)
                    );
                }))
                .addNode("seal_blocked", node_async((NodeAction<L18State>) state -> {
                    List<String> reasons = new ArrayList<>();
                    String notes = state.releaseNotes() == null ? "" : state.releaseNotes();
                    if ("fail".equals(state.contractCheck())) {
                        if (notes.contains("FORCE_CONTRACT_FAIL")) {
                            reasons.add("契约校验失败：release_notes 含 FORCE_CONTRACT_FAIL（演练位），已阻断。");
                        } else {
                            reasons.add("契约校验失败：期望 " + state.expectedContractVersion()
                                    + " vs 代码 " + state.observedContractVersion());
                        }
                    }
                    if ("fail".equals(state.dependencyLockCheck())) {
                        if (notes.contains("FORCE_LOCK_FAIL")) {
                            reasons.add("依赖锁定失败：release_notes 含 FORCE_LOCK_FAIL（演练位），已阻断。");
                        } else {
                            reasons.add("依赖漂移：期望 pin=" + state.expectedDepsPin()
                                    + " 环境 REPO_DEPS_PIN=" + state.observedDepsPin());
                        }
                    }
                    if ("fail".equals(state.preflightCheck())) {
                        reasons.add("预检失败，详见 preflight_log");
                    }
                    String body = reasons.isEmpty() ? "未知阻塞原因" : String.join("\n", reasons);
                    String report = "[" + state.traceId() + "] 发布已阻塞\n"
                            + "app_env=" + state.appEnv() + " release_id=" + state.releaseId() + "\n\n"
                            + body + "\n\n"
                            + "preflight_log:\n" + state.preflightLog();
                    LOG.warning(() -> "[" + state.traceId() + "] seal_blocked");
                    return Map.of(
                            L18State.GOVERNANCE_DECISION, "hold",
                            L18State.RISK_NARRATIVE, "",
                            L18State.FINAL_REPORT, report,
                            L18State.DIAGNOSTICS, List.of("seal:blocked")
                    );
                }))
                .addNode("seal_invalid_release", node_async((NodeAction<L18State>) state -> {
                    String report = "[" + state.traceId() + "] release_id 为空或仅空白，已拒绝执行后续治理步骤。";
                    return Map.of(
                            L18State.GOVERNANCE_DECISION, "hold",
                            L18State.FINAL_REPORT, report,
                            L18State.DIAGNOSTICS, List.of("seal:invalid_release")
                    );
                }))
                .addEdge(START, "normalize_release")
                .addConditionalEdges("normalize_release", edge_async(Lesson18App::routeAfterNormalize), routesNorm)
                .addEdge("load_env_profile", "verify_contract_and_pins")
                .addEdge("verify_contract_and_pins", "preflight_health")
                .addConditionalEdges("preflight_health", edge_async(Lesson18App::routeAfterGates), routesGates)
                .addEdge("assess_release_risk", "governance_finalize")
                .addEdge("governance_finalize", END)
                .addEdge("seal_blocked", END)
                .addEdge("seal_invalid_release", END);
    }

    static HashMap<String, Object> seed(
            String traceId,
            String appEnv,
            String mode,
            String releaseId,
            String releaseNotes
    ) {
        HashMap<String, Object> m = new HashMap<>();
        m.put(L18State.TRACE_ID, traceId);
        m.put(L18State.APP_ENV, appEnv);
        m.put(L18State.MODE, mode);
        m.put(L18State.RELEASE_ID, releaseId);
        m.put(L18State.RELEASE_NOTES, releaseNotes);
        m.put(L18State.RELEASE_GATE, "pending");
        m.put(L18State.ENV_PROFILE_SUMMARY, "");
        m.put(L18State.EXPECTED_CONTRACT_VERSION, "");
        m.put(L18State.OBSERVED_CONTRACT_VERSION, STATE_CONTRACT_VERSION);
        m.put(L18State.CONTRACT_CHECK, "pending");
        m.put(L18State.EXPECTED_DEPS_PIN, "");
        m.put(L18State.OBSERVED_DEPS_PIN, "");
        m.put(L18State.DEPENDENCY_LOCK_CHECK, "pending");
        m.put(L18State.PREFLIGHT_CHECK, "pending");
        m.put(L18State.PREFLIGHT_LOG, "");
        m.put(L18State.RISK_NARRATIVE, "");
        m.put(L18State.GOVERNANCE_DECISION, "pending");
        m.put(L18State.FINAL_REPORT, "");
        m.put(L18State.DIAGNOSTICS, new ArrayList<String>());
        return m;
    }

    public static void main(String[] args) throws GraphStateException {
        Logger root = Logger.getLogger("");
        root.setLevel(Level.INFO);
        for (var h : root.getHandlers()) {
            h.setLevel(Level.INFO);
        }
        System.out.println("=".repeat(72));
        System.out.println("第十八课：生产化发布治理（LangGraph4j）");
        System.out.println("=".repeat(72));

        var g = buildGraph().compile();

        runCase(g, "主路径 dev fallback", seed("java-happy", "dev", "fallback", "rel-j1", "例行迭代"));
        runCase(g, "契约失败", seed("java-contract", "dev", "fallback", "rel-j2", "FORCE_CONTRACT_FAIL"));
        runCase(g, "锁定失败", seed("java-lock", "dev", "fallback", "rel-j3", "FORCE_LOCK_FAIL"));
        runCase(g, "空 release_id", seed("java-invalid", "dev", "fallback", "   ", "x"));

        System.out.println("\n对照 Python：`python 18_production_governance_graph.py`。");
    }

    static void runCase(org.bsc.langgraph4j.CompiledGraph<L18State> g, String label, HashMap<String, Object> init)
            throws GraphStateException {
        System.out.println("\n" + "-".repeat(72));
        System.out.println(label);
        System.out.println("-".repeat(72));
        L18State end = g.invoke(init).orElseThrow();
        System.out.println(end.finalReport());
        System.out.println("[decision] " + end.governanceDecision());
        System.out.println("[diagnostics] " + end.diagnostics());
    }
}
