"""
第十五课：评测体系与质量门禁（Evaluation / Regression / Quality Gate）

与前序课关系：
--------------
- 第 13～14 课把「可观测」与「失败可恢复」做进图内；本课讨论：**如何系统证明图没有回归**，
  以及如何在升级依赖/改节点实现时守住 **对外契约**（状态字段、`invoke` 入参形状等）。
- 评测逻辑通常与 **被测业务图（SUT）** 解耦：仓库、CI、评测任务调度在工程里往往独立；
  本脚本仍给出一个 **极薄的批处理拓扑**（`bootstrap → regression_worker → gate_finalize`），
  表示「编排层把一批用例跑完再汇总」，避免误以为必须把 pytest 写进节点里。

本节要点（思想与 API，对照 `langgraph==1.1.10`）：
-------------------------------------------------
1. **黄金用例（Golden Cases）**  
   - 为每条用例固定 `user_message`，对终态 `intent` / `reply` 做断言（精确相等或子串包含）。  
   - 业务上可扩展为：BLEU、结构化 JSON diff、LLM-as-judge；本课用确定性规则节点，保证无 API Key 也可跑 CI。

2. **黑盒调用 CompiledGraph.invoke**  
   - `invoke(input_state, config)`：本节关注 **输出状态** 是否满足契约，而不是节点内部实现。  
   - `config` 仍使用 **`RunnableConfig`**：`{"configurable": {"thread_id": ...}}` 与第 12～14 课一致，
     **每个用例独占 thread_id** 可避免评测串线（与生产多租户隔离思想一致）。

3. **质量门禁（Quality Gate）**  
   - `MIN_PASS_RATIO`：通过率低于阈值则 **进程退出码 1**（模拟流水线失败）。  
   - 生产常见做法：门禁 + 报表上传；本课在 stderr 打印简短 JSON 行便于采集。

4. **契约 / 兼容性**  
   - **TypedDict 字段名即契约**：改名或删字段会导致下游评测与 API 序列化失败。  
   - 版本升级时：**先跑本套件再合并**，是「接口不变」约束的可执行定义之一。

5. **图内「批处理」节点（教学向）**  
   - `regression_worker` **在单节点内**循环调用 SUT：真实工程中也可以改为队列 worker、
     或 LangGraph `Send` 动态分片（见第 10 课）；此处优先 **可读 + 可调试**。

6. **`get_graph().draw_mermaid_png()`**  
   - 评测编排图与 SUT 图 **分别导出**，便于评审「谁调谁」。

Failure Path：
-------------
- 故意将某条用例期望设为错误（见 `EVIL_CASE` 开关）可触发门禁失败；  
- `user_message` 含 **`force_evaluator_crash`** 时 SUT 写入 `invalid` 意图，用于观察失败报表中的 case 状态。

主路径拓扑（SUT：客服意图草稿）：
----------------------------------
START → normalize_message → classify_intent ──route_intent──→ draft_refund   ──┐
                         │                    │              draft_shipping ├──→ seal_response → END
                         │                    │              draft_general  ──┤
                         │                    └──→ draft_invalid ──────────────┘

评测编排拓扑（薄包装，对应大纲「批处理」示意）：
----------------------------------------------
START → bootstrap_run → regression_worker → gate_finalize → END

最小回归：
----------
`python 15_evaluation_quality_gate_graph.py`

接口不变清单（本课 DoD）：
-------------------------
- SUT 状态键：`request_id`, `user_message`, `intent`, `reply`, `diagnostics`  
- `intent` 取值：`refund` | `shipping` | `general` | `invalid`  
- 编排状态键：`run_id`, `eval_reports`, `pass_count`, `fail_count`, `gate_ok`, `gate_detail`
"""

from __future__ import annotations

import json
import logging
import operator
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal, Sequence

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

_LOG = logging.getLogger("lesson15.eval")


# ---------------------------------------------------------------------------
# 契约：SUT（被测图）状态 —— 字段名请勿随意改动（对照大纲「接口不变」）
# ---------------------------------------------------------------------------
Intent = Literal["", "refund", "shipping", "general", "invalid"]


