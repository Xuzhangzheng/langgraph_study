"""
09b（进阶）：生产向「父状态超集 + 子图/节点 input_schema 子集」——电商出库与支付对账编排

真实业务背景（简化建模）：
----------------------------
- 订单编排器（OMS）掌握**全貌**：客户邮箱、收货城市、SKU、数量、支付流水等。
- **WMS（仓储）第三方**：只需 `order_id + sku + qty` 生成拣货单；合同与合规上不应把客户邮箱、收货地址写进 WMS 的入参 payload。
- **支付对账任务**：只需 `order_id + payment_intent_id + amount_cents` 调用 PSP 查询；不需要地址与邮箱。

LangGraph 里对应两套手段（本脚本各给一个最小可运行示例）：
1) **子图单独 compile**：`StateGraph(WmsSubState)` 嵌进主图 —— 子图节点读写渠道仅限子 schema；
   父状态中 `customer_email` / `ship_to_city` 等仍在**父 Channel** 中传递，但子图内部函数**不声明**这些键，
   团队约定「WMS 包下禁止引用父级 PII 字段」（类型检查可配合 TypedDict/mypy）。
2) **主图上的普通节点 + `input_schema=...`**：`payment_recon` 只对 `PaymentReconInput` 可见字段做类型收窄，
   与官方文档 `add_node(fn, input_schema=NodeInput)` 一致（见 `langgraph.graph.state.StateGraph.add_node`  overload）。

注意：运行时 dict 仍可能含多余键；**防线 = schema/代码审查 + 出站 payload 序列化白名单 + 日志脱敏**。
本课示教「编排分层」与 LangGraph API，**不**替代安全审计。

主路径拓扑：

    START → wms_fulfillment（子图：仅 WmsSubState）→ payment_recon（input_schema 收窄）→ finalize_order → END

前置：已读 `09_subgraph_modular_graph.py`。
"""

from __future__ import annotations

from pathlib import Path

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


# ---------------------------------------------------------------------------
# 父图「全量状态」：仅编排器节点应读写 PII 汇总 / 业务总结
# ---------------------------------------------------------------------------
class OrderFullState(TypedDict, total=False):
    order_id: str  # 业务单号
    tenant_id: str  # 租户 / 店铺
    customer_email: str  # PII：客户邮箱（不得出现在 WMS 子图类型定义中）
    ship_to_city: str  # PII：收货城市（同理）
    sku: str  # 行项目物料编码
    qty: int  # 行项目数量
    payment_intent_id: str  # 第三方支付意图 id（对账用）
    amount_cents: int  # 对账金额（分）
    pick_ticket_id: str  # WMS 回写的拣货单号
    reconciliation_status: str  # 支付对账结果摘要
    orchestration_summary: str  # 给运营/审计的人类可读汇总


# ---------------------------------------------------------------------------
# 子图状态：仅含可下发给仓储接口的字段（与真实 WMS OpenAPI 请求体对齐思想）
# ---------------------------------------------------------------------------
class WmsSubState(TypedDict, total=False):
    order_id: str
    sku: str
    qty: int
    pick_ticket_id: str  # 子图内生成后 merge 回父状态


def wms_allocate_pick_ticket(state: WmsSubState) -> dict:
    """
    模拟 WMS「占库 + 出拣货单」：入参类型中**没有**邮箱/地址，避免误传到下游。
    """
    oid = state.get("order_id", "")
    sku = state.get("sku", "")
    qty = int(state.get("qty") or 0)
    print(f"  [WMS subgraph] allocate_pick_ticket(order_id={oid!r}, sku={sku!r}, qty={qty})")
    if qty <= 0:  # 简单校验
        return {"pick_ticket_id": "WMS-REJECT-BAD-QTY"}
    ticket = f"PICK-{oid}-{sku}"  # 教学占位：真实为 WMS 返回的票号
    print(f"  [WMS subgraph] -> pick_ticket_id={ticket!r}")
    return {"pick_ticket_id": ticket}


def build_wms_subgraph() -> StateGraph:
    """仓储子图：单节点即可说明子 schema；多节点时仍只用 WmsSubState。"""
    g = StateGraph(WmsSubState)
    g.add_node("allocate_pick_ticket", wms_allocate_pick_ticket)
    g.add_edge(START, "allocate_pick_ticket")
    g.add_edge("allocate_pick_ticket", END)
    return g


