"""
第八课：多工具路由与工具选择策略

与第 5 课对比：
- 第 5 课：decide_tool -> 二选一/三选一工具 -> finalize（已熟悉「路由 + 工具 + 汇总」）
- 本课：在**同一套图**里放 **3 个真实工具 + 1 条兜底**，强调**选择策略（优先级、关键词、未命中回退）**

图结构（与大纲一致）：

    START
      -> select_tools（写入 selected_tool + route_note）
      -> route_tools
            |-- calculator_tool --> finalize_result --> END
            |-- time_tool ------> finalize_result --> END
            |-- lookup_tool ----> finalize_result --> END
            └── fallback_reply -------------------> END

重要语义（避免「merge」误解）：
- **每一轮 invoke 只会走下述 ONE 条工具支路**：calculator / time / lookup 三选一（或由 select_tools 判成 fallback）。
  不会「按优先级依次跑完三个工具」再把三个结果拼在一起；那种属于**多工具链式 / 并行 fan-out+fain-in**，本课刻意不做（大纲第 10 课并行与聚合）。
- **`finalize_result` 名称与第 5 课一致**：含义是「把本轮**已执行的那一个**工具产出（或 tool_error）统一排版成 final_answer」，不是把多工具输出做归并。
- 三条边都指向 `finalize_result` 的原因：与第 2 课一样是 **fan-in 到同一收尾节点**，只是复用**同一段**格式化逻辑，减少复制粘贴；**不是**多路结果汇总。

自本课起：正文尽量「每行代码旁附注释」；并与 java/ 目录下 LangGraph4j 对照课同步。
"""

from __future__ import annotations  # 推迟求值注解

from datetime import datetime  # 时间工具用本地时间
from pathlib import Path  # 导出图路径
from typing import Literal, TypedDict  # 路由返回值类型、状态 schema

from langgraph.graph import END, START, StateGraph  # 图构建原语

# ---------------------------------------------------------------------------
# 静态「词典」工具：演示「非算术、非时间」类工具；真实系统可换 HTTP/DB
# ---------------------------------------------------------------------------
GLOSSARY: dict[str, str] = {  # key 一律小写，便于与用户输入归一化比对
    "langgraph": "LangGraph：面向多步骤、有状态的 LLM 应用编排库，常与 LangChain 生态配合。",
    "langchain": "LangChain：构建 LLM 应用的框架，提供模型抽象、链、工具与数据连接器。",
}


class MultiToolState(TypedDict):
    """
    多工具路由示例的状态。
    route_note：本课专用，用自然语言解释「为什么选这条路」，便于看日志学习策略。
    """

    user_input: str  # 用户原始输入
    selected_tool: str  # calculator | time | lookup | fallback（由选择器写入）
    tool_input: str  # 传给具体工具的参数（表达式、词条名等）
    route_note: str  # 策略说明：优先级、命中了哪些规则
    tool_output: str  # 工具成功时的结构化/半结构化输出
    tool_error: str  # 工具失败时的错误信息
    final_answer: str  # 对用户展示的最终结果（finalize_result 或兜底生成）
    step_count: int  # 教学计数：观察走了多少节点


