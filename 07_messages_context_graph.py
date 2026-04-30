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

自本课起：正文尽量「每行代码旁附注释」，便于对照阅读。
"""

from __future__ import annotations  # 推迟求值注解，允许类体内前向引用类型名

import os  # 读取环境变量（API Key、Base URL 等）
from pathlib import Path  # 跨平台路径，用于定位 .env 与导出图文件
from typing import Annotated, Literal  # Annotated：挂 reducer；Literal：限制 mode 枚举字符串

from dotenv import load_dotenv  # 从 .env 加载密钥到 os.environ，避免明文写进仓库
from langchain_core.messages import (
    AIMessage,  # 助手侧消息，generate 节点用它把模型回复写回 state
    AnyMessage,  # Human/AI/System 等消息基类的联合类型别名，便于标注列表元素
    HumanMessage,  # 用户侧消息，append 节点把本轮用户话封装成它
    RemoveMessage,  # 与 add_messages 配合：按 id 删除或配合 REMOVE_ALL 整表清空
    SystemMessage,  # 系统提示，仅参与 LLM 调用列表，不强制出现在持久 messages 里
)
from langchain_openai import ChatOpenAI  # OpenAI/兼容 HTTP 接口的聊天模型封装（与第六课一致）
from langgraph.graph import END, START, StateGraph, add_messages  # 图原语 + 消息列表合并 reducer
from langgraph.graph.message import REMOVE_ALL_MESSAGES  # RemoveMessage 的特殊 id：清空再追加 = 裁剪实现
from typing_extensions import NotRequired, TypedDict  # TypedDict：状态 schema；NotRequired：可选路由标记字段


class MessageChatState(TypedDict):
    """
    messages：对话轨迹，必须用 Annotated[..., add_messages] 合并多节点写入。
    pending_user_text：本轮要追加的用户话（演示用；真实服务里可来自 HTTP 请求体）。
    mode：llm / fallback（无 Key 时可稳定跑通）。
    max_messages_to_keep：>0 时在 trim_history 里只保留最后 N **条消息**；<=0 表示不裁剪。
    input_valid：append_user_message 设置；用于路由到空输入分支。
    """

    messages: Annotated[list[AnyMessage], add_messages]  # 对话历史；多节点返回的 messages 由 add_messages 归并
    pending_user_text: str  # 本轮待并入的用户文本（invoke 时由调用方写入）
    mode: Literal["llm", "fallback"]  # 是否调用外部模型：llm 走网络；fallback 本地拼字串
    max_messages_to_keep: int  # trim_history 保留条数上限；<=0 表示整段保留不裁
    input_valid: NotRequired[bool]  # append 节点写入：True 走裁剪+生成；False 走空输入分支


def get_llm_config() -> tuple[str, str, str, str]:
    """与第六课一致：openai / ark。"""
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()  # 读 PROVIDER，缺省 openai，统一小写
    if provider == "ark":  # 火山方舟官方 SDK 路径
        api_key = os.getenv("ARK_API_KEY", "").strip()  # 方舟 API Key
        base_url = os.getenv(  # 方舟 API 根地址，缺省北京区
            "ARK_BASE_URL",
            "https://ark.cn-beijing.volces.com/api/v3",
        ).strip()
        model = os.getenv("ARK_MODEL", "").strip()  # 方舟侧模型名（非 ep- 端点名，按控制台为准）
    else:  # 走 OpenAI 或任意 OpenAI 兼容端点
        provider = "openai"  # 归一化：非 ark 一律按 openai 兼容处理
        api_key = os.getenv("OPENAI_API_KEY", "").strip()  # 常见：OPENAI_API_KEY
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()  # 兼容层可改中转 URL
        model = os.getenv("OPENAI_MODEL", "gpt-5.5").strip()  # 缺省模型名，可被 .env 覆盖
    return provider, api_key, base_url, model  # 四元组供后续校验与调用


def validate_llm_config(  # 在真正请求前 fail-fast，错误信息比 HTTP 异常好读
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
) -> None:
    if not api_key:  # 无 Key 无法鉴权
        raise ValueError(f"{provider} api_key is missing")
    if not base_url:  # 无地址无法建连
        raise ValueError(f"{provider} base_url is missing")
    if not model:  # 无模型名 SDK 不知如何路由
        raise ValueError(f"{provider} model is missing")


def _ark_response_to_text(response: object) -> str:
    """与第六课思路一致：兼容 Ark responses.create 多版本返回结构。"""
    output_text = getattr(response, "output_text", "") or ""  # 新版 SDK 常见聚合字段
    if output_text:  # 有直接文本则用最省事路径
        return str(output_text).strip()
    out_list = getattr(response, "output", None) or []  # 否则遍历 output 列表拆块
    pieces: list[str] = []  # 收集 assistant 可见纯文本片段
    for item in out_list:  # 逐项检查（reasoning / message 等）
        if getattr(item, "type", None) == "message":  # 只取最终消息类型
            for block in getattr(item, "content", []) or []:  # content 可能是多块
                t = getattr(block, "text", None)  # 每块上的 text 字段
                if t:  # 有字才拼接
                    pieces.append(str(t))
    if pieces:  # 拼出 assistant 正文
        return "\n".join(pieces).strip()
    out_obj = getattr(response, "output", None)  # 再试旧式单对象 output.text
    maybe_text = getattr(out_obj, "text", "") if out_obj is not None else ""
    if maybe_text:  # 旧字段有值则返回
        return str(maybe_text).strip()
    return str(response)  # 最后兜底：字符串化整个响应，避免 None


def append_user_message(state: MessageChatState) -> dict:
    text = (state.get("pending_user_text") or "").strip()  # 取本轮用户输入并去空白
    if not text:  # 空串或纯空白：不追加 HumanMessage
        return {"input_valid": False}  # 标记无效，交给条件边走 empty_input_node
    return {
        "messages": [HumanMessage(content=text)],  # 用 add_messages 追加一条用户消息到 state
        "input_valid": True,  # 标记有效，继续 trim -> generate
    }


def route_after_append(  # conditional_edges 的路由函数：返回值必须是下游节点名之一
    state: MessageChatState,
) -> Literal["trim_history", "empty_input_node"]:
    if state.get("input_valid") is True:  # 上一轮 append 成功写入用户话
        return "trim_history"  # 先去裁剪再走生成
    return "empty_input_node"  # 否则短路到空输入说明节点


def empty_input_node(_: MessageChatState) -> dict:
    return {
        "messages": [AIMessage(content="【边界】pending_user_text 为空，未追加用户消息。")],  # 仅占位一条 AI，便于 stream 里看到终点
    }


def trim_history(state: MessageChatState) -> dict:
    """
    仅保留最近 max_messages_to_keep 条消息（Human/AI 各算一条）。
    <=0：不裁剪。
    实现：先 RemoveMessage(REMOVE_ALL_MESSAGES) 清空，再写回保留后缀（add_messages 语义）。
    """
    cap = state["max_messages_to_keep"]  # 读取配置上限
    msgs = list(state["messages"])  # 快照当前列表，避免遍历时结构变化
    if cap <= 0 or len(msgs) <= cap:  # 不裁或本身够短：本节点不写回 state
        return {}  # 空 dict 表示不产生更新
    kept = msgs[-cap:]  # 只留末尾 cap 条（含本轮刚 append 的用户消息）
    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),  # 先清空历史通道（add_messages 约定语义）
            *kept,  # 再按顺序写回要保留的消息，相当于“删除前缀”
        ],
    }


def _format_context_for_fallback(messages: list[AnyMessage]) -> str:
    parts: list[str] = []  # 每行一条「角色: 内容」
    for m in messages:  # 遍历当前所有消息
        role = type(m).__name__.replace("Message", "")  # 用类名推导 Human/AI/System 等标签
        parts.append(f"- {role}: {m.content!s}")  # !s 强制 str，避免非字符串 content 异常
    return "\n".join(parts)  # 合成多行文本供 fallback 展示


def generate_with_context(state: MessageChatState) -> dict:
    """
    用当前 messages 作为上下文调用模型；fallback 下用规则拼接最近若干条，不访问外网。
    """
    msgs = state["messages"]  # 已裁剪后的对话列表
    if state["mode"] == "fallback":  # 教学稳定路径：不发起网络请求
        ctx = _format_context_for_fallback(msgs)  # 把人机消息打成可读摘要
        reply = (
            "【Fallback】以下是当前 messages 摘要（用于理解上下文如何汇总）：\n"
            f"{ctx}\n----\n"
            "（配置 LLM 与密钥后可将 mode 设为 llm 走真实多轮。）"
        )  # 多行说明 + 摘要，帮助理解 messages 如何进上下文
        return {"messages": [AIMessage(content=reply)]}  # 助手回合也写进 messages，供下轮引用

    provider, api_key, base_url, model = get_llm_config()  # 拉环境与密钥
    try:
        validate_llm_config(provider, api_key, base_url, model)  # 缺参则进 except
    except Exception as exc:  # noqa: BLE001  # 捕获所有校验错误，转成 AI 回复不写 traceback 到控制台
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"【配置无效，退回规则答复】{exc}\n"
                        + _format_context_for_fallback(msgs)
                    ),
                ),  # 仍追加一条 AIMessage，保持 state 形状一致
            ],
        }

    system = SystemMessage(
        content=(
            "你是一个简洁的中文助手。请结合完整对话历史回答；"
            "若用户要求回忆前文，必须基于历史，不要编造。"
        ),
    )  # 系统层行为约束，与多轮 human/ai 历史分开更清晰
    to_invoke = [system, *msgs]  # 调用模型时的完整消息序列：先系统再历史

    try:
        if provider == "ark":  # 方舟：走官方 SDK单串 input
            from volcenginesdkarkruntime import Ark  # 延迟导入：没装包时不影响 fallback

            client = Ark(base_url=base_url, api_key=api_key)  # 构造客户端
            # Ark 单串 input：把消息简单拼成一页文本，教学用与 06 一致思路
            blob = "\n".join(
                f"[{type(m).__name__}]: {m.content!s}" for m in to_invoke
            )  # 多行字符串模拟 chat transcript
            response = client.responses.create(model=model, input=blob)  # HTTP 调用
            text = _ark_response_to_text(response)  # 解析为纯文本
        else:  # OpenAI 兼容：原生多消息
            llm = ChatOpenAI(
                model=model,  # 端点使用的模型 id
                temperature=0.2,  # 略随机，教学用低温度更稳
                api_key=api_key,  # 鉴权
                base_url=base_url,  # 可指向代理或兼容服务
            )
            result = llm.invoke(to_invoke)  # 传入 BaseMessage 列表
            text = result.content if hasattr(result, "content") else str(result)  # 取正文或降级 str
    except Exception as exc:  # noqa: BLE001  # 网络/限流/解析等一律吞掉，转成可读 AI 字串
        text = f"【LLM 调用失败】{exc}\n" + _format_context_for_fallback(msgs)

    return {"messages": [AIMessage(content=text)]}  # 模型响应进入历史，完成一轮对话闭环


def build_graph():
    b = StateGraph(MessageChatState)  # 用 TypedDict 声明状态 schema
    b.add_node("append_user_message", append_user_message)  # 节点1：写用户消息
    b.add_node("empty_input_node", empty_input_node)  # 节点2：空输入占位回复
    b.add_node("trim_history", trim_history)  # 节点3：按条数裁剪
    b.add_node("generate_with_context", generate_with_context)  # 节点4：生成助手消息

    b.add_edge(START, "append_user_message")  # 入口总是先做 append
    b.add_conditional_edges(
        "append_user_message",  # 从该节点出发
        route_after_append,  # 路由函数名（被 StateGraph 调用并传当前 state）
        {
            "trim_history": "trim_history",  # 返回值 -> 目标节点 id
            "empty_input_node": "empty_input_node",
        },
    )  # 映射表：保证路由返回值必有边
    b.add_edge("trim_history", "generate_with_context")  # 裁剪后一定生成
    b.add_edge("empty_input_node", END)  # 空输入直接结束
    b.add_edge("generate_with_context", END)  # 正常对话结束本 invoke
    return b.compile()  # 编译为可 invoke/stream 的对象


def export_graph_image(graph) -> None:
    graph_obj = graph.get_graph()  # 取出可绘制的图描述对象
    png_path = Path(__file__).with_name("07_messages_context_graph.png")  # PNG 与脚本同目录
    mermaid_path = Path(__file__).with_name("07_messages_context_graph.mmd")  # 无绘图依赖时回退
    try:
        png_path.write_bytes(graph_obj.draw_mermaid_png())  # 尝试转成 PNG 字节写入
        print(f"[图导出] {png_path}")  # 告知用户路径
    except Exception as exc:  # noqa: BLE001  # 缺 graphviz 等环境则降级
        mermaid_path.write_text(graph_obj.draw_mermaid(), encoding="utf-8")  # 文本 mermaid 仍可预览
        print(f"[图导出] PNG 失败 ({exc})，已写 {mermaid_path}")


def _base_initial(  # 拼初始 state，减少 demo 里重复字典
    pending: str,  # 本轮用户话
    mode: Literal["llm", "fallback"],  # 运行模式
    max_keep: int,  # 裁剪参数
    existing_messages: list[AnyMessage] | None = None,  # 多轮时传入上一轮末尾的 messages
) -> MessageChatState:
    return {
        "messages": list(existing_messages or []),  # 拷贝一份列表，避免外层被误改
        "pending_user_text": pending,  # 本轮新话
        "mode": mode,  # llm 或 fallback
        "max_messages_to_keep": max_keep,  # 0 表示不裁
    }


def demo() -> None:
    load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=False)  # 同目录 .env；override=False 保系统已设变量优先
    g = build_graph()  # 构图
    export_graph_image(g)  # 导出 PNG/MMD

    print("=" * 72)  # 分隔线
    print("1) Happy Path：fallback 多轮（手动传入上一轮 messages）")  # 案例标题
    print("=" * 72)
    s1 = g.invoke(_base_initial("我叫小明，请记住。", "fallback", 0))  # 第一轮：不裁剪
    print("--- 第一轮最后一条 AI ---")  # 说明
    print(s1["messages"][-1].content)  # 取最后一条消息正文

    s2 = g.invoke(  # 第二轮：把完整历史带回来
        _base_initial(
            "我刚才说我叫什么？",  # 依赖上一轮 self-intro
            "fallback",
            0,
            existing_messages=s1["messages"],  # 多轮关键：手动续写 messages
        ),
    )
    print("--- 第二轮最后一条 AI ---")
    print(s2["messages"][-1].content)

    print("\n" + "=" * 72)
    print("2) 边界：裁剪 max_messages_to_keep=2，再追问名字（预期记不住）")
    print("=" * 72)
    long_ctx = list(s2["messages"])  # 固定用第二轮末尾历史做实验
    s3 = g.invoke(
        _base_initial("只问好。", "fallback", 2, existing_messages=long_ctx),  # 只保留 2 条消息
    )
    print(f"裁剪后消息条数: {len(s3['messages'])}")  # 应小于等于裁剪前+本轮增量
    print("最后一条 AI:", s3["messages"][-1].content[:200], "...")  # 截断防刷屏

    print("\n" + "=" * 72)
    print("3) Failure Path：空用户输入 -> empty_input_node")
    print("=" * 72)
    bad = g.invoke(_base_initial("   ", "fallback", 0))  # 纯空白触发空输入分支
    print(bad["messages"][-1].content)  # 打印边界说明

    print("\n" + "=" * 72)
    print("4) LLM 模式（需有效配置；否则 generate 内退回规则/错误文本）")
    print("=" * 72)
    s_llm = g.invoke(_base_initial("用一句话介绍 LangGraph。", "llm", 0))  # 走真实或降级调用
    print(s_llm["messages"][-1].content[:800])  # 预览前 800 字

    print("\n本课 DoD：")  # 自检清单
    print("- 主路径：1)+4) 能跑通其一（建议 fallback 必绿）")
    print("- 故障/边界：3) 空输入 + 2) 裁剪导致上下文丢失")
    print("- 回归：python 07_messages_context_graph.py")
    print('- 接口稳定字段：messages / pending_user_text / mode / max_messages_to_keep')


if __name__ == "__main__":  # 脚本直跑入口
    demo()  # 执行全部教学案例
