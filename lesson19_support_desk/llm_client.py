"""
LLM 网关：与第 6 课一致——`openai` 走 `ChatOpenAI`，`ark` 走 `volcenginesdkarkruntime.Ark`。

节点模块只调用 `generate_reply_text` / `judge_reply_quality`，不在业务文件里直接 `import Ark`。

质检协议（HTTP 外部服务与 LLM-as-judge 共用解析形状）：
- 成功时解析 JSON 对象，字段：`score`（0–100 整数）、`passed`（布尔）、`feedback`（字符串，未通过时回灌生成节点）。
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from lesson19_support_desk.state import RunMode


@dataclass(frozen=True)
class JudgeResult:
    """一次质检结果：供 `node_evaluate` 写入状态。"""

    score: int
    passed: bool
    feedback: str
    source: str  # judge:llm_openai | judge:llm_ark | judge:http | 由调用方追加


def _provider_bundle() -> tuple[str, str, str, str]:
    """读取 LLM_PROVIDER 及对应密钥、base、model。"""

    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider == "ark":
        key = os.getenv("ARK_API_KEY", "").strip()
        base = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").strip()
        model = os.getenv("ARK_MODEL", "").strip()
        return provider, key, base, model
    provider = "openai"
    key = os.getenv("OPENAI_API_KEY", "").strip()
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    return provider, key, base, model


def _ark_input(system: str, human: str) -> str:
    """Ark `responses.create` 仅支持单字符串 input：与第 6 课拼法一致。"""

    return "【系统要求】\n" + system + "\n【用户任务】\n" + human


def _call_ark(system: str, human: str, api_key: str, base_url: str, model: str) -> str:
    from volcenginesdkarkruntime import Ark

    client = Ark(base_url=base_url, api_key=api_key)
    resp = client.responses.create(model=model, input=_ark_input(system, human))
    out = getattr(resp, "output_text", "") or ""
    if out:
        return str(out).strip()
    obj = getattr(resp, "output", None)
    t = getattr(obj, "text", "") if obj is not None else ""
    if t:
        return str(t).strip()
    return str(resp)


def _call_openai(system: str, human: str, api_key: str, base_url: str, model: str, *, temperature: float = 0.2) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model=model, temperature=temperature, api_key=api_key, base_url=base_url)
    msg = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    return str(msg.content).strip()


def generate_reply_text(*, mode: RunMode, intent: str, user_message: str, feedback: str) -> tuple[str, str]:
    """
    返回 (正文, diagnostics 片段)。
    `mode=fallback` 时返回模板，不抛异常到图外。
    """

    if mode != "llm":
        fb = f"\n（上轮反馈：{feedback}）" if feedback.strip() else ""
        return (
            f"【Fallback-{intent}】已收到：{user_message[:200]}{'…' if len(user_message) > 200 else ''}"
            f"{fb}\n请补充订单号或物流单号便于处理。",
            "gen:fallback",
        )

    prov, key, base, model = _provider_bundle()
    if not key or not model:
        return "【Fallback】LLM 未配置完整密钥。", "gen:no_config"

    system = (
        "你是电商售前客服助手。根据 intent 用中文简短作答；缺信息时明确索要订单号或运单号。"
        " intent=" + intent
    )
    human = "用户原话：\n" + user_message + "\n" + (feedback.strip() and f"内部反馈：{feedback}\n")
    try:
        if prov == "ark":
            body = _call_ark(system, human, key, base, model)
            tag = "gen:ark"
        else:
            body = _call_openai(system, human, key, base, model)
            tag = "gen:openai"
        return body or "【空响应】", tag
    except Exception as exc:  # noqa: BLE001 —— Capstone：写入诊断而非崩溃
        return f"【LLM 异常】{type(exc).__name__}: {exc}", "gen:error"


def _parse_judge_json_blob(raw: str) -> JudgeResult | None:
    """从模型或 HTTP 响应中抽出首个 JSON 对象并转为 `JudgeResult`（`source` 由上层填写）。"""

    text = raw.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        d = json.loads(m.group())
        score = int(d["score"])
        score = max(0, min(100, score))
        passed_raw = d.get("passed", score >= 70)
        if isinstance(passed_raw, bool):
            passed = passed_raw
        else:
            passed = str(passed_raw).lower() in ("true", "1", "yes")
        fb = str(d.get("feedback", "")).strip()
        if not passed and not fb:
            fb = "质检未通过：请更具体并主动索要订单号/运单号（若适用）。"
        return JudgeResult(score=score, passed=passed, feedback=fb, source="")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def judge_reply_via_http(
    url: str,
    *,
    intent: str,
    user_message: str,
    draft_reply: str,
    timeout_sec: float,
) -> tuple[JudgeResult | None, str]:
    """POST JSON 到企业质检微服务；响应体须与 LLM-as-judge 同形的 JSON 对象。"""

    payload = json.dumps(
        {"intent": intent, "user_message": user_message, "draft_reply": draft_reply},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return None, f"judge:http_error:{type(exc).__name__}"

    parsed = _parse_judge_json_blob(body)
    if parsed is None:
        return None, "judge:http_bad_json"
    return (
        JudgeResult(
            score=parsed.score,
            passed=parsed.passed,
            feedback=parsed.feedback,
            source="judge:http",
        ),
        "judge:http_ok",
    )


def judge_reply_with_llm(*, intent: str, user_message: str, draft_reply: str) -> tuple[JudgeResult | None, str]:
    """LLM-as-judge：与生成共用 `LLM_PROVIDER` / `ARK_*` / `OPENAI_*`。"""

    prov, key, base, model = _provider_bundle()
    if not key or not model:
        return None, "judge:llm_no_config"

    system = (
        "你是严格的电商售前客服答复质检员。只输出一个 JSON 对象，不要代码块，不要其它文字。"
        '键：score(0到100的整数)、passed(布尔)、feedback(字符串)。'
        "规则：答复须礼貌、与 intent 相符；涉及退款/物流时应引导用户提供订单号或运单号；"
        "passed=true 当且仅当质量达到可对外发送标准。"
    )
    human = f"intent={intent}\n用户原话：\n{user_message}\n\n待评草稿：\n{draft_reply}\n"
    try:
        if prov == "ark":
            raw = _call_ark(system, human, key, base, model)
            tag_base = "judge:llm_ark"
        else:
            raw = _call_openai(system, human, key, base, model, temperature=0.0)
            tag_base = "judge:llm_openai"
        parsed = _parse_judge_json_blob(raw)
        if parsed is None:
            return None, f"{tag_base}_parse_fail"
        return (
            JudgeResult(
                score=parsed.score,
                passed=parsed.passed,
                feedback=parsed.feedback,
                source=tag_base,
            ),
            f"{tag_base}_ok",
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"judge:llm_exc:{type(exc).__name__}"


def judge_reply_quality(
    *,
    mode: RunMode,
    intent: str,
    user_message: str,
    draft_reply: str,
) -> tuple[JudgeResult | None, str]:
    """
    `mode=llm` 时：若配置了 `CAPSTONE_JUDGE_HTTP_URL` 则先走外部 HTTP；失败或未配置再走 LLM-as-judge。
    `None` 表示调用方应回退到规则评分。
    """

    if mode != "llm":
        return None, "judge:skip_mode_fallback"

    http_url = os.getenv("CAPSTONE_JUDGE_HTTP_URL", "").strip()
    if http_url:
        raw_to = os.getenv("CAPSTONE_JUDGE_HTTP_TIMEOUT", "30").strip() or "30"
        try:
            timeout_sec = float(raw_to)
        except ValueError:
            timeout_sec = 30.0
        timeout_sec = max(1.0, min(timeout_sec, 120.0))
        res, diag = judge_reply_via_http(
            http_url,
            intent=intent,
            user_message=user_message,
            draft_reply=draft_reply,
            timeout_sec=timeout_sec,
        )
        if res is not None:
            return res, diag

    return judge_reply_with_llm(intent=intent, user_message=user_message, draft_reply=draft_reply)