def select_tools(state: MultiToolState) -> MultiToolState:  # 第一拍：只做「选路」，不执行重活
    """
    工具选择策略（教学版，刻意写死优先级）：
    1) 计算器：出现「计算」或输入在去掉空格后含 + - * /（与第 5 课类似）
    2) 时间：含「几点」「时间」「现在」等
    3) 词条 lookup：含「是什么」且在词典里能提取到 key；或整句归一化后本身是词典 key
    4) 兜底：以上皆不满足

    若多条同时命中：按上述顺序**先到先得**（例如同时像算术又像问时间，先试计算器）。
    """
    user_input = state["user_input"]  # 取出本轮用户话
    normalized = user_input.replace(" ", "")  # 去掉空格便于检测运算符

    print("\n[select_tools] 节点开始执行")
    print(f"[select_tools] user_input={user_input!r}")

    selected_tool = "fallback"  # 默认兜底，后续命中则覆盖
    tool_input = ""  # 默认无工具入参
    route_note = "未命中专用工具关键词，将走 fallback_reply。"  # 默认说明

    if "计算" in user_input or any(op in normalized for op in ("+", "-", "*", "/")):  # 优先算术分支
        selected_tool = "calculator"
        if "计算" in user_input:  # 若中文提示「计算」则截断后半段为表达式
            tool_input = user_input.split("计算", maxsplit=1)[1].strip()
        else:
            tool_input = user_input  # 否则整句当表达式（如 "3+5"）
        route_note = "优先级1：检测到算术相关关键词或运算符，选 calculator。"
    elif any(k in user_input for k in ("几点", "时间", "现在")):  # 时间类
        selected_tool = "time"
        tool_input = ""
        route_note = "优先级2：检测到时间相关关键词，选 time。"
    elif "是什么" in user_input:  # 词条：「X是什么」
        term = user_input.split("是什么", maxsplit=1)[0].strip().lower()  # 取问号前主语并做小写
        if term in GLOSSARY:  # 词典里真有这条
            selected_tool = "lookup"
            tool_input = term
            route_note = "优先级3：「是什么」句型且词条在内置词典中，选 lookup。"
        else:
            route_note = f"优先级3：虽有「是什么」，但词条 {term!r} 不在词典，最终兜底。"
    elif user_input.strip().lower() in GLOSSARY:  # 用户直接输入一个词当词条名
        selected_tool = "lookup"
        tool_input = user_input.strip().lower()
        route_note = "优先级3：整句即为词典 key，选 lookup。"
    # else: 保持 fallback

    print(f"[select_tools] selected_tool={selected_tool} tool_input={tool_input!r}")
    print(f"[select_tools] route_note={route_note}")

    return {
        "selected_tool": selected_tool,
        "tool_input": tool_input,
        "route_note": route_note,
        "tool_output": "",  # 新一轮选择时清空上轮输出，避免污染 final 排版
        "tool_error": "",
        "step_count": state["step_count"] + 1,
    }


def route_tools(  # conditional_edges 的「路由函数」：返回值必须是下游节点 id
    state: MultiToolState,
) -> Literal["calculator_tool", "time_tool", "lookup_tool", "fallback_reply"]:
    tool = state["selected_tool"]  # 读取选择器结果
    print("\n[route_tools] 路由执行")
    print(f"[route_tools] -> {tool}")
    if tool == "calculator":
        return "calculator_tool"
    if tool == "time":
        return "time_tool"
    if tool == "lookup":
        return "lookup_tool"
    return "fallback_reply"


def calculator_tool(state: MultiToolState) -> MultiToolState:  # 与第 5 课同思路：白名单 + eval
    """计算器：教学用 eval，字符集严格限制；生产请换安全表达式引擎。"""
    expression = state["tool_input"]
    allowed = set("0123456789+-*/%.() ")

    print("\n[calculator_tool] 节点开始执行")
    print(f"[calculator_tool] expression={expression!r}")

    if not expression:  # 没有可算式
        return {
            "tool_error": "未找到可计算表达式。",
            "step_count": state["step_count"] + 1,
        }
    if any(ch not in allowed for ch in expression):  # 非白名单字符
        return {
            "tool_error": "表达式包含非法字符（仅允许数字与 +-*/%() 与空格）。",
            "step_count": state["step_count"] + 1,
        }
    try:
        result = eval(expression, {"__builtins__": {}}, {})  # 禁 builtins 减小风险
        return {
            "tool_output": f"{expression} = {result}",
            "step_count": state["step_count"] + 1,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "tool_error": f"计算失败：{exc}",
            "step_count": state["step_count"] + 1,
        }


def time_tool(state: MultiToolState) -> MultiToolState:  # 简单本地时间
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n[time_tool] 节点开始执行")
    print(f"[time_tool] now={now}")
    return {
        "tool_output": f"当前本地时间：{now}",
        "step_count": state["step_count"] + 1,
    }


def lookup_tool(state: MultiToolState) -> MultiToolState:  # 词典查询
    key = state["tool_input"].strip().lower()
    print("\n[lookup_tool] 节点开始执行")
    print(f"[lookup_tool] key={key!r}")
    body = GLOSSARY.get(key)  # dict 查找 O(1)
    if not body:
        return {
            "tool_error": f"词典未收录：{key!r}",
            "step_count": state["step_count"] + 1,
        }
    return {
        "tool_output": body,
        "step_count": state["step_count"] + 1,
    }


