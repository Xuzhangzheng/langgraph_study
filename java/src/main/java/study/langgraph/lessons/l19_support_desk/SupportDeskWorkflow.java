package study.langgraph.lessons.l19_support_desk;

import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;

import java.util.Map;

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 仅负责图装配；节点逻辑在 {@link SupportDeskNodes}，路由在 {@link L19Routing}。
 */
public final class SupportDeskWorkflow {

    private SupportDeskWorkflow() {
    }

    public static StateGraph<L19State> build() throws GraphStateException {
        Map<String, String> routesIngest = Map.of("ok", "classify_intent", "invalid", "finalize_reply");
        Map<String, String> routesClass = Map.of(
                "tool_calculator", "tool_calculator",
                "tool_time", "tool_time",
                "generate_reply", "generate_reply"
        );
        Map<String, String> routesEval = Map.of("retry_generate", "generate_reply", "finalize_reply", "finalize_reply");

        return new StateGraph<>(L19State.SCHEMA, L19State::new)
                .addNode("ingest", node_async((org.bsc.langgraph4j.action.NodeAction<L19State>) SupportDeskNodes::ingest))
                .addNode("classify_intent", node_async((org.bsc.langgraph4j.action.NodeAction<L19State>) SupportDeskNodes::classify))
                .addNode("tool_calculator", node_async((org.bsc.langgraph4j.action.NodeAction<L19State>) SupportDeskNodes::toolCalculator))
                .addNode("tool_time", node_async((org.bsc.langgraph4j.action.NodeAction<L19State>) SupportDeskNodes::toolTime))
                .addNode("generate_reply", node_async((org.bsc.langgraph4j.action.NodeAction<L19State>) SupportDeskNodes::generate))
                .addNode("evaluate_reply", node_async((org.bsc.langgraph4j.action.NodeAction<L19State>) SupportDeskNodes::evaluate))
                .addNode("finalize_reply", node_async((org.bsc.langgraph4j.action.NodeAction<L19State>) SupportDeskNodes::finalize))
                .addEdge(START, "ingest")
                .addConditionalEdges("ingest", edge_async(L19Routing::routeAfterIngest), routesIngest)
                .addConditionalEdges("classify_intent", edge_async(L19Routing::routeAfterClassify), routesClass)
                .addEdge("tool_calculator", "finalize_reply")
                .addEdge("tool_time", "finalize_reply")
                .addEdge("generate_reply", "evaluate_reply")
                .addConditionalEdges("evaluate_reply", edge_async(L19Routing::routeAfterEvaluate), routesEval)
                .addEdge("finalize_reply", END);
    }
}
