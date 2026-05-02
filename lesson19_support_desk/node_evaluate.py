"""
评估节点：
- **`mode=fallback`**（整条生成链未调主 LLM）：沿用 **规则评分**，与离线回归一致。
- **`mode=llm`**：优先 **外部 HTTP 质检**（`CAPSTONE_JUDGE_HTTP_URL`），否则 **LLM-as-judge**
  （与第 6 课同源网关：`LLM_PROVIDER` + `ARK_*` / `OPENAI_*`）；解析失败或异常时 **回退规则**，保证图不崩。

输出 `quality_passed` 驱动条件边是否回到 `generate_reply`。
"""

from __future__ import annotations

from lesson19_support_desk.llm_client import judge_reply_quality
from lesson19_support_desk.state import RunMode, SupportDeskState


def _evaluate_by_rules(state: SupportDeskState) -> SupportDeskState:
    """教学用规则评分（与原 Capstone 行为一致），作 fallback / fallback 模式主路径。"""

    draft = (state.get("draft_reply") or "").strip()
    intent = state.get("intent") or "general"

    score = 30
    if len(draft) >= 40:
        score += 30
    if intent in ("refund", "shipping") and any(k in draft for k in ("订单", "单号", "运单", "物流")):
        score += 25
    elif intent == "general":
        score += 15
    if "LLM 异常" in draft or "【LLM 异常】" in draft:
        score = min(score, 45)

    passed = score >= 70
    fb = "" if passed else "请更具体：给出可操作步骤，并主动索要订单号/运单号（若适用）。"

    return {
        "quality_score": min(100, score),
        "quality_passed": passed,
        "feedback_for_generation": fb,
        "diagnostics": [f"evaluate:rules_score={score},pass={passed}"],
    }


def evaluate_reply(state: SupportDeskState) -> SupportDeskState:
    mode: RunMode = state.get("mode") or "fallback"  # type: ignore[assignment]
    intent = str(state.get("intent") or "general")
    user_message = (state.get("normalized_message") or "").strip()
    draft = (state.get("draft_reply") or "").strip()

    if mode == "llm" and draft:
        judged, diag = judge_reply_quality(
            mode=mode,
            intent=intent,
            user_message=user_message,
            draft_reply=draft,
        )
        if judged is not None:
            fb = judged.feedback if not judged.passed else ""
            return {
                "quality_score": judged.score,
                "quality_passed": judged.passed,
                "feedback_for_generation": fb,
                "diagnostics": [f"evaluate:{judged.source},{diag}"],
            }

        merged = _evaluate_by_rules(state)
        extra = merged.get("diagnostics") or []  # type: ignore[assignment]
        return {
            **merged,
            "diagnostics": list(extra) + [f"evaluate:fallback_rules_after_judge,{diag}"],
        }

    return _evaluate_by_rules(state)
