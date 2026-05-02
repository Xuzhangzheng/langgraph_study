"""
第十七课：多 Agent 协作图（Planner / Executor / Critic，单状态总线）

与前序课关系：
--------------
- 第 4 课 Mini-Agent：**生成 → 评估 → 条件边重试**；本课把「评估」提升为独立的 **Critic 角色**，并允许 **打回 Planner 或 Executor**。
- 第 6～7 课：LLM / 分层提示词；本课 **三个节点复用同一套 Provider 与环境变量**，仅 **system prompt 不同**，贴近业务里「多角色复用网关」的常见做法。
- 第 16 课：**按 LLM_PROVIDER 切换 openai / ark**、`responses.create` 单串 `input`；本课三处调用与该模式完全一致。

本节要点（思想、问题拆解、API）：
----------------------------------
1. **为何仍是「一张图」，却叫多 Agent**
   - 工程上常以 **专职提示词 + 专职状态片段** 表示不同职责；不一定要多进程。**状态即消息协议**：Planner 写 `plan_outline`，Executor 读它并写 `draft_answer`，Critic 读后写 `critic_verdict` + `critic_feedback`。
2. **冲突与收敛**
   - Critic 可裁决 `pass`（结束链）、`revise_executor`（只改稿子）、`revise_planner`（计划不适则回到 Planner）。
   - 必须设 **`iteration` + `max_iterations`**，防止条件边回路 **无限振荡**（与第 3、4 课 max_attempt 思想同源）。
3. **LangGraph 1.1.10 API**
   - `StateGraph(TypedDict)`、`add_conditional_edges(源节点, Callable[[State], str], {路由返回值: 目标节点})`：**返回值必须与字典键完全一致**。
   - `Annotated[list[str], operator.add]` 作用于 `diagnostics`，多节点 **追加** 而不相互覆盖。
4. **环境与 LLM（与第 6、16 课对齐）**
   - `mode=llm`：`LLM_PROVIDER=openai` → `OPENAI_*` + `ChatOpenAI`；`LLM_PROVIDER=ark` → `ARK_*` + `volcenginesdkarkruntime.Ark`、`client.responses.create`。
   - Ark 仅有 **一个 `input` 字符串**：用「【系统要求】/【用户任务】」拼装，等价第 6 课 `build_ark_input_text`。
5. **Failure Path（脚本必须可跑）**
   - **空目标** → `normalize_goal` → `seal_invalid_goal`。
   - **`FORCE_*`（fallback 或无 Key）**：可控地触发 `pass` / `revise_*` / 持续 `revise_executor` **直至 max_iterations → `finalize_abort`**。
   - **`llm` 模式**：Critic 输出 **严格 JSON** 解析失败 → 记入 `diagnostics` 并按 `revise_executor` 兜底一次，避免死锁。

接口不变清单（本课 DoD）：
--------------------------
- `request_id`, `user_goal`, `mode`, `goal_gate`, `plan_outline`, `draft_answer`, `final_answer`,
  `critic_verdict`, `critic_feedback`, `iteration`, `max_iterations`, `diagnostics`
- `goal_gate`：`pending` | `ok` | `invalid`
- `mode`：`llm` | `fallback`
- `critic_verdict`：`pending`（初始占位） | `pass` | `revise_executor` | `revise_planner`

主路径 / 分支拓扑：
------------------
START → normalize_goal ─route──→ planner → executor → critic ─route──→ finalize_pass → END
                          │                                        ├→（未超限 revise_executor → executor）
                          │                                        ├→（未超限 revise_planner → planner）
                          │                                        └→ finalize_abort（超限或兜底）→ END
                          └→ seal_invalid_goal → END

最小回归：
----------
python 17_multi_agent_collaboration_graph.py
"""

from __future__ import annotations

import json
import logging
import operator
import os
import re
from pathlib import Path
from typing import Annotated, Any, Callable, Literal

from dotenv import load_dotenv
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph


# -----------------------------------------------------------------------------
# Logger：与第 16 课一致的命名空间，便于在日志系统中按课过滤。
# -----------------------------------------------------------------------------
_LOG = logging.getLogger("lesson17.multi_agent")

