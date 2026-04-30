"""
第六课：LLM 接入与提示词分层

这一课目标：
1) 把前面学过的图结构接入真实 LLM（langchain-openai）
2) 学会“提示词分层”：system prompt + task prompt
3) 保持接口稳定：即使没有配置 API Key，也能走 fallback 模式运行

核心思想：
- 图结构不变（START -> generate_answer -> END）
- 节点内部可以从“规则输出”升级为“LLM 输出”
- 通过状态字段控制运行模式（llm / fallback）
"""

import os
from pathlib import Path
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph


class LLMState(TypedDict):
    """
    第六课状态结构。

    字段说明：
    - user_input: 用户输入
    - task_type: 任务类型（qa / rewrite）
    - mode: 运行模式（llm / fallback）
    - provider: 当前选中的 provider（openai / ark）
    - system_prompt: 系统提示词（角色与规则）
    - task_prompt: 任务提示词（当前任务的具体要求）
    - answer: 最终生成结果
    - error: 执行中的错误信息
    """

    user_input: str
    task_type: str
    mode: Literal["llm", "fallback"]
    provider: str
    system_prompt: str
    task_prompt: str
    answer: str
    error: str


def detect_task_type(user_input: str) -> str:
    """
    简单任务分类：
    - 包含“改写/润色/重写” -> rewrite
    - 其他 -> qa
    """

    if any(keyword in user_input for keyword in ("改写", "润色", "重写")):
        return "rewrite"
    return "qa"


def build_prompts(task_type: str, user_input: str) -> tuple[str, str]:
    """
    提示词分层：
    - system_prompt：固定角色与质量规则
    - task_prompt：随任务动态变化
    """

    system_prompt = (
        "你是一个严谨的 AI 助手。"
        "回答要结构清晰、简洁、准确；"
        "如果信息不足，要明确说明假设。"
    )

    if task_type == "rewrite":
        task_prompt = (
            "请对下面这段文本进行改写，要求：保留原意、表达更自然、语句更精炼。\n"
            f"原文：{user_input}"
        )
    else:
        task_prompt = (
            "请回答下面的问题，要求：先给结论，再给 2-3 条要点解释。\n"
            f"问题：{user_input}"
        )

    return system_prompt, task_prompt


def get_llm_config() -> tuple[str, str, str, str]:
    """
    从环境变量读取 LLM 提供方配置。

    支持：
    - openai（默认）
    - ark（火山引擎方舟，官方 SDK）
    """

    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    if provider == "ark":
        api_key = os.getenv("ARK_API_KEY", "").strip()
        base_url = os.getenv(
            "ARK_BASE_URL",
            "https://ark.cn-beijing.volces.com/api/v3",
        ).strip()
        # Ark SDK 里 model 可直接使用模型名（如 doubao-seed-2-0-lite-260215）
        model = os.getenv("ARK_MODEL", "").strip()
    else:
        provider = "openai"
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.getenv("OPENAI_MODEL", "gpt-5.5").strip()

    return provider, api_key, base_url, model


def build_ark_input_text(state: LLMState) -> str:
    """
    Ark SDK 的 input 只有一个字符串，因此我们把 system_prompt/task_prompt 手工拼起来，
    以保持三种 provider 的提示词结构一致，便于你学习理解。
    """

    return (
        "【系统要求】\n"
        f"{state['system_prompt']}\n"
        "【用户任务】\n"
        f"{state['task_prompt']}"
    )


def build_openai_messages(state: LLMState) -> list:
    """
    OpenAI / OpenAI-兼容接口：使用 SystemMessage + HumanMessage。
    """

    return [
        SystemMessage(content=state["system_prompt"]),
        HumanMessage(content=state["task_prompt"]),
    ]


def validate_llm_config(provider: str, api_key: str, base_url: str, model: str) -> None:
    """
    调用前做必要校验，避免你遇到难读的网络/404 错误才发现是配置问题。
    """

    if not api_key:
        raise ValueError(f"{provider} api_key is missing")
    if not base_url:
        raise ValueError(f"{provider} base_url is missing")
    if not model:
        raise ValueError(f"{provider} model is missing")

    # 兼容层常见坑：model 需要填 endpoint_id（通常 ep-xxxxxx），不是展示名。
    if provider == "volcengine" and not model.startswith("ep-"):
        raise ValueError(
            "volcengine model should be endpoint_id (ep-xxx)。"
            "请在方舟控制台选择 endpoint_id 填入 VOLCENGINE_MODEL。"
        )


