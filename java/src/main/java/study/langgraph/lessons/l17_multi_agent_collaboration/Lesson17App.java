package study.langgraph.lessons.l17_multi_agent_collaboration;

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

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第十七课：多 Agent 协作图（Planner / Executor / Critic）。
 * <p>
 * <b>本课学习目标（与 Python 文件头对齐）：</b>
 * <ul>
 *   <li><b>状态总线协议</b>：{@link L17State#PLAN_OUTLINE} / {@link L17State#DRAFT_ANSWER} /
 *   {@link L17State#CRITIC_VERDICT} / {@link L17State#CRITIC_FEEDBACK} 在四角色间的传递。</li>
 *   <li><b>回路收敛</b>：{@link L17State#ITERATION} &gt; {@link L17State#MAX_ITERATIONS} →
 *   {@code finalize_abort}。</li>
 *   <li><b>LangGraph4j API</b>：{@link StateGraph#addConditionalEdges} 的返回值必须映射到 routes。</li>
 *   <li><b>离线验收</b>：{@code FORCE_PASS} / {@code FORCE_REVISE_*_ONCE} / {@code FORCE_MAX_SPIN}，
 *   与 Python fallback 完全一致。</li>
 *   <li><b>LLM</b>：{@code LLM_PROVIDER=openai} 走 LangChain4j；{@code ark} 为占位（完整 Ark 以 Python + volcenginesdkarkruntime 为准）。</li>
 * </ul>
 */
@SuppressWarnings({"SameParameterValue", "java:S1192"})
public final class Lesson17App {

    private Lesson17App() {
    }

    private static final Logger LOG = Logger.getLogger(Lesson17App.class.getName());

    /**
     * 与 Python `_fallback_planner_text`：同步字符串，便于双端对齐回归。
     */
    static String fallbackPlannerText(String goal) {
        return "【Fallback-Planner】\n"
                + "针对目标：" + goal + "\n\n"
                + "步骤表：\n"
                + "1. 复述用户目标并用一句话划定范围。\n"
                + "2. 罗列 3 条以内可执行要点（不写空洞口号）。\n"
                + "3. 指明若信息不足应向用户索要的关键字段。\n";
    }

    /**
     * 与 Python `_fallback_executor_text`：把计划节选截断至 200 字，等价 Python 切片。
     */
    static String fallbackExecutorText(String goal, String plan, String feedbackTail) {
        String snippet = plan;
        if (snippet.length() > 200) {
            snippet = snippet.substring(0, 200) + "…";
        }
        String fb = "";
        if (feedbackTail != null && !feedbackTail.isBlank()) {
            fb = "\n上一轮 Critic：" + feedbackTail.trim();
        }
        return "【Fallback-Executor 草案】\n"
                + "围绕「" + goal + "」按步骤执行。\n\n"
                + "执行依据（计划节选）：" + snippet + "\n"
                + fb;
    }

    /** 二元组承载 Critic 输出，替代 Python tuple。 */
    static final class CritiqueResult {

        final String verdict;
        final String feedback;

        CritiqueResult(String verdict, String feedback) {
            this.verdict = verdict;
            this.feedback = feedback;
        }
    }

    /**
     * Python `_fallback_critic_routing` 的逐行镜像：FORCE_* 优先级完全一致。
     */
    static CritiqueResult fallbackCriticRouting(String goal, int itBefore) {
        String g = goal == null ? "" : goal;

        if (g.contains("FORCE_PASS")) {

            return new CritiqueResult("pass", "fallback:FORCE_PASS 触发直接通过。");
        }
        if (g.contains("FORCE_REVISE_PLAN_ONCE")) {

            if (itBefore == 0) {
                return new CritiqueResult("revise_planner", "fallback:请先收紧计划口径。");
            }
            return new CritiqueResult("pass", "fallback:计划已补足。");
        }
        if (g.contains("FORCE_REVISE_EXEC_ONCE")) {

            if (itBefore == 0) {
                return new CritiqueResult("revise_executor", "fallback:草稿缺具体动作。");
            }
            return new CritiqueResult("pass", "fallback:草稿已可读。");
        }
        if (g.contains("FORCE_MAX_SPIN")) {

            return new CritiqueResult("revise_executor", "fallback:刻意制造打转供验收 max_iterations。");
        }

        if (itBefore == 0) {

            return new CritiqueResult("revise_executor", "fallback:第一轮常规挑刺（离线规则）。");
        }
        return new CritiqueResult("pass", "fallback:第二轮视为满意。");
    }

    /** `normalize_goal` 条件边：`invalid`/`ok` → 相邻节点——键名必须与 Map 完全一致。 */
    static String routeAfterNormalize(L17State state) {

        return "invalid".equals(state.goalGate()) ? "invalid" : "ok";
    }

    /**
     * Critic 之后的路由：`iterate` &gt; `max` 时优先收口，阻止无限 loop。
     */
    static String routeAfterCritic(L17State state) {

        String verdict = state.criticVerdict();

        int iteration = state.iteration();
        int max = state.maxIterations();

        if ("pass".equals(verdict)) {

            return "finalize_pass";
        }

        if (iteration > max) {

            return "finalize_abort";
        }

        if ("revise_executor".equals(verdict)) {

            return "loop_executor";
        }

        return "loop_planner";
    }

    /** 尝试单次 OpenAI-compatible 调用：`empty` Optional 触发上层回落 stub。 */
    static Optional<String> tryOpenAiLlm(String system, String human, double temperature) {

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
                    .temperature(temperature)
                    .build();
            Response<AiMessage> resp = llm.generate(
                    SystemMessage.from(system),
                    UserMessage.from(human)
            );
            return Optional.of(resp.content().text().trim());

        } catch (Exception e) {

            LOG.log(Level.WARNING, "OpenAI invocation failed → stub", e);
            return Optional.empty();
        }
    }

    /**
     * 极简 JSON string literal 编码：<b>Critic human 打包</b> 与通用 stub 够用即可。

     */

    static String jsonString(String s) {

        if (s == null) {

            return "\"\"";
        }

        StringBuilder sb = new StringBuilder(s.length() + 8);

        sb.append('"');

        for (int i = 0; i < s.length(); i++) {

            char c = s.charAt(i);

            switch (c) {

                case '\\', '"' -> sb.append('\\').append(c);

                case '\n' -> sb.append("\\n");

                case '\r' -> sb.append("\\r");

                case '\t' -> sb.append("\\t");

                default -> {

                    if (c < 0x20) {

                        sb.append(String.format(Locale.ROOT, "\\u%04x", (int) c));

                    } else {

                        sb.append(c);

                    }

                }

            }

        }

        sb.append('"');

        return sb.toString();
    }

    /**
     * 仅解析单层 string 值的 JSON object —— 对应 Critic 输出 {@code {\"verdict\":...,\"feedback\":...}}。

     */

    static final class JsonLite {

        private final HashMap<String, String> kv = new HashMap<>();

        static JsonLite parseObject(String json) throws Exception {

            JsonLite lite = new JsonLite();

            String t = json.strip();

            if (!t.startsWith("{") || !t.endsWith("}")) {

                throw new IllegalArgumentException("not_object");

            }

            String inner = t.substring(1, t.length() - 1).strip();

            while (!inner.isEmpty()) {

                int keyStart = inner.indexOf('"');

                if (keyStart < 0) {

                    break;
                }

                int keyEnd = inner.indexOf('"', keyStart + 1);

                String key = inner.substring(keyStart + 1, keyEnd).strip();

                int colon = inner.indexOf(':', keyEnd + 1);

                int valQuote = inner.indexOf('"', colon + 1);

                int scan = valQuote + 1;

                StringBuilder val = new StringBuilder();

                boolean esc = false;

                while (scan < inner.length()) {

                    char c = inner.charAt(scan);

                    if (esc) {

                        switch (c) {

                            case 'n' -> val.append('\n');

                            case 'r' -> val.append('\r');

                            case 't' -> val.append('\t');

                            default -> val.append(c);

                        }

                        esc = false;

                    } else if (c == '\\') {

                        esc = true;

                    } else if (c == '"') {

                        break;

                    } else {

                        val.append(c);

                    }

                    scan++;

                }

                lite.kv.put(key, val.toString());

                int comma = inner.indexOf(',', scan);

                inner = comma < 0 ? "" : inner.substring(comma + 1).strip();

            }

            return lite;

        }

        String getString(String k, String def) {

            return kv.getOrDefault(k, def);

        }

    }

    /**
     * 解析 Critic JSON：与 Python `_parse_critic_payload` ——单行对象，失败退回 revise_executor。
     */
    static CritiqueResult parseCriticPayload(String raw) {

        try {
            String text = raw == null ? "" : raw.strip();
            int start = text.indexOf('{');

            int end = text.lastIndexOf('}');

            if (start >= 0 && end > start) {

                text = text.substring(start, end + 1);
            }

            JsonLite obj = JsonLite.parseObject(text);

            String v = obj.getString("verdict", "").toLowerCase(Locale.ROOT).strip();

            String verdict = ("pass".equals(v) || "revise_executor".equals(v) || "revise_planner".equals(v)) ? v : "revise_executor";
            String feedback = obj.getString("feedback", "JSON 字段 feedback 为空：请下一轮补充。").strip();

            return new CritiqueResult(verdict, feedback.isEmpty()

                    ? "JSON 字段 feedback 为空：请下一轮补充。"
                    : feedback);

        } catch (Exception e) {

            LOG.fine(() -> "critic JSON parse fail: " + e.getMessage());

            return new CritiqueResult("revise_executor", "JSON 解析失败：请下一轮压缩输出为单行合法 JSON。");
        }
    }

    /** 构造与 Python invoke 载荷对称的编译图——节点名完全一致供日志对照。 */
    static StateGraph<L17State> buildGraph() throws GraphStateException {

        Map<String, String> routesNorm = Map.of(
                "ok", "planner",
                "invalid", "seal_invalid_goal"
        );

        Map<String, String> routesCrit = Map.of(
                "finalize_pass", "finalize_pass",
                "finalize_abort", "finalize_abort",
                "loop_executor", "executor",
                "loop_planner", "planner"
        );

        return new StateGraph<>(L17State.SCHEMA, L17State::new)
                .addNode("normalize_goal", node_async((NodeAction<L17State>) state -> {

                    String raw = state.userGoal() == null ? "" : state.userGoal().trim();
                    String rid = state.requestId();

                    if (raw.isEmpty()) {

                        LOG.info(() -> "[" + rid + "] normalize_goal: invalid");
                        return Map.of(
                                L17State.USER_GOAL, "",
                                L17State.GOAL_GATE, "invalid",
                                L17State.DIAGNOSTICS, List.of("normalize:invalid_empty")
                        );
                    }

                    LOG.info(() -> "[" + rid + "] normalize_goal: ok");
                    return Map.of(
                            L17State.USER_GOAL, raw,
                            L17State.GOAL_GATE, "ok",
                            L17State.DIAGNOSTICS, List.of("normalize:ok")
                    );
                }))

                .addNode("planner", node_async((NodeAction<L17State>) state -> {

                    String rid = state.requestId();

                    String goal = state.userGoal();

                    String mode = state.mode();

                    String fb = state.criticFeedback();

                    if ("llm".equals(mode)) {

                        String system = "你是企业内部的多步骤任务规划器（Planner）。"
                                + "只输出「可执行 checklist」，使用编号列表；不写最终对用户的长回答。"
                                + "若上一轮 Critic 要求改计划，请吸收其 critique 重写计划。";

                        String human = "业务目标（原文）：" + goal + "\n\n上一轮反馈（可为空）：" + fb + "\n";

                        String stubText = fb.isBlank()

                                ? fallbackPlannerText(goal)

                                : fallbackPlannerText(goal)

                                + "\n（已并入 Critic 要求修订计划：" + fb.strip() + "）\n";

                        String outline;
                        String diag;

                        String provider = CourseEnv.get("LLM_PROVIDER", "openai").toLowerCase(Locale.ROOT);

                        if ("ark".equals(provider)) {

                            outline = arkPlannerStub(system, human, stubText);

                            diag = outline.startsWith("【Java-Ark占位】") ? "planner:llm_ok_ark_stub" : "planner:llm_ok_ark_placeholder";
                            LOG.info(() -> "[" + rid + "] planner: ark path → " + diag);

                        } else {

                            Optional<String> opt = tryOpenAiLlm(system, human, 0.2);
                            if (opt.isPresent()) {

                                outline = opt.get();
                                diag = "planner:llm_ok_openai";

                            } else {

                                outline = stubText;

                                diag = "planner:stub_env";
                            }

                        }

                        return Map.of(
                                L17State.PLAN_OUTLINE, outline,

                                L17State.DRAFT_ANSWER, "",

                                L17State.DIAGNOSTICS, List.of("planner:done diag=" + diag)
                        );

                    }

                    String outlineLocal = fb.isBlank()
                            ? fallbackPlannerText(goal)

                            : fallbackPlannerText(goal) + "\n（已并入 Critic 要求修订计划：" + fb.strip() + "）\n";

                    LOG.info(() -> "[" + rid + "] planner fallback outline len=" + outlineLocal.length());
                    return Map.of(
                            L17State.PLAN_OUTLINE, outlineLocal,
                            L17State.DRAFT_ANSWER, "",
                            L17State.DIAGNOSTICS, List.of("planner:done diag=planner:stub")
                    );
                }))
                .addNode("executor", node_async((NodeAction<L17State>) state -> {

                    String rid = state.requestId();

                    String goal = state.userGoal();

                    String plan = state.planOutline();

                    String mode = state.mode();

                    String verdict = state.criticVerdict();

                    String fb = state.criticFeedback();

                    String fbForExec = "";
                    // 等价 Python：Planner 回流后不强行把对上轮 plan 的评论塞给 Executor——仅执行器关切反馈

                    boolean takeFb = verdict == null || "revise_executor".equals(verdict) || "pending".equals(verdict) || "pass".equals(verdict);

                    if (takeFb && fb != null && !fb.isBlank()) {

                        fbForExec = fb.strip();

                    }

                    if ("llm".equals(mode)) {

                        String system = "你是企业内部执行写手（Executor）。"
                                + "根据 Planner 的步骤表，为用户提供「中文、可直接阅读的答复」。"
                                + "不得编造与用户目标无关的步骤；遵循计划先后顺序。"
                                + "若有 Critic 反馈且仍与当前草案有关，请务必逐条对齐修订。";

                        String human = "用户目标：" + goal + "\n\n计划：\n" + plan + "\n\n针对草稿的上一轮批评（可能没有）："

                                + fbForExec + "\n";

                        String stubDraft = fallbackExecutorText(goal, plan, fbForExec);

                        String diag;

                        String draft;

                        String provider = CourseEnv.get("LLM_PROVIDER", "openai").toLowerCase(Locale.ROOT);

                        if ("ark".equals(provider)) {

                            draft = arkExecutorStub(system, human, stubDraft);

                            diag = draft.startsWith("【Java-Ark占位】") ? "executor:llm_ok_ark_stub" : "executor:stub";

                            LOG.info(() -> "[" + rid + "] executor: ark stub");

                        } else {

                            Optional<String> opt = tryOpenAiLlm(system, human, 0.25);
                            if (opt.isPresent()) {

                                draft = opt.get();

                                diag = "executor:llm_ok_openai";

                            } else {

                                draft = stubDraft;

                                diag = "executor:stub_env";
                            }

                        }

                        return Map.of(L17State.DRAFT_ANSWER, draft,

                                L17State.DIAGNOSTICS, List.of("executor:done diag=" + diag));

                    }

                    String draftLocal = fallbackExecutorText(goal, plan, fbForExec);

                    LOG.info(() -> "[" + rid + "] executor fallback len=" + draftLocal.length());
                    return Map.of(
                            L17State.DRAFT_ANSWER, draftLocal,
                            L17State.DIAGNOSTICS, List.of("executor:done diag=executor:stub")

                    );

                }))
                .addNode("critic", node_async((NodeAction<L17State>) state -> {

                    String rid = state.requestId();

                    String mode = state.mode();

                    String goal = state.userGoal();

                    String plan = state.planOutline();

                    String draft = state.draftAnswer();

                    int itBefore = state.iteration();

                    int maxIt = state.maxIterations();

                    CritiqueResult cr;

                    String diagPiece;

                    if ("llm".equals(mode)) {

                        String system = "你是质量标准审核员（Critic）。只允许输出单行 JSON对象，不要有 markdown，不要注释。"
                                + "Schema: {\"verdict\":\"pass|revise_executor|revise_planner\",\"feedback\":\"中文短评\"}"
                                + "裁决准则：plan 是否缺失关键步骤、draft 是否答非所问、draft 是否违背 plan。"
                                + "若仅是措辞问题选 revise_executor；若结构性缺失选 revise_planner。";

                        String pTrim = plan.length() > 4000 ? plan.substring(0, 4000) : plan;

                        String dTrim = draft.length() > 6000 ? draft.substring(0, 6000) : draft;

                        String human = "{\"user_goal\":" + jsonString(goal)
                                + ",\"plan_outline\":" + jsonString(pTrim)
                                + ",\"draft_answer\":" + jsonString(dTrim) + "}";

                        CritiqueResult stubCr = fallbackCriticRouting(goal, itBefore);

                        String stubJson = "{\"verdict\":\"" + stubCr.verdict + "\",\"feedback\":\"" + escapeJson(stubCr.feedback) + "\"}";

                        String provider = CourseEnv.get("LLM_PROVIDER", "openai").toLowerCase(Locale.ROOT);

                        String rawOut;

                        if ("ark".equals(provider)) {

                            rawOut = arkCriticStub(system, human, stubJson);

                            diagPiece = "stub_json_via_ark_path";

                            LOG.info(() -> "[" + rid + "] critic: ark path → deterministic stub JSON");

                        } else {

                            Optional<String> opt = tryOpenAiLlm(system, human, 0.0);

                            rawOut = opt.orElse(stubJson);

                            diagPiece = opt.isPresent() ? "critic:llm_ok_openai_json" : "critic:fallback_stub_json_env";

                        }

                        cr = parseCriticPayload(rawOut);

                        diagPiece = "critic:" + diagPiece;

                    } else {

                        cr = fallbackCriticRouting(goal, itBefore);

                        diagPiece = "critic:fallback_rules";

                    }

                    int itAfter = "pass".equals(cr.verdict) ? itBefore : itBefore + 1;

                    LOG.info(() -> "[" + rid + "] critic verdict=" + cr.verdict + " iteration " + itBefore + "->" + itAfter + " max=" + maxIt);

                    return Map.of(
                            L17State.CRITIC_VERDICT, cr.verdict,
                            L17State.CRITIC_FEEDBACK, cr.feedback,
                            L17State.ITERATION, itAfter,
                            L17State.DIAGNOSTICS,

                            List.of("critic:verdict=" + cr.verdict + " " + diagPiece)
                    );
                }))
                .addNode("finalize_pass", node_async((NodeAction<L17State>) state -> {

                    String rid = state.requestId();

                    LOG.info(() -> "[" + rid + "] finalize_pass");
                    return Map.of(
                            L17State.FINAL_ANSWER, state.draftAnswer(),
                            L17State.DIAGNOSTICS, List.of("finalize:pass")

                    );

                }))
                .addNode("finalize_abort", node_async((NodeAction<L17State>) state -> {

                    LOG.warning(() -> "[" + state.requestId() + "] finalize_abort iteration=" + state.iteration());

                    String tail = "\n"

                            + "最后草案（仅供参考）：\n"

                            + state.draftAnswer();

                    String msg = "【未完成自动修订】达到最大回路次数或未能在自动审核中收敛。" + tail;
                    return Map.of(
                            L17State.FINAL_ANSWER, msg,
                            L17State.DIAGNOSTICS, List.of("finalize:abort_max_iterations")

                    );
                }))
                .addNode("seal_invalid_goal", node_async((NodeAction<L17State>) state -> Map.of(
                        L17State.FINAL_ANSWER,

                        "【输入无效】请先给出明确的业务目标或问题描述。",
                        L17State.DIAGNOSTICS,

                        List.of("seal:invalid_goal")
                )))
                .addEdge(START, "normalize_goal")
                .addConditionalEdges("normalize_goal", edge_async(Lesson17App::routeAfterNormalize), routesNorm)
                .addEdge("planner", "executor")
                .addEdge("executor", "critic")
                .addConditionalEdges("critic", edge_async(Lesson17App::routeAfterCritic), routesCrit)
                .addEdge("finalize_pass", END)

                .addEdge("finalize_abort", END)

                .addEdge("seal_invalid_goal", END);
    }

    /**
     * 方舟占位——与 Lesson16 Java 对齐：只有当 ARK_* 非空时才返回占位块，便于课堂对照 Python。
     */

    static String arkPlannerStub(String system, String human, String stubTextFallback) {

        String apiKey = CourseEnv.get("ARK_API_KEY", "");

        String model = CourseEnv.get("ARK_MODEL", "");

        if (!apiKey.isBlank() && !model.isBlank()) {

            String headHuman = human.length() > 120 ? human.substring(0, 120) + "…" : human;

            return "【Java-Ark占位】Lesson17 planner；请以 Python17 + Ark SDK 做实调用。\n"

                    + "model=" + model + "\nhuman_head=\n"

                    + headHuman;

        }
        return stubTextFallback;

    }

    /** Executor 侧的 Ark stub：结构与 planner 占位一致——避免凭空引入 Maven 方舟依赖 */

    static String arkExecutorStub(String system, String human, String stubTextFallback) {

        String apiKey = CourseEnv.get("ARK_API_KEY", "");

        String model = CourseEnv.get("ARK_MODEL", "");

        if (!apiKey.isBlank() && !model.isBlank()) {

            String headHuman = human.length() > 120 ? human.substring(0, 120) + "…" : human;

            return "【Java-Ark占位】Lesson17 executor；请以 Python17 为准。\n"

                    + "model=" + model + "\nhuman_head=\n"

                    + headHuman;

        }
        return stubTextFallback;

    }

    /** Critic 侧的 Ark stub：返回合法 JSON——直接走解析 */

    static String arkCriticStub(String system, String human, String stubJson) {

        String apiKey = CourseEnv.get("ARK_API_KEY", "");

        String model = CourseEnv.get("ARK_MODEL", "");

        if (!apiKey.isBlank() && !model.isBlank()) {

            return stubJson.replace("fallback:", "fallback:java_ark_placeholder:");

        }
        return stubJson;

    }

    /** Escape minimal JSON string for naive concat — avoids dependency on gson strict builder */
    static String escapeJson(String s) {

        if (s == null) {

            return "";
        }
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");

    }

    static void invokeCase(org.bsc.langgraph4j.CompiledGraph<L17State> g, String label, String sid, String goal, String mode, int mx) throws GraphStateException {

        HashMap<String, Object> init = new HashMap<>();

        init.put(L17State.REQUEST_ID, sid);

        init.put(L17State.USER_GOAL, goal);

        init.put(L17State.MODE, mode);

        init.put(L17State.GOAL_GATE, "pending");

        init.put(L17State.PLAN_OUTLINE, "");

        init.put(L17State.DRAFT_ANSWER, "");

        init.put(L17State.FINAL_ANSWER, "");

        init.put(L17State.CRITIC_VERDICT, "pending");

        init.put(L17State.CRITIC_FEEDBACK, "");

        init.put(L17State.ITERATION, 0);

        init.put(L17State.MAX_ITERATIONS, mx);

        init.put(L17State.DIAGNOSTICS, new ArrayList<String>());

        System.out.println("\n" + "=".repeat(72));

        System.out.println(label);

        System.out.println("=".repeat(72));

        L17State end = g.invoke(init).orElseThrow();

        System.out.println("final_answer:\n" + end.finalAnswer());

        System.out.println("critic_verdict=" + end.criticVerdict() + " iteration=" + end.iteration() + "/" + end.maxIterations());

        System.out.println("diagnostics=" + end.diagnostics());

    }

    /** 程序入口：复刻 Python demo 五条用例，`mode=fallback` 零密钥。 */
    public static void main(String[] args) throws GraphStateException {

        Logger root = Logger.getLogger("");
        root.setLevel(Level.INFO);
        for (var h : root.getHandlers()) {
            h.setLevel(Level.INFO);
        }

        System.out.println("=".repeat(72));

        System.out.println("第十七课：多 Agent 协作（LangGraph4j）");

        System.out.println("=".repeat(72));

        var compiled = buildGraph().compile();

        invokeCase(compiled,

                "最短路径：FORCE_PASS", "java-pass",

                "FORCE_PASS 写一个上线前检查单的骨架", "fallback", 3);

        invokeCase(compiled,

                "executor 回路一次", "java-exec-once",

                "FORCE_REVISE_EXEC_ONCE：说明灰度发布的三个检查点", "fallback", 3);

        invokeCase(compiled,

                "planner 回路一次", "java-plan-once",

                "FORCE_REVISE_PLAN_ONCE：如何把监控接入发布流水线", "fallback", 3);

        invokeCase(compiled,

                "打转 abort", "java-spin",

                "FORCE_MAX_SPIN 任意目标文本", "fallback", 2);

        invokeCase(compiled,

                "空目标", "java-invalid", "   ", "fallback", 3);

        System.out.println("\n对照 Python：`python 17_multi_agent_collaboration_graph.py`。");

        System.out.println();

    }
}