# -----------------------------------------------------------------------------
# Literal 别名：收窄字符串字面量含义，静态检查更友好。
# -----------------------------------------------------------------------------
GoalGate = Literal["pending", "ok", "invalid"]
RunMode = Literal["llm", "fallback"]
CriticVerdict = Literal["pending", "pass", "revise_executor", "revise_planner"]


# -----------------------------------------------------------------------------
# TypedDict：即本课的状态契约；字段名不要随意改，评测与 Java 对齐依赖这些键。
# -----------------------------------------------------------------------------
class AgentCollabState(TypedDict):
    """多角色协作共用状态——「黑板」模式的极简版。"""

    request_id: str
    user_goal: str
    mode: RunMode
    goal_gate: GoalGate
    plan_outline: str
    draft_answer: str
    final_answer: str
    critic_verdict: CriticVerdict
    critic_feedback: str
    iteration: int
    max_iterations: int
    diagnostics: Annotated[list[str], operator.add]


def _initial_state_chunk(
    request_id: str,
    user_goal: str,
    mode: RunMode,
    *,
    max_iterations: int,
) -> dict[str, Any]:
    """拼装 invoke 前除 diagnostics 以外的初始字段片段（caller 另有 diagnostics：[]）。"""
    return {
        "request_id": request_id,
        "user_goal": user_goal,
        "mode": mode,
        "goal_gate": "pending",
        "plan_outline": "",
        "draft_answer": "",
        "final_answer": "",
        "critic_verdict": "pending",
        "critic_feedback": "",
        "iteration": 0,
        "max_iterations": max_iterations,
    }


# -----------------------------------------------------------------------------
# LLM 配置：从第 16 课复制的环境约定，不改其它课文件的前提下保持行为一致。
# -----------------------------------------------------------------------------
def _get_llm_config() -> tuple[str, str, str, str]:
    """
    Returns:
        provider, api_key, base_url, model
    """

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
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    # 返回值四元组给调用方判断是否具备完整调用条件
    return provider, api_key, base_url, model


def _build_ark_input(system: str, human: str) -> str:
    """将 system/human 压成方舟 SDK 需要的单段文本（与第 6、16 课一致）。"""
    LOG.info("build_ark_input: system=%s human=%s", system, human)
    return (
        "【系统要求】\n"
        f"{system}\n"
        "【用户任务】\n"
        f"{human}"
    )


def _call_ark(system: str, human: str, api_key: str, base_url: str, model: str) -> str:
    """延迟导入 Ark，便于未安装 SDK 时仍可跑 fallback Demo。"""
    from volcenginesdkarkruntime import Ark

    client = Ark(base_url=base_url, api_key=api_key)
    response = client.responses.create(
        model=model,
        input=_build_ark_input(system, human),
    )
    # 两套属性名容错：适配不同 SDK 小版本差异
    output_text = getattr(response, "output_text", "")
    if output_text:
        return str(output_text).strip()

    output_obj = getattr(response, "output", None)
    maybe_text = getattr(output_obj, "text", "") if output_obj is not None else ""
    if maybe_text:
        return str(maybe_text).strip()

    return str(response)


def _call_openai_chat(system: str, human: str, api_key: str, base_url: str, model: str, temperature: float) -> str:
    """LangChain ChatOpenAI 调用路径；temperature 对不同角色可调。"""
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
    )
    out = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])

    # content 通常为 str；防御性转成文本
    return str(out.content).strip()


def _invoke_llm_or_stub(
    role: str,
    system: str,
    human: str,
    *,
    temperature: float,
    stub_fn: Callable[[], str],
) -> tuple[str, str]:
    """
    Args:
        role: 仅为 diagnostics 打点用（planner / executor / critic）。
        system: LLM system 片段。
        human: LLM user/human 片段。
        temperature: 采样温度。
        stub_fn: 无密钥或导入失败时的模板生成。

    Returns:
        (生成的文本, 诊断标签)。
    """

    load_dotenv()
    provider, api_key, base_url, model = _get_llm_config()

    if not api_key or not base_url or not model:
        text = stub_fn()
        diag = f"{role}:llm_skipped_missing_env provider={provider}"
        _LOG.warning("[%s] %s", role, diag)
        return text, diag

    try:

        if provider == "ark":
            txt = _call_ark(system, human, api_key, base_url, model)
            return txt, f"{role}:llm_ok_ark"

        txt = _call_openai_chat(system, human, api_key, base_url, model, temperature=temperature)

        return txt, f"{role}:llm_ok_openai"
    except ModuleNotFoundError as exc:
        _LOG.warning("[%s] import error → stub (%s)", role, exc)
        return stub_fn(), f"{role}:llm_import_error"
    except Exception as exc:

        _LOG.exception("[%s] llm failure → stub", role)
        return stub_fn(), f"{role}:llm_error_{exc.__class__.__name__}"