class SutState(TypedDict):
    """
    客服意图示例图的输入/输出载体。

    - user_message：用户原文；normalize 节点负责 strip
    - intent：classify 节点写入；条件边唯一路由键
    - reply：各 draft_* 节点写入；seal 仅追加 diagnostics
    """

    request_id: str
    user_message: str
    intent: Intent
    reply: str
    diagnostics: Annotated[list[str], operator.add]


# ---------------------------------------------------------------------------
# 编排层状态（批处理图）：汇总一次回归运行的计数与明细
# ---------------------------------------------------------------------------
class EvalOrchestrationState(TypedDict):
    """一次 CI 运行的元数据与结果；与 SUT 分离，避免污染生产 state schema。"""

    run_id: str
    eval_reports: list[dict[str, Any]]
    pass_count: int
    fail_count: int
    gate_ok: bool
    gate_detail: str


# ---------------------------------------------------------------------------
# 用例模型（工程上可迁至 JSON/YAML；此处内联便于单文件教学）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GoldenCase:
    """
    单条黄金用例：黑盒只关心 invoke 后的状态切片。

    Attributes:
        case_id: 稳定 ID，用于报表与 thread_id 后缀
        user_message: 输入给用户图的消息
        expect_intent: 对 `intent` 的精确期望
        reply_substrings: `reply` 必须全部包含的子串（大小写敏感，教学默认）
        label: 人类可读说明，进入 diagnostics / 日志
    """

    case_id: str
    user_message: str
    expect_intent: Intent
    reply_substrings: tuple[str, ...] = ()
    label: str = ""


@dataclass
class CaseResult:
    """单条执行结果：便于序列化成 JSON 行给日志采集。"""

    case_id: str
    passed: bool
    detail: str
    actual: dict[str, Any] = field(default_factory=dict)


# 内置套件：覆盖主路径与 invalid 分支
DEFAULT_GOLDEN_SUITE: tuple[GoldenCase, ...] = (
    GoldenCase("gc-001", "我要申请退款，订单 123", "refund", ("退款",), "退款意图"),
    GoldenCase("gc-002", "帮查一下快递物流到哪里了", "shipping", ("物流",), "物流意图"),
    GoldenCase("gc-003", "你好，随便问问", "general", ("咨询",), "闲聊/泛化"),
    GoldenCase("gc-004", "   ", "invalid", ("请先",), "空输入 → invalid"),
    GoldenCase(
        "gc-005",
        "force_evaluator_crash",
        "invalid",
        (),
        "人为触发失败分支（reply 不含强制子串时可用于看报表）",
    ),
)

# 门禁阈值：1.0 表示「套件全绿才放行」；可在实验中改为 0.8 观察「部分失败仍通过」
MIN_PASS_RATIO = 1.0

# 设为 True 可演示流水线失败（最后一条用例期望被故意写错）
EVIL_CASE = True


def _config_for_case(case_id: str) -> dict[str, Any]:
    """评测专用 RunnableConfig：thread 隔离 + tags 便于日志过滤。"""
    return {
        "configurable": {"thread_id": f"lesson-15-eval-{case_id}"},
        "tags": ["lesson-15", "evaluation"],
        "metadata": {"course": "langgraph-study", "lesson": "15"},
    }


# --- SUT 节点 ----------------------------------------------------------------


def normalize_message(state: SutState) -> dict:
    """规范化输入：去首尾空白；不改 intent/reply，保持节点职责单一。"""
    raw = state.get("user_message") or ""
    cleaned = raw.strip()
    _LOG.info("normalize_message request_id=%s len_in=%s len_out=%s", state.get("request_id"), len(raw), len(cleaned))
    return {
        "user_message": cleaned,
        "diagnostics": ["normalize:stripped"],
    }


