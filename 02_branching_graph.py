"""
第二课：理解 LangGraph 的条件分支（Branching / Routing）

第一课里，我们学习的是最简单的固定流程：

START -> 节点 A -> 节点 B -> END

这种图的特点是：
- 执行路线是写死的
- 不管输入是什么，都会走同一条路

但真实项目里，往往需要“根据当前状态决定下一步去哪里”。

例如：
- 如果用户问的是天气，就走“天气处理节点”
- 如果用户问的是数学题，就走“数学处理节点”
- 如果用户只是闲聊，就走“普通回复节点”

这就是 LangGraph 的分支能力。

本节你会学到：
1. 什么是“路由函数”
2. `add_conditional_edges(...)` 是怎么用的
3. 图如何根据 state 的内容，自动走向不同节点
4. 为什么 LangGraph 很适合 Agent / 工作流 / 多步骤决策系统
"""

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


# 这个状态结构比第一课稍微丰富一点。
# 我们新增了 route 字段，用来记录“当前应该走哪条分支”。
#
# 字段说明：
# - user_input: 用户输入的问题
# - route: 路由结果，表示后续要走哪个节点
# - answer: 节点处理后生成的结果
# - step_count: 用来观察图执行了几个节点
class BranchingState(TypedDict):
    user_input: str
    route: str
    answer: str
    step_count: int


def analyze_input(state: BranchingState) -> BranchingState:
    """
    第一个业务节点：分析用户输入。

    这个节点本身并不负责真正“回答问题”，
    它只做一件事：
    根据输入内容，先把 route 决定出来。

    这里为了方便学习，我们故意使用最朴素的关键词判断：
    - 包含“天气” -> weather
    - 包含“计算”或“+” -> math
    - 否则 -> chat

    在真实项目中，这里也可以换成：
    - LLM 路由
    - 分类器
    - 规则系统
    - 工具可用性判断
    """

    user_input = state["user_input"]

    print("\n[analyze_input] 节点开始执行")
    print(f"[analyze_input] 收到的 state: {state}")

    if "天气" in user_input:
        route = "weather"
    elif "计算" in user_input or "+" in user_input:
        route = "math"
    else:
        route = "chat"

    print(f"[analyze_input] 判断得到 route: {route}")

    return {
        "route": route,
        "step_count": state["step_count"] + 1,
    }


def route_next_step(state: BranchingState) -> Literal["weather_node", "math_node", "chat_node"]:
    """
    路由函数：决定“下一个节点是谁”。

    这是本节最重要的函数之一。

    注意它和普通节点函数的区别：
    - 普通节点函数：返回状态更新字典
    - 路由函数：返回“下一个节点的名字”

    换句话说：
    它不是在改数据，而是在“指路”。
    """

    route = state["route"]

    print("\n[route_next_step] 路由函数开始执行")
    print(f"[route_next_step] 当前 route: {route}")

    if route == "weather":
        return "weather_node"
    if route == "math":
        return "math_node"
    return "chat_node"


def weather_node(state: BranchingState) -> BranchingState:
    """
    天气分支节点。

    这里我们先不用真实天气 API，
    只是模拟“如果命中了天气类问题，会进入专门节点处理”。
    """

    print("\n[weather_node] 节点开始执行")
    print(f"[weather_node] 收到的 state: {state}")

    answer = (
        "这是天气分支给出的模拟回复："
        "你当前的问题被识别为天气相关，后续可以在这里接入真实天气 API。"
    )

    return {
        "answer": answer,
        "step_count": state["step_count"] + 1,
    }


def math_node(state: BranchingState) -> BranchingState:
    """
    数学分支节点。

    为了保持学习重点在“路由”上，
    这里不做复杂表达式解析，只返回说明性结果。

    后面如果你愿意，我们可以专门做一课：
    - 让路由进入数学工具节点
    - 再调用 Python 真实计算
    """

    print("\n[math_node] 节点开始执行")
    print(f"[math_node] 收到的 state: {state}")

    answer = (
        "这是数学分支给出的模拟回复："
        "你的问题被识别为计算相关，后续可以在这里接入计算工具。"
    )

    return {
        "answer": answer,
        "step_count": state["step_count"] + 1,
    }


def chat_node(state: BranchingState) -> BranchingState:
    """
    普通聊天分支节点。

    当前输入如果既不是天气，也不是计算，
    就会走到这个默认分支。
    """

    print("\n[chat_node] 节点开始执行")
    print(f"[chat_node] 收到的 state: {state}")

    answer = (
        "这是普通聊天分支给出的模拟回复："
        "当前输入没有命中特定业务路由，所以进入默认聊天处理。"
    )

    return {
        "answer": answer,
        "step_count": state["step_count"] + 1,
    }


def build_graph():
    """
    构建带条件分支的图。

    这节和第一课最大的区别就在这里：

    第一课用的是 add_edge(...) 固定连线；
    本节会额外使用 add_conditional_edges(...)，
    让图在运行过程中“动态决定下一步走向”。
    """

    graph_builder = StateGraph(BranchingState)

    # 先注册普通节点。
    graph_builder.add_node("analyze_input", analyze_input)
    graph_builder.add_node("weather_node", weather_node)
    graph_builder.add_node("math_node", math_node)
    graph_builder.add_node("chat_node", chat_node)

    # 图执行起点，先进入“输入分析节点”。
    graph_builder.add_edge(START, "analyze_input")

    # 条件边的含义：
    # 先执行 analyze_input，
    # 然后调用 route_next_step(state)，
    # 再根据返回结果决定进入哪个节点。
    #
    # 这里我们把路由返回值与具体节点名做显式映射，
    # 这样结构会更清楚，学习时也更好理解。
    graph_builder.add_conditional_edges(
        "analyze_input",
        route_next_step,
        {
            "weather_node": "weather_node",
            "math_node": "math_node",
            "chat_node": "chat_node",
        },
    )

    # 三个分支节点的处理结束后，都统一收敛到 END。
    graph_builder.add_edge("weather_node", END)
    graph_builder.add_edge("math_node", END)
    graph_builder.add_edge("chat_node", END)

    return graph_builder.compile()


def run_case(graph, user_input: str):
    """
    运行单个案例。

    我们单独写这个函数，是为了方便在一个脚本里演示多个输入。
    这样你能明显看到：
    不同输入，会导致图走不同分支。
    """

    initial_state: BranchingState = {
        "user_input": user_input,
        "route": "",
        "answer": "",
        "step_count": 0,
    }

    print("\n" + "=" * 80)
    print(f"开始运行案例，用户输入：{user_input}")
    print("=" * 80)
    print(f"初始 state: {initial_state}")

    final_state = graph.invoke(initial_state)

    print("\n[案例执行完成]")
    print(f"最终 state: {final_state}")


def main():
    """
    入口函数。

    这里一次演示三个案例：
    1. 天气问题
    2. 数学问题
    3. 默认聊天问题

    建议你运行后重点观察：
    - 每个案例的 route 是怎么变化的
    - 图最后到底进入了哪个分支节点
    - 最终 answer 是哪个节点生成的
    """

    graph = build_graph()

    run_case(graph, "今天北京天气怎么样？")
    run_case(graph, "请帮我计算 3 + 5")
    run_case(graph, "你好，给我介绍一下 LangGraph")


if __name__ == "__main__":
    main()
