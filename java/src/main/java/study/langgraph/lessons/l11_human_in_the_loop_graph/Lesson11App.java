package study.langgraph.lessons.l11_human_in_the_loop_graph;

import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.NodeAction;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第十一课：人机协同拓扑（对照 {@code 11_human_in_the_loop_graph.py}）。
 * <p>
 * <strong>与 Python 的差异</strong>：Python 使用官方 {@code interrupt()} + {@code Command(resume)}
 * 与 {@code InMemorySaver}，挂起时状态由 LangGraph 接管。LangGraph4j 本仓库所用 {@link StateGraph}
 * 课程示例中未接入同等 {@code interrupt} API，此处用 {@linkplain #HUMAN_QUEUE 阻塞队列}
 * 在 {@code human_review} 节点内模拟「等待外部传入决策」——同一时间线内连续 {@code take()}，
 * 由 {@link #main} 在单次 {@code invoke} 前按顺序 {@code offer}，以演示<strong>同构图与分支/回流</strong>。
 * 生产级 HITL 请以 Python 侧或引擎扩展为准。
 */
public final class Lesson11App {

    private Lesson11App() {
    }

    /** 教学用：main 预先放入多个人工决策，供单次 {@code invoke} 内多轮「送审」消耗。 */
    public static final BlockingQueue<Map<String, Object>> HUMAN_QUEUE = new LinkedBlockingQueue<>();

    static StateGraph<L11State> buildGraph() throws GraphStateException {
        Map<String, String> afterHuman = new HashMap<>();
        afterHuman.put("continue_flow", "continue_flow");
        afterHuman.put("agent_step", "agent_step");
        afterHuman.put("end_rejected", "end_rejected");

        return new StateGraph<>(L11State.SCHEMA, L11State::new)
                .addNode("agent_step", node_async(agentStep()))
                .addNode("human_review", node_async(humanReview()))
                .addNode("continue_flow", node_async(continueFlow()))
                .addNode("end_rejected", node_async(endRejected()))
                .addEdge(START, "agent_step")
                .addEdge("agent_step", "human_review")
                .addConditionalEdges(
                        "human_review",
                        edge_async(state -> {
                            String d = state.humanDecision().toLowerCase();
                            if ("approved".equals(d)) {
                                return "continue_flow";
                            }
                            if ("edit".equals(d)) {
                                return "agent_step";
                            }
                            return "end_rejected";
                        }),
                        afterHuman
                )
                .addEdge("continue_flow", END)
                .addEdge("end_rejected", END);
    }

    static NodeAction<L11State> agentStep() {
        return state -> {
            int n = state.revisionCount() + 1;
            String topic = state.topic();
            String prev = state.proposal().trim();
            String body = prev.isEmpty()
                    ? "自动生成的首版要点（topic=" + topic + "）"
                    : prev;
            String text = "[修订 " + n + "] " + body;
            System.out.println("  [agent_step] -> " + (text.length() > 72 ? text.substring(0, 72) + "…" : text));
            return Map.of(
                    L11State.REVISION_COUNT, n,
                    L11State.PROPOSAL, text
            );
        };
    }

    static NodeAction<L11State> humanReview() {
        return state -> {
            System.out.println("  [human_review] 等待人工决策（队列模拟）…");
            Map<String, Object> raw;
            try {
                raw = HUMAN_QUEUE.take();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return Map.of(L11State.HUMAN_DECISION, "rejected");
            }
            Object decObj = raw.get("decision");
            String decision = decObj != null ? decObj.toString().trim().toLowerCase() : "rejected";
            if ("true".equalsIgnoreCase(decision)) {
                decision = "approved";
            }
            if ("false".equalsIgnoreCase(decision)) {
                decision = "rejected";
            }
            Map<String, Object> out = new HashMap<>();
            out.put(L11State.HUMAN_DECISION, decision);
            if ("edit".equals(decision)) {
                Object edited = raw.get("edited_proposal");
                String prop = edited != null ? edited.toString() : state.proposal();
                out.put(L11State.PROPOSAL, prop);
                System.out.println("  [human_review] 人工要求修改，已写回 proposal（len=" + prop.length() + "）");
            } else {
                System.out.println("  [human_review] 人工决策：" + decision);
            }
            return out;
        };
    }

    static NodeAction<L11State> continueFlow() {
        return state -> {
            System.out.println("  [continue_flow] 审批通过，写入 final_output");
            return Map.of(L11State.FINAL_OUTPUT, state.proposal());
        };
    }

    static NodeAction<L11State> endRejected() {
        return state -> {
            System.out.println("  [end_rejected] 已驳回");
            String prop = state.proposal();
            String note = "驳回（草案摘要）：" + prop.substring(0, Math.min(80, prop.length()));
            return Map.of(L11State.FINAL_OUTPUT, note);
        };
    }

    static Map<String, Object> initialState(String topic) {
        Map<String, Object> m = new HashMap<>();
        m.put(L11State.TOPIC, topic);
        m.put(L11State.PROPOSAL, "");
        m.put(L11State.REVISION_COUNT, 0);
        m.put(L11State.HUMAN_DECISION, "");
        m.put(L11State.FINAL_OUTPUT, "");
        return m;
    }

    public static void main(String[] args) throws GraphStateException {
        var compiled = buildGraph().compile();

        System.out.println("=".repeat(72));
        System.out.println("1) edit 再 approved（队列先入两条，再一次 invoke）");
        System.out.println("=".repeat(72));
        HUMAN_QUEUE.clear();
        HUMAN_QUEUE.offer(Map.of(
                "decision", "edit",
                "edited_proposal", "【人工】加强审计日志保留期说明"
        ));
        HUMAN_QUEUE.offer(Map.of("decision", "approved"));
        var fin = compiled.invoke(initialState("上线前风控策略变更")).orElseThrow();
        if (fin instanceof L11State) {
            L11State s = (L11State) fin;
            String o = s.finalOutput();
            System.out.println("\n终态 final_output 前 200 字：");
            System.out.println(o.length() > 200 ? o.substring(0, 200) + "…" : o);
        }

        System.out.println("\n" + "=".repeat(72));
        System.out.println("2) rejected");
        System.out.println("=".repeat(72));
        HUMAN_QUEUE.clear();
        HUMAN_QUEUE.offer(Map.of("decision", "rejected"));
        var rej = compiled.invoke(initialState("被拒演示 topic")).orElseThrow();
        if (rej instanceof L11State) {
            System.out.println(((L11State) rej).finalOutput());
        }
    }
}