# -----------------------------------------------------------------------------
# Critic JSON 解析：生产里常配合「输出 schema / tool」——本课手写解析以利阅读。
# -----------------------------------------------------------------------------
_JSON_BLOCK = re.compile(r"\{[^{}]*\"verdict\"[^{}]*\}", re.DOTALL)


def _parse_critic_payload(raw: str) -> tuple[CriticVerdict, str]:
    """

    Expect keys: verdict, feedback. Unknown verdict falls back to revise_executor once.

    Args:
        raw: 模型产出，可能混入 markdown 围栏。

    Returns:
        (verdict枚举, feedback文本)
    """

    text = raw.strip()

    verdict: CriticVerdict = "revise_executor"
    feedback = "默认：按照 Critic JSON 缺失或不可解析路由到 executor 修订。"
    blob = text

    m = _JSON_BLOCK.search(text)
    if m:
        blob = m.group(0)

    try:
        obj = json.loads(blob)
        v = str(obj.get("verdict", "")).strip().lower()
        if v in {"pass", "revise_executor", "revise_planner"}:

            verdict = v  # type: ignore[assignment]
        fb = obj.get("feedback", "")
        if isinstance(fb, str) and fb.strip():

            feedback = fb.strip()

    except json.JSONDecodeError:

        verdict = "revise_executor"
        feedback = "JSON 解析失败：请下一轮压缩输出为单行合法 JSON。"
    # 返回值供 critic 节点合并进 state

    return verdict, feedback


# -----------------------------------------------------------------------------
# 节点 normalize_goal：对齐第 16 课的空输入门禁写法。
# -----------------------------------------------------------------------------
def normalize_goal(state: AgentCollabState) -> dict[str, Any]:
    """

    Strip 空白；非法则打上 invalid Gate，Planner 根本不会被执行。

    Returns:
        局部增量 dict（LangGraph merge 进全局 state）。
    """

    raw = (state.get("user_goal") or "").strip()
    rid = state.get("request_id") or ""
    # 守卫：阻断空目标任务进入 planner，避免无谓 token 开销
    if not raw:

        _LOG.info("[%s] normalize_goal: invalid empty", rid)
        # 不写 plan/draft/critic——直接由后续收口节点对用户可见解释
        return {
            "user_goal": "",
            "goal_gate": "invalid",
            "diagnostics": ["normalize:invalid_empty"],
        }

    _LOG.info("[%s] normalize_goal: ok len=%s", rid, len(raw))
    # 清洗后的 canonical goal 回填，保证下游节点对齐同一字符串
    return {
        "user_goal": raw,
        "goal_gate": "ok",
        "diagnostics": ["normalize:ok"],
    }


def route_after_normalize_goal(state: AgentCollabState) -> Literal["ok", "invalid"]:
    """

    Conditional edge 函数的返回值必须与 `add_conditional_edges` routes 映射键完全一致。

    Returns:
        路由标签（不是下一个节点内部的业务 verdict）。
    """

    return "invalid" if state.get("goal_gate") == "invalid" else "ok"


# -----------------------------------------------------------------------------
# Fallback 三套角色产出：离线可复现、coverage CI 不需外网。
# -----------------------------------------------------------------------------
def _fallback_planner_text(goal: str) -> str:
    """离线计划模板：三段步骤，结构上像「可执行任务分解」而非散文。"""
    return (
        "【Fallback-Planner】\n"
        f"针对目标：{goal}\n\n"
        "步骤表：\n"
        "1. 复述用户目标并用一句话划定范围。\n"
        "2. 罗列 3 条以内可执行要点（不写空洞口号）。\n"
        "3. 指明若信息不足应向用户索要的关键字段。\n"
    )


