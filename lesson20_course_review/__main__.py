"""
第二十课入口：

- 默认：打印课表摘要 + 进阶路线片段
- `--mmd`：写 `lesson20_learning_path.mmd`
- `--verify`：artifact 巡检 + 第 19 课回归（任一项失败则 exit 1）
"""

from __future__ import annotations

import argparse
import sys

from lesson20_course_review.advancement import format_roadmap_text
from lesson20_course_review.catalog import LESSONS
from lesson20_course_review.mermaid_path import write_mermaid
from lesson20_course_review.verify import repo_root_from_here, run_full_verify


def main() -> None:
    parser = argparse.ArgumentParser(description="第二十课：课程复盘与进阶路线")
    parser.add_argument("--mmd", action="store_true", help="写出学习路径 Mermaid 文件")
    parser.add_argument("--verify", action="store_true", help="artifact + lesson19 回归")
    parser.add_argument("--roadmap-only", action="store_true", help="只打印进阶路线")
    args = parser.parse_args()
    root = repo_root_from_here()

    if args.verify:
        rep = run_full_verify(root)
        if not rep.artifact_ok:
            print("[verify] 缺失 artifact：")
            for m in rep.missing:
                print("  ", m)
        else:
            print("[verify] artifacts OK")
        print(f"[verify] lesson19 regression {rep.regression_passed}/{rep.regression_total}")
        ok = rep.artifact_ok and rep.regression_passed == rep.regression_total
        sys.exit(0 if ok else 1)

    if args.roadmap_only:
        print(format_roadmap_text())
        return

    if args.mmd:
        p = write_mermaid(root)
        print(f"[lesson20] wrote {p}")
        return

    print("=== LangGraph 课程主路径（1～19）复盘 ===\n")
    for row in LESSONS:
        kw = ", ".join(row.keywords)
        print(f"  {row.no:2d}. {row.title}")
        print(f"      交付: {row.artifact}")
        print(f"      要点: {kw}\n")
    print(format_roadmap_text())


if __name__ == "__main__":
    main()
