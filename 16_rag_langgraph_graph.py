"""
第十六课：RAG + LangGraph 基础整合（检索 → 重排 → 生成）

与前序课关系：
--------------
- 第 5～8 课：工具与多工具路由；本课把「外部知识」看成一类特殊资源，通过 **检索节点** 拉入上下文。
- 第 6～7 课：LLM 与消息；本课在 **生成节点** 把检索片段组装成可追溯的上下文块（工程上常叫 context packing）。
- 第 13～14 课：可观测与容错；本课在节点内对 **空库 / 无命中 / 非法查询** 走显式分支，避免把错误答案伪装成「有据」。

本节要点（思想、问题拆解、API）：
----------------------------------
1. **RAG 流水线在图上的切分（工程心智模型）**
   - **Retrieve**：从文档库（本课为内存 KB；生产可换向量库 + Hybrid Search）取候选片段。
   - **Rerank**：用更强但更贵的信号（本课用启发式：标题命中加权；生产可接交叉编码器 / 精排服务）。
   - **Generate**：只允许使用 `context_chunks` 中给出的可见证据回答，并输出 **可解释引用**（cite）。
   - 分成节点的好处：可独立限流、缓存、替换实现，以及 **对无命中单独产品策略**（免责声明、引导转人工）。

2. **LangGraph API（`langgraph==1.1.10`）**
   - `StateGraph(RagState)`：`TypedDict` 描述跨节点状态；列表型 **审计字段** 仍用 `Annotated[list, operator.add]` 做追加合并（与第 10、14 课一致思路）。
   - `add_node` / `add_edge` / `add_conditional_edges`：
     - 条件边函数签名：**`(state: RagState) -> str`**，返回值必须是 `routes` 字典里存在的 **键**。
   - `compile()` 得到 `CompiledGraph`，对外仍主要是 **`invoke(initial_state)`**；`get_graph().draw_mermaid_png()` 导出拓扑（与前几课一致）。

3. **状态中建议显式携带的「可观测字段」（本课 DoD）**
   - `retrieved_chunks`：粗排结果（含 `score` / `doc_id`）。
   - `context_chunks`：重排后进入生成的子集（字段名即 **接口契约** 的一部分）。
   - `citations`：给人读的引用行，便于客服 / 合规审计。

4. **Failure / 边界路径（教学中必跑）**
   - 空查询 → `normalize_query` 走 **invalid** 支路。
   - 查询包含 **`FORCE_NO_HIT`** → 模拟「库有文档但策略强制无命中」，走 **无证据** 应答。
   - 正常查询 → 有命中 → `rerank_heuristic` → `generate_with_evidence`。
   - `mode=llm` 时：读环境变量 **`LLM_PROVIDER`**（与第 6 课一致）——`openai` 走延迟导入的 `langchain_openai`；**`ark`** 走 **`volcenginesdkarkruntime`**，将 system/human 拼成单段 `input` 调用 `client.responses.create`；未安装依赖或未配置 Key 则 **fallback** 模板。

5. **本课刻意不引入额外 Python 依赖（生成层除外）**
   - 检索为重写的轻量 **词元重叠** 打分；**生成层**若走 `ark` / `openai` 分别依赖仓库已锁定的 **`volcengine-python-sdk[ark]`** / **`langchain-openai`**（与第 6 课一致，便于对照）。

主路径 / 分支拓扑：
------------------
START → normalize_query ──route_after_normalize──→ retrieve_lexical ──route_after_retrieve──→ rerank_heuristic → generate_with_evidence → END
                          │                                                      └→ seal_no_evidence_answer → END
                          └→ seal_invalid_query → END

最小回归：
----------
`python 16_rag_langgraph_graph.py`

接口不变清单（本课 DoD）：
-------------------------
- 状态键：`request_id`, `user_query`, `mode`, `query_gate`, `retrieved_chunks`, `context_chunks`,
  `answer`, `citations`, `diagnostics`
- `query_gate`：`pending` | `ok` | `invalid`
- `mode`：`llm` | `fallback`
"""

from __future__ import annotations

