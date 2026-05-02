"""
状态契约（接口不变）：全图节点只通过本 `TypedDict` 通信。

Capstone 刻意把「字段含义」固定在一处文件，模拟企业里的 **API / Proto / OpenAPI** 单源。
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

MessageGate = Literal["pending", "ok", "invalid"]
Intent = Literal["pending", "refund", "shipping", "general", "math", "time", "invalid"]
RunMode = Literal["llm", "fallback"]


class SupportDeskState(TypedDict):
    """售前支持台主状态：线程级数据由 checkpointer + `thread_id` 承载（见 `application.py`）。"""

    request_id: str  # 单次请求关联 ID（日志、追踪）
    user_message: str  # 原始用户输入
    normalized_message: str  # 去空白等规范结果
    message_gate: MessageGate  # 入参门禁
    intent: Intent  # 路由意图
    tool_expression: str  # 算术分支时抽取的表达式
    tool_output: str  # 工具成功输出
    tool_error: str  # 工具失败原因
    draft_reply: str  # LLM 或工具链路中间的「答复草稿」
    final_reply: str  # 对用户暴露的唯一收口文本
    quality_score: int  # 评估节点写入 0–100
    quality_passed: bool  # 是否通过门槛
    feedback_for_generation: str  # 未通过时回灌给生成节点
    attempt: int  # 当前生成轮次
    max_attempts: int  # 与第 4 课同一语义的安全上限
    mode: RunMode  # llm | fallback
    diagnostics: Annotated[list[str], operator.add]  # 多节点追加审计
