"""
环境与静态配置：集中读 `.env` / `os.environ`，避免节点函数里散落 `getenv`。

职责：
- 决定默认 `mode`、日志级别占位；
- 不把业务状态写在这里——业务只在 `state.py`。
"""

from __future__ import annotations

import os

from dotenv import load_dotenv


def bootstrap_env() -> None:
    """在进程入口调用一次：加载仓库根 `.env`，与第 6 课惯例一致。"""

    load_dotenv()  # 幂等；重复调用通常无害


def default_run_mode() -> str:
    """演示默认走 `fallback`；真实环境可由 `CAPSTONE_LLM_MODE` 覆盖为 `llm`。"""

    return os.getenv("CAPSTONE_LLM_MODE", "fallback").strip().lower()  # llm | fallback


def default_max_attempts_generate() -> int:
    """生成—评估回路的上限，与第 4 课 `max_attempts` 思想一致。"""

    raw = os.getenv("CAPSTONE_MAX_ATTEMPTS", "2").strip()
    return max(1, int(raw))  # 至少 1，防配置成 0
