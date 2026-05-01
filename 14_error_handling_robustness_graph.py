"""
第十四课：错误处理与鲁棒性工程（Error Handling / Resilience）

与前序课关系：
--------------
- 第 13 课用 **`stream` / `logging`** 把运行轨迹「看得见」；本课把 **失败当成一等公民**：
  在图内显式分支 **重试 + 退避**、**不可恢复降级**，并把痕迹写入 `diagnostics`。
- **幂等 / 超时 / 熔断**：本脚本用注释 + 「可重入节点」写法提示；真正对接 LLM 或外部 HTTP 时，
  建议在 **节点外缘** 用客户端超时、舱壁隔离与熔断库（如 resilience4j），避免阻塞 LangGraph worker。

本节要点（对照 `langgraph==1.1.10`）：
-----------------------------------
- **不要在节点里抛未捕获异常**：否则整次 `invoke` 失败；教学上优先 **捕获 → 写入 state → 路由到恢复支路**
  （与第 13 课 `stub_error` 思路一致，本课扩展到 **循环重试**）。
- **指数退避（ capped ）**：`backoff_then_retry` 用 `time.sleep` 演示；上限避免拖慢课堂演示。
- **条件边三元路由**：`risk_status in {ok, retry, degraded}`，对应大纲「成功 / 错误恢复」拓扑。
- **`get_graph().draw_mermaid_png()`**：复杂环路与恢复路径适合一眼对照。

Failure Path：`input_text` 为空、`fatal` / `boom`（不可重试）、`flaky`（可重试直至 `attempt` 达阈后成功）、
故意 **`attempt` 过大** 可走降级（本课由 `flaky` 耗尽前仅在数值 `< MAX_TRANSIENT_ATTEMPT` 时返回 `retry`）。

**最小回归**：`python 14_error_handling_robustness_graph.py`，对照打印的 `attempt` 与 `diagnostics` 顺序。

**补充（真实业务叙事）**：见同课 `14b_payment_capture_resilience_graph.py`（支付请款 + PSP 语义，拓扑与 14 课一致）。
"""

from __future__ import annotations

import logging
import operator
import time
from pathlib import Path
from typing import Annotated, Literal

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

# ---------------------------------------------------------------------------
# 日志：本课独立 logger，便于在控制台过滤「第 14 课」相关行（与第 13 课 pattern 一致）
# ---------------------------------------------------------------------------
_LOG = logging.getLogger("lesson14.robust")

# ---------------------------------------------------------------------------
# 常量：瞬时故障判定的「教学阈值」——与 attempt 联动，不是生产里的固定真理
# - attempt=0,1：仍视为可重试；≥2 时认为下游已恢复（14b 里会换成 PSP 报文语义，逻辑同构）
# ---------------------------------------------------------------------------
MAX_TRANSIENT_ATTEMPT = 2

# 退避秒数：指数增长但 cap，避免课堂/CI 里 sleep 过长
_BACKOFF_CAP_S = 0.35
_BACKOFF_BASE_S = 0.04


class RobustnessState(TypedDict):
    """
    教学最小状态（本脚本对外约定，与 demo 入参一致，勿随意改字段名以免对照大纲失效）。

    - request_id：人工可读请求号，便于日志关联（可类比 trace 里的 business id）
    - input_text：业务输入字符串；本课用子串 flaky/fatal/boom 模拟三类行为，见 risky_call
    - attempt：当前已重试轮次（仅 backoff 节点负责 +1）
    - risk_status：条件边路由键；仅 risky_call 写入语义值，路由函数只读
    - diagnostics：各节点追加的运营/排障痕迹（operator.add 合并）
    - result_summary：给人或下游系统读的终态摘要
    """

    request_id: str
    input_text: str
    attempt: int
    risk_status: Literal["", "ok", "retry", "degraded"]
    diagnostics: Annotated[list[str], operator.add]
    result_summary: str