def _fallback_executor_text(goal: str, plan: str, feedback: str) -> str:
    """Executor 必须把 plan_outline 与用户目标串起来产出草案。"""
    tail = ""
    if feedback.strip():

        tail = "\n上一轮 Critic：" + feedback.strip()
    # 草稿刻意短：展示「可被 Critic」形态
    return (
        "【Fallback-Executor 草案】\n"
        f"围绕「{goal}」按步骤执行。\n\n"
        f"执行依据（计划节选）：{plan[:200]}{'…' if len(plan) > 200 else ''}\n"
        f"{tail}"
    )


def planner_node(state: AgentCollabState) -> dict[str, Any]:
    """Planner：写入 plan_outline。"""
    rid = state.get("request_id") or ""
    goal = state.get("user_goal") or ""
    mode = state.get("mode", "fallback")

    fb = state.get("critic_feedback") or ""
    diag_tag = "planner:stub"

    if mode == "llm":
        system = (
            "你是企业内部的多步骤任务规划器（Planner）。"
            "只输出「可执行 checklist」，使用编号列表；不写最终对用户的长回答。"
            "若上一轮 Critic 要求改计划，请吸收其 critique 重写计划。"
        )
        human = f"业务目标（原文）：{goal}\n\n上一轮反馈（可为空）：{fb}\n"

        def stub() -> str:
            """LLM 不可用时兜底：仍要有结构化的计划占位。"""
            return _fallback_planner_text(goal)

        outline, diag_tag = _invoke_llm_or_stub("planner", system, human, temperature=0.2, stub_fn=stub)

    else:
        outline = _fallback_planner_text(goal)
        if fb.strip():

            outline += "\n（已并入 Critic 要求修订计划：" + fb.strip() + "）\n"

    _LOG.info("[%s] planner: outline_len=%s", rid, len(outline))

    return {
        "plan_outline": outline,
        # 回到 Planner 后可以清空旧草案，迫使 Executor 重写（教学上更清晰）
        "draft_answer": "",
        "diagnostics": [f"planner:done diag={diag_tag}"],
    }


def executor_node(state: AgentCollabState) -> dict[str, Any]:
    """Executor：只消费 plan + goal + （可选）上一轮针对 executor 的反馈。"""
    rid = state.get("request_id") or ""
    goal = state.get("user_goal") or ""
    plan = state.get("plan_outline") or ""
    mode = state.get("mode", "fallback")

    verdict = state.get("critic_verdict") or "pending"

    fb = state.get("critic_feedback") or ""
    diag_tag = "executor:stub"

    fb_for_exec = ""

    # 若非「改计划」类回流，可把 feedback 视作对草案的评语
    if verdict in {"revise_executor", "pending", "pass"} and fb.strip():

        fb_for_exec = fb.strip()

    if mode == "llm":
        system = (
            "你是企业内部执行写手（Executor）。"
            "根据 Planner 的步骤表，为用户提供「中文、可直接阅读的答复」。"
            "不得编造与用户目标无关的步骤；遵循计划先后顺序。"
            "若有 Critic 反馈且仍与当前草案有关，请务必逐条对齐修订。"
        )
        human = (
            f"用户目标：{goal}\n\n"
            f"计划：\n{plan}\n\n"
            f"针对草稿的上一轮批评（可能没有）：{fb_for_exec}\n"
        )

        def stub() -> str:
            return _fallback_executor_text(goal, plan, fb_for_exec)

        draft, diag_tag = _invoke_llm_or_stub("executor", system, human, temperature=0.25, stub_fn=stub)

    else:
        draft = _fallback_executor_text(goal, plan, fb_for_exec)

    _LOG.info("[%s] executor: draft_len=%s", rid, len(draft))
    # 草稿覆盖旧值：每次执行器运行都是新的草案版本
    return {
        "draft_answer": draft,
        "diagnostics": [f"executor:done diag={diag_tag}"],
    }


