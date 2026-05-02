"""
第十八课：生产化发布治理与版本契约（配置 · 锁定 · 门禁 · 风险评估）

与前序课关系：
--------------
- 第 6 课：LLM 与 Ark SDK；本课在 **风险评估节点** 复用同一套 `LLM_PROVIDER` / `ARK_*` / `OPENAI_*` 与 **`build_ark_input_text` 式的单串 input**。
- 第 13～14 课：可观测与容错；本课把「运维视角」搬进状态机：**分环境 profile、依赖 pin、契约版本、preflight**，失败走显式收口节点而非裸异常。
- 第 15 课：质量门禁思想；本课是 **发布侧门禁**（未过则 `seal_blocked`），可并入 CI/CD 前步。

本节要点（思想、问题拆解、要掌握的 API / 参数）：
--------------------------------------------------
1. **为何用 LangGraph 做「发布治理流水线」**
   - 与业务 Agent 图相同工具链：审计字段走状态、分支可测、可把一步拆成独立节点便于加日志与重试策略。
2. **分环境配置（12-factor 的缩小学）**
   - `app_env`：`dev` / `staging` / `prod`；`load_env_profile` 只读 **`os.environ`**（由 `load_dotenv` 预填），生成 **`env_profile_summary`** 便于 LLM 与人类报告引用。
3. **接口契约与「破坏性变更」**
   - 代码内常量 **`STATE_CONTRACT_VERSION`** 表示本图 **对外状态键语义** 的版本；环境变量 **`EXPECTED_STATE_CONTRACT_VERSION`** 表示上线清单期望版本；不一致 → **契约门禁失败**。
4. **依赖锁定（教学模拟）**
   - `REPO_DEPS_PIN`：仓库在 CI 注入的「锁定指纹」占位符；与 profile 中的 **`expected_deps_pin`** 比对；`dev` 常跳过，`staging`/`prod` 强制。
5. **`preflight_health`（健康检查桩）**
   - 汇聚为 `preflight_log`；失败条件：`FORCE_PREFLIGHT_FAIL` 或生产模式下缺失关键观测开关（本课用 **`REQUIRE_TRACING_IN_PROD`** 模拟）。
6. **LangGraph 1.1.10**
   - `StateGraph(TypedDict)`、`add_conditional_edges(source, router, {"返回值": "下一节点"})`：**返回值与字典键字符串完全一致**。
   - `Annotated[list[str], operator.add]`：`diagnostics` 多节点追加。
7. **LLM 风险评估（与第 6 课对齐）**
   - `mode=llm`：`LLM_PROVIDER=openai` → `ChatOpenAI.invoke([SystemMessage, HumanMessage])`；**`ark`** → `volcenginesdkarkruntime.Ark`、`client.responses.create(model=..., input=...)`，`input` 为单字符串。
   - Ark 响应：优先 **`output_text`**，否则 **`output.text`**，再 **`str(response)`**（小版本兼容）。
8. **Failure Path（必跑）**
   - 空 `release_id` → `seal_invalid_release`。
   - `FORCE_CONTRACT_FAIL` / `FORCE_LOCK_FAIL` / `FORCE_PREFLIGHT_FAIL` → `seal_blocked`。
   - `FORCE_HOLD` / `FORCE_ROLLBACK`：过门禁后在 `governance_finalize` 影响 **`governance_decision`**。

主路径 / 分支拓扑：
------------------
START → normalize_release ─route──→ load_env_profile → verify_contract_and_pins → preflight_health
                                                                                        ─route──→ assess_release_risk → governance_finalize → END
                                                                                        └→ seal_blocked → END
                          └→ seal_invalid_release → END

最小回归：
----------
`python 18_production_governance_graph.py`

行内注释约定：
--------------
- `import`、类型别名等「样板区」不强行逐行打断阅读。
- **每个节点函数**内，对影响状态写入与分支判断的语句附加行尾 `# …` 说明，贴近课堂板书节奏。

接口不变清单（本课 DoD）：
-------------------------
- `trace_id`, `app_env`, `mode`, `release_id`, `release_notes`, `release_gate`,
  `env_profile_summary`, `expected_contract_version`, `observed_contract_version`,
  `contract_check`, `expected_deps_pin`, `observed_deps_pin`, `dependency_lock_check`,
  `preflight_check`, `preflight_log`, `risk_narrative`, `governance_decision`,
  `final_report`, `diagnostics`
- `release_gate`：`pending` | `ok` | `invalid`
- `contract_check` / `dependency_lock_check` / `preflight_check`：`pending` | `pass` | `fail`
- `mode`：`llm` | `fallback`
- `governance_decision`：`pending` | `promote` | `hold` | `rollback_recommend`
"""

