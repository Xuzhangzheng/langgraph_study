package study.langgraph.lessons.l16_rag_langgraph_graph;

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

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;
import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;

/**
 * 第十六课：RAG + LangGraph 基础整合（对照 {@code 16_rag_langgraph_graph.py}）。
 * <p>
 * <b>本课学习目标（与 Python 文件头一致）：</b>
 * <ul>
 *   <li><b>流水线切分</b>：normalize（门禁）→ retrieve（粗排）→ 条件边（无命中则产品话术）→ rerank（启发式精排）→ generate（LLM 或模板）。</li>
 *   <li><b>可解释性</b>：{@link L16State#CITATIONS} 与 {@link L16State#CONTEXT_CHUNKS} 显式进状态，避免「黑盒答案」。</li>
 *   <li><b>LangGraph4j API</b>：{@link StateGraph#addConditionalEdges} 的 route 返回值必须命中 routes 字典的键；节点返回 {@code Map} 偏更新。</li>
 *   <li><b>LLM 提供方</b>：{@code LLM_PROVIDER=openai} 走 LangChain4j；{@code ark} 与第 6 课一致为 <b>占位</b>，真 Ark 以 Python + volcenginesdkarkruntime 为准。</li>
 *   <li><b>故障路径</b>：空查询、{@code FORCE_NO_HIT} 强制无结果，与 Python 一致。</li>
 * </ul>
 * <p>
 * Python 侧 {@code add_conditional_edges} 与完整 LLM 行为以 Python 脚本为准；本类默认 demo 使用 {@code mode=fallback}。
 */
public final class Lesson16App {

    private Lesson16App() {
    }

    private static final Logger LOG = Logger.getLogger(Lesson16App.class.getName());

    /**
     * 与 Python 脚本同参：控制召回数量、进入生成的证据条数、以及粗排噪声过滤阈值。
     * 调参影响延迟与答案质量，一般不随 LangGraph 版本变化。
     */
    private static final int RETRIEVAL_TOP_K = 5;
    private static final int RERANK_TOP_K = 3;
    private static final double MIN_HIT_SCORE = 0.12;

    /** 与 Python 正则等价的词元切分模式。 */
    private static final Pattern TOKEN_PATTERN = Pattern.compile("[\\u4e00-\\u9fff]|[a-z0-9]+");

    /**
     * 与 Python {@code KB_DOC_BLUEPRINT} 同源：内存知识库（生产可替换为向量检索服务 + metadata）。
     */
    static List<Map<String, String>> defaultKb() {
        return List.of(
                Map.of(
                        "doc_id", "kb-refund-001",
                        "title", "退款与履约规则",
                        "body", "订单签收后 7 日内可申请无理由退款；若商品已激活数字许可，则不支持退款。"
                                + "请在工作日 09:00-18:00 提交工单并附上订单号。",
                        "source", "help-center/policy"
                ),
                Map.of(
                        "doc_id", "kb-ship-002",
                        "title", "物流配送与时效",
                        "body", "标准快递江浙沪次日达，其他区域约 3～5 个工作日。"
                                + "大促期间时效可能顺延，物流单号在发货后 24 小时内更新。",
                        "source", "help-center/logistics"
                ),
                Map.of(
                        "doc_id", "kb-api-003",
                        "title", "开放平台速率限制",
                        "body", "默认租户 QPS 为 20，突发令牌桶容量 40。"
                                + "返回 HTTP 429 时请按 Retry-After 退避；我们建议在客户端做指数退避并上限封顶。",
                        "source", "developer/rate-limit"
                )
        );
    }

    /** 与 Python {@code _tokenize} 一致：中英混排简单切分，无第三方分词。 */
    static List<String> tokenize(String text) {
        String lower = text.toLowerCase();
        ArrayList<String> pieces = new ArrayList<>();
        Matcher m = TOKEN_PATTERN.matcher(lower);
        while (m.find()) {
            pieces.add(m.group());
        }
        return pieces;
    }

    /** 与 Python {@code round(s, 4)} 一致，避免浮点展示过长。 */
    static double round4(double v) {
        return Math.round(v * 10000.0) / 10000.0;
    }

