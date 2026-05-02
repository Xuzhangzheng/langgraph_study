"""
无状态工具实现：纯函数，便于单测与将来替换成 HTTP/ gRPC 下游。

图内 `node_tools` 只负责 **编排与错误捕获**，真正的算术/时间规则在这里。
"""

from __future__ import annotations

import ast
import operator as op
from datetime import datetime


_ALLOWED_BINOPS: dict[type, object] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
}


def safe_eval_arithmetic(expression: str) -> float:
    """
    极简安全算术：只允许多个非负整数/小数的四则运算树；拒绝名字、调用、属性等。
    生产环境应换「专门数学库 / 沙箱服务」——此处与第 5/8 课教学同款思路。
    """

    tree = ast.parse(expression.strip(), mode="eval")  # 解析为表达式 AST

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)  # 一元负号
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
            fn = _ALLOWED_BINOPS[type(node.op)]
            return float(fn(_eval(node.left), _eval(node.right)))  # type: ignore[arg-type,misc]
        raise ValueError("unsupported_ast")

    return _eval(tree)


def now_local_iso() -> str:
    """返回本机当前时间 ISO 字符串，供「时间工具」节点引用。"""

    return datetime.now().astimezone().replace(microsecond=0).isoformat()