from __future__ import annotations  # 推迟注解求值，便于前向引用类型别名

import json  # 演示日志行 JSON 序列化（与第 16～17 课一致）
import logging  # 标准库日志，对齐第 13～14 课可观测习惯
import operator  # `operator.add` 用作 list reducer
import os  # 读环境变量：契约版本、REPO_DEPS_PIN、LLM 配置等
import re  # 在风险文本中匹配「致命」等关键词以自动 hold
from pathlib import Path  # 图导出路径与 __file__ 同级
from typing import Annotated, Any, Literal  # TypedDict、Literal 收窄、Annotated reducer

from dotenv import load_dotenv  # 与第 6 课一致：从仓库根 `.env` 装载
from typing_extensions import TypedDict  # Python 3.11 仍用扩展的 TypedDict 以统一课程风格

from langgraph.graph import END, START, StateGraph  # LangGraph 1.1.10 核心 API


# 与课程大纲中「接口不变」对应的**契约版本号**：与部署清单不一致时门禁失败（教学上模拟生产漂移）。
STATE_CONTRACT_VERSION = "2026.05.course.state.v18.v1"


_LOG = logging.getLogger("lesson18.production_governance")


ReleaseGate = Literal["pending", "ok", "invalid"]
RunMode = Literal["llm", "fallback"]
AppEnv = Literal["dev", "staging", "prod"]
TriState = Literal["pending", "pass", "fail"]
GovernanceDecision = Literal["pending", "promote", "hold", "rollback_recommend"]


class GovernancePipelineState(TypedDict):
    """
    发布治理流水线状态：字段名为双端（Python/Java）与评测契约的一部分，不要随意重命名。
    """

    trace_id: str
    app_env: AppEnv
    mode: RunMode
    release_id: str
    release_notes: str
    release_gate: ReleaseGate
    env_profile_summary: str
    expected_contract_version: str
    observed_contract_version: str
    contract_check: TriState
    expected_deps_pin: str
    observed_deps_pin: str
    dependency_lock_check: TriState
    preflight_check: TriState
    preflight_log: str
    risk_narrative: str
    governance_decision: GovernanceDecision
    final_report: str
    diagnostics: Annotated[list[str], operator.add]


def _initial_chunk(
    trace_id: str,
    app_env: AppEnv,
    mode: RunMode,
    release_id: str,
    release_notes: str,
) -> dict[str, Any]:
    """
    构造除 `diagnostics` 外的初始字段片段；`diagnostics` 在 invoke 入口单独给 `[]` 以启用 reducer。
    """

    return {
        "trace_id": trace_id,
        "app_env": app_env,
        "mode": mode,
        "release_id": release_id,
        "release_notes": release_notes,
        "release_gate": "pending",
        "env_profile_summary": "",
        "expected_contract_version": "",
        "observed_contract_version": STATE_CONTRACT_VERSION,
        "contract_check": "pending",
        "expected_deps_pin": "",
        "observed_deps_pin": "",
        "dependency_lock_check": "pending",
        "preflight_check": "pending",
        "preflight_log": "",
        "risk_narrative": "",
        "governance_decision": "pending",
        "final_report": "",
    }


