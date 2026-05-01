"""
14b（进阶）：支付请款（Capture）编排 —— 用真实业务语义讲清第 14 课的「重试 / 退避 / 降级」

业务背景（简化）：
-----------------
- 订单系统在发货后调用 **PSP（支付服务提供商）** 做 **Capture（请款）**，将预授权转为实扣。
- **可重试**：网关返回 503、限流、超时等 —— 不应立刻判失败，应 **退避后重 dial**（本课用 sleep 模拟）。
- **不可重试**：拒付、风控拒绝、商户号无效等 —— 应立即走 **财务/订单降级**（人工工单或关单），避免重复请款引发纠纷。
- **校验失败**：报文缺关键字段 —— 无调用 PSP 的意义，直接降级。

与 `14_error_handling_robustness_graph.py` 的关系：
-------------------------------------------------
- **图拓扑与路由键 `risk_status` 完全一致**（ok / retry / degraded + backoff 环），仅状态字段名与
  「模拟 PSP 返回」的规则改为行业可读表述。
- 学完 14 课抽象版后，用本脚本对照「同样在图里显式处理失败类」。

本脚本状态字段（14b 独立约定，不影响 14 课文件接口）：
----------------------------------------------------
- correlation_id：全链路追踪号（可对齐日志平台）
- capture_payload：教学用「请款请求摘要」单行字符串（真实场景多为结构化报文 + 签名）
- psp_attempt：已对 PSP 发起的轮次（不含即将发起的那次）
- risk_status / operations_log / settlement_summary：语义同 14 课的 risk_status / diagnostics / result_summary

**最小回归**：`python 14b_payment_capture_resilience_graph.py`
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

_LOG = logging.getLogger("lesson14b.capture")

# 与第 14 课同构：前两次 PSP 「瞬时类」结果触发重试，第三次同一 payload 视为成功（教学假设）
MAX_TRANSIENT_ATTEMPT = 2
_BACKOFF_CAP_S = 0.35
_BACKOFF_BASE_S = 0.04


def _payload_lower(payload: str) -> str:
    return payload.strip().lower()


def _is_transient_symptom(payload_lower: str) -> bool:
    """模拟 PSP/网络层「可重试」类信号（503、限流、超时、网关忙）。"""
    markers = ("503", "502", "504", "rate_limit", "timeout", "transient", "gw_busy", "temporarily_unavailable")
    return any(m in payload_lower for m in markers)


def _is_hard_decline(payload_lower: str) -> bool:
    """模拟「请款业务拒绝」—— 重试通常无效或风险高。"""
    markers = ("declined", "fraud", "invalid_merchant", "hard_fail", "chargeback_hold", "do_not_retry")
    return any(m in payload_lower for m in markers)


class PaymentCaptureState(TypedDict):
    """14b 专用状态；字段名贴合支付域，便于与产品/财务口述对齐。"""

    correlation_id: str
    capture_payload: str
    psp_attempt: int
    risk_status: Literal["", "ok", "retry", "degraded"]
    operations_log: Annotated[list[str], operator.add]
    settlement_summary: str


def invoke_psp_capture(state: PaymentCaptureState) -> dict:
    """
    节点：调用 PSP 请款（教学用分支模拟真实 RPC 结果分类）。

    生产注意：
    - 此处应 try/except 捕获网络异常，映射到 risk_status，而不是让异常冒泡到图外。
    - **幂等键**（idempotency-key）应在 HTTP 头或报文体中携带，避免重试时重复请款；本课省略以实现极简。
    """
    cid = state.get("correlation_id") or ""
    raw = state.get("capture_payload") or ""
    pl = raw.strip()
    attempt = int(state.get("psp_attempt") or 0)
    _LOG.info("invoke_psp_capture correlation_id=%s psp_attempt=%s len=%s", cid, attempt, len(pl))

    if not pl:
        _LOG.warning("capture_payload empty → no PSP call")
        return {
            "risk_status": "degraded",
            "settlement_summary": "【结算降级】请款报文为空，未调用 PSP",
            "operations_log": ["psp:validation_empty_payload"],
        }

    low = _payload_lower(pl)
    if _is_hard_decline(low):
        _LOG.warning("PSP hard decline (simulated)")
        return {
            "risk_status": "degraded",
            "settlement_summary": "【结算降级】PSP 拒绝请款（风控/商户状态等，禁止自动重试）",
            "operations_log": ["psp:hard_decline"],
        }

    if _is_transient_symptom(low):
        if attempt < MAX_TRANSIENT_ATTEMPT:
            _LOG.info("PSP transient symptom psp_attempt=%s → schedule retry", attempt)
            return {
                "risk_status": "retry",
                "operations_log": [f"psp:transient_symptom psp_attempt={attempt}"],
            }
        head = pl[:48] + ("…" if len(pl) > 48 else "")
        _LOG.info("PSP recovered after backoff (teaching)")
        return {
            "risk_status": "ok",
            "settlement_summary": f"请款成功：第 {attempt} 次重 dial 后确认；payload 摘要：{head}",
            "operations_log": ["psp:recovered_after_backoff"],
        }

    head = pl[:48] + ("…" if len(pl) > 48 else "")
    return {
        "risk_status": "ok",
        "settlement_summary": f"请款成功：一次到账；摘要：{head}",
        "operations_log": ["psp:ok_first_call"],
    }


def backoff_before_redial(state: PaymentCaptureState) -> dict:
    """重试前等待：生产可改为 jitter + 最大重试次数告警。"""
    cid = state.get("correlation_id") or ""
    attempt = int(state.get("psp_attempt") or 0)
    delay = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2**attempt))
    _LOG.info("backoff_before_redial correlation_id=%s sleep=%.3fs next_psp_attempt=%s", cid, delay, attempt + 1)
    time.sleep(delay)
    return {
        "psp_attempt": attempt + 1,
        "operations_log": [f"backoff:slept={delay:.3f}s next_psp_attempt={attempt + 1}"],
    }


def route_after_psp(state: PaymentCaptureState) -> str:
    """与第 14 课 `route_after_risky` 同构。"""
    status = state.get("risk_status") or ""
    if status == "ok":
        return "post_capture_audit_ok"
    if status == "retry":
        return "backoff_before_redial"
    if status == "degraded":
        return "degraded_finance_notice"
    _LOG.error("route_after_psp unexpected risk_status=%r", status)
    return "degraded_finance_notice"


def post_capture_audit_ok(state: PaymentCaptureState) -> dict:
    """成功后对接账务/审计系统的占位节点（只打日志，避免膨胀）。"""
    _LOG.info("post_capture_audit_ok correlation_id=%s", state.get("correlation_id") or "")
    return {"operations_log": ["audit:capture_posted_ok"]}


def degraded_finance_notice(state: PaymentCaptureState) -> dict:
    """降级：触发人工或写「待处理结算队列」—— 本课只追加日志行。"""
    _LOG.warning("degraded_finance_notice correlation_id=%s", state.get("correlation_id") or "")
    return {"operations_log": ["finance:manual_followup_required"]}


def build_payment_capture_graph():
    """
    START → invoke_psp_capture ──route──→ post_capture_audit_ok → END
                           │ backoff_before_redial → invoke_psp_capture（循环）
                           └──→ degraded_finance_notice → END
    """
    g = StateGraph(PaymentCaptureState)
    g.add_node("invoke_psp_capture", invoke_psp_capture)
    g.add_node("backoff_before_redial", backoff_before_redial)
    g.add_node("post_capture_audit_ok", post_capture_audit_ok)
    g.add_node("degraded_finance_notice", degraded_finance_notice)
    g.add_edge(START, "invoke_psp_capture")
    g.add_conditional_edges(
        "invoke_psp_capture",
        route_after_psp,
        {
            "post_capture_audit_ok": "post_capture_audit_ok",
            "backoff_before_redial": "backoff_before_redial",
            "degraded_finance_notice": "degraded_finance_notice",
        },
    )
    g.add_edge("backoff_before_redial", "invoke_psp_capture")
    g.add_edge("post_capture_audit_ok", END)
    g.add_edge("degraded_finance_notice", END)
    saver = InMemorySaver()
    return g.compile(checkpointer=saver), saver


def export_graph_png(compiled_graph, filename: str) -> None:
    graph_obj = compiled_graph.get_graph()
    png_path = Path(__file__).with_name(filename)
    mermaid_path = Path(__file__).with_name(filename.replace(".png", ".mmd"))
    try:
        png_path.write_bytes(graph_obj.draw_mermaid_png())
        print(f"[图导出] {png_path}")
    except Exception as exc:  # noqa: BLE001
        mermaid_path.write_text(graph_obj.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mermaid_path}")


def _cfg(suffix: str) -> dict:
    return {
        "configurable": {"thread_id": f"lesson-14b-{suffix}"},
        "tags": ["lesson-14b", "payment-capture"],
        "metadata": {"course": "langgraph-study", "lesson": "14b"},
    }


def _init(**kwargs: str | int) -> PaymentCaptureState:
    base: PaymentCaptureState = {
        "correlation_id": "",
        "capture_payload": "",
        "psp_attempt": 0,
        "risk_status": "",
        "operations_log": [],
        "settlement_summary": "",
    }
    merged = {**base, **kwargs}  # type: ignore[misc]
    return merged  # type: ignore[return-value]


def demo() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    graph, _ = build_payment_capture_graph()

    print("=" * 72)
    print("14b：Happy Path —— 一次请款成功")
    print("=" * 72)
    r1 = graph.invoke(
        _init(
            correlation_id="cap-happy-1",
            capture_payload="order_id=SO-9001 intent=pi_abc amount_cents=50000 merchant=MID-01",
        ),
        _cfg("happy"),
    )
    print("  settlement_summary:", repr(r1.get("settlement_summary")))
    print("  psp_attempt:", r1.get("psp_attempt"))
    print("  operations_log:", r1.get("operations_log"))

    print("\n" + "=" * 72)
    print("14b：PSP 返回瞬时类故障（503）—— 退避重试后成功")
    print("=" * 72)
    r2 = graph.invoke(
        _init(
            correlation_id="cap-transient-1",
            capture_payload="order_id=SO-9002 PSP_error=503 Service Unavailable (simulated)",
        ),
        _cfg("transient"),
    )
    print("  settlement_summary:", repr(r2.get("settlement_summary")))
    print("  psp_attempt:", r2.get("psp_attempt"))
    print("  operations_log:", r2.get("operations_log"))

    print("\n" + "=" * 72)
    print("14b：硬拒绝（fraud / declined）—— 不得自动重试，走财务降级")
    print("=" * 72)
    r3 = graph.invoke(
        _init(
            correlation_id="cap-decline-1",
            capture_payload="order_id=SO-9003 PSP=fraud blocked transaction declined",
        ),
        _cfg("decline"),
    )
    print("  operations_log:", r3.get("operations_log"))
    print("  settlement_summary:", repr(r3.get("settlement_summary")))

    print("\n" + "=" * 72)
    print("14b：空报文 —— 校验失败")
    print("=" * 72)
    r4 = graph.invoke(
        _init(correlation_id="cap-empty-1", capture_payload="   "),
        _cfg("empty"),
    )
    print("  operations_log:", r4.get("operations_log"))
    print("  settlement_summary:", repr(r4.get("settlement_summary")))

    export_graph_png(graph, "14b_payment_capture_resilience_graph.png")

    print("\n" + "=" * 72)
    print("小结：图中显式区分「可重试瞬时故障」与「业务硬失败」，与第 14 课抽象版一一对应。")
    print("=" * 72)


if __name__ == "__main__":
    demo()
