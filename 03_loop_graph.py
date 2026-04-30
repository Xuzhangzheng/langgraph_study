"""
第三课：理解 LangGraph 的循环（Loop / Re-try / Iteration）

前两课我们分别学了：
1) 线性流程：固定顺序执行
2) 条件分支：根据状态走不同路径

这节学习第三个核心能力：循环。

循环在 Agent 场景非常常见，例如：
- 思考 -> 行动 -> 观察 -> 再思考（直到任务完成）
- 生成答案 -> 自检 -> 不合格则重写
- 调工具失败 -> 重试（直到成功或超过上限）

本例用一个最小但直观的任务来演示：
“不断给文本追加补充句子，直到长度达到目标值，再结束。”

学习重点：
1. 如何在 state 中保存“当前进度”和“最大迭代次数”
2. 如何用 add_conditional_edges 让图回到之前节点形成循环
3. 如何设置安全退出条件，避免无限循环
"""

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class LoopState(TypedDict):
    """
    循环示例中的状态结构。

    字段说明：
    - topic: 主题（要围绕哪个主题扩写）
    - draft: 当前草稿文本（每轮都会被修改）
    - min_length: 目标最小长度（达到后即可结束）
    - iteration: 当前迭代次数（已执行多少轮扩写）
    - max_iterations: 最多允许迭代次数（安全上限，防止无限循环）
    - done: 是否已经满足结束条件
    """

    topic: str
    draft: str
    min_length: int
    iteration: int
    max_iterations: int
    done: bool


def write_or_expand_draft(state: LoopState) -> LoopState:
    """
    写作/扩写节点：每次执行都把 draft 扩展一点。

    这里我们不调用大模型，直接追加固定模板句，
    目的是让你聚焦“循环控制机制”而不是模型效果。
    """

    topic = state["topic"]
    draft = state["draft"]
    iteration = state["iteration"]

    print("\n[write_or_expand_draft] 节点开始执行")
    print(f"[write_or_expand_draft] 当前 iteration: {iteration}")
    print(f"[write_or_expand_draft] 执行前 draft 长度: {len(draft)}")

    # 每一轮补充一小段文本，模拟“迭代改进”。
    addition = (
        f" 第{iteration + 1}轮补充：围绕“{topic}”，"
        "我们进一步强调核心概念、实践价值和学习建议。"
    )
    updated_draft = draft + addition

    print(f"[write_or_expand_draft] 执行后 draft 长度: {len(updated_draft)}")

    return {
        "draft": updated_draft,
        "iteration": iteration + 1,
    }


def check_completion(state: LoopState) -> LoopState:
    """
    检查节点：判断是否满足退出条件。

    结束条件有两个（满足其一即可）：
    1. 文本长度 >= min_length（任务达标）
    2. iteration >= max_iterations（达到安全上限）

    done=True 表示下一步应该结束。
    """

    draft_length = len(state["draft"])
    min_length = state["min_length"]
    iteration = state["iteration"]
    max_iterations = state["max_iterations"]

    reached_length_goal = draft_length >= min_length
    reached_iteration_limit = iteration >= max_iterations
    done = reached_length_goal or reached_iteration_limit

    print("\n[check_completion] 节点开始执行")
    print(f"[check_completion] 当前 draft 长度: {draft_length}")
    print(f"[check_completion] 目标最小长度: {min_length}")
    print(f"[check_completion] 当前迭代次数: {iteration}")
    print(f"[check_completion] 最大迭代次数: {max_iterations}")
    print(f"[check_completion] 是否完成 done: {done}")

    return {"done": done}


def route_after_check(state: LoopState) -> Literal["continue_writing", "finish"]:
    """
    路由函数：检查后决定是继续循环还是结束。

    - done=False -> 回到写作节点，继续下一轮
    - done=True  -> 走向结束节点
    """

    if state["done"]:
        print("\n[route_after_check] 决策：finish（结束循环）")
        return "finish"

    print("\n[route_after_check] 决策：continue_writing（继续下一轮）")
    return "continue_writing"


def finish_node(state: LoopState) -> LoopState:
    """
    结束节点：整理最终结果（可选步骤）。

    这个节点不是必须的，但教学上很有帮助：
    你可以在这里做最终收尾，比如：
    - 格式化输出
    - 记录统计信息
    - 写入数据库
    """

    print("\n[finish_node] 节点开始执行")
    print(f"[finish_node] 最终 iteration: {state['iteration']}")
    print(f"[finish_node] 最终 draft 长度: {len(state['draft'])}")

    # 本示例不再修改内容，直接返回空更新也可以。
    # 这里保持显式返回，方便你理解节点行为一致性。
    return {
        "done": True,
    }


def build_graph():
    """
    构建循环图。

    执行路径是：
    START -> write_or_expand_draft -> check_completion
           -> (done=False) 回到 write_or_expand_draft
           -> (done=True) 进入 finish_node -> END
    """

    builder = StateGraph(LoopState)

    builder.add_node("write_or_expand_draft", write_or_expand_draft)
    builder.add_node("check_completion", check_completion)
    builder.add_node("finish_node", finish_node)

    builder.add_edge(START, "write_or_expand_draft")
    builder.add_edge("write_or_expand_draft", "check_completion")

    # 条件路由：在检查后动态决定“继续循环 or 结束”
    builder.add_conditional_edges(
        "check_completion",
        route_after_check,
        {
            "continue_writing": "write_or_expand_draft",
            "finish": "finish_node",
        },
    )

    builder.add_edge("finish_node", END)

    return builder.compile()


def main():
    """
    入口函数：运行一个循环案例。

    推荐你先跑一次看日志，再修改这些参数观察行为变化：
    - min_length 改大：循环轮数会增加
    - max_iterations 改小：可能在达标前提前停止（安全退出）
    """

    graph = build_graph()

    initial_state: LoopState = {
        "topic": "LangGraph 学习路线",
        "draft": "开篇：我们正在学习如何用图来组织 LLM 应用。",
        "min_length": 220,
        "iteration": 0,
        "max_iterations": 3,
        "done": False,
    }

    print("=" * 80)
    print("第三课：运行循环图（直到满足条件）")
    print("=" * 80)
    print(f"初始 state: {initial_state}")

    final_state = graph.invoke(initial_state)

    print("\n" + "=" * 80)
    print("图执行结束")
    print("=" * 80)
    print(f"最终 iteration: {final_state['iteration']}")
    print(f"最终 done: {final_state['done']}")
    print(f"最终 draft 长度: {len(final_state['draft'])}")
    print(f"最终 draft 内容:\n{final_state['draft']}")

    print("\n观察建议：")
    print("1) 看日志中 route_after_check 的决策是否符合预期")
    print("2) 看 iteration 如何随着循环增加")
    print("3) 修改 min_length / max_iterations 后重新运行对比")


if __name__ == "__main__":
    main()