def classify_intent(state: SutState) -> dict:
    """
    规则分类器：生产可替换为 LLM + 结构化输出；本课保证确定性。

    特殊输入 `force_evaluator_crash`：模拟「已知失败用例」走 invalid，不等于抛异常。
    """
    msg = (state.get("user_message") or "").strip()
    rid = state.get("request_id") or ""
    if not msg:
        _LOG.warning("classify_intent: empty after normalize request_id=%s", rid)
        return {"intent": "invalid", "diagnostics": ["classify:empty"]}

    if "force_evaluator_crash" in msg:
        _LOG.warning("classify_intent: force failure token request_id=%s", rid)
        return {
            "intent": "invalid",
            "reply": "【测试桩】检测到强制失败标记。",
            "diagnostics": ["classify:force_evaluator_crash"],
        }

    lowered = msg.lower()
    if any(k in msg for k in ("退款", "退货", "refund")):
        return {"intent": "refund", "diagnostics": ["classify:refund"]}
    if any(k in msg for k in ("物流", "快递", "shipping", "查单")) or "track" in lowered:
        return {"intent": "shipping", "diagnostics": ["classify:shipping"]}
    return {"intent": "general", "diagnostics": ["classify:general"]}


def route_after_classify(state: SutState) -> str:
    """条件边：路由键必须与 add_conditional_edges 的 map 键一致。"""
    intent = state.get("intent") or ""
    if intent == "refund":
        return "draft_refund"
    if intent == "shipping":
        return "draft_shipping"
    if intent == "general":
        return "draft_general"
    if intent == "invalid":
        return "draft_invalid"
    _LOG.error("route_after_classify: unknown intent=%r → draft_invalid", intent)
    return "draft_invalid"


def draft_refund(state: SutState) -> dict:
    """退款支路：写入可读 reply，供黄金用例子串断言。"""
    return {
        "reply": "已记录您的退款诉求，将在 1 个工作日内处理。",
        "diagnostics": ["draft:refund"],
    }


def draft_shipping(state: SutState) -> dict:
    return {
        "reply": "正在为您查询物流状态，请稍候刷新订单详情页。",
        "diagnostics": ["draft:shipping"],
    }


def draft_general(state: SutState) -> dict:
    return {
        "reply": "感谢您的咨询，我们已收到，将由人工坐席跟进。",
        "diagnostics": ["draft:general"],
    }


def draft_invalid(state: SutState) -> dict:
    """invalid：若 classify 已写 reply（强制失败桩），则不覆盖。"""
    existing = state.get("reply") or ""
    if existing:
        return {"diagnostics": ["draft:invalid_passthrough"]}
    return {
        "reply": "请先描述您的问题，以便为您分流到对应坐席。",
        "diagnostics": ["draft:invalid_default"],
    }


def seal_response(state: SutState) -> dict:
    """收口节点：只追加审计痕迹，示幂等与 checkpoint 安全回放场景。"""
    _LOG.info("seal_response request_id=%s intent=%s", state.get("request_id"), state.get("intent"))
    return {"diagnostics": ["seal:ok"]}


def build_sut_graph():
    """
    构建并编译 SUT：注入 memory checkpointer，与第 12～14 课演示风格一致。

    Returns:
        (compiled_graph, saver) 元组；评测算子只需 compiled_graph。
    """
    g = StateGraph(SutState)
    g.add_node("normalize_message", normalize_message)
    g.add_node("classify_intent", classify_intent)
    g.add_node("draft_refund", draft_refund)
    g.add_node("draft_shipping", draft_shipping)
    g.add_node("draft_general", draft_general)
    g.add_node("draft_invalid", draft_invalid)
    g.add_node("seal_response", seal_response)

    g.add_edge(START, "normalize_message")
    g.add_edge("normalize_message", "classify_intent")
    g.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        {
            "draft_refund": "draft_refund",
            "draft_shipping": "draft_shipping",
            "draft_general": "draft_general",
            "draft_invalid": "draft_invalid",
        },
    )
    for n in ("draft_refund", "draft_shipping", "draft_general", "draft_invalid"):
        g.add_edge(n, "seal_response")
    g.add_edge("seal_response", END)

    saver = InMemorySaver()
    return g.compile(checkpointer=saver), saver


def export_graph_png(compiled_graph: Any, filename: str) -> None:
    """与前几课一致：优先 PNG，失败写 Mermaid。"""
    graph_obj = compiled_graph.get_graph()
    png_path = Path(__file__).with_name(filename)
    mermaid_path = Path(__file__).with_name(filename.replace(".png", ".mmd"))
    try:
        png_path.write_bytes(graph_obj.draw_mermaid_png())
        print(f"[图导出] {png_path}")
    except Exception as exc:  # noqa: BLE001
        mermaid_path.write_text(graph_obj.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mermaid_path}")


