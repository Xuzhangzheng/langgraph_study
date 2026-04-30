package study.langgraph.lessons.l07_messages_context_graph;

import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.data.message.ChatMessage;
import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.output.Response;
import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;
import study.langgraph.lessons.l06_llm_integration_graph.Lesson06App;
import study.langgraph.support.CourseEnv;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第七课：消息与上下文（对照 {@code 07_messages_context_graph.py}）。
 */
public final class Lesson07App {

    private Lesson07App() {
    }

    static String formatContextForFallback(List<ChatMessage> messages) {
        StringBuilder sb = new StringBuilder();
        for (ChatMessage m : messages) {
            String role = m.type() == null ? "Msg" : m.type().name();
            sb.append("- ").append(role).append(": ").append(singleTextOf(m)).append("\n");
        }
        return sb.toString();
    }

    static String singleTextOf(ChatMessage m) {
        try {
            if (m instanceof UserMessage um) {
                return um.singleText();
            }
            if (m instanceof AiMessage am) {
                return am.text();
            }
            if (m instanceof SystemMessage sm) {
                return sm.text();
            }
        } catch (Exception ignored) {
        }
        return m.toString();
    }

    static final class AppendUserMessage implements NodeAction<L07State> {
        @Override
        public Map<String, Object> apply(L07State state) {
            String text = state.pendingUserText() == null ? "" : state.pendingUserText().trim();
            if (text.isEmpty()) {
                return Map.of(L07State.INPUT_VALID, false);
            }
            List<ChatMessage> next = new ArrayList<>(state.messages());
            next.add(UserMessage.from(text));
            return Map.of(
                    L07State.MESSAGES, next,
                    L07State.INPUT_VALID, true
            );
        }
    }

    static final class EmptyInputNode implements NodeAction<L07State> {
        @Override
        public Map<String, Object> apply(L07State state) {
            List<ChatMessage> next = new ArrayList<>(state.messages());
            next.add(AiMessage.from("【边界】pending_user_text 为空，未追加用户消息。"));
            return Map.of(L07State.MESSAGES, next);
        }
    }

    static final class TrimHistory implements NodeAction<L07State> {
        @Override
        public Map<String, Object> apply(L07State state) {
            int cap = state.maxMessagesToKeep();
            List<ChatMessage> msgs = state.messages();
            if (cap <= 0 || msgs.size() <= cap) {
                return Map.of();
            }
            List<ChatMessage> kept = new ArrayList<>(msgs.subList(msgs.size() - cap, msgs.size()));
            return Map.of(L07State.MESSAGES, kept);
        }
    }

    static final class GenerateWithContext implements NodeAction<L07State> {
        @Override
        public Map<String, Object> apply(L07State state) {
            List<ChatMessage> msgs = state.messages();
            if ("fallback".equals(state.mode())) {
                String ctx = formatContextForFallback(msgs);
                String reply = "【Fallback】以下是当前 messages 摘要（用于理解上下文如何汇总）：\n"
                        + ctx + "----\n"
                        + "（配置 LLM 与密钥后可将 mode 设为 llm 走真实多轮。）";
                List<ChatMessage> next = new ArrayList<>(msgs);
                next.add(AiMessage.from(reply));
                return Map.of(L07State.MESSAGES, next);
            }

            var cfg = Lesson06App.getLlmConfig();
            try {
                Lesson06App.validateLlmConfig(cfg);
            } catch (Exception e) {
                List<ChatMessage> next = new ArrayList<>(msgs);
                next.add(AiMessage.from("【配置无效，退回规则答复】" + e.getMessage() + "\n" + formatContextForFallback(msgs)));
                return Map.of(L07State.MESSAGES, next);
            }

            if ("ark".equals(cfg.provider())) {
                List<ChatMessage> next = new ArrayList<>(msgs);
                next.add(AiMessage.from("【Java 示例】ark 路径见第六课说明；以下为摘要：\n" + formatContextForFallback(msgs)));
                return Map.of(L07State.MESSAGES, next);
            }

            try {
                ChatLanguageModel model = OpenAiChatModel.builder()
                        .apiKey(cfg.apiKey())
                        .baseUrl(cfg.baseUrl())
                        .modelName(cfg.model())
                        .temperature(0.2)
                        .build();
                SystemMessage system = SystemMessage.from(
                        "你是一个简洁的中文助手。请结合完整对话历史回答；若用户要求回忆前文，必须基于历史，不要编造。");
                List<ChatMessage> toInvoke = new ArrayList<>();
                toInvoke.add(system);
                toInvoke.addAll(msgs);
                Response<AiMessage> response = model.generate(toInvoke);
                String text = response.content().text();
                List<ChatMessage> next = new ArrayList<>(msgs);
                next.add(AiMessage.from(text));
                return Map.of(L07State.MESSAGES, next);
            } catch (Exception e) {
                List<ChatMessage> next = new ArrayList<>(msgs);
                next.add(AiMessage.from("【LLM 调用失败】" + e.getMessage() + "\n" + formatContextForFallback(msgs)));
                return Map.of(L07State.MESSAGES, next);
            }
        }
    }

