package study.langgraph.lessons.l16_rag_langgraph_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 第十六课状态（对照 {@code 16_rag_langgraph_graph.py} 的 {@code RagState}）。
 * <p>
 * <b>字段契约</b>：键名须与 Python TypedDict 一致，便于双端对照日志与 invoke 载荷；
 * {@link #RETRIEVED_CHUNKS} / {@link #CONTEXT_CHUNKS} 为「段落结构」列表，元素为平面 Map（doc_id、title、body、score、source）。
 */
public final class L16State extends AgentState {

    public static final String REQUEST_ID = "request_id";
    /** 经 {@code normalize_query} 修剪后的查询；空串表示非法输入支路 */
    public static final String USER_QUERY = "user_query";
    /** {@code llm}：尝试 OpenAI 兼容接口；{@code fallback}：模板归纳（与 Python 默认 demo 一致） */
    public static final String MODE = "mode";
    /** {@code pending} → 初始；{@code ok} → 可检索；{@code invalid} → 空查询收口 */
    public static final String QUERY_GATE = "query_gate";
    /** 粗排检索输出（含 score） */
    public static final String RETRIEVED_CHUNKS = "retrieved_chunks";
    /** 重排后供生成消费的子集 */
    public static final String CONTEXT_CHUNKS = "context_chunks";
    public static final String ANSWER = "answer";
    /** 生成节点写入：每条对应一段证据的简短引用说明 */
    public static final String CITATIONS = "citations";
    /** 各节点追加的诊断/审计字符串；使用 appender 通道合并多节点输出 */
    public static final String DIAGNOSTICS = "diagnostics";

    /**
     * LangGraph4j 通道定义：
     * <ul>
     *   <li>{@code base}：标量或整对象替换（如整表替换 retrieved_chunks）</li>
     *   <li>{@code appender}：列表按追加合并，等价 Python {@code Annotated[list, operator.add]}</li>
     * </ul>
     */
    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            REQUEST_ID, Channels.base(() -> ""),
            USER_QUERY, Channels.base(() -> ""),
            MODE, Channels.base(() -> "fallback"),
            QUERY_GATE, Channels.base(() -> "pending"),
            RETRIEVED_CHUNKS, Channels.base(ArrayList::new),
            CONTEXT_CHUNKS, Channels.base(ArrayList::new),
            ANSWER, Channels.base(() -> ""),
            CITATIONS, Channels.base(ArrayList::new),
            DIAGNOSTICS, Channels.appender(ArrayList::new)
    );

    public L16State(Map<String, Object> init) {
        super(init);
    }

    public String requestId() {
        return value(REQUEST_ID).map(Object::toString).orElse("");
    }

    public String userQuery() {
        return value(USER_QUERY).map(Object::toString).orElse("");
    }

    public String mode() {
        return value(MODE).map(Object::toString).orElse("fallback");
    }

    public String queryGate() {
        return value(QUERY_GATE).map(Object::toString).orElse("pending");
    }

    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> retrievedChunks() {
        return value(RETRIEVED_CHUNKS).map(v -> (List<Map<String, Object>>) v).orElseGet(List::of);
    }

    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> contextChunks() {
        return value(CONTEXT_CHUNKS).map(v -> (List<Map<String, Object>>) v).orElseGet(List::of);
    }

    public String answer() {
        return value(ANSWER).map(Object::toString).orElse("");
    }

    @SuppressWarnings("unchecked")
    public List<String> citations() {
        return value(CITATIONS).map(v -> (List<String>) v).orElseGet(List::of);
    }

    @SuppressWarnings("unchecked")
    public List<String> diagnostics() {
        return value(DIAGNOSTICS).map(v -> (List<String>) v).orElseGet(List::of);
    }
}