# --- 评测算子 ---------------------------------------------------------------


def _init_sut_state(case: GoldenCase) -> SutState:
    return {
        "request_id": case.case_id,
        "user_message": case.user_message,
        "intent": "",
        "reply": "",
        "diagnostics": [],
    }


def run_single_case(compiled_sut: Any, case: GoldenCase) -> CaseResult:
    """
    对单条 GoldenCase 执行 invoke + 断言。

    注意：这里刻意 **不用** 图内子图嵌套，保持评测代码可被 pytest 直接 import。
    """
    final = compiled_sut.invoke(_init_sut_state(case), _config_for_case(case.case_id))
    intent = final.get("intent") or ""
    reply = final.get("reply") or ""

    if intent != case.expect_intent:
        return CaseResult(
            case_id=case.case_id,
            passed=False,
            detail=f"intent 期望 {case.expect_intent!r} 实际 {intent!r}",
            actual={"intent": intent, "reply": reply},
        )

    for sub in case.reply_substrings:
        if sub not in reply:
            return CaseResult(
                case_id=case.case_id,
                passed=False,
                detail=f"reply 缺少子串 {sub!r}: {reply!r}",
                actual={"intent": intent, "reply": reply},
            )

    return CaseResult(
        case_id=case.case_id,
        passed=True,
        detail="ok",
        actual={"intent": intent, "reply": reply},
    )


def run_golden_suite(
    compiled_sut: Any,
    cases: Sequence[GoldenCase],
) -> tuple[list[CaseResult], float]:
    """
    运行完整套件并计算通过率。

    Returns:
        (results, pass_ratio)
    """
    results: list[CaseResult] = []
    for c in cases:
        results.append(run_single_case(compiled_sut, c))
    n = len(results)
    passed_n = sum(1 for r in results if r.passed)
    ratio = passed_n / n if n else 1.0
    return results, ratio


def evaluate_gate(pass_ratio: float) -> tuple[bool, str]:
    """质量门禁：返回 (是否通过, 人类可读说明)。"""
    ok = pass_ratio + 1e-9 >= MIN_PASS_RATIO
    detail = f"pass_ratio={pass_ratio:.3f} min_required={MIN_PASS_RATIO:.3f} → {'PASS' if ok else 'FAIL'}"
    return ok, detail


# --- 薄编排图（批处理示意）---------------------------------------------------


def bootstrap_run(state: EvalOrchestrationState) -> dict:
    """初始化一次评测运行的计数器。"""
    rid = state.get("run_id") or "run-local"
    _LOG.info("bootstrap_run run_id=%s", rid)
    return {
        "eval_reports": [],
        "pass_count": 0,
        "fail_count": 0,
        "gate_ok": False,
        "gate_detail": "",
    }


def regression_worker(state: EvalOrchestrationState, compiled_sut: Any, cases: Sequence[GoldenCase]) -> dict:
    """
    单节点内跑完整套件：生产中可替换为向消息队列投递 case_id。

    设计权衡：不把「循环」拆成多个 LangGraph super-step，避免本课焦点偏离到 Send API。
    """
    results, ratio = run_golden_suite(compiled_sut, cases)
    passed_n = sum(1 for r in results if r.passed)
    fail_n = len(results) - passed_n
    reports = [
        {
            "case_id": r.case_id,
            "passed": r.passed,
            "detail": r.detail,
            "actual": r.actual,
        }
        for r in results
    ]
    gate_ok, gate_detail = evaluate_gate(ratio)
    _LOG.info(
        "regression_worker done run_id=%s pass=%s fail=%s ratio=%.3f gate=%s",
        state.get("run_id"),
        passed_n,
        fail_n,
        ratio,
        gate_ok,
    )
    return {
        "eval_reports": reports,
        "pass_count": passed_n,
        "fail_count": fail_n,
        "gate_ok": gate_ok,
        "gate_detail": gate_detail,
    }