    public static StateGraph buildGraph() throws GraphStateException {
        Map<String, String> afterAppend = Map.of(
                "trim_history", "trim_history",
                "empty_input_node", "empty_input_node"
        );
        return new StateGraph<>(L07State.SCHEMA, L07State::new)
                .addNode("append_user_message", node_async(new AppendUserMessage()))
                .addNode("empty_input_node", node_async(new EmptyInputNode()))
                .addNode("trim_history", node_async(new TrimHistory()))
                .addNode("generate_with_context", node_async(new GenerateWithContext()))
                .addEdge(START, "append_user_message")
                .addConditionalEdges(
                        "append_user_message",
                        edge_async(s -> s.inputValid() ? "trim_history" : "empty_input_node"),
                        afterAppend
                )
                .addEdge("trim_history", "generate_with_context")
                .addEdge("empty_input_node", END)
                .addEdge("generate_with_context", END);
    }

    static Map<String, Object> baseInitial(
            String pending,
            String mode,
            int maxKeep,
            List<ChatMessage> existing
    ) {
        Map<String, Object> m = new HashMap<>();
        m.put(L07State.MESSAGES, new ArrayList<>(existing != null ? existing : List.of()));
        m.put(L07State.PENDING_USER_TEXT, pending);
        m.put(L07State.MODE, mode);
        m.put(L07State.MAX_MESSAGES_TO_KEEP, maxKeep);
        m.put(L07State.INPUT_VALID, false);
        return m;
    }

    static ChatMessage lastAi(L07State s) {
        List<ChatMessage> msgs = s.messages();
        for (int i = msgs.size() - 1; i >= 0; i--) {
            ChatMessage m = msgs.get(i);
            if (m instanceof AiMessage) {
                return m;
            }
        }
        return msgs.isEmpty() ? AiMessage.from("") : msgs.get(msgs.size() - 1);
    }

    public static void demo() throws GraphStateException {
        var g = buildGraph().compile();

        System.out.println("=".repeat(72));
        System.out.println("1) Happy Path：fallback 多轮");
        System.out.println("=".repeat(72));
        var s1 = g.invoke(baseInitial("我叫小明，请记住。", "fallback", 0, null)).orElseThrow();
        if (s1 instanceof L07State a) {
            System.out.println("--- 第一轮最后一条 AI ---");
            System.out.println(singleTextOf(lastAi(a)));
        }
        var s2 = g.invoke(baseInitial(
                "我刚才说我叫什么？",
                "fallback",
                0,
                ((L07State) s1).messages()
        )).orElseThrow();
        if (s2 instanceof L07State b) {
            System.out.println("--- 第二轮最后一条 AI ---");
            System.out.println(singleTextOf(lastAi(b)));
        }

        System.out.println("\n" + "=".repeat(72));
        System.out.println("2) 边界：裁剪 max_messages_to_keep=2");
        System.out.println("=".repeat(72));
        var longCtx = new ArrayList<>(((L07State) s2).messages());
        var s3 = g.invoke(baseInitial("只问好。", "fallback", 2, longCtx)).orElseThrow();
        if (s3 instanceof L07State c) {
            System.out.println("裁剪后消息条数: " + c.messages().size());
            String tail = singleTextOf(lastAi(c));
            System.out.println("最后一条 AI: " + tail.substring(0, Math.min(200, tail.length())) + (tail.length() > 200 ? "..." : ""));
        }

        System.out.println("\n" + "=".repeat(72));
        System.out.println("3) Failure Path：空用户输入");
        System.out.println("=".repeat(72));
        var bad = g.invoke(baseInitial("   ", "fallback", 0, null)).orElseThrow();
        if (bad instanceof L07State d) {
            System.out.println(singleTextOf(lastAi(d)));
        }

        System.out.println("\n" + "=".repeat(72));
        System.out.println("4) LLM 模式（需有效 OPENAI 配置）");
        System.out.println("=".repeat(72));
        var sLlm = g.invoke(baseInitial("用一句话介绍 LangGraph。", "llm", 0, null)).orElseThrow();
        if (sLlm instanceof L07State e) {
            String tail = singleTextOf(lastAi(e));
            System.out.println(tail.substring(0, Math.min(800, tail.length())));
        }
    }

    public static void main(String[] args) throws GraphStateException {
        System.out.println("[配置] LLM_PROVIDER=" + CourseEnv.get("LLM_PROVIDER", "openai"));
        demo();
    }
}