def _get_llm_config() -> tuple[str, str, str, str]:
    """
    与第 6/16/17 课一致：返回 (provider, api_key, base_url, model)。
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

    return provider, api_key, base_url, model


def _build_ark_input(system: str, human: str) -> str:
    """
    Ark `responses.create` 仅接受单段 `input`：把 system/human 拼成与第 6 课相同的结构化文本。
    """

    return (
        "【系统要求】\n"
        f"{system}\n"
        "【用户任务】\n"
        f"{human}"
    )


def _call_ark(system: str, human: str, api_key: str, base_url: str, model: str) -> str:
    """
    延迟导入 Ark：未安装 SDK 时上层可捕获并回落模板文案。
    """

    from volcenginesdkarkruntime import Ark

    client = Ark(base_url=base_url, api_key=api_key)
    response = client.responses.create(
        model=model,
        input=_build_ark_input(system, human),
    )
    output_text = getattr(response, "output_text", "")
    if output_text:
        return str(output_text).strip()

    output_obj = getattr(response, "output", None)
    maybe_text = getattr(output_obj, "text", "") if output_obj is not None else ""
    if maybe_text:
        return str(maybe_text).strip()

    return str(response)


def _call_openai_chat(
    system: str,
    human: str,
    api_key: str,
    base_url: str,
    model: str,
) -> str:
    """
    OpenAI 兼容路径：`ChatOpenAI.invoke` 接收 `SystemMessage` + `HumanMessage`。
    """

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=model,
        temperature=0.1,
        api_key=api_key,
        base_url=base_url,
    )
    out = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    return str(out.content).strip()


def _invoke_llm_or_template(*, system: str, human: str, mode: RunMode) -> tuple[str, str]:
    """
    返回 (正文, 诊断后缀)；失败或 fallback 走模板，不抛异常到图外。
    """

    if mode != "llm":
        return (
            (
                "【Fallback-风险评估】\n"
                "1) 监控：请求错误率、P95 延迟、LLM 调用失败率、checkout 转化。\n"
                "2) 回滚：保留上一镜像 tag；一键切流或按比例灰度回退。\n"
                "3) 契约：对照 STATE_CONTRACT_VERSION 与集成测试黄金用例。\n"
            ),
            "risk:mode=fallback",
        )

    provider, api_key, base_url, model = _get_llm_config()
    if not api_key or not base_url or not model:
        return (
            "【Fallback-风险评估】缺少 LLM 密钥或模型配置；已跳过远端推理。",
            "risk:llm_config_incomplete",
        )

    try:
        if provider == "ark":
            body = _call_ark(system, human, api_key, base_url, model)
        else:
            body = _call_openai_chat(system, human, api_key, base_url, model)
        return body, f"risk:llm_ok:{provider}"
    except Exception as exc:  # noqa: BLE001 ——教案：写入 diagnostics 而非中断图
        return (
            f"【Fallback-风险评估】LLM 调用异常：{exc}",
            f"risk:llm_error:{type(exc).__name__}",
        )


def normalize_release(state: GovernancePipelineState) -> GovernancePipelineState:
    """
    门禁1：规范化 `release_id` / `release_notes`，空 ID 直接标 `invalid` 收口。
    """

    rid = (state.get("release_id") or "").strip()  # 去空白；避免仅空格的「伪 ID」
    notes = (state.get("release_notes") or "").strip()  # 变更说明与 FORCE_* 关键字共用此字段
    gate: ReleaseGate = "invalid" if not rid else "ok"  # 空 release_id 拒绝进入环境读取
    diag = f"normalize:gate={gate}"  # 审计：normalize 结果

    _LOG.info("[%s] normalize release_gate=%s", state.get("trace_id"), gate)  # 运维视角：关联 trace_id

    return {
        "release_id": rid,  # 写回规范化后的 ID
        "release_notes": notes,  # 写回规范化后的备注
        "release_gate": gate,  # 供条件边消费
        "diagnostics": [diag],  # reducer 追加一条
    }


def route_after_normalize(state: GovernancePipelineState) -> Literal["ok", "invalid"]:
    """
    条件边路由：`release_gate == invalid` → `seal_invalid_release`（键名在 build 中与节点名对应）。
    """

    return "invalid" if state.get("release_gate") == "invalid" else "ok"


def load_env_profile(state: GovernancePipelineState) -> GovernancePipelineState:
    """
    门禁2：按 `app_env` 加载**逻辑 profile**（工程上可替换为 Consul/K8s ConfigMap；此处用内存表 + 环境变量快照字符串）。
    """

    env = state["app_env"]  # 来自 invoke 初值：dev/staging/prod
    profiles: dict[AppEnv, dict[str, str]] = {
        "dev": {
            "expected_deps_pin": "",  # 开发机常不强制锁文件指纹
            "feature_flags": "shadow_mode=on,canary=0%",
            "log_level": "DEBUG",
        },
        "staging": {
            "expected_deps_pin": "sha256:course-staging-lock-001",  # 教学用固定期望值
            "feature_flags": "shadow_mode=off,canary=10%",
            "log_level": "INFO",
        },
        "prod": {
            "expected_deps_pin": "sha256:course-prod-lock-001",
            "feature_flags": "shadow_mode=off,canary=1%",
            "log_level": "WARN",
        },
    }
    row = profiles.get(env, profiles["dev"])  # 未知 env 回落 dev，防崩溃
    observed_pin = os.getenv("REPO_DEPS_PIN", "").strip()  # CI 注入的「锁定指纹」占位
    summary_lines = [
        f"app_env={env}",
        f"feature_flags={row['feature_flags']}",
        f"log_level={row['log_level']}",
        f"expected_deps_pin={row['expected_deps_pin'] or '(dev_skip)'}",
        f"REPO_DEPS_PIN_env={observed_pin or '(empty)'}",
    ]

    _LOG.info("[%s] load_env_profile lines=%s", state.get("trace_id"), len(summary_lines))  # 行数可 quick 检查

    return {
        "env_profile_summary": "\n".join(summary_lines),  # 给 LLM/人读的紧凑多行
        "expected_deps_pin": row["expected_deps_pin"],  # 下游门禁比对
        "observed_deps_pin": observed_pin,  # 实际环境
        "diagnostics": ["profile:loaded"],
    }


def verify_contract_and_pins(state: GovernancePipelineState) -> GovernancePipelineState:
    """
    门禁3：契约版本 + 依赖 pin；失败写入 `contract_check` / `dependency_lock_check` 供后续路由。
    """

    notes = state.get("release_notes") or ""  # 读取演练关键字 FORCE_*
    observed = STATE_CONTRACT_VERSION  # 代码内「真源」版本
    expected = os.getenv("EXPECTED_STATE_CONTRACT_VERSION", observed).strip()  # 部署清单侧期望；缺省则与代码一致 → 便于本地 Happy Path

    contract: TriState = "pass"  # 缺省通过
    if "FORCE_CONTRACT_FAIL" in notes:  # 教学：不改环境也能演练失败
        contract = "fail"
    elif expected != observed:  # 真实漂移：清单与代码常量不一致
        contract = "fail"

    lock: TriState = "pass"
    env_kind = state["app_env"]  # 与 profile 规则共用同一枚举
    exp_pin = (state.get("expected_deps_pin") or "").strip()  # profile 期望
    obs_pin = (state.get("observed_deps_pin") or "").strip()  # 环境实际
    if "FORCE_LOCK_FAIL" in notes:  # 教学演练
        lock = "fail"
    elif env_kind in ("staging", "prod"):  # 非 dev：强制对齐 pin
        if not exp_pin:  # profile 配置缺失（防御性）
            lock = "fail"
        elif obs_pin != exp_pin:  # CI 未注入或注入错指纹
            lock = "fail"

    _LOG.info(
        "[%s] verify contract=%s lock=%s",
        state.get("trace_id"),
        contract,
        lock,
    )

    return {
        "expected_contract_version": expected,  # 写入状态便于 seal_blocked 打印
        "observed_contract_version": observed,
        "contract_check": contract,  # 三元门禁之一
        "dependency_lock_check": lock,  # 三元门禁之二
        "diagnostics": [f"verify:contract={contract},lock={lock}"],
    }


def preflight_health(state: GovernancePipelineState) -> GovernancePipelineState:
    """
    门禁4：上线前健康与观测桩；生产要求 `REQUIRE_TRACING_IN_PROD=true`（教学用布尔 env）。
    """

    notes = state.get("release_notes") or ""
    lines: list[str] = [
        "check:artifact_present=pass",  # 模拟制品已上传
        "check:migration_dry_run=pass",  # 模拟 DB migration dry-run
    ]
    result: TriState = "pass"

    if "FORCE_PREFLIGHT_FAIL" in notes:  # 教学闸
        result = "fail"
        lines.append("check:forced_failure=fail")
    elif state["app_env"] == "prod":  # 生产附加条：必须打开 tracing 开关（占位语义）
        tracing = os.getenv("REQUIRE_TRACING_IN_PROD", "").strip().lower() in ("1", "true", "yes")
        if not tracing:
            result = "fail"
            lines.append("check:tracing_required_in_prod=fail")
        else:
            lines.append("check:tracing_required_in_prod=pass")
    else:
        lines.append("check:tracing_optional_non_prod=pass")

    log_body = "\n".join(lines)  # 多行文本进入状态，Seal/LLM 都能引用

    _LOG.info("[%s] preflight=%s", state.get("trace_id"), result)

    return {
        "preflight_check": result,  # 三元门禁之三
        "preflight_log": log_body,
        "diagnostics": [f"preflight:{result}"],
    }


def route_after_gates(state: GovernancePipelineState) -> Literal["continue", "blocked"]:
    """
    聚合三门禁：任一 `fail` → `blocked` → `seal_blocked` 节点生成人类可读失败报告。
    """

    if state.get("contract_check") == "fail":  # 短路：优先契约
        return "blocked"
    if state.get("dependency_lock_check") == "fail":  # 依赖漂移
        return "blocked"
    if state.get("preflight_check") == "fail":  # 可观测性/健康检查
        return "blocked"

    return "continue"  # 进入风险评估节点


def assess_release_risk(state: GovernancePipelineState) -> GovernancePipelineState:
    """
    在门禁全通过后，调用 LLM（或模板）生成**风险叙述**，供最终决策引用。
    """

    system = (  # System 侧：角色 + 输出形状（与第 6 课分层提示同一思路）
        "你是发布评审助手。根据给定的发布说明与环境摘要，输出简洁中文："
        "① 主要风险 ② 建议监控指标 ③ 回滚触发条件（各不超过 3 条短句）。"
        "不要编造未提供的版本号。"
    )
    human = (  # Human 侧：把状态里已审计的字段打包，避免模型编造 release_id
        f"release_id={state.get('release_id')}\n"
        f"release_notes:\n{state.get('release_notes')}\n\n"
        f"env_profile_summary:\n{state.get('env_profile_summary')}\n\n"
        f"preflight_log:\n{state.get('preflight_log')}\n"
    )
    body, diag = _invoke_llm_or_template(system=system, human=human, mode=state["mode"])  # 统一入口：内部再分 ark/openai/fallback

    return {
        "risk_narrative": body,  # 供 governance_finalize 解析关键词与输出报告
        "diagnostics": [diag],
    }


def governance_finalize(state: GovernancePipelineState) -> GovernancePipelineState:
    """
    综合 `risk_narrative` 与 **脚本关键字** 得出 `governance_decision` 并拼装 `final_report`。
    """

    notes = state.get("release_notes") or ""
    risk = (state.get("risk_narrative") or "").strip()
    decision: GovernanceDecision = "promote"
    if "FORCE_ROLLBACK" in notes:
        decision = "rollback_recommend"
    elif "FORCE_HOLD" in notes:
        decision = "hold"
    elif re.search(r"\b(致命|严重事故|P0)\b", risk):
        decision = "hold"

    report_lines = [
        f"[{state.get('trace_id')}] 发布治理结论",
        f"- app_env: {state.get('app_env')}",
        f"- release_id: {state.get('release_id')}",
        f"- contract: {state.get('contract_check')} (expected={state.get('expected_contract_version')}, observed={state.get('observed_contract_version')})",
        f"- dependency_lock: {state.get('dependency_lock_check')}",
        f"- preflight: {state.get('preflight_check')}",
        f"- decision: {decision}",
        "",
        "风险与操作提示：",
        risk,
    ]
    report = "\n".join(report_lines)

    _LOG.info("[%s] finalize decision=%s", state.get("trace_id"), decision)

    return {
        "governance_decision": decision,
        "final_report": report,
        "diagnostics": [f"finalize:{decision}"],
    }


def seal_blocked(state: GovernancePipelineState) -> GovernancePipelineState:
    """
    任一门禁失败时的收口：不调用 LLM，给出可审计的 `final_report`。
    """

    notes = state.get("release_notes") or ""
    reasons: list[str] = []
    if state.get("contract_check") == "fail":
        if "FORCE_CONTRACT_FAIL" in notes:
            reasons.append("契约校验失败：release_notes 含 FORCE_CONTRACT_FAIL（演练位），已阻断。")
        else:
            reasons.append(
                f"契约校验失败：期望 {state.get('expected_contract_version')} vs 代码 {state.get('observed_contract_version')}",
            )
    if state.get("dependency_lock_check") == "fail":
        if "FORCE_LOCK_FAIL" in notes:
            reasons.append("依赖锁定失败：release_notes 含 FORCE_LOCK_FAIL（演练位），已阻断。")
        else:
            reasons.append(
                f"依赖漂移：期望 pin={state.get('expected_deps_pin')!r} 环境 REPO_DEPS_PIN={state.get('observed_deps_pin')!r}",
            )
    if state.get("preflight_check") == "fail":
        reasons.append("预检失败，详见 preflight_log")

    body = "\n".join(reasons) if reasons else "未知阻塞原因（不应到达）"
    report = (
        f"[{state.get('trace_id')}] 发布已阻塞\n"
        f"app_env={state.get('app_env')} release_id={state.get('release_id')}\n\n"
        f"{body}\n\n"
        f"preflight_log:\n{state.get('preflight_log')}"
    )

    _LOG.warning("[%s] seal_blocked", state.get("trace_id"))

    return {
        "governance_decision": "hold",
        "risk_narrative": "",
        "final_report": report,
        "diagnostics": ["seal:blocked"],
    }


def seal_invalid_release(state: GovernancePipelineState) -> GovernancePipelineState:
    """
    空 `release_id` 的产品化收口：直接返回说明，不走后续环境读取（避免无意义 I/O）。
    """

    report = (
        f"[{state.get('trace_id')}] release_id 为空或仅空白，已拒绝执行后续治理步骤。"
    )

    return {
        "governance_decision": "hold",
        "final_report": report,
        "diagnostics": ["seal:invalid_release"],
    }


def build_production_governance_graph() -> Any:
    """
    装配 `StateGraph`：`compile()` 后为可 `invoke` 的图实例。
    """

    graph = StateGraph(GovernancePipelineState)

    graph.add_node("normalize_release", normalize_release)
    graph.add_node("load_env_profile", load_env_profile)
    graph.add_node("verify_contract_and_pins", verify_contract_and_pins)
    graph.add_node("preflight_health", preflight_health)
    graph.add_node("assess_release_risk", assess_release_risk)
    graph.add_node("governance_finalize", governance_finalize)
    graph.add_node("seal_blocked", seal_blocked)
    graph.add_node("seal_invalid_release", seal_invalid_release)

    graph.add_edge(START, "normalize_release")

    graph.add_conditional_edges(
        "normalize_release",
        route_after_normalize,
        {"ok": "load_env_profile", "invalid": "seal_invalid_release"},
    )

    graph.add_edge("load_env_profile", "verify_contract_and_pins")
    graph.add_edge("verify_contract_and_pins", "preflight_health")

    graph.add_conditional_edges(
        "preflight_health",
        route_after_gates,
        {"continue": "assess_release_risk", "blocked": "seal_blocked"},
    )

    graph.add_edge("assess_release_risk", "governance_finalize")
    graph.add_edge("governance_finalize", END)
    graph.add_edge("seal_blocked", END)
    graph.add_edge("seal_invalid_release", END)

    return graph.compile()


def export_graph_png(compiled_graph: Any, filename: str) -> None:
    """
    导出 PNG；若本机缺 graphviz，则写入 `.mmd` 由 Mermaid 渲染器处理。
    """

    graph_obj = compiled_graph.get_graph()
    png_path = Path(__file__).with_name(filename)
    mermaid_path = Path(__file__).with_name(filename.replace(".png", ".mmd"))

    try:
        png_path.write_bytes(graph_obj.draw_mermaid_png())
        print(f"[图导出] {png_path}")
    except Exception as exc:  # noqa: BLE001
        mermaid_path.write_text(graph_obj.draw_mermaid(), encoding="utf-8")
        print(f"[图导出] PNG 失败 ({exc})，已写 {mermaid_path}")


def _full_initial(
    trace_id: str,
    app_env: AppEnv,
    mode: RunMode,
    release_id: str,
    release_notes: str,
) -> GovernancePipelineState:
    """
    TypedDict 完整初态：`diagnostics` 必须 `[]`，否则 reducer 行为未定义。
    """

    base = _initial_chunk(trace_id, app_env, mode, release_id, release_notes)
    merged: GovernancePipelineState = {**base, "diagnostics": []}  # type: ignore[misc]
    return merged


def demo() -> None:
    """
    多场景演示：主路径、`FORCE_*`、空 release_id；最后导出拓扑图。
    """

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    load_dotenv()
    graph = build_production_governance_graph()

    scenarios: list[tuple[str, AppEnv, RunMode, str, str, str]] = [
        (
            "happy-dev",
            "dev",
            "fallback",
            "rel-1001",
            "例行迭代：优化 Prompt 缓存键；无 schema 变更。",
            "主路径：门禁通过 + fallback 风险评估",
        ),
        (
            "blocked-contract",
            "dev",
            "fallback",
            "rel-1002",
            "FORCE_CONTRACT_FAIL 人为演练清单失败",
            "契约门禁失败 → seal_blocked（dev 可单独验契约而不必先配 REPO_DEPS_PIN）",
        ),
        (
            "blocked-lock",
            "dev",
            "fallback",
            "rel-1003",
            "FORCE_LOCK_FAIL 依赖漂移演练",
            "锁定门禁失败（关键字强制；staging/prod 亦会校验真实 REPO_DEPS_PIN）",
        ),
        (
            "invalid-id",
            "dev",
            "fallback",
            "   ",
            "空 ID 应拒绝",
            "normalize → seal_invalid_release",
        ),
    ]

    print("=" * 72)
    print("第十八课：生产化发布治理与版本契约")
    print("=" * 72)

    for trace_id, env, mode, rid, notes, caption in scenarios:
        print("\n" + "-" * 72)
        print(caption)
        print("-" * 72)
        out = graph.invoke(_full_initial(trace_id, env, mode, rid, notes))
        print((out.get("final_report") or "").strip())
        print("[decision]", out.get("governance_decision"))
        print("[diagnostics]", out.get("diagnostics"))

    sample = graph.invoke(
        _full_initial(
            "json-demo",
            "dev",
            "fallback",
            "rel-json",
            "演示 JSON 日志接入",
        ),
    )
    print("\n[json]", json.dumps({"lesson": 18, "decision": sample.get("governance_decision")}, ensure_ascii=False))

    export_graph_png(graph, "18_production_governance_graph.png")

    print("\n" + "=" * 72)
    print(
        "说明：mode=llm 时 LLM_PROVIDER=openai 用 OPENAI_*；ark 用 ARK_*（与第 6 课一致）。"
        " staging/prod 需设置 REPO_DEPS_PIN 与 profile 中 expected 一致；"
        " prod 另需 REQUIRE_TRACING_IN_PROD=true 通过预检。",
    )
    print("=" * 72)


if __name__ == "__main__":
    demo()