def _fallback_critic_routing(state: AgentCollabState) -> tuple[CriticVerdict, str]:
    """

    通过用户 goal 内置 token 观测三种路由 + 无限打转导致的 abort。

    优先级：FORCE_PASS > FORCE_REVISE_PLAN_* > FORCE_REVISE_EXEC_* > FORCE_MAX_SPIN > pass

    Returns:
        critic_verdict, critic_feedback。
    """

    goal = state.get("user_goal") or ""
    it_before = int(state.get("iteration") or 0)

    # 明示通过：门禁测试「最短路径 finalize_pass」
    if "FORCE_PASS" in goal:

        return "pass", "fallback:FORCE_PASS 触发直接通过。"
    # 第一轮打回 Planner、第二轮必须通过：演示「计划中游修正」回路
    if "FORCE_REVISE_PLAN_ONCE" in goal:

        return ("revise_planner", "fallback:请先收紧计划口径。") if it_before == 0 else ("pass", "fallback:计划已补足。")
    # 第一轮打执行器、第二轮通过：最常见的「措辞/事实密度」修整
    if "FORCE_REVISE_EXEC_ONCE" in goal:

        return ("revise_executor", "fallback:草稿缺具体动作。") if it_before == 0 else ("pass", "fallback:草稿已可读。")

    # 永远打回 executor——配合 max_iterations → finalize_abort
    if "FORCE_MAX_SPIN" in goal:

        return "revise_executor", "fallback:刻意制造打转供验收 max_iterations。"
    # 不含 token 的默认 fallback：单次轻微修订后收口为通过（使普通 demo 能结束）
    if it_before == 0:

        return "revise_executor", "fallback:第一轮常规挑刺（离线规则）。"
    return "pass", "fallback:第二轮视为满意。"


def critic_node(state: AgentCollabState) -> dict[str, Any]:
    """

    LLM path：强迫输出 JSON。\nFallback path：`FORCE_*` 规则。

    iteration 语义：仅在 **非 pass** 时递增，用于与 max_iterations 比较。

    Returns:
        含 verdict/feedback/iteration 增量。
    """
    rid = state.get("request_id") or ""
    mode = state.get("mode", "fallback")

    goal = state.get("user_goal") or ""
    plan = state.get("plan_outline") or ""

    draft = state.get("draft_answer") or ""
    max_it = int(state.get("max_iterations") or 3)
    it_before = int(state.get("iteration") or 0)
    verdict: CriticVerdict
    feedback: str
    diag_tag = ""

    if mode == "llm":
        system = (
            "你是质量标准审核员（Critic）。只允许输出单行 JSON对象，不要有 markdown，不要注释。"
            "Schema: {\"verdict\":\"pass|revise_executor|revise_planner\",\"feedback\":\"中文短评\"}"
            "\n裁决准则：plan 是否缺失关键步骤、draft 是否答非所问、draft 是否违背 plan。"
            "若仅是措辞问题选 revise_executor；若结构性缺失选 revise_planner。"
        )

        human = json.dumps(
            {"user_goal": goal, "plan_outline": plan[:4000], "draft_answer": draft[:6000]},
            ensure_ascii=False,
        )

        def stub() -> str:
            v, fb = _fallback_critic_routing(state)
            return json.dumps({"verdict": v, "feedback": fb}, ensure_ascii=False)

        payload, diag_tag = _invoke_llm_or_stub("critic", system, human, temperature=0.0, stub_fn=stub)
        verdict, feedback = _parse_critic_payload(payload)
        diag_tag = f"critic:{diag_tag}"
    else:
        verdict, feedback = _fallback_critic_routing(state)
        diag_tag = "critic:fallback_rules"

    it_after = it_before

    # 只有通过时不累计「修理次数」——否则每次非 pass 都 +1

    if verdict != "pass":

        it_after = it_before + 1

    _LOG.info(
        "[%s] critic: verdict=%s iteration %s→%s max=%s",
        rid,
        verdict,
        it_before,
        it_after,
        max_it,
    )

    # 单次合并返回：避免拆分多次 invoke 的中间态难以调试
    return {
        "critic_verdict": verdict,
        "critic_feedback": feedback,
        "iteration": it_after,
        "diagnostics": [f"critic:verdict={verdict} {diag_tag}"],
    }


