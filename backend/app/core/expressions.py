"""A very small, safe expression evaluator.

The Condition and Filter nodes let a user type an expression such as
`value > 10 and "urgent" in value`. Running that through `eval` would hand
whoever built the pipeline the whole interpreter, so instead the expression
is parsed to an AST and walked by hand: only the node types listed below are
executed, and anything else raises `ExpressionError`.

There are no names to resolve beyond the ones the caller supplies, no
attribute access, no subscripting of arbitrary objects, no calls to anything
but the handful of whitelisted builtins, and no imports - so there is no
route from an expression to the filesystem, the network or the process.
"""

import ast
import operator
from typing import Any, Dict

MAX_EXPRESSION_LENGTH = 500

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}

_COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

# Pure, bounded, and safe to call with anything the walker can produce.
_FUNCTIONS = {
    'abs': abs,
    'bool': bool,
    'float': float,
    'int': int,
    'len': len,
    'lower': lambda s: str(s).lower(),
    'max': max,
    'min': min,
    'round': round,
    'str': str,
    'upper': lambda s: str(s).upper(),
}


class ExpressionError(ValueError):
    """Raised for anything the evaluator will not run."""


def _evaluate(node: ast.AST, names: Dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, names)

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in names:
            return names[node.id]
        raise ExpressionError("unknown name '{}'".format(node.id))

    if isinstance(node, ast.BinOp):
        handler = _BINARY.get(type(node.op))
        if handler is None:
            raise ExpressionError('unsupported operator')
        # Guarded so a typo divides by zero into a readable message rather
        # than an unhandled ZeroDivisionError from inside the engine.
        try:
            return handler(_evaluate(node.left, names), _evaluate(node.right, names))
        except ZeroDivisionError:
            raise ExpressionError('division by zero')

    if isinstance(node, ast.UnaryOp):
        handler = _UNARY.get(type(node.op))
        if handler is None:
            raise ExpressionError('unsupported unary operator')
        return handler(_evaluate(node.operand, names))

    if isinstance(node, ast.BoolOp):
        values = node.values
        if isinstance(node.op, ast.And):
            result: Any = True
            for value in values:
                result = _evaluate(value, names)
                if not result:
                    return result  # Short-circuits, like Python itself.
            return result
        result = False
        for value in values:
            result = _evaluate(value, names)
            if result:
                return result
        return result

    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, names)
        for op, comparator in zip(node.ops, node.comparators):
            handler = _COMPARE.get(type(op))
            if handler is None:
                raise ExpressionError('unsupported comparison')
            right = _evaluate(comparator, names)
            if not handler(left, right):
                return False
            left = right  # Keeps chained comparisons (a < b < c) correct.
        return True

    if isinstance(node, ast.Call):
        # Only bare names, so `obj.method()` and `__import__(...)` cannot appear.
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise ExpressionError('only simple function calls are allowed')
        function = _FUNCTIONS.get(node.func.id)
        if function is None:
            raise ExpressionError("unknown function '{}'".format(node.func.id))
        return function(*[_evaluate(arg, names) for arg in node.args])

    if isinstance(node, (ast.List, ast.Tuple)):
        values = [_evaluate(element, names) for element in node.elts]
        return values if isinstance(node, ast.List) else tuple(values)

    if isinstance(node, ast.IfExp):
        branch = node.body if _evaluate(node.test, names) else node.orelse
        return _evaluate(branch, names)

    raise ExpressionError('{} is not allowed in an expression'.format(type(node).__name__))


def evaluate(expression: str, names: Dict[str, Any]) -> Any:
    """Evaluate `expression` with `names` in scope.

    Raises `ExpressionError` for a syntax error or for any construct outside
    the supported subset.
    """
    if not isinstance(expression, str) or not expression.strip():
        raise ExpressionError('expression is empty')
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ExpressionError(
            'expression exceeds {} characters'.format(MAX_EXPRESSION_LENGTH)
        )

    try:
        tree = ast.parse(expression.strip(), mode='eval')
    except SyntaxError as error:
        raise ExpressionError('syntax error: {}'.format(error.msg))

    return _evaluate(tree, names)


def evaluate_truthy(expression: str, names: Dict[str, Any]) -> bool:
    """Evaluate and coerce to a bool, for the branching nodes."""
    return bool(evaluate(expression, names))