import json
import logging
from math import log
import operator
import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

_LOG = logging.getLogger("lesson16.rag")

# ---------------------------------------------------------------------------
# 一、状态契约（「接口不变」）
# 作用：LangGraph 在节点之间只传递这一块状态；字段名一旦作为 API/评测契约，改名即为破坏性变更。
# ---------------------------------------------------------------------------

QueryGate = Literal["pending", "ok", "invalid"]
RunMode = Literal["llm", "fallback"]


class RagState(TypedDict):
    """
    RAG 主图状态。

    - user_query：normalize 后用于检索；初始 invoke 可与对外 API 的 raw 字段分离（本课合并教学）。
    - retrieved_chunks / context_chunks：dict 列表，单条含 doc_id、title、body、score、source（序列化友好）。
    """

    request_id: str
    user_query: str
    mode: RunMode
    query_gate: QueryGate
    retrieved_chunks: list[dict[str, Any]]
    context_chunks: list[dict[str, Any]]
    answer: str
    citations: list[str]
    # 多节点可各自追加一条字符串；Annotated + operator.add 与 LangGraph 的 reducer 约定一致，避免后写覆盖前写。
    diagnostics: Annotated[list[str], operator.add]


# ---------------------------------------------------------------------------
# 二、知识库与检索打分（无向量库依赖）
# 作用：用最小可复现代码演示「查询 → 文档得分」；生产可整块替换为 embedding 检索 + BM25 混合，图上节点名可保持不变。
# ---------------------------------------------------------------------------

# 演示用静态知识条：生产环境中通常来自 CMS/工单系统/向量库 metadata；此处硬编码仅便于对照 Python/Java 行为。
KB_DOC_BLUEPRINT: list[dict[str, str]] = [
    {
        "doc_id": "kb-refund-001",
        "title": "退款与履约规则",
        "body": (
            "订单签收后 7 日内可申请无理由退款；若商品已激活数字许可，则不支持退款。"
            "请在工作日 09:00-18:00 提交工单并附上订单号。"
        ),
        "source": "help-center/policy",
    },
    {
        "doc_id": "kb-ship-002",
        "title": "物流配送与时效",
        "body": (
            "标准快递江浙沪次日达，其他区域约 3～5 个工作日。"
            "大促期间时效可能顺延，物流单号在发货后 24 小时内更新。"
        ),
        "source": "help-center/logistics",
    },
    {
        "doc_id": "kb-api-003",
        "title": "开放平台速率限制",
        "body": (
            "默认租户 QPS 为 20，突发令牌桶容量 40。"
            "返回 HTTP 429 时请按 Retry-After 退避；我们建议在客户端做指数退避并上限封顶。"
        ),
        "source": "developer/rate-limit",
    },
]


def _tokenize(text: str) -> list[str]:
    """
    将用户查询与文档正文转为「词元」列表，供重叠率打分。

    中英混排简单切分：单字中文 + 连续 alnum 英文/数字；不依赖 jieba 等，方便单文件阅读与 CI 离线。
    """
    lowered = text.lower()
    pieces: list[str] = []
    for m in re.finditer(r"[\u4e00-\u9fff]|[a-z0-9]+", lowered):
        pieces.append(m.group(0))
    return pieces


def _lexical_score(query_tokens: set[str], doc_title: str, doc_body: str) -> float:
    """
    粗排分数：查询词元在「标题+正文」中的命中比例，标题额外加权。

    非 BM25/向量相似度，仅用于教学；数值越大表示与用户问题字面越相关。
    """
    if not query_tokens:
        return 0.0
    blob_tokens = set(_tokenize(doc_title + " " + doc_body))
    inter = query_tokens & blob_tokens
    base = len(inter) / max(len(query_tokens), 1)
    title_hits = query_tokens & set(_tokenize(doc_title))
    bonus = 0.05 * min(len(title_hits), 3)
    return float(min(1.0, base + bonus))


