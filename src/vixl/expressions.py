"""Safe arithmetic for templates, workflows and the ``calc`` variable filter.

A template or workflow field whose whole value is a string starting with ``=`` is an expression once its
``${variables}`` are filled: ``"=${pad} + 76.34 * ${k}"``. Plain text is never evaluated (``==`` writes a literal
leading ``=``). The expression is parsed with ``ast`` and walked node by node; nothing reaches ``eval`` or ``exec``.

Allowed: numbers, ``+ - * / // %``, unary ``-`` and ``+``, parentheses, and the functions ``min``, ``max``, ``round``
and ``abs`` called with plain arguments. Everything else is refused: names (only the ``calc`` filter's ``x``),
attributes, subscripts, keywords, strings, comparisons, ``**`` (no exponent, so no huge numbers) and any other call.
Work is bounded: at most ``MAX_LENGTH`` characters and ``MAX_NODES`` syntax nodes, finite results within
``MAX_MAGNITUDE``, and division or remainder by zero is an error.
"""

import ast
import math

from .errors import VixlError

MAX_LENGTH = 500
MAX_NODES = 200
MAX_MAGNITUDE = 1e12
FUNCTIONS = {"min": 2, "max": 2, "round": 1, "abs": 1}  # the fewest arguments each takes
OPERATORS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%"}


def _error(text, message):
    return VixlError("invalid_expression", f"Expression {text!r}: {message}", field="expression",
                     allowed=["numbers", "+ - * / // %", "parentheses", "min", "max", "round", "abs"])


def is_expression(value):
    return isinstance(value, str) and value.startswith("=") and not value.startswith("==")


def evaluate(text, names=None):
    """The number ``text`` (without its leading ``=``) evaluates to: an int when it is whole, else a float.
    ``names`` binds the only names allowed (the ``calc`` filter binds ``x``)."""
    names = names or {}
    if not isinstance(text, str) or not text.strip():
        raise _error(text, "is empty")
    if len(text) > MAX_LENGTH:
        raise _error(text[:40] + "…", f"is longer than {MAX_LENGTH} characters")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise _error(text, "is not arithmetic (numbers, operators, parentheses, min, max, round, abs)") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise _error(text, f"has more than {MAX_NODES} parts")
    value = _number(_walk(tree.body, text, names), text)
    return int(value) if float(value).is_integer() else value


def _number(value, text):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(text, "does not give a number")
    try:
        value = float(value)
    except OverflowError as exc:
        raise _error(text, "is too large") from exc
    if not math.isfinite(value) or abs(value) > MAX_MAGNITUDE:
        raise _error(text, f"gives a number beyond ±{MAX_MAGNITUDE:g}")
    return value


def _walk(node, text, names):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise _error(text, f"{node.value!r} is not a number")
        return _number(node.value, text)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _walk(node.operand, text, names)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
        left, right = _walk(node.left, text, names), _walk(node.right, text, names)
        kind = type(node.op)
        if kind in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise _error(text, "divides by zero")
        if kind is ast.Add:
            result = left + right
        elif kind is ast.Sub:
            result = left - right
        elif kind is ast.Mult:
            result = left * right
        elif kind is ast.Div:
            result = left / right
        elif kind is ast.FloorDiv:
            result = left // right
        else:
            result = left % right
        return _number(result, text)
    if isinstance(node, ast.Name):
        if node.id in names:
            return _number(names[node.id], text)
        raise _error(text, f"names {node.id!r}; only numbers and min, max, round and abs calls are allowed"
                     + (f" (and {', '.join(sorted(names))})" if names else ""))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            raise _error(text, "calls something other than min, max, round or abs")
        name = node.func.id
        if node.keywords or any(isinstance(arg, ast.Starred) for arg in node.args):
            raise _error(text, f"{name} takes plain arguments")
        args = [_walk(arg, text, names) for arg in node.args]
        if name in ("min", "max"):
            if not 2 <= len(args) <= 32:
                raise _error(text, f"{name} takes 2 to 32 numbers")
            return min(args) if name == "min" else max(args)
        if name == "abs":
            if len(args) != 1:
                raise _error(text, "abs takes one number")
            return abs(args[0])
        if not 1 <= len(args) <= 2 or (len(args) == 2 and not (args[1].is_integer() and 0 <= args[1] <= 10)):
            raise _error(text, "round takes a number and optionally 0 to 10 decimals")
        return float(round(args[0], int(args[1]) if len(args) == 2 else None))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        raise _error(text, "uses **; exponents are not supported")
    raise _error(text, f"uses {type(node).__name__}, which is not arithmetic")


def resolve(value, substitute, notes=None):
    """``value`` with every whole-field ``=`` expression evaluated after ``substitute`` fills its variables.
    ``notes`` collects ``"FIELD: EXPRESSION → RESULT"`` lines for the ``normalized`` report."""

    def visit(item, path):
        if isinstance(item, dict):
            return {key: visit(child, f"{path}.{key}" if path else key) for key, child in item.items()}
        if isinstance(item, list):
            return [visit(child, f"{path}[{index}]") for index, child in enumerate(item)]
        if isinstance(item, str) and item.startswith("=="):
            return substitute(item[1:])
        if is_expression(item):
            filled = substitute(item[1:])
            result = evaluate(filled if isinstance(filled, str) else str(filled))
            if notes is not None:
                notes.append(f"{path or 'value'}: {item!r} → {result}")
            return result
        return substitute(item) if isinstance(item, str) else item

    return visit(value, "")
