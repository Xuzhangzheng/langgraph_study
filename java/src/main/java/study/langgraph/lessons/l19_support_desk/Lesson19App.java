package study.langgraph.lessons.l19_support_desk;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.GraphStateException;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;

/**
 * 第十九课 Capstone 入口：与 Python `python -m lesson19_support_desk` 对照。
 * <p>多文件结构：{@link L19State} / {@link L19Routing} / {@link SupportDeskNodes} / {@link SupportDeskWorkflow}。</p>
 */
public final class Lesson19App {

    private Lesson19App() {
    }

    static Map<String, Object> seed(String rid, String msg, String mode, int maxAttempts) {
        Map<String, Object> m = new HashMap<>();
        m.put(L19State.REQUEST_ID, rid);
        m.put(L19State.USER_MESSAGE, msg);
        m.put(L19State.NORMALIZED_MESSAGE, "");
        m.put(L19State.MESSAGE_GATE, "pending");
        m.put(L19State.INTENT, "pending");
        m.put(L19State.TOOL_EXPRESSION, "");
        m.put(L19State.TOOL_OUTPUT, "");
        m.put(L19State.TOOL_ERROR, "");
        m.put(L19State.DRAFT_REPLY, "");
        m.put(L19State.FINAL_REPLY, "");
        m.put(L19State.QUALITY_SCORE, 0);
        m.put(L19State.QUALITY_PASSED, false);
        m.put(L19State.FEEDBACK_FOR_GENERATION, "");
        m.put(L19State.ATTEMPT, 0);
        m.put(L19State.MAX_ATTEMPTS, maxAttempts);
        m.put(L19State.MODE, mode);
        m.put(L19State.DIAGNOSTICS, new ArrayList<String>());
        return m;
    }

    static void runCase(CompiledGraph<L19State> g, String label, Map<String, Object> init) throws GraphStateException {
        System.out.println("--- " + label + " ---");
        L19State out = g.invoke(init).orElseThrow();
        System.out.println(out.finalReply());
        System.out.println("diagnostics=" + out.diagnostics());
    }

    public static void main(String[] args) throws GraphStateException {
        System.out.println("第十九课 Capstone（LangGraph4j）— 多文件支持台");
        CompiledGraph<L19State> g = SupportDeskWorkflow.build().compile();
        runCase(g, "算术", seed("j1", "计算 3+10", "fallback", 2));
        runCase(g, "退款", seed("j2", "我要退款", "fallback", 2));
        runCase(g, "空输入", seed("j3", "   ", "fallback", 2));
        System.out.println("对照 Python：python -m lesson19_support_desk");
    }
}
