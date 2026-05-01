package study.langgraph.lessons.l09_subgraph_modular_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.Map;

/**
 * 第九课：主图与子图共用的状态 schema（对照 {@code 09_subgraph_modular_graph.py} 的 {@code PipelineState}）。
 * <p>
 * 本课为教学清晰，主/子图共用同一 AgentState；真实项目可拆成更小 schema 并通过字段白名单衔接。
 */
public final class L09State extends AgentState {

    /** 外部传入的原始用户文本。 */
    public static final String RAW_INPUT = "raw_input";
    /** 子图 α 产出：去空白、小写后的规范化文本。 */
    public static final String NORMALIZED = "normalized";
    /** 子图 α 产出：短摘要。 */
    public static final String SECTION_A_SUMMARY = "section_a_summary";
    /** 子图 β 产出：扩写段落。 */
    public static final String SECTION_B_DETAIL = "section_b_detail";
    /** 主图最终拼装结果。 */
    public static final String FINAL_REPORT = "final_report";
    /**
     * 门禁错误标记；{@code empty_input} 表示不进入子图。
     */
    public static final String ERROR_NOTE = "error_note";
    /** 步数计数（本课仅主图节点递增，子图内节点不碰此字段，避免父子合并歧义）。 */
    public static final String STEP_COUNT = "step_count";

    /** LangGraph4j 通道表：一律 {@link Channels#base} 默认值。 */
    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            RAW_INPUT, Channels.base(() -> ""),
            NORMALIZED, Channels.base(() -> ""),
            SECTION_A_SUMMARY, Channels.base(() -> ""),
            SECTION_B_DETAIL, Channels.base(() -> ""),
            FINAL_REPORT, Channels.base(() -> ""),
            ERROR_NOTE, Channels.base(() -> ""),
            STEP_COUNT, Channels.base(() -> 0)
    );

    public L09State(Map<String, Object> init) {
        super(init);
    }

    public String rawInput() {
        return value(RAW_INPUT).map(Object::toString).orElse("");
    }

    public String normalized() {
        return value(NORMALIZED).map(Object::toString).orElse("");
    }

    public String sectionASummary() {
        return value(SECTION_A_SUMMARY).map(Object::toString).orElse("");
    }

    public String sectionBDetail() {
        return value(SECTION_B_DETAIL).map(Object::toString).orElse("");
    }

    public String finalReport() {
        return value(FINAL_REPORT).map(Object::toString).orElse("");
    }

    public String errorNote() {
        return value(ERROR_NOTE).map(Object::toString).orElse("");
    }

    public int stepCount() {
        return value(STEP_COUNT).map(v -> ((Number) v).intValue()).orElse(0);
    }
}