    /**
     * 与 Python {@code _lexical_score} 一致：查询词与文档词元重叠率 + 标题命中奖励。
     *
     * @return 0～1，越大表示字面相关性越高（非语义向量分数）
     */
    static double lexicalScore(Set<String> queryTokens, String docTitle, String docBody) {
        if (queryTokens.isEmpty()) {
            return 0.0;
        }
        Set<String> blob = new HashSet<>(tokenize(docTitle + " " + docBody));
        Set<String> inter = new HashSet<>(queryTokens);
        inter.retainAll(blob);
        double base = inter.size() / (double) Math.max(queryTokens.size(), 1);
        Set<String> titleTok = new HashSet<>(tokenize(docTitle));
        Set<String> titleHits = new HashSet<>(queryTokens);
        titleHits.retainAll(titleTok);
        double bonus = 0.05 * Math.min(titleHits.size(), 3);
        return Math.min(1.0, base + bonus);
    }

    /**
     * {@code normalize_query} 之后的条件路由：invalid → 收口节点；否则进入检索。
     * 返回值必须与 {@code routesNorm} 中键一致，否则运行期路由失败。
     */
    static String routeAfterNormalize(L16State state) {
        if ("invalid".equals(state.queryGate())) {
            return "invalid";
        }
        return "retrieve";
    }

    /**
     * {@code retrieve_lexical} 之后的条件路由：无检索结果走无证据话术，避免空上下文调用生成。
     */
    static String routeAfterRetrieve(L16State state) {
        List<Map<String, Object>> chunks = state.retrievedChunks();
        if (chunks == null || chunks.isEmpty()) {
            return "no_evidence";
        }
        return "rerank";
    }

    /** 组装一条与 Python retrieve 输出同结构的 chunk，便于双端 JSON 对比。 */
    static Map<String, Object> packChunkRow(String docId, String title, String body, double score, String source) {
        HashMap<String, Object> row = new HashMap<>();
        row.put("doc_id", docId);
        row.put("title", title);
        row.put("body", body);
        row.put("score", score);
        row.put("source", source);
        return row;
    }

