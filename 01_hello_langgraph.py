"""
第一课：用最小示例认识 LangGraph

这节的目标非常简单：

1. 知道 LangGraph 是怎么“组织步骤”的
2. 知道什么是“状态（state）”
3. 知道节点（node）如何读取和更新状态
4. 能亲手运行一个最小图，并看懂输出结果

这个文件故意不接入大模型 API，
这样你可以先把 LangGraph 的运行机制学扎实，
后面再逐步接 OpenAI、工具调用、Memory、Agent。
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


# TypedDict 用来声明“状态”的结构。
# 你可以把它理解为：
# “整个图在执行过程中，会一直携带这样一个字典对象往前传递。”
#
# 这里我们只放两个字段，尽量保持简单：
# - message: 当前要处理的文本
# - step_count: 当前一共经过了多少个节点
#
# 在后续更复杂的例子里，state 里还可以放：
# - 用户问题
# - 对话历史
# - 工具调用结果
# - 检索得到的文档
# - 路由标记
# - 是否结束的判断条件
class LessonState(TypedDict):
    message: str
    step_count: int


def prepare_message(state: LessonState) -> LessonState:
    """
    第一个节点：准备消息。

    节点函数的核心规律：
    - 输入：state
    - 输出：对 state 的更新内容

    在 LangGraph 里，节点本质上就是“接收状态 -> 返回状态更新”的函数。

    这里我们做两件小事：
    1. 把 message 改造成更适合展示的文本
    2. 把 step_count + 1，表示已经执行过一个节点
    """

    original_message = state["message"]

    # 这里故意把处理逻辑写得很直白，
    # 方便你观察“节点对状态做了什么修改”。
    prepared_message = f"Hello, LangGraph! 原始输入是：{original_message}"

    print("\n[prepare_message] 节点开始执行")
    print(f"[prepare_message] 收到的 state: {state}")
    print(f"[prepare_message] 生成的新 message: {prepared_message}")

    # 返回值是“状态更新字典”。
    # LangGraph 会把它合并回当前 state。
    return {
        "message": prepared_message,
        "step_count": state["step_count"] + 1,
    }


def summarize_result(state: LessonState) -> LessonState:
    """
    第二个节点：整理最终结果。

    这个节点继续接收上一个节点更新后的 state，
    然后再基于它做一次加工。

    你会发现：
    LangGraph 的执行思路其实很像“流水线”。
    每个节点关心自己的输入和输出，
    整个图则负责把节点按顺序串起来。
    """

    current_message = state["message"]
    current_step_count = state["step_count"]

    final_message = (
        f"{current_message} | 图执行完成，总共经过 {current_step_count + 1} 个节点。"
    )

    print("\n[summarize_result] 节点开始执行")
    print(f"[summarize_result] 收到的 state: {state}")
    print(f"[summarize_result] 生成的最终 message: {final_message}")

    return {
        "message": final_message,
        "step_count": current_step_count + 1,
    }


def build_graph():
    """
    构建 LangGraph 图对象。

    这里是整个文件最重要的部分之一。

    StateGraph(LessonState) 的意思是：
    - 我们要创建一个“基于状态流转”的图
    - 整个图里流动的状态结构，遵循 LessonState

    接下来我们会做 4 件事：
    1. 创建 graph builder
    2. 注册节点
    3. 连接边（定义执行顺序）
    4. compile 成可运行图
    """

    # 第一步：创建一个图构建器。
    graph_builder = StateGraph(LessonState)

    # 第二步：注册两个节点。
    # add_node("节点名", 节点函数)
    #
    # 这里的“节点名”是图里的标识符，
    # 后续 add_edge 时就靠这个名字来连线。
    graph_builder.add_node("prepare_message", prepare_message)
    graph_builder.add_node("summarize_result", summarize_result)

    # 第三步：定义执行顺序。
    #
    # START 表示图的起点
    # END 表示图的终点
    #
    # 执行链路如下：
    # START -> prepare_message -> summarize_result -> END
    graph_builder.add_edge(START, "prepare_message")
    graph_builder.add_edge("prepare_message", "summarize_result")
    graph_builder.add_edge("summarize_result", END)

    # 第四步：把 builder 编译成真正可执行的 graph。
    return graph_builder.compile()


def main():
    """
    程序入口。

    invoke(...) 可以理解成：
    “给图一个初始状态，然后让它从 START 开始跑到 END。”
    """

    graph = build_graph()

    # 初始状态必须符合 LessonState 的结构。
    initial_state: LessonState = {
        "message": "这是我学习 LangGraph 的第一天",
        "step_count": 0,
    }

    print("=" * 80)
    print("第一课：运行一个最小 LangGraph")
    print("=" * 80)
    print(f"初始 state: {initial_state}")

    # 图开始执行。
    final_state = graph.invoke(initial_state)

    print("\n" + "=" * 80)
    print("图执行结束")
    print("=" * 80)
    print(f"最终 state: {final_state}")

    # 给学习者一个清晰的观察点：
    # 看看初始 state 与最终 state 有什么变化。
    print("\n你现在应该重点观察两件事：")
    print("1. message 是如何在不同节点中被不断加工的")
    print("2. step_count 是如何随着节点执行而递增的")


if __name__ == "__main__":
    main()