def finalize_pass(state: AgentCollabState) -> dict[str, Any]:
    """通过闸门：对用户暴露的最终字段只保留 final_answer。"""
    rid = state.get("request_id") or ""
    ans = state.get("draft_answer") or ""
    _LOG.info("[%s] finalize_pass", rid)

    # 可把 draft 拷贝到 final，未来若要与「内部草稿」分离可在此处脱敏或加免责声明
    return {
        "final_answer": ans,
        "diagnostics": ["finalize:pass"],
    }


def finalize_abort(state: AgentCollabState) -> dict[str, Any]:
    """超限或风险场景：明示未通过质量闸，但仍然返回可观测的诊断链。"""
    rid = state.get("request_id") or ""
    _LOG.warning("[%s] finalize_abort iteration=%s", rid, state.get("iteration"))

    # 对用户可见话术需与 INTERNAL 报错区分——避免把 iteration 泄露成噪音，只表达「需人工介入」
    txt = (
        "【未完成自动修订】达到最大回路次数或未能在自动审核中收敛。\n"
        "最后草案（仅供参考）：\n"
        + (state.get("draft_answer") or "")
    )
    return {
        "final_answer": txt,
        "diagnostics": ["finalize:abort_max_iterations"],
    }


def seal_invalid_goal(_state: AgentCollabState) -> dict[str, Any]:
    """空目标专用收口——与第 16 课 seal_invalid_query 对称。"""
    return {
        "final_answer": "【输入无效】请先给出明确的业务目标或问题描述。",
        "diagnostics": ["seal:invalid_goal"],
    }


def route_after_critic(
    state: AgentCollabState,
) -> Literal["finalize_pass", "finalize_abort", "loop_executor", "loop_planner"]:
    """

    Conditional edges from critic：先判 pass / 超限，再看需回到哪个角色。

    Returns:
        routing map keys（不是 LangGraph END 常量）。
    """
    verdict = state.get("critic_verdict") or "pending"
    iteration = int(state.get("iteration") or 0)
    max_it = int(state.get("max_iterations") or 3)

    # 通过后立即收尾，不关心 iteration 计数

    if verdict == "pass":

        return "finalize_pass"

    # iteration：在 critic_node 已对非 pass 执行 +1——此处与 max_iterations 比较
    # 设计：iteration == max_it 仍可再走一轮修理；一旦 > max_it 立即停止（具体边界可用业务调参）

    if iteration > max_it:

        return "finalize_abort"

    if verdict == "revise_executor":

        return "loop_executor"
    # 其余 revise_planner 或未知 verdict 都打回 Planner 重新分解

    return "loop_planner"


def build_multi_agent_collab_graph() -> Any:

    """

    Registers nodes/wires compiling到可 repeatedly invoke 的图对象。

    Returns:
        CompiledGraph（类型随 langgraph 版本略有不同，脚本内用 Any 降低静态噪音）。
    """
    graph: StateGraph = StateGraph(AgentCollabState)

    # 注册节点：`name` 与条件边返回值引用的字符串严格一致——利于 draw_mermaid 对照

    graph.add_node("normalize_goal", normalize_goal)
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("critic", critic_node)

    graph.add_node("finalize_pass", finalize_pass)
    graph.add_node("finalize_abort", finalize_abort)
    graph.add_node("seal_invalid_goal", seal_invalid_goal)

    # ENTRY：用户目标先门禁，再决定是否进入 Planner

    graph.add_edge(START, "normalize_goal")
    routes_norm_ok: dict[str, str] = {
        "ok": "planner",
        "invalid": "seal_invalid_goal",
    }
    graph.add_conditional_edges("normalize_goal", route_after_normalize_goal, routes_norm_ok)

    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "critic")

    routes_crit = {
        "finalize_pass": "finalize_pass",
        "finalize_abort": "finalize_abort",
        "loop_executor": "executor",
        "loop_planner": "planner",
    }
    graph.add_conditional_edges("critic", route_after_critic, routes_crit)

    graph.add_edge("finalize_pass", END)
    graph.add_edge("finalize_abort", END)

    graph.add_edge("seal_invalid_goal", END)

    compiled = graph.compile()
    # compile() 后即得到与前几课一致的 invoke/stream 面板
    return compiled