# ---------------------------------------------------------------------------
# 支付对账节点：主图节点 + input_schema —— API 形状与 PSP 查询参数一致
# ---------------------------------------------------------------------------
class PaymentReconInput(TypedDict, total=False):
    order_id: str
    payment_intent_id: str
    amount_cents: int


def payment_recon(state: PaymentReconInput) -> dict:
    """
    模拟「支付网关对账」RPC：仅依赖 intent + 金额，符合最小暴露原则。
    函数签名 + PaymentReconInput 即团队契约；不要在函数体内访问未声明字段。
    """
    pid = state.get("payment_intent_id", "")
    cents = int(state.get("amount_cents") or 0)
    oid = state.get("order_id", "")
    print(f"  [PaymentRecon node] PSP lookup intent={pid!r} amount_cents={cents} (order_id={oid!r})")
    ok = bool(pid) and cents > 0  # 教学占位：真实为 PSP 返回状态
    status = "matched_psp_record" if ok else "recon_failed_missing_fields"
    return {"reconciliation_status": status}


def finalize_order(state: OrderFullState) -> dict:
    """编排收口：只有这里「合法」把 PII 与业务结果写进一段给人看的总结（可对接审计日志）。"""
    email = state.get("customer_email", "")
    city = state.get("ship_to_city", "")
    summary = (
        f"[Orchestrator] 订单 {state.get('order_id')} 结案：\n"
        f"  - 拣货单: {state.get('pick_ticket_id')}\n"
        f"  - 对账: {state.get('reconciliation_status')}\n"
        f"  - PII 仅本节点拼接展示: email 尾缀 …{email[-8:] if len(email) > 8 else email} / city={city!r}\n"
        f"  - WMS 子图与 PaymentRecon 的 input_schema 均不包含上述 PII 字段定义。"
    )
    print("\n[finalize_order] 写入 orchestration_summary")
    return {"orchestration_summary": summary}


def build_main_graph() -> StateGraph:
    """父图状态为 OrderFullState；嵌入 WMS 子图 + 窄输入对账节点。"""
    wms_compiled = build_wms_subgraph().compile()
    main = StateGraph(OrderFullState)
    main.add_node("wms_fulfillment", wms_compiled)
    main.add_node("payment_recon", payment_recon, input_schema=PaymentReconInput)
    main.add_node("finalize_order", finalize_order)
    main.add_edge(START, "wms_fulfillment")
    main.add_edge("wms_fulfillment", "payment_recon")
    main.add_edge("payment_recon", "finalize_order")
    main.add_edge("finalize_order", END)
    return main


def export_graph_image(graph) -> None:
    go = graph.get_graph()
    png = Path(__file__).with_name("09b_order_subgraph_input_schema_graph.png")
    mmd = Path(__file__).with_name("09b_order_subgraph_input_schema_graph.mmd")
    try:
        png.write_bytes(go.draw_mermaid_png())
        print(f"[图导出] {png}")
    except Exception as exc:  # noqa: BLE001
        mmd.write_text(go.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mmd}")


def demo() -> None:
    g = build_main_graph().compile()
    export_graph_image(g)

    initial: OrderFullState = {
        "order_id": "SO-9001",
        "tenant_id": "TEN-A",
        "customer_email": "buyer@example.com",
        "ship_to_city": "上海",
        "sku": "SKU-豆乳-1L",
        "qty": 3,
        "payment_intent_id": "pi_mock_abc123",
        "amount_cents": 19900,
        "pick_ticket_id": "",
        "reconciliation_status": "",
        "orchestration_summary": "",
    }

    print("=" * 72)
    print("09b 生产向示例：全量订单状态 → WMS 子图（WmsSubState）→ 对账节点（PaymentReconInput）→ 汇总")
    print("=" * 72)
    out = g.invoke(initial)
    print("\n--- orchestration_summary ---")
    print(out.get("orchestration_summary", ""))
    print("\n--- 仍可读的父状态键（含 PII）---")
    print("customer_email:", out.get("customer_email"))
    print("pick_ticket_id:", out.get("pick_ticket_id"))
    print("reconciliation_status:", out.get("reconciliation_status"))

    print("\n本课要点：")
    print("- 子图用更小的 TypedDict 定义「可出站给 WMS 的数据契约」")
    print("- 对账用 add_node(..., input_schema=PaymentReconInput) 与官方进阶一致")
    print("- 生产还须：出站序列化白名单、密钥分环境、日志脱敏、代码评审")


if __name__ == "__main__":
    demo()
