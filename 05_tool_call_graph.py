"""
第五课：工具调用基础（Tool Node）

前四课我们已经掌握：
1) 线性流程
2) 条件分支
3) 循环重试
4) mini-agent（分支 + 循环 + 评估）

这一课进入非常关键的一步：工具调用。

在真实 Agent 场景中，模型并不总是“直接回答”，
而是会决定“是否调用工具”来获取更可靠的外部能力，例如：
- 计算器
- 时间查询
- 搜索接口
- 数据库查询
- 业务 API

本示例先不接 LLM 的 function calling，
而是先把“工具节点工作流”学明白：

START
  -> decide_tool              # 判断要不要用工具，用哪个工具
  -> (calculator / time / no_tool)
  -> finalize_result          # 统一整理输出
  -> END

学习重点：
1. 如何把 Python 函数封装成“工具节点”
2. 如何设计工具输入输出字段
3. 工具失败时如何把错误写回 state
4. 多工具路由的基本图结构
"""

from datetime import datetime
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class ToolState(TypedDict):
    """
    工具调用示例的状态结构。

    字段说明：
    - user_input: 用户输入
    - selected_tool: 选中的工具名（calculator / time / no_tool）
    - tool_input: 提取出的工具输入（例如数学表达式）
    - tool_output: 工具执行结果
    - tool_error: 工具执行错误（若失败）
    - final_answer: 最终回复文本
    - step_count: 节点执行计数（学习观察用）
    """

    user_input: str
    selected_tool: str
    tool_input: str
    tool_output: str
    tool_error: str
    final_answer: str
    step_count: int


def decide_tool(state: ToolState) -> ToolState:
    """
    决策节点：根据输入判断是否调用工具，以及调用哪个工具。

    教学版规则（故意简单）：
    - 含“几点/时间/现在” -> time
    - 含“计算”或包含 + - * / -> calculator
    - 否则 -> no_tool

    真实项目里，这里通常由 LLM 决定（tool calling），
    但路由结构本质上是一样的。
    """

    user_input = state["user_input"]
    normalized = user_input.replace(" ", "")

    print("\n[decide_tool] 节点开始执行")
    print(f"[decide_tool] user_input: {user_input}")

    if any(keyword in user_input for keyword in ("几点", "时间", "现在")):
        selected_tool = "time"
        tool_input = ""
    elif "计算" in user_input or any(op in normalized for op in ("+", "-", "*", "/")):
        selected_tool = "calculator"

        # 简单提取表达式：
        # - 如果有“计算”，取它后面的字符串
        # - 否则直接使用原输入
        if "计算" in user_input:
            tool_input = user_input.split("计算", maxsplit=1)[1].strip()
        else:
            tool_input = user_input
    else:
        selected_tool = "no_tool"
        tool_input = ""

    print(f"[decide_tool] selected_tool: {selected_tool}")
    print(f"[decide_tool] tool_input: {tool_input}")

    return {
        "selected_tool": selected_tool,
        "tool_input": tool_input,
        "step_count": state["step_count"] + 1,
        # 决策节点清空上一轮工具结果，避免状态污染。
        "tool_output": "",
        "tool_error": "",
    }


def route_tool(state: ToolState) -> Literal["calculator_tool", "time_tool", "no_tool_node"]:
    """
    路由函数：根据 selected_tool 选择下一节点。
    """

    selected_tool = state["selected_tool"]
    print("\n[route_tool] 路由函数开始执行")
    print(f"[route_tool] selected_tool: {selected_tool}")

    if selected_tool == "calculator":
        return "calculator_tool"
    if selected_tool == "time":
        return "time_tool"
    return "no_tool_node"


def calculator_tool(state: ToolState) -> ToolState:
    """
    计算器工具节点。

    这里使用 Python eval 做教学演示，因此做了非常严格的字符白名单校验：
    - 仅允许数字、空格、小数点、括号、+-*/%
    - 发现其他字符直接拒绝执行

    注意：真实生产环境不建议直接 eval 用户输入，
    应使用专门的表达式解析器（如 asteval / numexpr / 自定义 parser）。
    """

    expression = state["tool_input"]
    allowed_chars = set("0123456789+-*/%.() ")

    print("\n[calculator_tool] 节点开始执行")
    print(f"[calculator_tool] expression: {expression}")

    if not expression:
        return {
            "tool_error": "未找到可计算表达式，请在“计算”后提供表达式，例如：计算 12 * (3 + 5)",
            "step_count": state["step_count"] + 1,
        }

    if any(ch not in allowed_chars for ch in expression):
        return {
            "tool_error": "表达式包含非法字符，当前仅支持数字与 +-*/%()",
            "step_count": state["step_count"] + 1,
        }

    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return {
            "tool_output": f"{expression} = {result}",
            "step_count": state["step_count"] + 1,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "tool_error": f"计算失败：{exc}",
            "step_count": state["step_count"] + 1,
        }