    /**
     * 构建与 Python 完全同构的 StateGraph：节点名、条件边键、状态字段常量均应对齐，便于对照调试。
     */
    static StateGraph<L16State> buildGraph() throws GraphStateException {
        List<Map<String, String>> kb = defaultKb();

        // conditional_edges(normalize_query)：键 → 下一节点名
        Map<String, String> routesNorm = Map.of(
                "retrieve", "retrieve_lexical",
                "invalid", "seal_invalid_query"
        );
        // conditional_edges(retrieve_lexical)
        Map<String, String> routesRet = Map.of(
                "rerank", "rerank_heuristic",
                "no_evidence", "seal_no_evidence_answer"
        );

        return new StateGraph<>(L16State.SCHEMA, L16State::new)
                // 节点 1：输入门禁——strip 后为空则 invalid，不写检索字段
                .addNode("normalize_query", node_async((NodeAction<L16State>) state -> {
                    String raw = state.userQuery() == null ? "" : state.userQuery().trim();
                    String rid = state.requestId();
                    if (raw.isEmpty()) {
                        LOG.info(() -> "[" + rid + "] normalize: empty → invalid");
                        return Map.of(
                                L16State.USER_QUERY, "",
                                L16State.QUERY_GATE, "invalid",
                                L16State.DIAGNOSTICS, List.of("normalize:invalid_empty")
                        );
                    }
                    LOG.info(() -> "[" + rid + "] normalize: ok");
                    return Map.of(
                            L16State.USER_QUERY, raw,
                            L16State.QUERY_GATE, "ok",
                            L16State.DIAGNOSTICS, List.of("normalize:ok")
                    );
                }))
                // 节点 2：粗排——FORCE_NO_HIT 用于测试无证据分支；否则对 KB 打分并阈值过滤
                .addNode("retrieve_lexical", node_async((NodeAction<L16State>) state -> {
                    String rid = state.requestId();
                    String q = state.userQuery();
                    if (q != null && q.contains("FORCE_NO_HIT")) {
                        LOG.warning(() -> "[" + rid + "] retrieve: forced empty");
                        return Map.of(
                                L16State.RETRIEVED_CHUNKS, new ArrayList<Map<String, Object>>(),
                                L16State.DIAGNOSTICS, List.of("retrieve:forced_empty")
                        );
                    }
                    Set<String> qTokens = new LinkedHashSet<>(tokenize(q == null ? "" : q));
                    ArrayList<Map<String, Object>> scored = new ArrayList<>();
                    for (Map<String, String> row : kb) {
                        double s = lexicalScore(qTokens, row.get("title"), row.get("body"));
                        scored.add(packChunkRow(
                                row.get("doc_id"),
                                row.get("title"),
                                row.get("body"),
                                round4(s),
                                row.get("source")));
                    }
                    scored.sort(Comparator.comparingDouble(m -> -((Number) m.get("score")).doubleValue()));
                    ArrayList<Map<String, Object>> top = new ArrayList<>();
                    for (int i = 0; i < Math.min(RETRIEVAL_TOP_K, scored.size()); i++) {
                        Map<String, Object> row = scored.get(i);
                        if (((Number) row.get("score")).doubleValue() >= MIN_HIT_SCORE) {
                            top.add(row);
                        }
                    }
                    LOG.info(() -> "[" + rid + "] retrieve: kept=" + top.size());
                    return Map.of(
                            L16State.RETRIEVED_CHUNKS, top,
                            L16State.DIAGNOSTICS, List.of("retrieve:raw_candidates=" + scored.size() + " kept=" + top.size())
                    );
                }))
                // 节点 3：启发式精排——标题命中加权后写入 context_chunks，供生成唯一消费
                .addNode("rerank_heuristic", node_async((NodeAction<L16State>) state -> {
                    String rid = state.requestId();
                    Set<String> qTokens = new LinkedHashSet<>(tokenize(state.userQuery()));
                    List<Map<String, Object>> items = new ArrayList<>(state.retrievedChunks());
                    ArrayList<Map<String, Object>> reranked = new ArrayList<>();
                    for (Map<String, Object> it : items) {
                        Set<String> titleTokens = new HashSet<>(tokenize(String.valueOf(it.getOrDefault("title", ""))));
                        Set<String> inter = new HashSet<>(qTokens);
                        inter.retainAll(titleTokens);
                        double titleBoost = inter.isEmpty() ? 1.0 : 1.15;
                        HashMap<String, Object> row = new HashMap<>(it);
                        double newScore = round4(((Number) it.get("score")).doubleValue() * titleBoost);
                        row.put("score", newScore);
                        row.put("rerank_note", titleBoost > 1.0 ? "title_boost" : "as_is");
                        reranked.add(row);
                    }
                    reranked.sort(Comparator.comparingDouble(m -> -((Number) m.get("score")).doubleValue()));
                    ArrayList<Map<String, Object>> ctx = new ArrayList<>(reranked.subList(0, Math.min(RERANK_TOP_K, reranked.size())));
                    LOG.info(() -> "[" + rid + "] rerank: n=" + ctx.size());
                    return Map.of(
                            L16State.CONTEXT_CHUNKS, ctx,
                            L16State.DIAGNOSTICS, List.of("rerank:selected=" + ctx.size())
                    );
                }))
                // 节点 4：生成——可选 LangChain4j OpenAI；失败或未配置则模板归纳，并始终带 citations
                .addNode("generate_with_evidence", node_async((NodeAction<L16State>) state -> {
                    String rid = state.requestId();
                    String mode = state.mode();
                    List<Map<String, Object>> chunks = state.contextChunks();
                    ArrayList<String> citeLines = new ArrayList<>();
                    StringBuilder ctxBlock = new StringBuilder();
                    for (int i = 0; i < chunks.size(); i++) {
                        Map<String, Object> ch = chunks.get(i);
                        int n = i + 1;
                        // 拼证据块：序号与 doc_id 供模型引用、供 citations 审计
                        String did = String.valueOf(ch.getOrDefault("doc_id", ""));
                        String title = String.valueOf(ch.getOrDefault("title", ""));
                        String body = String.valueOf(ch.getOrDefault("body", ""));
                        String src = String.valueOf(ch.getOrDefault("source", ""));
                        ctxBlock.append("[").append(n).append("] (").append(did).append(") ").append(title)
                                .append("\n来源:").append(src).append("\n").append(body).append("\n\n");
                        citeLines.add(String.format("[%d] %s [%s] score=%s",
                                n, did, title, ch.get("score")));
                    }
                    String system = "你是企业知识库问答助手。只根据用户消息后面提供的「证据块」回答；"
                            + "不得编造证据中不存在的政策数字。若证据不足请明确说明缺口。";
                    String human = "用户问题：" + state.userQuery() + "\n\n证据块（内部材料）：\n" + ctxBlock
                            + "\n请用中文：先给结论，再列 2～4 条要点，必要时指出引用序号。";

                    if ("llm".equals(mode)) {
                        String llmProvider = CourseEnv.get("LLM_PROVIDER", "openai").toLowerCase();
                        // 与第 6 课一致：Java 示例对 Ark 使用占位输出；真 Ark 调用以 Python 16（volcenginesdkarkruntime）为准。
                        if ("ark".equals(llmProvider)) {
                            String apiKey = CourseEnv.get("ARK_API_KEY", "");
                            String baseUrl = CourseEnv.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3");
                            String arkModel = CourseEnv.get("ARK_MODEL", "");
                            if (!apiKey.isBlank() && !baseUrl.isBlank() && !arkModel.isBlank()) {
                                String stub = "【Java RAG-Ark 占位】与 Lesson06 CallArkNode 同源；请用 Python 16 + ARK_* 环境变量做真实对话。\n"
                                        + "model=" + arkModel + "\n证据摘要前 80 字："
                                        + human.substring(0, Math.min(80, human.length()))
                                        + (human.length() > 80 ? "…" : "");
                                LOG.info(() -> "[" + rid + "] generate: ark stub");
                                return Map.of(
                                        L16State.ANSWER, stub,
                                        L16State.CITATIONS, new ArrayList<>(citeLines),
                                        L16State.DIAGNOSTICS, List.of("generate:llm_ok_ark_stub")
                                );
                            }
                            LOG.warning(() -> "[" + rid + "] generate: ark skipped (env)");
                        } else {
                            String apiKey = CourseEnv.get("OPENAI_API_KEY", "");
                            String baseUrl = CourseEnv.get("OPENAI_BASE_URL", "https://api.openai.com/v1");
                            String model = CourseEnv.get("OPENAI_MODEL", "gpt-4o-mini");
                            if (!apiKey.isBlank() && !baseUrl.isBlank() && !model.isBlank()) {
                                try {
                                    ChatLanguageModel llm = OpenAiChatModel.builder()
                                            .apiKey(apiKey)
                                            .baseUrl(baseUrl)
                                            .modelName(model)
                                            .temperature(0.2)
                                            .build();
                                    Response<AiMessage> resp = llm.generate(
                                            SystemMessage.from(system),
                                            UserMessage.from(human)
                                    );
                                    String text = resp.content().text().trim();
                                    LOG.info(() -> "[" + rid + "] generate: llm ok");
                                    return Map.of(
                                            L16State.ANSWER, text,
                                            L16State.CITATIONS, new ArrayList<>(citeLines),
                                            L16State.DIAGNOSTICS, List.of("generate:llm_ok")
                                    );
                                } catch (Exception e) {
                                    LOG.log(Level.WARNING, "[" + rid + "] generate: llm fail → fallback", e);
                                }
                            } else {
                                LOG.warning(() -> "[" + rid + "] generate: llm skipped (env)");
                            }
                        }
                    }

                    Map<String, Object> head = chunks.isEmpty() ? Map.of() : chunks.get(0);
                    String headBody = String.valueOf(head.getOrDefault("body", ""));
                    String trunc = headBody.length() > 180 ? headBody.substring(0, 180) + "…" : headBody;
                    String summary = "根据知识片段「" + head.getOrDefault("title", "无标题") + "」：" + trunc;
                    String fallback = "【模板归纳】" + summary + "\n（Java demo：mode=fallback 或 LLM 未配置。）";
                    return Map.of(
                            L16State.ANSWER, fallback,
                            L16State.CITATIONS, new ArrayList<>(citeLines),
                            L16State.DIAGNOSTICS, List.of("generate:fallback_template")
                    );
                }))
                // 节点 5/6：异常或空结果收口——固定文案，不产生伪造引用
                .addNode("seal_no_evidence_answer", node_async((NodeAction<L16State>) state -> Map.of(
                        L16State.ANSWER, "【无匹配知识】当前知识库未检索到与您问题足够相关的条目。"
                                + "建议换一种描述、提供订单号或联系人工客服。",
                        L16State.CITATIONS, new ArrayList<String>(),
                        L16State.DIAGNOSTICS, List.of("seal:no_evidence")
                )))
                .addNode("seal_invalid_query", node_async((NodeAction<L16State>) state -> Map.of(
                        L16State.ANSWER, "【输入无效】请先输入有效的问题内容。",
                        L16State.CITATIONS, new ArrayList<String>(),
                        L16State.DIAGNOSTICS, List.of("seal:invalid_query")
                )))
                .addEdge(START, "normalize_query")
                .addConditionalEdges("normalize_query", edge_async(Lesson16App::routeAfterNormalize), routesNorm)
                .addConditionalEdges("retrieve_lexical", edge_async(Lesson16App::routeAfterRetrieve), routesRet)
                // 主路径线性段：rerank → generate → END
                .addEdge("rerank_heuristic", "generate_with_evidence")
                .addEdge("generate_with_evidence", END)
                .addEdge("seal_no_evidence_answer", END)
                .addEdge("seal_invalid_query", END);
    }

