package study.langgraph.lessons.l04b_reducer_graph;

import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 04b：并行分支 + notes 合并（对照 {@code 04b_reducer_graph.py}）。
 *
 * <p>说明：Python 版用 {@code Send} 按 topics 动态 fan-out；LangGraph4j 无同等 API 时，
 * 本示例用「START 静态三分支」演示同一 superstep 多路写入 {@code notes} 的 reducer（appender）行为，
 * 教学意图与 04b 一致。</p>
 */
public final class Lesson04bApp {

    private Lesson04bApp() {
    }

    public static final class GoodState extends AgentState {
        public static final String NOTES = "notes";

        public static final Map<String, Channel<?>> SCHEMA = Map.of(
                NOTES, Channels.appender(ArrayList::new)
        );

        public GoodState(Map<String, Object> init) {
            super(init);
        }

        @SuppressWarnings("unchecked")
        public List<String> notes() {
            return value(NOTES).map(v -> (List<String>) v).orElseGet(List::of);
        }
    }

    public static final class BrokenState extends AgentState {
        public static final String NOTES = "notes";

        public static final Map<String, Channel<?>> SCHEMA = Map.of(
                NOTES, Channels.base(() -> new ArrayList<String>())
        );

        public BrokenState(Map<String, Object> init) {
            super(init);
        }
    }

    static final class AnnotGood implements NodeAction<GoodState> {
        private final String topic;

        AnnotGood(String topic) {
            this.topic = topic;
        }

        @Override
        public Map<String, Object> apply(GoodState state) {
            String line = "[" + topic + "] 这是并行节点生成的一行说明。";
            System.out.println("  [annotate_topic] topic=" + topic + " -> 追加 1 条 notes");
            return Map.of(GoodState.NOTES, List.of(line));
        }
    }

    static final class AnnotBroken implements NodeAction<BrokenState> {
        private final String topic;

        AnnotBroken(String topic) {
            this.topic = topic;
        }

        @Override
        public Map<String, Object> apply(BrokenState state) {
            System.out.println("  [annotate_topic_broken] topic=" + topic);
            return Map.of(BrokenState.NOTES, List.of("[" + topic + "] 说明。"));
        }
    }

    static StateGraph buildGood() throws GraphStateException {
        return new StateGraph<>(GoodState.SCHEMA, GoodState::new)
                .addNode("ann_a", node_async(new AnnotGood("A")))
                .addNode("ann_b", node_async(new AnnotGood("B")))
                .addNode("ann_c", node_async(new AnnotGood("C")))
                .addEdge(START, "ann_a")
                .addEdge(START, "ann_b")
                .addEdge(START, "ann_c")
                .addEdge("ann_a", END)
                .addEdge("ann_b", END)
                .addEdge("ann_c", END);
    }

    static StateGraph buildBroken() throws GraphStateException {
        return new StateGraph<>(BrokenState.SCHEMA, BrokenState::new)
                .addNode("ann_a", node_async(new AnnotBroken("A")))
                .addNode("ann_b", node_async(new AnnotBroken("B")))
                .addNode("ann_c", node_async(new AnnotBroken("C")))
                .addEdge(START, "ann_a")
                .addEdge(START, "ann_b")
                .addEdge(START, "ann_c")
                .addEdge("ann_a", END)
                .addEdge("ann_b", END)
                .addEdge("ann_c", END);
    }

    static void streamDemo(org.bsc.langgraph4j.CompiledGraph<GoodState> g, Map<String, Object> initial) {
        System.out.println("=".repeat(72));
        System.out.println("3) stream：观察逐步输出（LangGraph4j 无 Python 的 stream_mode=updates，用默认流代替）");
        System.out.println("=".repeat(72));
        int i = 0;
        for (var item : g.stream(initial)) {
            i++;
            System.out.println("  --- chunk #" + i + " ---");
            System.out.println("  " + item);
        }
        System.out.println();
    }

    public static void main(String[] args) throws GraphStateException {
        Map<String, Object> initialGood = new HashMap<>();
        initialGood.put(GoodState.NOTES, new ArrayList<String>());

        System.out.println("=".repeat(72));
        System.out.println("1) 无 reducer（base 单值列表）：并行三写可能未合并或行为因引擎而异");
        System.out.println("=".repeat(72));
        try {
            var bad = buildBroken().compile();
            var out = bad.invoke(initialGood).orElseThrow();
            System.out.println("最终 state: " + out);
        } catch (Exception e) {
            System.out.println("捕获到异常：\n  " + e.getClass().getName() + ": " + e.getMessage());
        }

        System.out.println("\n" + "=".repeat(72));
        System.out.println("2) appender：并行结果合并为一条列表");
        System.out.println("=".repeat(72));
        var good = buildGood().compile();
        var goodOut = good.invoke(initialGood).orElseThrow();
        System.out.println("最终 state notes：" + ((GoodState) goodOut).notes());

        streamDemo(good, initialGood);

        System.out.println("\n学习要点：并行同一步写同一 key 需要合适 Channel/reducer；Python Send 动态 fan-out 见原脚本。");
    }
}
