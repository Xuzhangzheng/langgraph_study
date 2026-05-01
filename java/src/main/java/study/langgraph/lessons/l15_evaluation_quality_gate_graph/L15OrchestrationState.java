package study.langgraph.lessons.l15_evaluation_quality_gate_graph;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 第十五课：评测编排（薄批处理图）状态，与 Python {@code EvalOrchestrationState} 对齐。
 * <p>
 * {@code eval_reports} 在 {@code regression_worker} 节点中被整体替换为本次运行的明细列表，
 * 与 Python 侧「最后一次写入覆盖」行为一致；生产可改为对象存储引用 + 节点只写指针。
 */
public final class L15OrchestrationState extends AgentState {

    public static final String RUN_ID = "run_id";
    /** 每条用例的 JSON 友好结构：case_id / passed / detail / actual */
    public static final String EVAL_REPORTS = "eval_reports";
    public static final String PASS_COUNT = "pass_count";
    public static final String FAIL_COUNT = "fail_count";
    public static final String GATE_OK = "gate_ok";
    public static final String GATE_DETAIL = "gate_detail";

    public static final Map<String, Channel<?>> SCHEMA = Map.of(
            RUN_ID, Channels.base(() -> ""),
            EVAL_REPORTS, Channels.base(ArrayList::new),
            PASS_COUNT, Channels.base(() -> 0),
            FAIL_COUNT, Channels.base(() -> 0),
            GATE_OK, Channels.base(() -> false),
            GATE_DETAIL, Channels.base(() -> "")
    );

    public L15OrchestrationState(Map<String, Object> init) {
        super(init);
    }

    public String runId() {
        return value(RUN_ID).map(Object::toString).orElse("");
    }

    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> evalReports() {
        return value(EVAL_REPORTS).map(v -> (List<Map<String, Object>>) v).orElseGet(List::of);
    }

    public int passCount() {
        return value(PASS_COUNT)
                .map(v -> v instanceof Number ? ((Number) v).intValue() : Integer.parseInt(v.toString()))
                .orElse(0);
    }

    public int failCount() {
        return value(FAIL_COUNT)
                .map(v -> v instanceof Number ? ((Number) v).intValue() : Integer.parseInt(v.toString()))
                .orElse(0);
    }

    public boolean gateOk() {
        return value(GATE_OK).map(v -> Boolean.parseBoolean(v.toString())).orElse(false);
    }

    public String gateDetail() {
        return value(GATE_DETAIL).map(Object::toString).orElse("");
    }
}