def gate_finalize(state: EvalOrchestrationState) -> dict:
    """收口：仅追加结构化日志行（stdout 由 demo 统一打印）。"""
    return {}


def build_eval_orchestration_graph(compiled_sut: Any, cases: Sequence[GoldenCase]):
    """
    构建评测编排图；`regression_worker` 通过闭包捕获 SUT 与 cases。

    说明：LangGraph 节点签名默认为 (state) -> partial update；此处用 factory 注入依赖。
    """

    def _worker(state: EvalOrchestrationState) -> dict:
        return regression_worker(state, compiled_sut, cases)

    g = StateGraph(EvalOrchestrationState)
    g.add_node("bootstrap_run", bootstrap_run)
    g.add_node("regression_worker", _worker)
    g.add_node("gate_finalize", gate_finalize)
    g.add_edge(START, "bootstrap_run")
    g.add_edge("bootstrap_run", "regression_worker")
    g.add_edge("regression_worker", "gate_finalize")
    g.add_edge("gate_finalize", END)
    return g.compile()


def _maybe_evil_suite(suite: Sequence[GoldenCase]) -> list[GoldenCase]:
    """演示「契约被破坏」：最后一条用例故意期望错误 intent。"""
    lst = list(suite)
    if EVIL_CASE and lst:
        last = lst[-1]
        lst[-1] = GoldenCase(
            case_id=last.case_id + "-evil",
            user_message=last.user_message,
            expect_intent="refund",  # 蓄意错误：应为 invalid
            reply_substrings=last.reply_substrings,
            label=last.label + "（evil）",
        )
    return lst


def demo() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    sut, _ = build_sut_graph()
    suite = _maybe_evil_suite(DEFAULT_GOLDEN_SUITE)

    print("=" * 72)
    print("第十五课：SUT 单次 invoke 演示（Happy Path）")
    print("=" * 72)
    one = sut.invoke(
        {
            "request_id": "demo-1",
            "user_message": "我要退款",
            "intent": "",
            "reply": "",
            "diagnostics": [],
        },
        _config_for_case("demo-1"),
    )
    print("  intent:", one.get("intent"))
    print("  reply:", one.get("reply"))
    print("  diagnostics:", one.get("diagnostics"))

    print("\n" + "=" * 72)
    print("第十五课：黄金套件 + 质量门禁（可对照 CI）")
    print("=" * 72)
    results, ratio = run_golden_suite(sut, suite)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.case_id}: {r.detail}")
    gate_ok, gate_detail = evaluate_gate(ratio)
    print(f"\n  {gate_detail}")

    # 结构化一行：便于 ELK / CloudWatch 等采集（教学向）
    payload = {
        "lesson": 15,
        "pass_ratio": ratio,
        "gate_ok": gate_ok,
        "cases": [{"id": r.case_id, "passed": r.passed} for r in results],
    }
    print("  [json] " + json.dumps(payload, ensure_ascii=False))

    print("\n" + "=" * 72)
    print("第十五课：评测编排图（bootstrap → regression_worker → gate_finalize）")
    print("=" * 72)
    orch = build_eval_orchestration_graph(sut, suite)
    orch_out = orch.invoke(
        {
            "run_id": "ci-lesson-15-local",
            "eval_reports": [],
            "pass_count": 0,
            "fail_count": 0,
            "gate_ok": False,
            "gate_detail": "",
        }
    )
    print("  pass_count:", orch_out.get("pass_count"))
    print("  fail_count:", orch_out.get("fail_count"))
    print("  gate_ok:", orch_out.get("gate_ok"))
    print("  gate_detail:", orch_out.get("gate_detail"))

    export_graph_png(sut, "15_evaluation_quality_gate_sut_graph.png")
    export_graph_png(orch, "15_evaluation_quality_gate_orchestration_graph.png")

    print("\n" + "=" * 72)
    print("说明：将 `EVIL_CASE=True` 可演示门禁失败；生产请把 GoldenCase 外置为 JSON 并由 CI 传入。")
    print("=" * 72)

    if not gate_ok:
        sys.exit(1)


if __name__ == "__main__":
    demo()