def export_graph_png(compiled_graph: Any, filename: str) -> None:

    """

    Mirrors第16课PNG/Mermaid导出写法：绘图失败时将 `.mmd` 留给人工渲染。

    Args:
        compiled_graph：compile() 返回值。
        filename：`'17_multi_agent_collaboration_graph.png'`。
    """

    graph_obj = compiled_graph.get_graph()
    png_path = Path(__file__).with_name(filename)
    # 若缺少 graphviz 二进制，PNG 常会失败——此时保留 mermaid text 也不失真
    mermaid_path = Path(__file__).with_name(filename.replace(".png", ".mmd"))

    try:
        png_path.write_bytes(graph_obj.draw_mermaid_png())
        print(f"[图导出] {png_path}")
    except Exception as exc:  # noqa: BLE001 ——教案示例需要吞并打印原因

        mermaid_path.write_text(graph_obj.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mermaid_path}")


def _full_initial(
    request_id: str,
    goal: str,
    mode: RunMode,
    *,
    max_iterations: int,
) -> AgentCollabState:
    """构造完整 TypedDict：`diagnostics` 起点必须是空列表以启用 reducer。"""
    base = _initial_state_chunk(request_id, goal, mode, max_iterations=max_iterations)
    merged: AgentCollabState = {**base, "diagnostics": []}  # type: ignore[misc]

    return merged


def demo() -> None:

    """

    Demonstrates多条路径：`FORCE_*`/`invalid`/普通 fallback；最后导出拓扑图PNG。

    `mode=fallback` 让 CI/课堂零密钥可跑——需要真实 LLM 时改第三列或用环境变量触发。

    """

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    graph = build_multi_agent_collab_graph()

    scenarios: list[tuple[str, str, str, RunMode, int]] = [
        # (
        #     "case-pass-forced",
        #     "FORCE_PASS 写一个上线前检查单的骨架",
        #     "最短路径：Critic 直接 pass",
        #     "fallback",
        #     3,
        # )
        # ,
        (
            "case-exec-loop-once",
            "FORCE_REVISE_EXEC_ONCE：说明灰度发布的三个检查点",
            "Failure→Happy：_executor 回路一次后 pass",
            "fallback",
            3,
        )
        # ,
        # (
        #     "case-planner-loop-once",
        #     "FORCE_REVISE_PLAN_ONCE：如何把监控接入发布流水线",
        #     "Failure→Happy：_planner 回路一次后 pass",
        #     "fallback",
        #     3,
        # )
        # ,
        # (
        #     "case-spin-abort",
        #     "FORCE_MAX_SPIN 任意目标文本",
        #     "Failure：永远在 executor 打转→finalize_abort",
        #     "fallback",
        #     2,
        # )
        # ,
        # (
        #     "case-invalid-empty",
        #     "   ",
        #     "Failure：空目标 seal_invalid_goal",
        #     "fallback",
        #     3,
        # ),
    ]

    print("=" * 72)

    print("第十七课：多 Agent 协作（Planner / Executor / Critic）")
    print("=" * 72)

    for sid, goal, caption, md, mx in scenarios:
        print("\n" + "-" * 72)
        print(caption)

        print("-" * 72)
        out = graph.invoke(_full_initial(sid, goal, md, max_iterations=mx))
        print("="*72)
        print("final_answer:\n", (out.get("final_answer") or "").strip())
        print("="*72)
        print("critic_verdict:", out.get("critic_verdict"))
        print("="*72)
        print("iteration:", out.get("iteration"), "/", out.get("max_iterations"))
        print("="*72)
        print("diagnostics:", out.get("diagnostics"))
        print("="*72)


    # 单行 JSON Demo：对齐第16课末尾 json.dumps 打点方式，便于接入日志流水线

    sample = graph.invoke(_full_initial("json-demo", "解释 SLI/SLO", "fallback", max_iterations=3))
    print("\n[json]", json.dumps({"lesson": 17, "final_head": (sample.get("final_answer") or "")[:80]}, ensure_ascii=False))

    export_graph_png(graph, "17_multi_agent_collaboration_graph.png")

    print("\n" + "=" * 72)
    print("说明：mode=llm 时 LLM_PROVIDER=openai 用 OPENAI_*；ark 用 ARK_*（第 6/16 课一致）。")

    print("=" * 72)


if __name__ == "__main__":
    demo()
