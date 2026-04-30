"""
第四课：组合分支与循环，构建一个 Mini-Agent 图

前三课我们分别学了：
1) 线性流程（固定顺序）
2) 条件分支（根据状态路由）
3) 循环迭代（直到满足条件）

这一课把它们组合起来，得到一个更像“Agent 工作流”的最小原型：

START
  -> classify_task                # 先判断任务类型（路由）
  -> (qa / rewrite) 分支
  -> generate_answer             # 生成候选答案
  -> evaluate_answer             # 评估答案是否达标
  -> (pass -> END) / (fail -> 回到 generate_answer 重试)

学习重点：
1. 如何把“路由 + 循环”放在同一张图里
2. 如何把评估结果写入 state，并用于下一步决策
3. 如何设置 max_attempts 防止无限重试
"""

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class MiniAgentState(TypedDict):
    """
    Mini-Agent 示例中的状态结构。

    字段说明：
    - user_input: 用户输入的原始任务
    - task_type: 任务类别（qa / rewrite）
    - attempt: 当前尝试次数（每次生成 +1）
    - max_attempts: 最大允许尝试次数（安全上限）
    - candidate_answer: 当前候选答案
    - quality_score: 质量评分（0~100，示例里用规则模拟）
    - pass_threshold: 通过阈值（>= 该值即视为通过）
    - passed: 是否通过评估
    - feedback: 评估反馈（下一轮可用于改进）
    """

    user_input: str
    task_type: str
    attempt: int
    max_attempts: int
    candidate_answer: str
    quality_score: int
    pass_threshold: int
    passed: bool
    feedback: str


def classify_task(state: MiniAgentState) -> MiniAgentState:
    """
    第一步：分类任务。

    我们用简单规则分类：
    - 输入里包含“改写/润色/重写” -> rewrite
    - 其他默认 -> qa
    """

    user_input = state["user_input"]
    print("\n[classify_task] 节点开始执行")
    print(f"[classify_task] user_input: {user_input}")

    if any(keyword in user_input for keyword in ("改写", "润色", "重写")):
        task_type = "rewrite"
    else:
        task_type = "qa"

    print(f"[classify_task] 识别 task_type: {task_type}")
    return {"task_type": task_type}


def route_task(state: MiniAgentState) -> Literal["qa_prepare", "rewrite_prepare"]:
    """
    路由函数：根据 task_type 决定进入哪个准备节点。
    """

    task_type = state["task_type"]
    print("\n[route_task] 路由开始执行")
    print(f"[route_task] 当前 task_type: {task_type}")
    return "rewrite_prepare" if task_type == "rewrite" else "qa_prepare"


def qa_prepare(state: MiniAgentState) -> MiniAgentState:
    """
    QA 分支准备节点。

    这里不直接回答问题，只是把反馈信息初始化好，
    让后续生成节点知道“当前分支的目标”。
    """

    print("\n[qa_prepare] 节点开始执行")
    return {"feedback": "目标：给出结构清晰、要点完整的回答。"}


def rewrite_prepare(state: MiniAgentState) -> MiniAgentState:
    """
    改写分支准备节点。

    作用与 qa_prepare 一致，只是目标导向不同。
    """

    print("\n[rewrite_prepare] 节点开始执行")
    return {"feedback": "目标：保留原意，表达更自然、更精炼。"}


def generate_answer(state: MiniAgentState) -> MiniAgentState:
    """
    生成候选答案节点（可循环执行）。

    为了聚焦图逻辑，这里不调用真实 LLM，而是规则模拟：
    - 每次 attempt 增加，文本会更“完整”
    - 同时把上一轮 feedback 拼进去，模拟“根据评估改进”
    """

    user_input = state["user_input"]
    task_type = state["task_type"]
    attempt = state["attempt"] + 1
    feedback = state["feedback"]

    print("\n[generate_answer] 节点开始执行")
    print(f"[generate_answer] task_type: {task_type}")
    print(f"[generate_answer] 当前 attempt: {attempt}")
    print(f"[generate_answer] 使用反馈: {feedback}")

    if task_type == "rewrite":
        candidate = (
            f"第{attempt}版改写：\n"
            f"- 原句：{user_input}\n"
            f"- 改写：这个内容可以表达为“{user_input}”，语气更自然。\n"
            f"- 改进说明：{feedback}"
        )
    else:
        candidate = (
            f"第{attempt}版回答：\n"
            f"- 问题：{user_input}\n"
            "- 回答要点：先定义概念，再给步骤，最后给注意事项。\n"
            f"- 改进说明：{feedback}"
        )

    print(f"[generate_answer] candidate: {candidate}")
    return {
        "attempt": attempt,
        "candidate_answer": candidate,
    }