def time_tool(state: ToolState) -> ToolState:
    """
    时间工具节点：返回当前本地时间。
    """

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n[time_tool] 节点开始执行")
    print(f"[time_tool] now: {now}")

    return {
        "tool_output": f"当前本地时间是：{now}",
        "step_count": state["step_count"] + 1,
    }


def no_tool_node(state: ToolState) -> ToolState:
    """
    无工具节点：当输入不需要工具时走这里。
    """

    print("\n[no_tool_node] 节点开始执行")
    return {
        "tool_output": "当前请求不需要工具，走直接回复逻辑。",
        "step_count": state["step_count"] + 1,
    }


def finalize_result(state: ToolState) -> ToolState:
    """
    汇总节点：把工具结果统一包装成最终回复。

    这样做的好处是：
    - 不管前面走哪个工具分支
    - 最终对外输出格式一致
    """

    print("\n[finalize_result] 节点开始执行")
    print(f"[finalize_result] state: {state}")

    if state["tool_error"]:
        final_answer = (
            f"工具 `{state['selected_tool']}` 执行失败。\n"
            f"错误信息：{state['tool_error']}\n"
            "建议：请调整输入后重试。"
        )
    elif state["selected_tool"] == "no_tool":
        final_answer = (
            "这是直接回复分支：\n"
            "当前输入未命中工具调用条件。"
        )
    else:
        final_answer = (
            f"工具 `{state['selected_tool']}` 执行成功。\n"
            f"结果：{state['tool_output']}"
        )

    return {
        "final_answer": final_answer,
        "step_count": state["step_count"] + 1,
    }


def build_graph():
    """
    构建工具调用图。
    """

    builder = StateGraph(ToolState)

    builder.add_node("decide_tool", decide_tool)
    builder.add_node("calculator_tool", calculator_tool)
    builder.add_node("time_tool", time_tool)
    builder.add_node("no_tool_node", no_tool_node)
    builder.add_node("finalize_result", finalize_result)

    builder.add_edge(START, "decide_tool")
    builder.add_conditional_edges(
        "decide_tool",
        route_tool,
        {
            "calculator_tool": "calculator_tool",
            "time_tool": "time_tool",
            "no_tool_node": "no_tool_node",
        },
    )

    builder.add_edge("calculator_tool", "finalize_result")
    builder.add_edge("time_tool", "finalize_result")
    builder.add_edge("no_tool_node", "finalize_result")
    builder.add_edge("finalize_result", END)

    return builder.compile()


def run_case(graph, user_input: str):
    """
    运行单个案例，观察不同输入触发的分支。
    """

    initial_state: ToolState = {
        "user_input": user_input,
        "selected_tool": "",
        "tool_input": "",
        "tool_output": "",
        "tool_error": "",
        "final_answer": "",
        "step_count": 0,
    }

    print("\n" + "=" * 80)
    print(f"开始案例：{user_input}")
    print("=" * 80)
    print(f"初始 state: {initial_state}")

    final_state = graph.invoke(initial_state)

    print("\n[案例结束]")
    print(f"selected_tool: {final_state['selected_tool']}")
    print(f"step_count: {final_state['step_count']}")
    print("final_answer:")
    print(final_state["final_answer"])


def main():
    """
    入口函数：演示三个常见输入场景。
    """

    graph = build_graph()

    # 场景1：计算器工具
    run_case(graph, "请帮我计算 12 * (3 + 5)")

    # 场景2：时间工具
    run_case(graph, "现在几点了？")

    # 场景3：不需要工具
    run_case(graph, "你好，简单介绍一下 LangGraph。")

    print("\n学习建议：")
    print("1) 在 decide_tool 中新增一个 weather_tool 分支练手")
    print("2) 故意输入非法表达式，观察 calculator_tool 的错误路径")
    print("3) 试着把 no_tool_node 改成调用 LLM 的直接回答节点")


if __name__ == "__main__":
    main()