def finalize_result(state: MultiToolState) -> MultiToolState:  # 仅此一条工具已跑完；把单次 tool 输出格式化成 final_answer（同第 5 课语义）
    print("\n[finalize_result] 格式化本轮单工具结果")
    if state["tool_error"]:  # 有错误：把工具名与错误展示给用户
        final = (
            f"工具 `{state['selected_tool']}` 执行失败。\n"
            f"错误：{state['tool_error']}\n"
            f"路由说明：{state['route_note']}"
        )
    else:  # 成功：带出 tool_output + 路由说明，方便对照策略
        final = (
            f"工具 `{state['selected_tool']}` 执行成功。\n"
            f"结果：{state['tool_output']}\n"
            f"路由说明：{state['route_note']}"
        )
    return {
        "final_answer": final,
        "step_count": state["step_count"] + 1,
    }


def fallback_reply(state: MultiToolState) -> MultiToolState:  # 未命中工具时的兜底答复
    print("\n[fallback_reply] 兜底分支")
    text = (
        "【兜底】当前输入未命中 calculator / time / lookup 的选取规则。\n"
        f"你可以尝试：\n"
        f"  - 算术：「计算 3*(2+1)」或直接「3*(2+1)」\n"
        f"  - 时间：「现在几点」\n"
        f"  - 词条：「LangGraph是什么」或单独发送「langgraph」\n"
        f"\n原始输入：{state['user_input']!r}\n"
        f"策略说明：{state['route_note']}"
    )
    return {
        "final_answer": text,
        "step_count": state["step_count"] + 1,
    }


def build_graph():  # 组装 StateGraph
    b = StateGraph(MultiToolState)  # 绑定状态类型
    b.add_node("select_tools", select_tools)  # 选择器节点
    b.add_node("calculator_tool", calculator_tool)
    b.add_node("time_tool", time_tool)
    b.add_node("lookup_tool", lookup_tool)
    b.add_node("finalize_result", finalize_result)
    b.add_node("fallback_reply", fallback_reply)

    b.add_edge(START, "select_tools")  # 入口
    b.add_conditional_edges(
        "select_tools",
        route_tools,
        {
            "calculator_tool": "calculator_tool",
            "time_tool": "time_tool",
            "lookup_tool": "lookup_tool",
            "fallback_reply": "fallback_reply",
        },
    )
    b.add_edge("calculator_tool", "finalize_result")  # fan-in：三路共用同一「收尾排版」节点，每轮仍只执行过其中一路
    b.add_edge("time_tool", "finalize_result")
    b.add_edge("lookup_tool", "finalize_result")
    b.add_edge("finalize_result", END)  # 工具路径结束
    b.add_edge("fallback_reply", END)  # 兜底直接结束
    return b.compile()


def export_graph_image(graph) -> None:  # 与第六、七课相同导出逻辑
    go = graph.get_graph()
    png = Path(__file__).with_name("08_multi_tool_routing_graph.png")
    mmd = Path(__file__).with_name("08_multi_tool_routing_graph.mmd")
    try:
        png.write_bytes(go.draw_mermaid_png())
        print(f"[图导出] {png}")
    except Exception as exc:  # noqa: BLE001
        mmd.write_text(go.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mmd}")


def run_case(graph, user_input: str) -> None:  # 单次 invoke 封装
    initial: MultiToolState = {
        "user_input": user_input,
        "selected_tool": "",
        "tool_input": "",
        "route_note": "",
        "tool_output": "",
        "tool_error": "",
        "final_answer": "",
        "step_count": 0,
    }
    print("\n" + "=" * 80)
    print(f"案例：{user_input}")
    print("=" * 80)
    out = graph.invoke(initial)
    print("\n[结束] selected_tool =", out["selected_tool"])
    print("final_answer:\n", out["final_answer"])


def main() -> None:  # 主入口：多案例覆盖 DoD
    g = build_graph()
    export_graph_image(g)

    run_case(g, "计算 20 + 22")  # Happy：calculator
    run_case(g, "现在几点")  # Happy：time
    run_case(g, "LangGraph是什么")  # Happy：lookup
    run_case(g, "langchain")  # Happy：lookup（整词命中）
    run_case(g, "你好，随便聊聊")  # 边界：fallback
    run_case(g, "计算 1 + )")  # 故障：表达式错误

    print("\n本课 DoD：")
    print("- 主路径：算术 / 时间 / 词典三选一 + finalize_result 统一排版（非多工具结果合并）")
    print("- 兜底：未命中走 fallback_reply")
    print("- 故障：计算器解析/求值失败时 finalize_result 展示 tool_error")
    print("- 回归：python 08_multi_tool_routing_graph.py")
    print("- Java 对照：mvn -q exec:java -Dexec.mainClass=...Lesson08App")


if __name__ == "__main__":
    main()
