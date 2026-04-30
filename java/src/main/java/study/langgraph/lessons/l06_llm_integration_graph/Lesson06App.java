package study.langgraph.lessons.l06_llm_integration_graph;

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

import java.util.HashMap;
import java.util.Map;

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第六课：LLM 接入（对照 {@code 06_llm_integration_graph.py}）。
 */
public final class Lesson06App {

    private Lesson06App() {
    }

    public record LlmConfig(String provider, String apiKey, String baseUrl, String model) {
    }

    public static LlmConfig getLlmConfig() {
        String provider = CourseEnv.get("LLM_PROVIDER", "openai").toLowerCase();
        if ("ark".equals(provider)) {
            return new LlmConfig(
                    "ark",
                    CourseEnv.get("ARK_API_KEY", ""),
                    CourseEnv.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
                    CourseEnv.get("ARK_MODEL", "")
            );
        }
        return new LlmConfig(
                "openai",
                CourseEnv.get("OPENAI_API_KEY", ""),
                CourseEnv.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                CourseEnv.get("OPENAI_MODEL", "gpt-5.5")
        );
    }

    public static void validateLlmConfig(LlmConfig c) {
        if (c.apiKey().isBlank()) {
            throw new IllegalArgumentException(c.provider() + " api_key is missing");
        }
        if (c.baseUrl().isBlank()) {
            throw new IllegalArgumentException(c.provider() + " base_url is missing");
        }
        if (c.model().isBlank()) {
            throw new IllegalArgumentException(c.provider() + " model is missing");
        }
    }

    static String detectTaskType(String userInput) {
        if (userInput.contains("改写") || userInput.contains("润色") || userInput.contains("重写")) {
            return "rewrite";
        }
        return "qa";
    }

    static String[] buildPrompts(String taskType, String userInput) {
        String system = "你是一个严谨的 AI 助手。回答要结构清晰、简洁、准确；如果信息不足，要明确说明假设。";
        String task;
        if ("rewrite".equals(taskType)) {
            task = "请对下面这段文本进行改写，要求：保留原意、表达更自然、语句更精炼。\n原文：" + userInput;
        } else {
            task = "请回答下面的问题，要求：先给结论，再给 2-3 条要点解释。\n问题：" + userInput;
        }
        return new String[]{system, task};
    }

    static String callOpenAiCompatible(L06State state, LlmConfig cfg) {
        ChatLanguageModel model = OpenAiChatModel.builder()
                .apiKey(cfg.apiKey())
                .baseUrl(cfg.baseUrl())
                .modelName(cfg.model())
                .temperature(0.2)
                .build();
        Response<AiMessage> response = model.generate(
                SystemMessage.from(state.systemPrompt()),
                UserMessage.from(state.taskPrompt())
        );
        return response.content().text();
    }

    static String callArkStub(L06State state, LlmConfig cfg) {
        return "【Java 示例】provider=ark 时建议在业务项目中接入火山官方 Java/HTTP SDK；此处为占位输出。\n"
                + "model=" + cfg.model() + " baseUrl=" + cfg.baseUrl() + "\n"
                + "任务摘要：" + state.taskPrompt().substring(0, Math.min(80, state.taskPrompt().length())) + "…";
    }

    static final class InitRequest implements NodeAction<L06State> {
        @Override
        public Map<String, Object> apply(L06State state) {
            String userInput = state.userInput();
            String taskType = detectTaskType(userInput);
            String[] prompts = buildPrompts(taskType, userInput);
            System.out.println("\n[init_request] task_type: " + taskType + ", mode: " + state.mode());
            return Map.of(
                    L06State.TASK_TYPE, taskType,
                    L06State.SYSTEM_PROMPT, prompts[0],
                    L06State.TASK_PROMPT, prompts[1],
                    L06State.PROVIDER, "",
                    L06State.ERROR, ""
            );
        }
    }

    static final class FallbackNode implements NodeAction<L06State> {
        @Override
        public Map<String, Object> apply(L06State state) {
            return Map.of(
                    L06State.ANSWER,
                    "【Fallback 模式】当前未调用真实 LLM。\n任务类型：" + state.taskType()
                            + "\n你可以在配置 LLM_PROVIDER 与对应 API Key 后切换到 llm 模式。"
            );
        }
    }

    static final class LoadLlmConfig implements NodeAction<L06State> {
        @Override
        public Map<String, Object> apply(L06State state) {
            LlmConfig cfg = getLlmConfig();
            try {
                validateLlmConfig(cfg);
                return Map.of(L06State.PROVIDER, cfg.provider(), L06State.ERROR, "");
            } catch (Exception e) {
                return Map.of(L06State.PROVIDER, cfg.provider(), L06State.ERROR, e.getMessage());
            }
        }
    }

