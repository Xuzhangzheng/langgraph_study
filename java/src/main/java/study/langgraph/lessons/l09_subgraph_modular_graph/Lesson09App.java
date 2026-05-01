package study.langgraph.lessons.l09_subgraph_modular_graph;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;

import java.util.HashMap;
import java.util.Map;

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第九课：子图与模块化编排（对照 {@code 09_subgraph_modular_graph.py}）。
 * <p>
 * <strong>与 Python 的差异</strong>：LangGraph4j 的 {@code addNode} 此处用「包装节点」调用
 * {@link CompiledGraph#invoke}，语义等价于 Python {@code add_node("sub", compiled)}——一整段子图在父图中表现为一步可调试单元。
 * <p>
 * 拓扑：gate_input →（条件）sub_alpha → sub_beta → assemble_final → END；空输入 → bad_input → END。
 */
public final class Lesson09App {

    private Lesson09App() {
    }

    /** 将当前父状态打成 Map，供子图 invoke 使用（全量快照，子图运行后再取增量写回）。 */
    static Map<String, Object> stateToMap(L09State s) {
        Map<String, Object> m = new HashMap<>();
        m.put(L09State.RAW_INPUT, s.rawInput());
        m.put(L09State.NORMALIZED, s.normalized());
        m.put(L09State.SECTION_A_SUMMARY, s.sectionASummary());
        m.put(L09State.SECTION_B_DETAIL, s.sectionBDetail());
        m.put(L09State.FINAL_REPORT, s.finalReport());
        m.put(L09State.ERROR_NOTE, s.errorNote());
        m.put(L09State.STEP_COUNT, s.stepCount());
        return m;
    }

    /** 包装「已编译子图」：invoke 后把子图负责的字段写回父图状态。 */
    static final class InvokeCompiledSubgraph implements NodeAction<L09State> {
        private final CompiledGraph<L09State> compiled;
        private final String logLabel;
        /** true=子图 α（更新 normalized + section_a）；false=子图 β（更新 section_b）。 */
        private final boolean alpha;

        InvokeCompiledSubgraph(CompiledGraph<L09State> compiled, String logLabel, boolean alpha) {
            this.compiled = compiled;
            this.logLabel = logLabel;
            this.alpha = alpha;
        }

        @Override
        public Map<String, Object> apply(L09State state) {
            System.out.println("\n[" + logLabel + "] 调用 CompiledGraph.invoke（嵌套执行子图内部节点）");
            L09State out = compiled.invoke(stateToMap(state)).orElseThrow();
            if (alpha) {
                return Map.of(
                        L09State.NORMALIZED, out.normalized(),
                        L09State.SECTION_A_SUMMARY, out.sectionASummary()
                );
            }
            return Map.of(L09State.SECTION_B_DETAIL, out.sectionBDetail());
        }
    }

    /** 子图 α 节点1：归一化 raw_input。 */
    static final class SubAlphaNormalize implements NodeAction<L09State> {
        @Override
        public Map<String, Object> apply(L09State state) {
            String text = state.rawInput().trim().toLowerCase();
            System.out.println("  [sub_α.normalize] -> " + text);
            return Map.of(L09State.NORMALIZED, text);
        }
    }

    /** 子图 α 节点2：生成短摘要。 */
    static final class SubAlphaBrief implements NodeAction<L09State> {
        @Override
        public Map<String, Object> apply(L09State state) {
            String base = state.normalized();
            String summary = "[α-摘要] 主题片段: " + base.substring(0, Math.min(48, base.length()))
                    + (base.length() > 48 ? "…" : "");
            System.out.println("  [sub_α.brief] " + summary);
            return Map.of(L09State.SECTION_A_SUMMARY, summary);
        }
    }

    /** 子图 β 单节点：占位扩写。 */
    static final class SubBetaElaborate implements NodeAction<L09State> {
        @Override
        public Map<String, Object> apply(L09State state) {
            String summary = state.sectionASummary();
            String norm = state.normalized();
            String detail = "[β-扩写] 基于归一化文本(" + norm.length()
                    + " 字) 与 摘要，生成说明性段落。\n"
                    + "（教学占位：真实场景可接 LLM / 模板库 / RAG。）\n"
                    + "----\n摘要回顾：" + summary;
            System.out.println("  [sub_β.elaborate] 完成扩写占位");
            return Map.of(L09State.SECTION_B_DETAIL, detail);
        }
    }

    /** 主图门禁：空输入则写入 error_note。 */
    static final class GateInput implements NodeAction<L09State> {
        @Override
        public Map<String, Object> apply(L09State state) {
            System.out.println("\n[gate_input] 检查 raw_input");
            if (state.rawInput().trim().isEmpty()) {
                System.out.println("  -> 空输入，标记 error_note");
                return Map.of(
                        L09State.ERROR_NOTE, "empty_input",
                        L09State.STEP_COUNT, state.stepCount() + 1
                );
            }
            return Map.of(
                    L09State.ERROR_NOTE, "",
                    L09State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    /** 空输入短路：不调用子图。 */
    static final class BadInput implements NodeAction<L09State> {
        @Override
        public Map<String, Object> apply(L09State state) {
            System.out.println("\n[bad_input] 短路分支");
            return Map.of(
                    L09State.FINAL_REPORT, "【拒绝执行】raw_input 为空。请传入非空字符串后再 invoke。",
                    L09State.STEP_COUNT, state.stepCount() + 1
            );
        }
    }

    /** 主图收尾：拼接各字段为 final_report。 */
    static final class AssembleFinal implements NodeAction<L09State> {
        @Override
        public Map<String, Object> apply(L09State state) {
            System.out.println("\n[assemble_final] 拼装最终报告");
            String block = "======== 最终报告 ========\n"
                    + "归一化: " + state.normalized() + "\n\n"
                    + state.sectionASummary() + "\n\n"
                    + state.sectionBDetail() + "\n"
                    + "==========================";
            return Map.of(L09State.FINAL_REPORT, block, L09State.STEP_COUNT, state.stepCount() + 1);
        }
    }

    /** 构建仅含 normalize→brief 的子图（未 compile）。 */
    public static StateGraph<L09State> buildSubgraphAlpha() throws GraphStateException {
        return new StateGraph<>(L09State.SCHEMA, L09State::new)
                .addNode("normalize", node_async(new SubAlphaNormalize()))
                .addNode("brief", node_async(new SubAlphaBrief()))
                .addEdge(START, "normalize")
                .addEdge("normalize", "brief")
                .addEdge("brief", END);
    }

    /** 构建仅含 elaborate 的子图（未 compile）。 */
    public static StateGraph<L09State> buildSubgraphBeta() throws GraphStateException {
        return new StateGraph<>(L09State.SCHEMA, L09State::new)
                .addNode("elaborate", node_async(new SubBetaElaborate()))
                .addEdge(START, "elaborate")
                .addEdge("elaborate", END);
    }

    /** 主图：串联两段子图（通过包装 invoke）与 assemble_final。 */
    public static StateGraph<L09State> buildMainGraph() throws GraphStateException {
        CompiledGraph<L09State> cAlpha = buildSubgraphAlpha().compile();
        CompiledGraph<L09State> cBeta = buildSubgraphBeta().compile();

        Map<String, String> afterGate = new HashMap<>();
        afterGate.put("sub_alpha", "sub_alpha");
        afterGate.put("bad_input", "bad_input");

        return new StateGraph<>(L09State.SCHEMA, L09State::new)
                .addNode("gate_input", node_async(new GateInput()))
                .addNode("bad_input", node_async(new BadInput()))
                .addNode("sub_alpha", node_async(new InvokeCompiledSubgraph(cAlpha, "sub_alpha", true)))
                .addNode("sub_beta", node_async(new InvokeCompiledSubgraph(cBeta, "sub_beta", false)))
                .addNode("assemble_final", node_async(new AssembleFinal()))
                .addEdge(START, "gate_input")
                .addConditionalEdges(
                        "gate_input",
                        edge_async(s -> "empty_input".equals(s.errorNote()) ? "bad_input" : "sub_alpha"),
                        afterGate
                )
                .addEdge("sub_alpha", "sub_beta")
                .addEdge("sub_beta", "assemble_final")
                .addEdge("assemble_final", END)
                .addEdge("bad_input", END);
    }

    static Map<String, Object> initial(String raw) {
        Map<String, Object> m = new HashMap<>();
        m.put(L09State.RAW_INPUT, raw);
        m.put(L09State.NORMALIZED, "");
        m.put(L09State.SECTION_A_SUMMARY, "");
        m.put(L09State.SECTION_B_DETAIL, "");
        m.put(L09State.FINAL_REPORT, "");
        m.put(L09State.ERROR_NOTE, "");
        m.put(L09State.STEP_COUNT, 0);
        return m;
    }

    public static void main(String[] args) throws GraphStateException {
        var g = buildMainGraph().compile();
        System.out.println("=".repeat(72));
        System.out.println("1) Happy Path：sub_alpha → sub_beta → assemble");
        System.out.println("=".repeat(72));
        var ok = g.invoke(initial("  LangGraph 子图演示  ")).orElseThrow();
        if (ok instanceof L09State) {
            L09State s = (L09State) ok;
            System.out.println(s.finalReport());
            System.out.println("step_count: " + s.stepCount());
        }
        System.out.println("\n" + "=".repeat(72));
        System.out.println("2) Failure Path：空输入");
        System.out.println("=".repeat(72));
        var bad = g.invoke(initial("   ")).orElseThrow();
        if (bad instanceof L09State) {
            L09State s2 = (L09State) bad;
            System.out.println(s2.finalReport());
            System.out.println("step_count: " + s2.stepCount());
        }
    }
}
