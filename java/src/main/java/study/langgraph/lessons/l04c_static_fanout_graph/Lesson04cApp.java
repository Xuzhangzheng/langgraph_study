package study.langgraph.lessons.l04c_static_fanout_graph;

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
 * 04c：静态 fan-out + join（对照 {@code 04c_static_fanout_graph.py}）。
 */
public final class Lesson04cApp {

    private Lesson04cApp() {
    }

    public static final class FanoutState extends AgentState {
        public static final String SEED = "seed";
        public static final String NOTES = "notes";

        public static final Map<String, Channel<?>> SCHEMA = Map.of(
                SEED, Channels.base(() -> ""),
                NOTES, Channels.appender(ArrayList::new)
        );

        public FanoutState(Map<String, Object> init) {
            super(init);
        }

        public String seed() {
            return value(SEED).map(Object::toString).orElse("");
        }

        @SuppressWarnings("unchecked")
        public List<String> notes() {
            return value(NOTES).map(v -> (List<String>) v).orElseGet(List::of);
        }
    }

    public static final class BrokenFanoutState extends AgentState {
        public static final String SEED = "seed";
        public static final String NOTES = "notes";

        public static final Map<String, Channel<?>> SCHEMA = Map.of(
                SEED, Channels.base(() -> ""),
                NOTES, Channels.base(() -> new ArrayList<String>())
        );

        public BrokenFanoutState(Map<String, Object> init) {
            super(init);
        }
    }

    public static final class ChainState extends AgentState {
        public static final String SEED = "seed";
        public static final String NOTES = "notes";

        public static final Map<String, Channel<?>> SCHEMA = Map.of(
                SEED, Channels.base(() -> ""),
                NOTES, Channels.appender(ArrayList::new)
        );

        public ChainState(Map<String, Object> init) {
            super(init);
        }

        @SuppressWarnings("unchecked")
        public List<String> notes() {
            return value(NOTES).map(v -> (List<String>) v).orElseGet(List::of);
        }
    }

    static StateGraph buildGood() throws GraphStateException {
        return new StateGraph<>(FanoutState.SCHEMA, FanoutState::new)
                .addNode("dosth", node_async((NodeAction<FanoutState>) state -> {
                    System.out.println("  [worker_dosth] 静态边 START→Dosth");
                    return Map.of(FanoutState.NOTES, List.of("Dosth: 收到 seed=" + state.seed()));
                }))
                .addNode("w_a", node_async((NodeAction<FanoutState>) state -> {
                    System.out.println("  [worker_a] 静态边 dosth→w_a");
                    return Map.of(FanoutState.NOTES, List.of("A: 收到 seed=" + state.seed()));
                }))
                .addNode("w_b", node_async((NodeAction<FanoutState>) state -> {
                    System.out.println("  [worker_b] 静态边 dosth→w_b");
                    return Map.of(FanoutState.NOTES, List.of("B: 收到 seed=" + state.seed()));
                }))
                .addNode("w_c", node_async((NodeAction<FanoutState>) state -> {
                    System.out.println("  [worker_c] 静态边 dosth→w_c");
                    return Map.of(FanoutState.NOTES, List.of("C: 收到 seed=" + state.seed()));
                }))
                .addNode("join_all", node_async((NodeAction<FanoutState>) state -> {
                    System.out.println("\n[join_all] 三分支已完成，当前 notes：");
                    for (String line : state.notes()) {
                        System.out.println("    - " + line);
                    }
                    return Map.of();
                }))
                .addEdge(START, "dosth")
                .addEdge("dosth", "w_a")
                .addEdge("dosth", "w_b")
                .addEdge("dosth", "w_c")
                .addEdge("w_a", "join_all")
                .addEdge("w_b", "join_all")
                .addEdge("w_c", "join_all")
                .addEdge("join_all", END);
    }