def call_openai_compatible_llm(
    state: LLMState,
    api_key: str,
    base_url: str,
    model: str,
) -> str:
    """调用 OpenAI / OpenAI-兼容接口（包括 volcengine 兼容层）。"""

    llm = ChatOpenAI(
        model=model,
        temperature=0.2,
        api_key=api_key,
        base_url=base_url,
    )
    result = llm.invoke(build_openai_messages(state))
    return result.content


def call_ark_llm(
    state: LLMState,
    api_key: str,
    base_url: str,
    model: str,
) -> str:
    """调用火山引擎官方 Ark SDK。"""

    # 延迟导入，避免未安装 SDK 时影响其他 provider 路径。
    from volcenginesdkarkruntime import Ark

    client = Ark(
        base_url=base_url,
        api_key=api_key,
    )
    response = client.responses.create(
        model=model,
        input=build_ark_input_text(state),
    )

    # 兼容不同 SDK 版本：优先 output_text，不存在则退化为字符串化。
    output_text = getattr(response, "output_text", "")  # 常见情况
    if output_text:
        return output_text

    output_obj = getattr(response, "output", None)
    maybe_text = getattr(output_obj, "text", "") if output_obj is not None else ""
    if maybe_text:
        return maybe_text

    return str(response)


def init_request(state: LLMState) -> LLMState:
    """
    初始化节点：识别任务类型并构造分层提示词。
    """

    user_input = state["user_input"]
    task_type = detect_task_type(user_input)
    system_prompt, task_prompt = build_prompts(task_type, user_input)

    print("\n[init_request] 节点开始执行")
    print(f"[init_request] task_type: {task_type}")
    print(f"[init_request] mode: {state['mode']}")

    return {
        "task_type": task_type,
        "system_prompt": system_prompt,
        "task_prompt": task_prompt,
        "provider": "",
        "error": "",
    }


def route_mode(state: LLMState) -> Literal["fallback_node", "load_llm_config"]:
    """
    第一层路由：决定是否走 LLM 调用链。
    """

    return "fallback_node" if state["mode"] == "fallback" else "load_llm_config"


def fallback_node(state: LLMState) -> LLMState:
    """
    fallback 节点：不调用外部 API，直接返回教学占位答案。
    """

    return {
        "answer": (
            "【Fallback 模式】当前未调用真实 LLM。\n"
            f"任务类型：{state['task_type']}\n"
            "你可以在配置 LLM_PROVIDER 与对应 API Key 后切换到 llm 模式。"
        )
    }


