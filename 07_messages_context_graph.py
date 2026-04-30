"""
第七课：消息状态与对话上下文

目标：
1) 用 LangGraph 标准 `add_messages` 把对话存进 state，而不是零散字符串字段
2) 可选裁剪历史（超窗口时丢掉旧消息，避免 token 膨胀）
3) 演示「多轮」：在同一张图上多次 invoke，手动把上一轮的 messages 传回（Checkpoint 见第 12 课）

图结构（与大纲一致）：

    START
      -> append_user_message
      -> (空输入则 empty_input_node，否则)
      -> trim_history
      -> generate_with_context（本课把「写入 assistant」合在这一步：返回 AIMessage）
      -> END

说明：大纲里的 append_assistant_message 与 generate 合并——模型产出即用 AIMessage 追加进 messages，
     少一层空转节点，语义相同。

前置：第六课 `06_llm_integration_graph.py`（本课复用环境与 LLM 调用习惯）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from typing_extensions import NotRequired, TypedDict


class MessageChatState(TypedDict):
    """
    messages：对话轨迹，必须用 Annotated[..., add_messages] 合并多节点写入。
    pending_user_text：本轮要追加的用户话（演示用；真实服务里可来自 HTTP 请求体）。
    mode：llm / fallback（无 Key 时可稳定跑通）。
    max_messages_to_keep：>0 时在 trim_history 里只保留最后 N **条消息**；<=0 表示不裁剪。
    input_valid：append_user_message 设置；用于路由到空输入分支。
    """

    messages: Annotated[list[AnyMessage], add_messages]
    pending_user_text: str
    mode: Literal["llm", "fallback"]
    max_messages_to_keep: int
    input_valid: NotRequired[bool]


def get_llm_config() -> tuple[str, str, str, str]:
    """与第六课一致：openai / ark。"""
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
        model = os.getenv("OPENAI_MODEL", "gpt-5.5").strip()
    return provider, api_key, base_url, model


def validate_llm_config(provider: str, api_key: str, base_url: str, model: str) -> None:
    if not api_key:
        raise ValueError(f"{provider} api_key is missing")
    if not base_url:
        raise ValueError(f"{provider} base_url is missing")
    if not model:
        raise ValueError(f"{provider} model is missing")


def _ark_response_to_text(response: object) -> str:
    """与第六课思路一致：兼容 Ark responses.create 多版本返回结构。"""
    output_text = getattr(response, "output_text", "") or ""
    if output_text:
        return str(output_text).strip()
    out_list = getattr(response, "output", None) or []
    pieces: list[str] = []
    for item in out_list:
        if getattr(item, "type", None) == "message":
            for block in getattr(item, "content", []) or []:
                t = getattr(block, "text", None)
                if t:
                    pieces.append(str(t))
    if pieces:
        return "\n".join(pieces).strip()
    out_obj = getattr(response, "output", None)
    maybe_text = getattr(out_obj, "text", "") if out_obj is not None else ""
    if maybe_text:
        return str(maybe_text).strip()
    return str(response)


def append_user_message(state: MessageChatState) -> dict:
    text = (state.get("pending_user_text") or "").strip()
    if not text:
        return {"input_valid": False}
    return {
        "messages": [HumanMessage(content=text)],
        "input_valid": True,
    }


def route_after_append(
    state: MessageChatState,
) -> Literal["trim_history", "empty_input_node"]:
    if state.get("input_valid") is True:
        return "trim_history"
    return "empty_input_node"


def empty_input_node(_: MessageChatState) -> dict:
    return {
        "messages": [AIMessage(content="【边界】pending_user_text 为空，未追加用户消息。")],
    }


def trim_history(state: MessageChatState) -> dict:
    """
    仅保留最近 max_messages_to_keep 条消息（Human/AI 各算一条）。
    <=0：不裁剪。
    实现：先 RemoveMessage(REMOVE_ALL_MESSAGES) 清空，再写回保留后缀（add_messages 语义）。
    """
    cap = state["max_messages_to_keep"]
    msgs = list(state["messages"])
    if cap <= 0 or len(msgs) <= cap:
        return {}
    kept = msgs[-cap:]
    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            *kept,
        ],
    }


def _format_context_for_fallback(messages: list[AnyMessage]) -> str:
    parts: list[str] = []
    for m in messages:
        role = type(m).__name__.replace("Message", "")
        parts.append(f"- {role}: {m.content!s}")
    return "\n".join(parts)


def generate_with_context(state: MessageChatState) -> dict:
    """
    用当前 messages 作为上下文调用模型；fallback 下用规则拼接最近若干条，不访问外网。
    """
    msgs = state["messages"]
    if state["mode"] == "fallback":
        ctx = _format_context_for_fallback(msgs)
        reply = (
            "【Fallback】以下是当前 messages 摘要（用于理解上下文如何汇总）：\n"
            f"{ctx}\n----\n"
            "（配置 LLM 与密钥后可将 mode 设为 llm 走真实多轮。）"
        )
        return {"messages": [AIMessage(content=reply)]}

    provider, api_key, base_url, model = get_llm_config()
    try:
        validate_llm_config(provider, api_key, base_url, model)
    except Exception as exc:  # noqa: BLE001
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"【配置无效，退回规则答复】{exc}\n"
                        + _format_context_for_fallback(msgs)
                    ),
                ),
            ],
        }

    system = SystemMessage(
        content=(
            "你是一个简洁的中文助手。请结合完整对话历史回答；"
            "若用户要求回忆前文，必须基于历史，不要编造。"
        ),
    )
    to_invoke = [system, *msgs]

    try:
        if provider == "ark":
            from volcenginesdkarkruntime import Ark

            client = Ark(base_url=base_url, api_key=api_key)
            # Ark 单串 input：把消息简单拼成一页文本，教学用与 06 一致思路
            blob = "\n".join(
                f"[{type(m).__name__}]: {m.content!s}" for m in to_invoke
            )
            response = client.responses.create(model=model, input=blob)
            text = _ark_response_to_text(response)
        else:
            llm = ChatOpenAI(
                model=model,
                temperature=0.2,
                api_key=api_key,
                base_url=base_url,
            )
            result = llm.invoke(to_invoke)
            text = result.content if hasattr(result, "content") else str(result)
    except Exception as exc:  # noqa: BLE001
        text = f"【LLM 调用失败】{exc}\n" + _format_context_for_fallback(msgs)

    return {"messages": [AIMessage(content=text)]}


def build_graph():
    b = StateGraph(MessageChatState)
    b.add_node("append_user_message", append_user_message)
    b.add_node("empty_input_node", empty_input_node)
    b.add_node("trim_history", trim_history)
    b.add_node("generate_with_context", generate_with_context)

    b.add_edge(START, "append_user_message")
    b.add_conditional_edges(
        "append_user_message",
        route_after_append,
        {
            "trim_history": "trim_history",
            "empty_input_node": "empty_input_node",
        },
    )
    b.add_edge("trim_history", "generate_with_context")
    b.add_edge("empty_input_node", END)
    b.add_edge("generate_with_context", END)
    return b.compile()


def export_graph_image(graph) -> None:
    graph_obj = graph.get_graph()
    png_path = Path(__file__).with_name("07_messages_context_graph.png")
    mermaid_path = Path(__file__).with_name("07_messages_context_graph.mmd")
    try:
        png_path.write_bytes(graph_obj.draw_mermaid_png())
        print(f"[图导出] {png_path}")
    except Exception as exc:  # noqa: BLE001
        mermaid_path.write_text(graph_obj.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mermaid_path}")


def _base_initial(
    pending: str,
    mode: Literal["llm", "fallback"],
    max_keep: int,
    existing_messages: list[AnyMessage] | None = None,
) -> MessageChatState:
    return {
        "messages": list(existing_messages or []),
        "pending_user_text": pending,
        "mode": mode,
        "max_messages_to_keep": max_keep,
    }


def demo() -> None:
    load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=False)
    g = build_graph()
    export_graph_image(g)

    print("=" * 72)
    print("1) Happy Path：fallback 多轮（手动传入上一轮 messages）")
    print("=" * 72)
    s1 = g.invoke(_base_initial("我叫小明，请记住。", "fallback", 0))
    print("--- 第一轮最后一条 AI ---")
    print(s1["messages"][-1].content)

    s2 = g.invoke(
        _base_initial(
            "我刚才说我叫什么？",
            "fallback",
            0,
            existing_messages=s1["messages"],
        ),
    )
    print("--- 第二轮最后一条 AI ---")
    print(s2["messages"][-1].content)

    print("\n" + "=" * 72)
    print("2) 边界：裁剪 max_messages_to_keep=2，再追问名字（预期记不住）")
    print("=" * 72)
    long_ctx = list(s2["messages"])
    s3 = g.invoke(
        _base_initial("只问好。", "fallback", 2, existing_messages=long_ctx),
    )
    print(f"裁剪后消息条数: {len(s3['messages'])}")
    print("最后一条 AI:", s3["messages"][-1].content[:200], "...")

    print("\n" + "=" * 72)
    print("3) Failure Path：空用户输入 -> empty_input_node")
    print("=" * 72)
    bad = g.invoke(_base_initial("   ", "fallback", 0))
    print(bad["messages"][-1].content)

    print("\n" + "=" * 72)
    print("4) LLM 模式（需有效配置；否则 generate 内退回规则/错误文本）")
    print("=" * 72)
    s_llm = g.invoke(_base_initial("用一句话介绍 LangGraph。", "llm", 0))
    print(s_llm["messages"][-1].content[:800])

    print("\n本课 DoD：")
    print("- 主路径：1)+4) 能跑通其一（建议 fallback 必绿）")
    print("- 故障/边界：3) 空输入 + 2) 裁剪导致上下文丢失")
    print("- 回归：python 07_messages_context_graph.py")
    print('- 接口稳定字段：messages / pending_user_text / mode / max_messages_to_keep')


if __name__ == "__main__":
    demo()
