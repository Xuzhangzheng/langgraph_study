package study.langgraph.lessons.l04d_reducer_strategies;

import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;
import org.bsc.langgraph4j.state.Reducer;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 04d：多种 reducer 策略（对照 {@code 04d_reducer_strategies.py}）。
 */
@SuppressWarnings("unchecked")
public final class Lesson04dApp {

    private Lesson04dApp() {
    }

    static final class GenericState extends AgentState {
        GenericState(Map<String, Object> init) {
            super(init);
        }
    }

    static Reducer mergeLines() {
        return (left, right) -> {
            String l = left == null ? "" : left.toString();
            String r = right == null ? "" : right.toString();
            if (l.isEmpty()) {
                return r;
            }
            if (r.isEmpty()) {
                return l;
            }
            return l + "\n" + r;
        };
    }

    static Reducer maxInt() {
        return (a, b) -> {
            int x = a == null ? 0 : ((Number) a).intValue();
            int y = b == null ? 0 : ((Number) b).intValue();
            return Math.max(x, y);
        };
    }

    static Reducer setUnion() {
        return (a, b) -> {
            Set<String> s = new HashSet<>();
            if (a != null) {
                s.addAll((Set<String>) a);
            }
            if (b != null) {
                s.addAll((Set<String>) b);
            }
            return s;
        };
    }

    static Reducer takeLastList() {
        return (left, right) -> right;
    }

    static Reducer mergeUniqueInOrder() {
        return (left, right) -> {
            List<String> out = new ArrayList<>();
            LinkedHashSet<String> seen = new LinkedHashSet<>();
            List<String> L = left == null ? List.of() : (List<String>) left;
            List<String> R = right == null ? List.of() : (List<String>) right;
            for (String x : L) {
                if (seen.add(x)) {
                    out.add(x);
                }
            }
            for (String x : R) {
                if (seen.add(x)) {
                    out.add(x);
                }
            }
            return out;
        };
    }

    static void demoSetUnion() throws GraphStateException {
        System.out.println("\n" + "=".repeat(72));
        System.out.println("1) set 并集 reducer");
        System.out.println("=".repeat(72));
        final String TAGS = "tags";
        Map<String, Channel<?>> schema = Map.of(TAGS, Channels.base(setUnion(), HashSet::new));
        var b = new StateGraph<>(schema, GenericState::new)
                .addNode("su_a", node_async((NodeAction<GenericState>) s -> Map.of(TAGS, Set.of("from_a"))))
                .addNode("su_b", node_async((NodeAction<GenericState>) s -> {
                    Set<String> z = new HashSet<>();
                    z.add("from_b");
                    z.add("shared");
                    return Map.of(TAGS, z);
                }))
                .addNode("su_c", node_async((NodeAction<GenericState>) s -> {
                    Set<String> z = new HashSet<>();
                    z.add("from_c");
                    z.add("shared");
                    return Map.of(TAGS, z);
                }))
                .addNode("join", node_async((NodeAction<GenericState>) s -> {
                    Set<String> tags = (Set<String>) s.value(TAGS).orElse(Set.of());
                    System.out.println("  [set_union] 合并后 tags = " + tags);
                    return Map.of();
                }));
        b.addEdge(START, "su_a").addEdge(START, "su_b").addEdge(START, "su_c");
        b.addEdge("su_a", "join").addEdge("su_b", "join").addEdge("su_c", "join");
        b.addEdge("join", END);
        var g = b.compile();
        Map<String, Object> in = new HashMap<>();
        in.put(TAGS, new HashSet<String>());
        System.out.println("  最终: " + g.invoke(in).orElseThrow());
    }

    static void demoMaxInt() throws GraphStateException {
        System.out.println("\n" + "=".repeat(72));
        System.out.println("2) int 取最大 reducer");
        System.out.println("=".repeat(72));
        final String BEST = "best";
        Map<String, Channel<?>> schema = Map.of(BEST, Channels.base(maxInt(), () -> 0));
        var b = new StateGraph<>(schema, GenericState::new)
                .addNode("mx_a", node_async((NodeAction<GenericState>) s -> Map.of(BEST, 3)))
                .addNode("mx_b", node_async((NodeAction<GenericState>) s -> Map.of(BEST, 9)))
                .addNode("mx_c", node_async((NodeAction<GenericState>) s -> Map.of(BEST, 5)))
                .addNode("join", node_async((NodeAction<GenericState>) s -> {
                    int v = ((Number) s.value(BEST).orElse(0)).intValue();
                    System.out.println("  [max] 合并后 best = " + v);
                    return Map.of();
                }));
        b.addEdge(START, "mx_a").addEdge(START, "mx_b").addEdge(START, "mx_c");
        b.addEdge("mx_a", "join").addEdge("mx_b", "join").addEdge("mx_c", "join");
        b.addEdge("join", END);
        var g = b.compile();
        System.out.println("  最终: " + g.invoke(Map.of(BEST, 0)).orElseThrow());
    }