    static StateGraph buildBroken() throws GraphStateException {
        return new StateGraph<>(BrokenFanoutState.SCHEMA, BrokenFanoutState::new)
                .addNode("w_a", node_async((NodeAction<BrokenFanoutState>) state -> {
                    System.out.println("  [worker_a_broken]");
                    return Map.of(BrokenFanoutState.NOTES, List.of("a"));
                }))
                .addNode("w_b", node_async((NodeAction<BrokenFanoutState>) state -> {
                    System.out.println("  [worker_b_broken]");
                    return Map.of(BrokenFanoutState.NOTES, List.of("b"));
                }))
                .addNode("w_c", node_async((NodeAction<BrokenFanoutState>) state -> {
                    System.out.println("  [worker_c_broken]");
                    return Map.of(BrokenFanoutState.NOTES, List.of("c"));
                }))
                .addNode("join_all", node_async((NodeAction<BrokenFanoutState>) s -> {
                    System.out.println("\n[join_all_broken]（不应在无 reducer 成功场景下跑到这里）");
                    return Map.of();
                }))
                .addEdge(START, "w_a")
                .addEdge(START, "w_b")
                .addEdge(START, "w_c")
                .addEdge("w_a", "join_all")
                .addEdge("w_b", "join_all")
                .addEdge("w_c", "join_all")
                .addEdge("join_all", END);
    }

    static StateGraph buildChain() throws GraphStateException {
        return new StateGraph<>(ChainState.SCHEMA, ChainState::new)
                .addNode("step_1", node_async((NodeAction<ChainState>) s -> {
                    System.out.println("  [step_1] 无前驱，第一拍即可运行");
                    return Map.of(ChainState.NOTES, List.of("step_1 done"));
                }))
                .addNode("step_2", node_async((NodeAction<ChainState>) state -> {
                    System.out.println("  [step_2] 依赖 step_1：只有前驱已写入 notes 才可能就绪");
                    int n = state.notes().size();
                    return Map.of(ChainState.NOTES, List.of("step_2 (运行至此已有 " + n + " 条 notes)"));
                }))
                .addNode("step_3", node_async((NodeAction<ChainState>) state -> {
                    System.out.println("  [step_3] 依赖 step_2：链式最后一环");
                    int n = state.notes().size();
                    return Map.of(ChainState.NOTES, List.of("step_3 (运行至此已有 " + n + " 条 notes)"));
                }))
                .addEdge(START, "step_1")
                .addEdge("step_1", "step_2")
                .addEdge("step_2", "step_3")
                .addEdge("step_3", END);
    }

    public static void main(String[] args) throws GraphStateException {
        Map<String, Object> initial = new HashMap<>();
        initial.put(FanoutState.SEED, "hello-static-fanout");
        initial.put(FanoutState.NOTES, new ArrayList<String>());

        System.out.println("=".repeat(72));
        System.out.println("1) 无 reducer：静态三分支并行写 notes，观察是否异常");
        System.out.println("=".repeat(72));
        try {
            buildBroken().compile().invoke(initial).orElseThrow();
        } catch (Exception e) {
            System.out.println("捕获到异常（可能符合预期，取决于引擎）：\n  " + e.getClass().getName() + ": " + e.getMessage());
        }

        System.out.println("\n" + "=".repeat(72));
        System.out.println("2) 有 reducer：静态 fan-out → join_all");
        System.out.println("=".repeat(72));
        var good = buildGood().compile();
        var fin = good.invoke(initial).orElseThrow();
        System.out.println("\n最终 state：");
        if (fin instanceof FanoutState fs) {
            System.out.println("  seed: " + fs.seed());
            System.out.println("  notes: " + fs.notes());
        }

        System.out.println("\n" + "=".repeat(72));
        System.out.println("3) 依赖链：step_1 → step_2 → step_3");
        System.out.println("=".repeat(72));
        Map<String, Object> chainInit = new HashMap<>();
        chainInit.put(ChainState.SEED, "linear-chain");
        chainInit.put(ChainState.NOTES, new ArrayList<String>());
        var chainG = buildChain().compile();
        var chainFinal = chainG.invoke(chainInit).orElseThrow();
        if (chainFinal instanceof ChainState cs) {
            System.out.println("  最终 state notes：" + cs.notes());
        }
        System.out.println("  stream:");
        int i = 0;
        for (var chunk : chainG.stream(chainInit)) {
            i++;
            System.out.println("  --- chunk #" + i + " ---");
            System.out.println("  " + chunk);
        }

        System.out.println("\n" + "=".repeat(72));
        System.out.println("4) fan-out 图 stream");
        System.out.println("=".repeat(72));
        int j = 0;
        for (var chunk : good.stream(initial)) {
            j++;
            System.out.println("  --- chunk #" + j + " ---");
            System.out.println("  " + chunk);
        }

        System.out.println("\n与 04b 对比：04b 偏动态 Send；04c 边在代码里写死。");
    }
}