# 粗排最多保留条数；过大会增加 rerank/LLM 成本。
RETRIEVAL_TOP_K = 5
# 进入生成节点的证据条数上限；与 prompt 长度、费用直接相关。
RERANK_TOP_K = 3
# 低于此分的文档视为「不相关」，过滤掉以免噪声进上下文（可按业务调参）。
MIN_HIT_SCORE = 0.12


# ---------------------------------------------------------------------------
# 三、图节点函数（每个函数 = 图上一个步骤；返回 dict 会与状态 merge）
# ---------------------------------------------------------------------------


def normalize_query(state: RagState) -> dict[str, Any]:
    """
    输入清洗与合法性门禁：strip 后若为空，将 query_gate 置 invalid。

    作用：避免空字符串仍去打分、浪费下游；与「无命中」分支区分开（invalid 是用户输入问题）。
    """
    raw = (state.get("user_query") or "").strip()
    rid = state.get("request_id") or ""
    if not raw:
        _LOG.info("[%s] normalize: empty query → invalid", rid)
        return {
            "user_query": "",
            "query_gate": "invalid",
            "diagnostics": ["normalize:invalid_empty"],
        }
    _LOG.info("[%s] normalize: ok len=%s", rid, len(raw))
    return {
        "user_query": raw,
        "query_gate": "ok",
        "diagnostics": ["normalize:ok"],
    }


def route_after_normalize(state: RagState) -> str:
    """
    根据 query_gate 决定下一节点；返回值须与 build_rag_graph 里 routes 字典的键完全一致。

    LangGraph：`add_conditional_edges(..., {"retrieve": "retrieve_lexical", "invalid": "..."})`
    """
    if state.get("query_gate") == "invalid":
        return "invalid"
    return "retrieve"