    static void demoMergeStr() throws GraphStateException {
        System.out.println("\n" + "=".repeat(72));
        System.out.println("3) 字符串按行合并");
        System.out.println("=".repeat(72));
        final String LOG = "log";
        Map<String, Channel<?>> schema = Map.of(LOG, Channels.base(mergeLines(), () -> ""));
        var b = new StateGraph<>(schema, GenericState::new)
                .addNode("lg_a", node_async((NodeAction<GenericState>) s -> Map.of(LOG, "[A] 第一条")))
                .addNode("lg_b", node_async((NodeAction<GenericState>) s -> Map.of(LOG, "[B] 第二条")))
                .addNode("lg_c", node_async((NodeAction<GenericState>) s -> Map.of(LOG, "[C] 第三条")))
                .addNode("join", node_async((NodeAction<GenericState>) s -> {
                    String log = s.value(LOG).map(Object::toString).orElse("");
                    System.out.println("  [merge_lines] 合并后 log:\n    " + log.replace("\n", "\n    "));
                    return Map.of();
                }));
        b.addEdge(START, "lg_a").addEdge(START, "lg_b").addEdge(START, "lg_c");
        b.addEdge("lg_a", "join").addEdge("lg_b", "join").addEdge("lg_c", "join");
        b.addEdge("join", END);
        var g = b.compile();
        var out = g.invoke(Map.of(LOG, "")).orElseThrow();
        System.out.println("  最终 log 长度: " + out.value(LOG).map(Object::toString).orElse("").length());
    }

    static void demoTakeLastList() throws GraphStateException {
        System.out.println("\n" + "=".repeat(72));
        System.out.println("4) 列表只保留最后一次写入（并行顺序可能不稳定）");
        System.out.println("=".repeat(72));
        final String PAYLOAD = "payload";
        Map<String, Channel<?>> schema = Map.of(PAYLOAD, Channels.base(takeLastList(), ArrayList::new));
        var b = new StateGraph<>(schema, GenericState::new)
                .addNode("ll_a", node_async((NodeAction<GenericState>) s -> Map.of(PAYLOAD, List.of("branch-A"))))
                .addNode("ll_b", node_async((NodeAction<GenericState>) s -> Map.of(PAYLOAD, List.of("branch-B"))))
                .addNode("ll_c", node_async((NodeAction<GenericState>) s -> Map.of(PAYLOAD, List.of("branch-C"))))
                .addNode("join", node_async((NodeAction<GenericState>) s -> {
                    List<String> pl = (List<String>) s.value(PAYLOAD).orElse(List.of());
                    System.out.println("  [take_last_list] 最终 payload = " + pl);
                    return Map.of();
                }));
        b.addEdge(START, "ll_a").addEdge(START, "ll_b").addEdge(START, "ll_c");
        b.addEdge("ll_a", "join").addEdge("ll_b", "join").addEdge("ll_c", "join");
        b.addEdge("join", END);
        var g = b.compile();
        System.out.println("  最终: " + g.invoke(Map.of(PAYLOAD, new ArrayList<String>())).orElseThrow());
    }

    static void demoUniqueMerge() throws GraphStateException {
        System.out.println("\n" + "=".repeat(72));
        System.out.println("5) 去重拼接 reducer");
        System.out.println("=".repeat(72));
        final String IDS = "ids";
        Map<String, Channel<?>> schema = Map.of(IDS, Channels.base(mergeUniqueInOrder(), ArrayList::new));
        var b = new StateGraph<>(schema, GenericState::new)
                .addNode("uq_a", node_async((NodeAction<GenericState>) s -> Map.of(IDS, List.of("u1", "u2"))))
                .addNode("uq_b", node_async((NodeAction<GenericState>) s -> Map.of(IDS, List.of("u2", "u3"))))
                .addNode("uq_c", node_async((NodeAction<GenericState>) s -> Map.of(IDS, List.of("u1", "u4"))))
                .addNode("join", node_async((NodeAction<GenericState>) s -> {
                    List<String> ids = (List<String>) s.value(IDS).orElse(List.of());
                    System.out.println("  [merge_unique_in_order] ids = " + ids);
                    return Map.of();
                }));
        b.addEdge(START, "uq_a").addEdge(START, "uq_b").addEdge(START, "uq_c");
        b.addEdge("uq_a", "join").addEdge("uq_b", "join").addEdge("uq_c", "join");
        b.addEdge("join", END);
        var g = b.compile();
        System.out.println("  最终: " + g.invoke(Map.of(IDS, new ArrayList<String>())).orElseThrow());
    }

    public static void main(String[] args) throws GraphStateException {
        System.out.println(Lesson04dApp.class.getSimpleName() + " — 对照 04d_reducer_strategies.py");
        demoSetUnion();
        demoMaxInt();
        demoMergeStr();
        demoTakeLastList();
        demoUniqueMerge();
        System.out.println("\n小结：reducer = Channels.base(...) 的二元合并；join = 多上游 addEdge 到同一节点。");
    }
}