def load_llm_config(state: LLMState) -> LLMState:
    """
    配置加载节点：读取 provider 并做基础校验。
    """

    provider, api_key, base_url, model = get_llm_config()
    try:
        validate_llm_config(provider, api_key, base_url, model)
        return {"provider": provider, "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {"provider": provider, "error": str(exc)}


def route_provider(state: LLMState) -> Literal["call_openai_node", "call_ark_node", "config_error_node"]:
    """
    第二层路由：根据 provider 和配置校验结果决定下一步。
    """

    if state["error"]:
        return "config_error_node"
    if state["provider"] == "ark":
        return "call_ark_node"
    return "call_openai_node"


def config_error_node(state: LLMState) -> LLMState:
    """
    配置异常节点：统一输出可读错误。
    """

    return {
        "answer": (
            "【自动回退到 Fallback】配置校验失败。\n"
            f"provider：{state['provider'] or 'unknown'}\n"
            f"错误：{state['error']}\n"
            "请检查 API Key、Base URL、模型名或 endpoint_id 配置。"
        )
    }


def call_openai_node(state: LLMState) -> LLMState:
    """
    OpenAI/兼容层调用节点。
    """

    provider, api_key, base_url, model = get_llm_config()
    try:
        answer = call_openai_compatible_llm(state, api_key, base_url, model)
        return {"answer": answer, "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {
            "answer": (
                "【自动回退到 Fallback】LLM 调用失败。\n"
                f"provider：{provider}\n"
                f"错误：{exc}\n"
                f"任务类型：{state['task_type']}\n"
                "请检查 API Key、Base URL、模型名、网络或权限。"
            ),
            "error": str(exc),
        }


def call_ark_node(state: LLMState) -> LLMState:
    """
    Ark 官方 SDK 调用节点。
    """

    provider, api_key, base_url, model = get_llm_config()
    try:
        answer = call_ark_llm(state, api_key, base_url, model)
        return {"answer": answer, "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {
            "answer": (
                "【自动回退到 Fallback】LLM 调用失败。\n"
                f"provider：{provider}\n"
                f"错误：{exc}\n"
                f"任务类型：{state['task_type']}\n"
                "请检查 API Key、Base URL、模型名、网络或权限。"
            ),
            "error": str(exc),
        }


def build_graph():
    """
    构建第六课图：

    START
      -> init_request
      -> route_mode
      -> fallback_node
         or load_llm_config -> route_provider
             -> call_openai_node / call_ark_node / config_error_node
      -> END
    """

    builder = StateGraph(LLMState)
    builder.add_node("init_request", init_request)
    builder.add_node("fallback_node", fallback_node)
    builder.add_node("load_llm_config", load_llm_config)
    builder.add_node("config_error_node", config_error_node)
    builder.add_node("call_openai_node", call_openai_node)
    builder.add_node("call_ark_node", call_ark_node)

    builder.add_edge(START, "init_request")
    builder.add_conditional_edges(
        "init_request",
        route_mode,
        {
            "fallback_node": "fallback_node",
            "load_llm_config": "load_llm_config",
        },
    )
    builder.add_conditional_edges(
        "load_llm_config",
        route_provider,
        {
            "call_openai_node": "call_openai_node",
            "call_ark_node": "call_ark_node",
            "config_error_node": "config_error_node",
        },
    )

    builder.add_edge("fallback_node", END)
    builder.add_edge("config_error_node", END)
    builder.add_edge("call_openai_node", END)
    builder.add_edge("call_ark_node", END)

    return builder.compile()


def export_graph_image(graph) -> None:
    """
    导出图结构图片。
    优先输出 PNG；若依赖环境不支持，则回退导出 mermaid 文本。
    """

    graph_obj = graph.get_graph()
    png_path = Path(__file__).with_name("06_llm_integration_graph.png")
    mermaid_path = Path(__file__).with_name("06_llm_integration_graph.mmd")

    try:
        png_bytes = graph_obj.draw_mermaid_png()
        png_path.write_bytes(png_bytes)
        print(f"[图导出] 已生成 PNG: {png_path}")
    except Exception as exc:  # noqa: BLE001
        mermaid_text = graph_obj.draw_mermaid()
        mermaid_path.write_text(mermaid_text, encoding="utf-8")
        print(f"[图导出] PNG 导出失败：{exc}")
        print(f"[图导出] 已回退导出 Mermaid: {mermaid_path}")


def run_case(graph, user_input: str, mode: Literal["llm", "fallback"]):
    """
    执行单个案例，观察 LLM 模式与 fallback 模式差异。
    """

    initial_state: LLMState = {
        "user_input": user_input,
        "task_type": "",
        "mode": mode,
        "provider": "",
        "system_prompt": "",
        "task_prompt": "",
        "answer": "",
        "error": "",
    }

    print("\n" + "=" * 80)
    print(f"开始案例 mode={mode}: {user_input}")
    print("=" * 80)

    final_state = graph.invoke(initial_state)

    print("[案例结束]")
    print(f"task_type: {final_state['task_type']}")
    print("answer:")
    print(final_state["answer"])
    if final_state["error"]:
        print(f"error: {final_state['error']}")


def main():
    """
    入口函数：
    - 先加载 .env（如果存在）
    - 演示 fallback 与 llm 两种模式
    """

    # 固定从当前脚本所在目录加载 .env，避免从其他工作目录运行时读取失败。
    dotenv_path = Path(__file__).with_name(".env")
    load_dotenv(dotenv_path=dotenv_path, override=False)
    provider, _, base_url, model = get_llm_config()
    print(f"[配置] LLM_PROVIDER={provider}, MODEL={model}, BASE_URL={base_url}")
    graph = build_graph()
    export_graph_image(graph)

    # 案例1：Fallback 模式（稳定可运行）
    run_case(graph, "请解释一下 LangGraph 和 LangChain 的关系。", mode="llm")

    # 案例2：LLM 模式（需要有效 provider 配置）
    run_case(graph, "请把这句话改写得更专业：java世界上最好的语言。", mode="llm")

    print("\n学习建议：")
    print("1) 修改 system_prompt，观察回答风格变化")
    print("2) 修改 task_prompt 模板，观察结构稳定性变化")
    print("3) 把 mode 全部改成 llm，体验真实模型输出")
    print("4) 想用火山官方 SDK 时，将 LLM_PROVIDER 设置为 ark")


if __name__ == "__main__":
    main()