def risky_call(state: RobustnessState) -> dict:
    """
    模拟「可能失败」的外部调用。

    设计意图：
    - 全程 return dict，不向 LangGraph 抛未捕获异常，保证失败也可路由到降级支路。
    - 真实项目里此处往往是 HTTP/SDK 调用 + try/except，把异常分类后写入 risk_status。
    """
    rid = state.get("request_id") or ""
    text = (state.get("input_text") or "").strip()
    attempt = int(state.get("attempt") or 0)
    _LOG.info("节点 risky_call request_id=%s attempt=%s len=%s", rid, attempt, len(text))

    # ----- 校验类失败：无重试价值，直接降级 -----
    if not text:
        _LOG.warning("risky_call: empty input")
        return {
            "risk_status": "degraded",
            "result_summary": "【降级】空输入，拒绝执行",
            "diagnostics": ["risky:validation_empty"],
        }

    lowered = text.lower()
    # ----- 不可恢复：业务/合规拒绝等，重试只会打爆下游或污染账务 -----
    if "fatal" in lowered or "boom" in lowered:
        _LOG.warning("risky_call: unrecoverable keyword")
        return {
            "risk_status": "degraded",
            "result_summary": "【降级】不可恢复错误（fatal/boom）",
            "diagnostics": ["risky:unrecoverable"],
        }

    # ----- 瞬时故障：允许在 attempt 未达阈值时返回 retry，进入 backoff 环 -----
    if "flaky" in lowered:
        if attempt < MAX_TRANSIENT_ATTEMPT:
            _LOG.info("risky_call: transient flaky attempt=%s → retry", attempt)
            return {
                "risk_status": "retry",
                "diagnostics": [f"risky:transient_flaky attempt={attempt}"],
            }
        summary = f"已恢复：在 attempt={attempt} 后完成（输入前 48 字：{text[:48]}{'…' if len(text) > 48 else ''}）"
        _LOG.info("risky_call: flaky recovered")
        return {
            "risk_status": "ok",
            "result_summary": summary,
            "diagnostics": ["risky:recovered_after_backoff"],
        }

    # ----- 主路径：一次成功 -----
    summary = f"主路径成功：{text[:48]}{'…' if len(text) > 48 else ''}"
    return {
        "risk_status": "ok",
        "result_summary": summary,
        "diagnostics": ["risky:ok_direct"],
    }


def backoff_then_retry(state: RobustnessState) -> dict:
    """
    重试前退避：降低 thundering herd 概率；cap 防止 sleep 无限增长。

    可重入性：
    - 只读 state、只写 attempt/diagnostics，不依赖模块级可变变量，便于从 checkpoint 恢复后安全重跑。
    """
    rid = state.get("request_id") or ""
    attempt = int(state.get("attempt") or 0)
    delay = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2**attempt))
    _LOG.info("节点 backoff_then_retry request_id=%s sleep=%.3fs next_attempt=%s", rid, delay, attempt + 1)
    time.sleep(delay)
    return {
        "attempt": attempt + 1,
        "diagnostics": [f"backoff:slept={delay:.3f}s next_attempt={attempt + 1}"],
    }


def route_after_risky(state: RobustnessState) -> str:
    """
    risky_call 之后的条件边：下一跳完全由 risk_status 决定。

    防护：若出现脏状态，落到 degraded_finish，避免 Map 缺少键导致运行期错误。
    """
    status = state.get("risk_status") or ""
    if status == "ok":
        return "finalize_success"
    if status == "retry":
        return "backoff_then_retry"
    if status == "degraded":
        return "degraded_finish"
    _LOG.error("route_after_risky: unexpected risk_status=%r → degraded_finish", status)
    return "degraded_finish"


def finalize_success(state: RobustnessState) -> dict:
    """成功支路收口：不重写 result_summary，只追加审计痕迹。"""
    rid = state.get("request_id") or ""
    _LOG.info("节点 finalize_success request_id=%s", rid)
    return {"diagnostics": ["finalize_success:done"]}


def degraded_finish(state: RobustnessState) -> dict:
    """
    降级支路收口。

    若节点因 checkpoint 被再次执行，只做追加 diagnostics，不假设全局「只跑一次」。
    """
    rid = state.get("request_id") or ""
    _LOG.warning("节点 degraded_finish request_id=%s", rid)
    return {"diagnostics": ["degraded_finish:sealed"]}


