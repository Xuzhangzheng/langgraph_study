"""
整体验证：① 主路径 artifact 是否存在于仓库；② 第 19 课回归套件是否全绿。

模拟「结课 CI」——失败时 **exit code 1**（由 `__main__.py` 消费）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lesson20_course_review.catalog import LESSONS


@dataclass(frozen=True)
class VerifyReport:
    artifact_ok: bool
    missing: tuple[str, ...]
    regression_passed: int
    regression_total: int


def repo_root_from_here() -> Path:
    """`lesson20_course_review/` 的父目录即仓库根（与第 19 课包并列）。"""
    return Path(__file__).resolve().parent.parent


def check_artifacts(root: Path) -> tuple[bool, tuple[str, ...]]:
    missing: list[str] = []
    for row in LESSONS:
        rel = row.artifact
        p = root / rel
        if rel == "lesson19_support_desk":
            if not p.is_dir():
                missing.append(rel)
        elif not p.is_file():
            missing.append(rel)
    return len(missing) == 0, tuple(missing)


def run_full_verify(root: Path | None = None) -> VerifyReport:
    """执行 artifact 检查 + 挂载 `lesson19_support_desk.regression.run_suite`。"""
    r = root or repo_root_from_here()
    ok, miss = check_artifacts(r)

    from lesson19_support_desk.regression import run_suite

    passed, total = run_suite(use_checkpointer=False)

    return VerifyReport(
        artifact_ok=ok,
        missing=miss,
        regression_passed=passed,
        regression_total=total,
    )
