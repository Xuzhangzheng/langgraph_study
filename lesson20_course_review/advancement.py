"""
进阶路线：把「学完之后干什么」落成**可打印的结构化章节**（非权威培训大纲，而是工程向备忘）。

对齐大纲「里程碑 E」：完成第 19 课 Capstone 后，用本模块做自规划检查点。
"""

from __future__ import annotations

# 三段式进阶（可与团队内部 30/60/90 天 OKR 对齐；此处保持通用）。
PHASE_NEXT_30_DAYS: tuple[str, ...] = (
    "巩固：用自己的业务域重写一条与第 4/19 课同构的「生成-评估」最小闭环。",
    "观测：为每个节点统一 `request_id` / `thread_id` 日志字段（对照第 13 课）。",
    "持久化：将第 12 课 InMemorySaver 换为团队选型的 Sqlite/Postgres checkpointer（另装官方扩展）。",
    "选修：跑通第 21 课将扩展的 `stream_mode` 与线上排错场景对齐。",
)

PHASE_60_TO_90_DAYS: tuple[str, ...] = (
    "规模化：多租户 `thread_id` 隔离、配额与限流（网关侧 + 节点内退避，对照第 14 课）。",
    "质量：把第 15 课黄金套件接入 CI；Capstone（第 19 课）增加 LLM-as-judge 成本与延迟预算。",
    "编排：在复杂域引入子图边界与显式状态契约（第 9/18 课组合）。",
    "治理：配置分环境、契约版本、发布门禁与回滚演练常态化（第 18 课流水线思想）。",
)


def format_roadmap_text() -> str:
    """供 CLI 与人类阅读的纯文本。"""
    lines: list[str] = [
        "=== 进阶路线（建议）===",
        "",
        "【约 30 天】",
        *[f"  - {x}" for x in PHASE_NEXT_30_DAYS],
        "",
        "【约 60～90 天】",
        *[f"  - {x}" for x in PHASE_60_TO_90_DAYS],
        "",
        "说明：Streaming 全量语义见大纲第 21 课；与第 13 课主脚本分工已写在大纲正文。",
    ]
    return "\n".join(lines)
