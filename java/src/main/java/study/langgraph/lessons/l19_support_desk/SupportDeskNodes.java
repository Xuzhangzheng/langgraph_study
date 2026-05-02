package study.langgraph.lessons.l19_support_desk;

import study.langgraph.support.CourseEnv;

import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;

import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.output.Response;

/**
 * 节点实现层：与 Python {@code lesson19_support_desk/node_*.py} 一一对应，便于 Code Review 时按文件 diff。
 */
public final class SupportDeskNodes {

    private static final Pattern SAFE_EXPR = Pattern.compile("^[0-9+\\-*/().\\s]+$");

    private SupportDeskNodes() {
    }

    public static Map<String, Object> ingest(L19State state) {
        String raw = state.userMessage() == null ? "" : state.userMessage().trim();
        String gate = raw.isEmpty() ? "invalid" : "ok";
        return Map.of(
                L19State.NORMALIZED_MESSAGE, raw,
                L19State.MESSAGE_GATE, gate,
                L19State.DIAGNOSTICS, List.of("ingest:gate=" + gate)
        );
    }

    public static Map<String, Object> classify(L19State state) {
        String text = state.normalizedMessage();
        String compact = text.replaceAll("\\s+", "");
        String intent = "general";
        String expr = "";
        if (text.contains("计算") || compact.chars().anyMatch(c -> "+-*/".indexOf(c) >= 0)) {
            intent = "math";
            if (text.contains("计算")) {
                int i = text.indexOf("计算");
                expr = text.substring(i + "计算".length()).trim();
            } else {
                expr = text;
            }
        } else if (text.contains("几点") || text.contains("时间") || text.contains("现在") || text.contains("日期")) {
            intent = "time";
        } else if (text.contains("退款") || text.contains("退钱")) {
            intent = "refund";
        } else if (text.contains("物流") || text.contains("快递") || text.contains("运单")) {
            intent = "shipping";
        }
        return Map.of(
                L19State.INTENT, intent,
                L19State.TOOL_EXPRESSION, expr,
                L19State.DIAGNOSTICS, List.of("classify:intent=" + intent)
        );
    }

    public static Map<String, Object> toolCalculator(L19State state) {
        String expr = state.toolExpression().isBlank() ? state.normalizedMessage() : state.toolExpression();
        try {
            if (!SAFE_EXPR.matcher(expr).matches()) {
                throw new IllegalArgumentException("unsafe_expression");
            }
            ScriptEngineManager mgr = new ScriptEngineManager();
            ScriptEngine eng = mgr.getEngineByName("JavaScript");
            if (eng == null) {
                throw new IllegalStateException("no_js_engine");
            }
            Object v = eng.eval(expr);
            String out = "计算结果：" + v;
            return Map.of(
                    L19State.TOOL_OUTPUT, out,
                    L19State.TOOL_ERROR, "",
                    L19State.DRAFT_REPLY, out,
                    L19State.DIAGNOSTICS, List.of("tool:calc_ok")
            );
        } catch (Exception e) {
            String err = "算术失败：" + e.getClass().getSimpleName();
            return Map.of(
                    L19State.TOOL_OUTPUT, "",
                    L19State.TOOL_ERROR, err,
                    L19State.DRAFT_REPLY, "暂时无法安全计算该表达式，请换用纯数字四则运算。",
                    L19State.DIAGNOSTICS, List.of("tool:calc_fail")
            );
        }
    }