    /**
     * 单次 invoke 演示：构造完整初始 Map（含空列表占位），打印终态关键字段。
     */
    static void invokeCase(org.bsc.langgraph4j.CompiledGraph<L16State> g, String label, String rid, String query, String mode)
            throws GraphStateException {
        HashMap<String, Object> init = new HashMap<>();
        init.put(L16State.REQUEST_ID, rid);
        init.put(L16State.USER_QUERY, query);
        init.put(L16State.MODE, mode);
        init.put(L16State.QUERY_GATE, "pending");
        init.put(L16State.RETRIEVED_CHUNKS, new ArrayList<>());
        init.put(L16State.CONTEXT_CHUNKS, new ArrayList<>());
        init.put(L16State.ANSWER, "");
        init.put(L16State.CITATIONS, new ArrayList<String>());
        init.put(L16State.DIAGNOSTICS, new ArrayList<String>());

        System.out.println("\n" + "=".repeat(72));
        System.out.println(label);
        System.out.println("=".repeat(72));

        L16State end = g.invoke(init).orElseThrow();
        System.out.println("answer:\n" + end.answer());
        System.out.println("citations: " + end.citations());
        System.out.println("diagnostics: " + end.diagnostics());
        if (!end.retrievedChunks().isEmpty()) {
            System.out.println("retrieved: " + end.retrievedChunks().stream()
                    .map(m -> m.get("doc_id") + "=" + m.get("score"))
                    .toList());
        }
    }

    /**
     * 程序入口：编译图并跑与 Python demo 对称的四组用例（主路径 / 限流 / 无命中 / 空查询）。
     */
    public static void main(String[] args) throws GraphStateException {
        Logger root = Logger.getLogger("");
        root.setLevel(Level.INFO);
        for (var h : root.getHandlers()) {
            h.setLevel(Level.INFO);
        }

        System.out.println("=".repeat(72));
        System.out.println("第十六课：RAG + LangGraph（LangGraph4j）");
        System.out.println("=".repeat(72));
        System.out.println("对照 Python：retrieve_lexical → rerank_heuristic → generate_with_evidence；分支见条件边。");

        var compiled = buildGraph().compile();

        invokeCase(compiled, "主路径：退款", "java-happy-refund", "申请退款需要满足什么条件？", "fallback");
        invokeCase(compiled, "主路径：速率限制", "java-happy-rate", "接口限速429的话客户端要怎么退避？", "fallback");
        invokeCase(compiled, "Failure：FORCE_NO_HIT", "java-nohit", "FORCE_NO_HIT 今天天气", "fallback");
        invokeCase(compiled, "Failure：空查询", "java-invalid", "   ", "fallback");
    }
}