def evaluate_answer(state: MiniAgentState) -> MiniAgentState:
    """
    评估节点：判断当前候选答案是否通过。

    评估规则（教学版，故意简单）：
    - 基础分 = attempt * 25
    - 如果候选答案长度 > 120，加 10 分
    - 最高 100 分

    通过条件：
    - score >= pass_threshold，或
    - attempt >= max_attempts（达到上限则强制停止循环）
    """

    attempt = state["attempt"]
    answer = state["candidate_answer"]
    pass_threshold = state["pass_threshold"]
    max_attempts = state["max_attempts"]

    print("\n[evaluate_answer] 节点开始执行")
    print(f"[evaluate_answer] 当前 attempt: {attempt}")
    print(f"[evaluate_answer] candidate 长度: {len(answer)}")

    score = attempt * 25
    if len(answer) > 120:
        score += 10
    score = min(score, 100)

    passed_by_score = score >= pass_threshold
    reached_max_attempts = attempt >= max_attempts
    passed = passed_by_score or reached_max_attempts

    if passed_by_score:
        feedback = "评估通过：质量已达到阈值。"
    elif reached_max_attempts:
        feedback = "达到最大尝试次数，停止循环（这是安全退出，不代表最佳质量）。"
    else:
        feedback = "评估未通过：请增加结构化说明，并补充更具体的细节。"

    print(f"[evaluate_answer] score: {score}")
    print(f"[evaluate_answer] pass_threshold: {pass_threshold}")
    print(f"[evaluate_answer] passed: {passed}")
    print(f"[evaluate_answer] feedback: {feedback}")

    return {
        "quality_score": score,
        "passed": passed,
        "feedback": feedback,
    }


def route_after_evaluation(state: MiniAgentState) -> Literal["finish", "retry_generate"]:
    """
    评估后路由：
    - passed=True  -> finish（结束）
    - passed=False -> retry_generate（继续生成下一版）
    """

    if state["passed"]:
        print("\n[route_after_evaluation] 决策：finish")
        return "finish"

    print("\n[route_after_evaluation] 决策：retry_generate")
    return "retry_generate"


def finish(state: MiniAgentState) -> MiniAgentState:
    """
    结束节点：这里不做复杂处理，只打印最终信息。
    """

    print("\n[finish] 节点开始执行")
    print(f"[finish] 最终 attempt: {state['attempt']}")
    print(f"[finish] 最终 score: {state['quality_score']}")
    return {"passed": True}


def build_graph():
    """
    构建完整的 Mini-Agent 图。
    """

    builder = StateGraph(MiniAgentState)

    # 注册节点
    builder.add_node("classify_task", classify_task)
    builder.add_node("qa_prepare", qa_prepare)
    builder.add_node("rewrite_prepare", rewrite_prepare)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("evaluate_answer", evaluate_answer)
    builder.add_node("finish", finish)

    # 起点：先分类
    builder.add_edge(START, "classify_task")

    # 分支：qa / rewrite
    builder.add_conditional_edges(
        "classify_task",
        route_task,
        {
            "qa_prepare": "qa_prepare",
            "rewrite_prepare": "rewrite_prepare",
        },
    )

    # 两个分支最终都汇合到生成节点
    builder.add_edge("qa_prepare", "generate_answer")
    builder.add_edge("rewrite_prepare", "generate_answer")

    # 生成后进入评估
    builder.add_edge("generate_answer", "evaluate_answer")

    # 评估后：通过就结束，否则回到生成节点重试
    builder.add_conditional_edges(
        "evaluate_answer",
        route_after_evaluation,
        {
            "finish": "finish",
            "retry_generate": "generate_answer",
        },
    )

    builder.add_edge("finish", END)

    return builder.compile()


def run_case(graph, user_input: str):
    """
    运行单个案例，方便你观察不同任务类型的行为。
    """

    initial_state: MiniAgentState = {
        "user_input": user_input,
        "task_type": "",
        "attempt": 0,
        "max_attempts": 2,
        "candidate_answer": "",
        "quality_score": 0,
        "pass_threshold": 70,
        "passed": False,
        "feedback": "初始反馈：请先生成一个可评估版本。",
    }

    print("\n" + "=" * 80)
    print(f"开始案例：{user_input}")
    print("=" * 80)
    print(f"初始 state: {initial_state}")

    final_state = graph.invoke(initial_state)

    print("\n[案例结束]")
    print(f"task_type: {final_state['task_type']}")
    print(f"attempt: {final_state['attempt']}")
    print(f"quality_score: {final_state['quality_score']}")
    print(f"passed: {final_state['passed']}")
    print(f"final feedback: {final_state['feedback']}")
    print("最终候选答案：")
    print(final_state["candidate_answer"])


def main():
    """
    入口函数：演示 QA 与 Rewrite 两类任务。
    """

    graph = build_graph()

    run_case(graph, "请解释一下什么是 LangGraph，以及适合哪些场景。")
    run_case(graph, "请把这句话改写得更自然：我今天学习了很多新知识，感觉很充实。")

    print("\n学习建议：")
    print("1) 把 pass_threshold 改高，观察循环轮次变化")
    print("2) 把 max_attempts 改成 1，观察安全退出行为")
    print("3) 试着把 evaluate_answer 改成你自己的评估规则")


if __name__ == "__main__":
    main()