def build_robustness_graph():
    """
    构图：含「自环」的恢复路径，导出 PNG 时便于和销售/产品一起过评审。

    START → risky_call ──route──→ finalize_success → END
                      │ backoff_then_retry → risky_call（循环）
                      └──→ degraded_finish → END
    """
    g = StateGraph(RobustnessState)
    g.add_node("risky_call", risky_call)
    g.add_node("backoff_then_retry", backoff_then_retry)
    g.add_node("finalize_success", finalize_success)
    g.add_node("degraded_finish", degraded_finish)
    g.add_edge(START, "risky_call")
    g.add_conditional_edges(
        "risky_call",
        route_after_risky,
        {
            "finalize_success": "finalize_success",
            "backoff_then_retry": "backoff_then_retry",
            "degraded_finish": "degraded_finish",
        },
    )
    g.add_edge("backoff_then_retry", "risky_call")
    g.add_edge("finalize_success", END)
    g.add_edge("degraded_finish", END)
    # 可观测/多线程演示与第 12/13 课一致：注入 memory checkpointer + thread_id
    saver = InMemorySaver()
    return g.compile(checkpointer=saver), saver


def export_graph_png(compiled_graph, filename: str) -> None:
    """与前几课相同：优先 PNG，失败则落 Mermaid 文本，避免缺依赖时阻断学习。"""
    graph_obj = compiled_graph.get_graph()
    png_path = Path(__file__).with_name(filename)
    mermaid_path = Path(__file__).with_name(filename.replace(".png", ".mmd"))
    try:
        png_path.write_bytes(graph_obj.draw_mermaid_png())
        print(f"[图导出] {png_path}")
    except Exception as exc:  # noqa: BLE001
        mermaid_path.write_text(graph_obj.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mermaid_path}")


def _base_config(thread_suffix: str) -> dict:
    """演示用 RunnableConfig：thread 隔离 + tags/metadata 占位（与第 13 课风格一致）。"""
    return {
        "configurable": {"thread_id": f"lesson-14-{thread_suffix}"},
        "tags": ["lesson-14", "robustness"],
        "metadata": {"course": "langgraph-study", "lesson": "14"},
    }


def _init_state(**kwargs: str | int) -> RobustnessState:
    """合并默认初值，减少 demo() 里重复抄写。"""
    defaults: RobustnessState = {
        "request_id": "",
        "input_text": "",
        "attempt": 0,
        "risk_status": "",
        "diagnostics": [],
        "result_summary": "",
    }
    merged = {**defaults, **kwargs}  # type: ignore[misc]
    return merged  # type: ignore[return-value]


def demo() -> None:
    """四套用例：成功、可恢复瞬时故障、不可恢复、校验失败。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    graph, _ = build_robustness_graph()

    print("=" * 72)
    print("第十四课：错误处理与鲁棒性（Happy Path：普通输入）")
    print("=" * 72)
    out_ok = graph.invoke(
        _init_state(request_id="req-ok", input_text="正常下单请求"),
        _base_config("happy"),
    )
    print("  result_summary:", repr(out_ok.get("result_summary")))
    print("  attempt:", out_ok.get("attempt"))
    print("  diagnostics:", out_ok.get("diagnostics"))

    print("\n" + "=" * 72)
    print("Failure Path：flaky → 两次退避重试 → 恢复成功")
    print("=" * 72)
    out_flaky = graph.invoke(
        _init_state(request_id="req-flaky", input_text="这是 flaky 下游，请多试几次"),
        _base_config("flaky"),
    )
    print("  result_summary:", repr(out_flaky.get("result_summary")))
    print("  attempt:", out_flaky.get("attempt"))
    print("  diagnostics:", out_flaky.get("diagnostics"))

    print("\n" + "=" * 72)
    print("Failure Path：fatal / boom（无重试，直接降级）")
    print("=" * 72)
    out_fatal = graph.invoke(
        _init_state(request_id="req-fatal", input_text="fatal error in payload"),
        _base_config("fatal"),
    )
    print("  diagnostics:", out_fatal.get("diagnostics"))
    print("  result_summary:", repr(out_fatal.get("result_summary")))

    print("\n" + "=" * 72)
    print("Failure Path：空输入（验证失败 → 降级）")
    print("=" * 72)
    out_empty = graph.invoke(
        _init_state(request_id="req-empty", input_text="   "),
        _base_config("empty"),
    )
    print("  diagnostics:", out_empty.get("diagnostics"))
    print("  result_summary:", repr(out_empty.get("result_summary")))

    export_graph_png(graph, "14_error_handling_robustness_graph.png")

    print("\n" + "=" * 72)
    print("说明：超时 / 熔断 / 舱壁应在客户端或中间件实现；节点内宜「捕获异常 → 写 state → 路由」。")
    print("=" * 72)


if __name__ == "__main__":
    demo()
