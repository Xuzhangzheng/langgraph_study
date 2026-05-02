"""
第十九课（Capstone）：多文件「支持台」应用包。

用 `python -m lesson19_support_desk` 从仓库根目录启动；不要把这个目录当作散落的脚本集合，
而是当作一个企业里可继续拆微服务、接 API 的 **应用边界**。
"""

from lesson19_support_desk.application import SupportDeskApplication
from lesson19_support_desk.workflow import build_support_desk_graph

__all__ = ["SupportDeskApplication", "build_support_desk_graph"]
