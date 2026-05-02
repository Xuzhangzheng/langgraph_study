"""
学习路径图：生成 **Mermaid** 源码，便于贴入 Confluence / Notion / 大纲附录。

不依赖 graphviz；由 `catalog.LESSONS` 驱动，避免手工维护两套列表。
"""

from __future__ import annotations

from pathlib import Path

from lesson20_course_review.catalog import LESSONS


def learning_mermaid_flowchart() -> str:
    """
    `flowchart LR`：按课号串联，关键字压缩在节点 label 内（仅作脑图提示）。
    """

    lines = [
        "%% 第二十课自动生成：课程主路径 1～19（与 lesson20_course_review.catalog 同源）",
        "flowchart LR",
    ]
    for i, row in enumerate(LESSONS):
        node = f"L{row.no}"
        kws = " / ".join(row.keywords[:2]) if row.keywords else ""
        label = f"{row.no}. {row.title}<br/><small>{kws}</small>"
        lines.append(f'  {node}["{label}"]')
        if i > 0:
            prev = f"L{LESSONS[i - 1].no}"
            lines.append(f"  {prev} --> {node}")
    lines.append("  L19 --> L20[20. 复盘与进阶路线<br/><small>本课工具包</small>]")
    return "\n".join(lines)


def write_mermaid(repo_root: Path, filename: str = "lesson20_learning_path.mmd") -> Path:
    """写入仓库根目录或指定目录旁；返回路径。"""
    out = (repo_root / filename).resolve()
    out.write_text(learning_mermaid_flowchart() + "\n", encoding="utf-8")
    return out
