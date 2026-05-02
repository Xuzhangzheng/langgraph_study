package study.langgraph.lessons.l19_support_desk;

/**
 * 条件边纯函数：与 Python {@code lesson19_support_desk.routing} 返回值字符串一致。
 */
public final class L19Routing {

    private L19Routing() {
    }

    public static String routeAfterIngest(L19State state) {
        return "invalid".equals(state.messageGate()) ? "invalid" : "ok";
    }

    public static String routeAfterClassify(L19State state) {
        String intent = state.intent();
        if ("math".equals(intent)) {
            return "tool_calculator";
        }
        if ("time".equals(intent)) {
            return "tool_time";
        }
        return "generate_reply";
    }

    public static String routeAfterEvaluate(L19State state) {
        if (state.qualityPassed()) {
            return "finalize_reply";
        }
        if (state.attempt() >= state.maxAttempts()) {
            return "finalize_reply";
        }
        return "retry_generate";
    }
}