def retrieve_lexical(state: RagState) -> dict[str, Any]:
    """
    粗排检索：对 KB 每篇文档算分，按分排序，取前 RETRIEVAL_TOP_K 且分数 ≥ MIN_HIT_SCORE 写入 retrieved_chunks。

    全量扫内存仅适合演示；线上应换倒排/向量 ANN。FORCE_NO_HIT 用于集成测试「无证据」产品话术，不写假检索结果。
    """
    rid = state.get("request_id", "")
    q = state.get("user_query", "")
    if "FORCE_NO_HIT" in q:
        _LOG.warning("[%s] retrieve: forced no hit", rid)
        return {
            "retrieved_chunks": [],
            "diagnostics": ["retrieve:forced_empty"],
        }

    q_tokens = set(_tokenize(q))
    scored: list[dict[str, Any]] = []
    # 对每篇文档算相关分并压平为可序列化结构（便于日志、后续换 RPC 检索服务时字段对齐）。
    for row in KB_DOC_BLUEPRINT:
        s = _lexical_score(q_tokens, row["title"], row["body"])
        scored.append(
            {
                "doc_id": row["doc_id"],
                "title": row["title"],
                "body": row["body"],
                "score": round(s, 4),
                "source": row["source"],
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    # 截断 + 阈值：弱相关文档不进入 rerank，减少误导 LLM 的风险。
    top = [x for x in scored[:RETRIEVAL_TOP_K] if x["score"] >= MIN_HIT_SCORE]
    _LOG.info("[%s] retrieve: kept=%s top_score=%s", rid, len(top), top[0]["score"] if top else 0)
    return {
        "retrieved_chunks": top,
        "diagnostics": [f"retrieve:raw_candidates={len(scored)} kept={len(top)}"],
    }


def route_after_retrieve(state: RagState) -> str:
    """retrieved_chunks 为空 → 无证据收口；否则进入 rerank_heuristic（精排/截断后再生成）。"""
    chunks = state.get("retrieved_chunks") or []
    if not chunks:
        return "no_evidence"
    return "rerank"


def rerank_heuristic(state: RagState) -> dict[str, Any]:
    """
    启发式重排：若查询词元出现在文档标题，则放大 score，再排序取前 RERANK_TOP_K 写入 context_chunks。

    作用：模拟「粗排召回多、精排挑最贴」；cross-encoder 等远程服务可替换本函数内部逻辑，对外仍只写 context_chunks。
    """
    rid = state.get("request_id", "")
    q_tokens = set(_tokenize(state.get("user_query", "")))
    items = list(state.get("retrieved_chunks") or [])
    reranked: list[dict[str, Any]] = []
    for it in items:
        title_tokens = set(_tokenize(str(it.get("title", ""))))
        title_boost = 1.15 if q_tokens & title_tokens else 1.0
        new_score = round(float(it.get("score", 0.0)) * title_boost, 4)
        row = dict(it)
        row["score"] = new_score
        row["rerank_note"] = "title_boost" if title_boost > 1.0 else "as_is"
        reranked.append(row)
    reranked.sort(key=lambda x: x["score"], reverse=True)
    ctx = reranked[:RERANK_TOP_K]
    _LOG.info("[%s] rerank: context_chunks=%s", rid, len(ctx))
    return {
        "context_chunks": ctx,
        "diagnostics": [f"rerank:selected={len(ctx)}"],
    }


def _get_llm_config_for_rag() -> tuple[str, str, str, str]:
    """
    读取 LLM 配置；与第 6 课 `get_llm_config` 保持一致，便于同一套 `.env` 跑通 RAG + 单纯 LLM 课。

    Returns:
        (provider, api_key, base_url, model)，其中 provider 为 ``openai`` 或 ``ark``。
    """
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider == "ark":
        api_key = os.getenv("ARK_API_KEY", "").strip()
        base_url = os.getenv(
            "ARK_BASE_URL",
            "https://ark.cn-beijing.volces.com/api/v3",
        ).strip()
        model = os.getenv("ARK_MODEL", "").strip()
    else:
        provider = "openai"
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    return provider, api_key, base_url, model


def _build_ark_rag_input(system: str, human: str) -> str:
    """Ark `responses.create` 仅需一个 input 字符串；结构对齐第 6 课 `build_ark_input_text`。"""
    _LOG.info("build_ark_rag_input: system=%s human=%s", system, human)
    return (
        "【系统要求】\n"
        f"{system}\n"
        "【用户任务】\n"
        f"{human}"
    )


def _call_ark_rag_llm(system: str, human: str, api_key: str, base_url: str, model: str) -> str:
    """与第 6 课 `call_ark_llm` 同源：火山方舟官方 SDK（延迟导入）。"""
    from volcenginesdkarkruntime import Ark

    client = Ark(base_url=base_url, api_key=api_key)
    response = client.responses.create(
        model=model,
        input=_build_ark_rag_input(system, human),
    )
    output_text = getattr(response, "output_text", "")
    if output_text:
        return str(output_text).strip()
    output_obj = getattr(response, "output", None)
    maybe_text = getattr(output_obj, "text", "") if output_obj is not None else ""
    if maybe_text:
        return str(maybe_text).strip()
    return str(response)


def _pack_context_block(chunks: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """
    将 context_chunks 拼成一段「证据块」字符串（喂给 LLM 或 echo 到模板），并生成 citations 列表。

    作用：统一 LLM 与 fallback 的上下文格式，引用行便于截图审计、前端展示来源。
    """
    lines: list[str] = []
    cites: list[str] = []
    for i, ch in enumerate(chunks, start=1):
        did = ch.get("doc_id", "")
        title = ch.get("title", "")
        body = ch.get("body", "")
        src = ch.get("source", "")
        lines.append(f"[{i}] ({did}) {title}\n来源:{src}\n{body}")
        # 引用行避免 « » 等字符：在 Windows GBK 控制台打印 demo 时会编码失败
        cites.append(f"[{i}] {did} [{title}] score={ch.get('score')}")
    return "\n\n".join(lines), cites


def generate_with_evidence(state: RagState) -> dict[str, Any]:
    """
    基于 context_chunks 生成最终 answer。

    ``mode=llm`` 时：按环境变量 ``LLM_PROVIDER`` 选择 **openai**（ChatOpenAI）或 **ark**（与第 6 课相同的 Ark SDK）；
    失败或未配置则走模板兜底。
    """
    rid = state.get("request_id", "")
    mode = state.get("mode", "fallback")
    chunks = state.get("context_chunks") or []
    ctx_block, cite_lines = _pack_context_block(chunks)

    system = (
        "你是企业知识库问答助手。只根据用户消息后面提供的「证据块」回答；"
        "不得编造证据中不存在的政策数字。若证据不足请明确说明缺口。"
    )
    human = (
        f"用户问题：{state.get('user_query', '')}\n\n"
        f"证据块（内部材料）：\n{ctx_block}\n\n"
        "请用中文：先给结论，再列 2～4 条要点，必要时指出引用序号。"
    )

    if mode == "llm":
        load_dotenv()
        provider, api_key, base_url, model = _get_llm_config_for_rag()
        if api_key and base_url and model:
            try:
                if provider == "ark":
                    text = _call_ark_rag_llm(system, human, api_key, base_url, model)
                else:
                    from langchain_core.messages import HumanMessage, SystemMessage
                    from langchain_openai import ChatOpenAI

                    llm = ChatOpenAI(model=model, temperature=0.2, api_key=api_key, base_url=base_url)
                    out = llm.invoke(
                        [SystemMessage(content=system), HumanMessage(content=human)],
                    )
                    text = str(out.content).strip()
                _LOG.info("[%s] generate: llm ok provider=%s len=%s", rid, provider, len(text))
                return {
                    "answer": text,
                    "citations": cite_lines,
                    "diagnostics": ["generate:llm_ok"],
                }
            except ModuleNotFoundError as exc:
                _LOG.warning("[%s] generate: missing LLM dependency → fallback (%s)", rid, exc)
                diag = "generate:llm_import_error"
            except Exception as exc:  # noqa: BLE001
                _LOG.exception("[%s] generate: llm failed → fallback", rid)
                diag = f"generate:llm_error {exc.__class__.__name__}"
        else:
            diag = "generate:llm_skipped_missing_env"
            _LOG.warning("[%s] %s provider=%s", rid, diag, provider)
    else:
        diag = "generate:mode_fallback"

    # 确定性兜底：不调用 LLM，从首条证据截断摘要，保证流水线在 CI/无 Key 下仍可断言行为。
    head = chunks[0] if chunks else {}
    summary = (
        f"根据知识片段「{ head.get('title', '无标题')}」：{head.get('body', '')[:180]}"
        f"{'…' if head.get('body') and len(str(head.get('body'))) > 180 else ''}"
    )
    fallback_answer = "【模板归纳】" + summary + "\n（未调用 LLM：mode=fallback 或环境未配置 / provider 无 Key。）"
    return {
        "answer": fallback_answer,
        "citations": cite_lines,
        "diagnostics": [diag if mode == "llm" else "generate:fallback_template"],
    }


def seal_no_evidence_answer(state: RagState) -> dict[str, Any]:
    """检索无可用片段时的固定话术：不伪造 citations，降低合规与客诉风险。"""
    return {
        "answer": (
            "【无匹配知识】当前知识库未检索到与您问题足够相关的条目。"
            "建议换一种描述、提供订单号或联系人工客服。"
        ),
        "citations": [],
        "diagnostics": ["seal:no_evidence"],
    }


def seal_invalid_query(state: RagState) -> dict[str, Any]:
    """normalize 判定无效后的收口：提示用户补全输入，不进行检索。"""
    return {
        "answer": "【输入无效】请先输入有效的问题内容。",
        "citations": [],
        "diagnostics": ["seal:invalid_query"],
    }


def export_graph_png(compiled_graph: Any, filename: str) -> None:
    """
    从已编译图导出结构图：优先 PNG（需 graphviz 等渲染链），失败则写 Mermaid 文本供人工渲染。

    作用：评审/文档与代码拓扑一致，避免「口头拓扑」与实现漂移。
    """
    graph_obj = compiled_graph.get_graph()
    png_path = Path(__file__).with_name(filename)
    mermaid_path = Path(__file__).with_name(filename.replace(".png", ".mmd"))
    try:
        png_path.write_bytes(graph_obj.draw_mermaid_png())
        print(f"[图导出] {png_path}")
    except Exception as exc:  # noqa: BLE001
        mermaid_path.write_text(graph_obj.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mermaid_path}")


def build_rag_graph() -> Any:
    """
    注册节点与边，编译为可 invoke 的图。

    拓扑要点：两条「条件边」分别处理（合法查询 vs 空查询）、（有检索结果 vs 无结果），其余为线性边。
    """
    g: StateGraph = StateGraph(RagState)
    g.add_node("normalize_query", normalize_query)
    g.add_node("retrieve_lexical", retrieve_lexical)
    g.add_node("rerank_heuristic", rerank_heuristic)
    g.add_node("generate_with_evidence", generate_with_evidence)
    g.add_node("seal_no_evidence_answer", seal_no_evidence_answer)
    g.add_node("seal_invalid_query", seal_invalid_query)

    # START 唯一入口：先 normalize，再由条件边分流。
    g.add_edge(START, "normalize_query")
    g.add_conditional_edges(
        "normalize_query",
        route_after_normalize,
        {
            "retrieve": "retrieve_lexical",
            "invalid": "seal_invalid_query",
        },
    )
    # 检索结束后：有 chunk 才做 rerank+generate；否则直接无证据话术结束。
    g.add_conditional_edges(
        "retrieve_lexical",
        route_after_retrieve,
        {
            "rerank": "rerank_heuristic",
            "no_evidence": "seal_no_evidence_answer",
        },
    )
    g.add_edge("rerank_heuristic", "generate_with_evidence")
    g.add_edge("generate_with_evidence", END)
    g.add_edge("seal_no_evidence_answer", END)
    g.add_edge("seal_invalid_query", END)
    return g.compile()


def _initial_state(request_id: str, user_query: str, mode: RunMode) -> RagState:
    # invoke 前一次性填入「输入侧」字段；节点运行过程中会逐步填充检索/生成结果。
    return {
        "request_id": request_id,
        "user_query": user_query,
        "mode": mode,
        "query_gate": "pending",
        "retrieved_chunks": [],
        "context_chunks": [],
        "answer": "",
        "citations": [],
        "diagnostics": [],
    }


def demo() -> None:
    """脚本入口：打印多组用例终态，并导出图 PNG（与课程大纲 DoD 一致）。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    app = build_rag_graph()

    # (request_id, user_query, 说明标签, mode)：覆盖主路径、强制无命中、空查询三类行为。
    cases: list[tuple[str, str, str, RunMode]] = [
        ("happy-refund", "申请退款需要满足什么条件？", "主路径：命中退款政策", "llm"),
        ("happy-rate", "接口限速429的话客户端要怎么退避？", "主路径：命中速率限制文档", "llm"),
        ("no-hit", "FORCE_NO_HIT 今天天气如何", "Failure：强制无命中", "llm"),
        ("invalid", "   ", "Failure：空查询", "llm"),
    ]

    print("=" * 72)
    print("第十六课：RAG + LangGraph（retrieve → rerank → generate）")
    print("=" * 72)

    for rid, q, label, mode in cases:
        print("\n" + "-" * 72)
        print(label)
        print("-" * 72)
        out = app.invoke(_initial_state(rid, q, mode))
        print("  answer:\n", (out.get("answer") or "").strip())
        print("  citations:", out.get("citations"))
        print("  diagnostics:", out.get("diagnostics"))
        if out.get("retrieved_chunks"):
            print("  retrieved (doc_id, score):", [(c.get("doc_id"), c.get("score")) for c in out["retrieved_chunks"]])

    # 结构化一行：便于对接日志采集
    sample = app.invoke(_initial_state("json-demo", "无理由退款", "fallback"))
    print("\n[json]", json.dumps({"lesson": 16, "answer_head": (sample.get("answer") or "")[:80]}, ensure_ascii=False))

    export_graph_png(app, "16_rag_langgraph_graph.png")

    print("\n" + "=" * 72)
    print("说明：mode=llm 时读 LLM_PROVIDER：openai 用 OPENAI_*；ark 用 ARK_*（与第 6 课一致）。默认 demo 为 fallback。")
    print("=" * 72)


if __name__ == "__main__":
    demo()