    static final class ConfigErrorNode implements NodeAction<L06State> {
        @Override
        public Map<String, Object> apply(L06State state) {
            return Map.of(
                    L06State.ANSWER,
                    "【自动回退到 Fallback】配置校验失败。\nprovider：" + state.provider() + "\n错误：" + state.error()
                            + "\n请检查 API Key、Base URL、模型名或 endpoint_id 配置。"
            );
        }
    }

    static final class CallOpenAiNode implements NodeAction<L06State> {
        @Override
        public Map<String, Object> apply(L06State state) {
            LlmConfig cfg = getLlmConfig();
            try {
                String answer = callOpenAiCompatible(state, cfg);
                return Map.of(L06State.ANSWER, answer, L06State.ERROR, "");
            } catch (Exception e) {
                return Map.of(
                        L06State.ANSWER,
                        "【自动回退到 Fallback】LLM 调用失败。\nprovider：" + cfg.provider() + "\n错误：" + e.getMessage()
                                + "\n任务类型：" + state.taskType(),
                        L06State.ERROR, e.getMessage()
                );
            }
        }
    }

    static final class CallArkNode implements NodeAction<L06State> {
        @Override
        public Map<String, Object> apply(L06State state) {
            LlmConfig cfg = getLlmConfig();
            try {
                validateLlmConfig(cfg);
                return Map.of(L06State.ANSWER, callArkStub(state, cfg), L06State.ERROR, "");
            } catch (Exception e) {
                return Map.of(
                        L06State.ANSWER,
                        "【自动回退】Ark 配置无效：" + e.getMessage(),
                        L06State.ERROR, e.getMessage()
                );
            }
        }
    }

    public static StateGraph buildGraph() throws GraphStateException {
        Map<String, String> routeMode = Map.of(
                "fallback_node", "fallback_node",
                "load_llm_config", "load_llm_config"
        );
        Map<String, String> routeProvider = new HashMap<>();
        routeProvider.put("call_openai_node", "call_openai_node");
        routeProvider.put("call_ark_node", "call_ark_node");
        routeProvider.put("config_error_node", "config_error_node");

        return new StateGraph<>(L06State.SCHEMA, L06State::new)
                .addNode("init_request", node_async(new InitRequest()))
                .addNode("fallback_node", node_async(new FallbackNode()))
                .addNode("load_llm_config", node_async(new LoadLlmConfig()))
                .addNode("config_error_node", node_async(new ConfigErrorNode()))
                .addNode("call_openai_node", node_async(new CallOpenAiNode()))
                .addNode("call_ark_node", node_async(new CallArkNode()))
                .addEdge(START, "init_request")
                .addConditionalEdges(
                        "init_request",
                        edge_async(s -> "fallback".equals(s.mode()) ? "fallback_node" : "load_llm_config"),
                        routeMode
                )
                .addConditionalEdges(
                        "load_llm_config",
                        edge_async(s -> {
                            if (!s.error().isEmpty()) {
                                return "config_error_node";
                            }
                            if ("ark".equals(s.provider())) {
                                return "call_ark_node";
                            }
                            return "call_openai_node";
                        }),
                        routeProvider
                )
                .addEdge("fallback_node", END)
                .addEdge("config_error_node", END)
                .addEdge("call_openai_node", END)
                .addEdge("call_ark_node", END);
    }

    static void runCase(org.bsc.langgraph4j.CompiledGraph<?> graph, String userInput, String mode)
            throws GraphStateException {
        Map<String, Object> initial = new HashMap<>();
        initial.put(L06State.USER_INPUT, userInput);
        initial.put(L06State.TASK_TYPE, "");
        initial.put(L06State.MODE, mode);
        initial.put(L06State.PROVIDER, "");
        initial.put(L06State.SYSTEM_PROMPT, "");
        initial.put(L06State.TASK_PROMPT, "");
        initial.put(L06State.ANSWER, "");
        initial.put(L06State.ERROR, "");
        System.out.println("\n" + "=".repeat(80));
        System.out.println("开始案例 mode=" + mode + ": " + userInput);
        var fs = graph.invoke(initial).orElseThrow();
        if (fs instanceof L06State s) {
            System.out.println("[案例结束] task_type=" + s.taskType());
            System.out.println("answer:\n" + s.value(L06State.ANSWER).orElse(""));
            if (!s.error().isEmpty()) {
                System.out.println("error: " + s.error());
            }
        }
    }

    public static void main(String[] args) throws GraphStateException {
        LlmConfig c = getLlmConfig();
        System.out.println("[配置] LLM_PROVIDER=" + c.provider() + ", MODEL=" + c.model() + ", BASE_URL=" + c.baseUrl());
        var g = buildGraph().compile();
        runCase(g, "请解释一下 LangGraph 和 LangChain 的关系。", "llm");
        runCase(g, "请把这句话改写得更专业：java世界上最好的语言。", "llm");
    }
}