    public static Map<String, Object> toolTime(L19State state) {
        String stamp = ZonedDateTime.now(ZoneId.systemDefault()).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME);
        String line = "当前本机时间（ISO）：" + stamp;
        return Map.of(
                L19State.TOOL_OUTPUT, line,
                L19State.TOOL_ERROR, "",
                L19State.DRAFT_REPLY, line,
                L19State.DIAGNOSTICS, List.of("tool:time_ok")
        );
    }

    static Optional<String> tryOpenAi(String system, String human) {
        String apiKey = CourseEnv.get("OPENAI_API_KEY", "");
        String baseUrl = CourseEnv.get("OPENAI_BASE_URL", "https://api.openai.com/v1");
        String model = CourseEnv.get("OPENAI_MODEL", "gpt-4o-mini");
        if (apiKey.isBlank() || model.isBlank()) {
            return Optional.empty();
        }
        try {
            ChatLanguageModel llm = OpenAiChatModel.builder()
                    .apiKey(apiKey)
                    .baseUrl(baseUrl)
                    .modelName(model)
                    .temperature(0.2)
                    .build();
            Response<AiMessage> resp = llm.generate(SystemMessage.from(system), UserMessage.from(human));
            return Optional.of(resp.content().text().trim());
        } catch (Exception e) {
            return Optional.empty();
        }
    }

    public static Map<String, Object> generate(L19State state) {
        int prev = state.attempt();
        String mode = state.mode();
        String intent = state.intent();
        String user = state.normalizedMessage();
        String fb = state.value(L19State.FEEDBACK_FOR_GENERATION).map(Object::toString).orElse("");
        String body;
        String tag;
        if (!"llm".equals(mode)) {
            String tail = fb.isBlank() ? "" : "\n（上轮反馈：" + fb + "）";
            body = "【Fallback-" + intent + "】已收到：" + user + tail + "\n请补充订单号或物流单号便于处理。";
            tag = "gen:fallback";
        } else {
            Optional<String> o = tryOpenAi(
                    "你是电商售前客服助手。intent=" + intent,
                    "用户原话：\n" + user + "\n内部反馈：\n" + fb
            );
            if (o.isPresent()) {
                body = o.get();
                tag = "gen:openai";
            } else {
                body = "【Fallback】LLM 未配置。";
                tag = "gen:no_config";
            }
        }
        return Map.of(
                L19State.ATTEMPT, prev + 1,
                L19State.DRAFT_REPLY, body,
                L19State.DIAGNOSTICS, List.of("generate:" + tag)
        );
    }

    public static Map<String, Object> evaluate(L19State state) {
        String draft = state.draftReply().strip();
        String intent = state.intent();
        int score = 30;
        if (draft.length() >= 40) {
            score += 30;
        }
        if (("refund".equals(intent) || "shipping".equals(intent))
                && (draft.contains("订单") || draft.contains("单号") || draft.contains("运单") || draft.contains("物流"))) {
            score += 25;
        } else if ("general".equals(intent)) {
            score += 15;
        }
        if (draft.contains("LLM 异常") || draft.contains("【LLM 异常】")) {
            score = Math.min(score, 45);
        }
        boolean passed = score >= 70;
        String feedback = passed ? "" : "请更具体：给出可操作步骤，并主动索要订单号/运单号（若适用）。";
        return Map.of(
                L19State.QUALITY_SCORE, Math.min(100, score),
                L19State.QUALITY_PASSED, passed,
                L19State.FEEDBACK_FOR_GENERATION, feedback,
                L19State.DIAGNOSTICS, List.of("evaluate:score=" + score + ",pass=" + passed)
        );
    }

    public static Map<String, Object> finalize(L19State state) {
        if ("invalid".equals(state.messageGate())) {
            return Map.of(
                    L19State.FINAL_REPLY, "【系统】未收到有效问题描述，请重新输入。",
                    L19State.DIAGNOSTICS, List.of("finalize:invalid_input")
            );
        }
        String intent = state.intent();
        if ("math".equals(intent) || "time".equals(intent)) {
            String text = state.draftReply().strip();
            if (text.isEmpty()) {
                text = state.toolOutput();
            }
            return Map.of(
                    L19State.FINAL_REPLY, text,
                    L19State.DIAGNOSTICS, List.of("finalize:tool:" + intent)
            );
        }
        String text = state.draftReply().strip();
        if (text.isEmpty()) {
            text = "【系统】暂无答复。";
        }
        if (!state.qualityPassed()) {
            text = text + "\n（备注：自动质检未完全通过，建议人工复核。）";
        }
        return Map.of(
                L19State.FINAL_REPLY, text,
                L19State.DIAGNOSTICS, List.of("finalize:llm_path")
        );
    }
}
