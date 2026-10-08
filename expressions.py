"""Shared, bounded arithmetic expression evaluator; never executes Python code."""
import ast
import math
import operator
import re


class ExpressionEvaluator:
    BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow}
    CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
           ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}

    def __init__(self, fields):
        self.fields = list(fields)
        self.cache = {}

    def _prepare(self, expression):
        variables = {}
        def field(name):
            if name not in self.fields:
                raise ValueError(f'CSV column not found: {name}')
            token = f'__c{len(variables)}'
            variables[token] = name
            return token
        expression = str(expression).strip()
        if not expression or len(expression) > 500:
            raise ValueError('Enter an expression of 1 to 500 characters.')
        prepared = re.sub(r'\[([^\]]+)\]', lambda m: field(m[1]), expression)
        # One substitution pass avoids substituting generated variable names.
        prepared = re.sub(r'\b[A-Za-z_][A-Za-z0-9_]*\b',
                          lambda m: field(m[0]) if m[0] in self.fields else m[0], prepared)
        return prepared, variables

    def compile(self, expression):
        if expression in self.cache:
            return self.cache[expression]
        prepared, variables = self._prepare(expression)
        try:
            tree = ast.parse(prepared, mode='eval')
        except SyntaxError as exc:
            raise ValueError('Invalid expression syntax.') from exc
        nodes = list(ast.walk(tree))
        if len(nodes) > 150:
            raise ValueError('Expression is too complex.')
        allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Name,
                   ast.Load, ast.Constant, ast.UAdd, ast.USub, *self.BIN, *self.CMP)
        for node in nodes:
            if not isinstance(node, allowed):
                raise ValueError('Use arithmetic, comparisons, parentheses and CSV columns only.')
            if isinstance(node, ast.Name) and node.id not in variables:
                raise ValueError(f'Unknown name: {node.id}. Use [brackets] for channel names with spaces.')
            if isinstance(node, ast.Constant) and (type(node.value) not in (int, float) or abs(node.value) > 1e308):
                raise ValueError('Only finite numeric constants are allowed.')
        result = (tree.body, variables)
        self.cache[expression] = result
        return result

    def evaluate(self, expression, row):
        tree, variables = self.compile(expression)
        def visit(node):
            if isinstance(node, ast.Constant):
                return float(node.value)
            if isinstance(node, ast.Name):
                return float(row[variables[node.id]])
            if isinstance(node, ast.UnaryOp):
                value = visit(node.operand)
                return -value if isinstance(node.op, ast.USub) else value
            if isinstance(node, ast.Compare):
                left = visit(node.left)
                for op, other in zip(node.ops, node.comparators):
                    right = visit(other)
                    if not math.isfinite(left) or not math.isfinite(right):
                        raise ValueError('Nonfinite operand')
                    if not self.CMP[type(op)](left, right):
                        return 0.0
                    left = right
                return 1.0
            left, right = visit(node.left), visit(node.right)
            if not math.isfinite(left) or not math.isfinite(right):
                raise ValueError('Nonfinite operand')
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError('Exponent outside supported range')
            return self.BIN[type(node.op)](left, right)
        try:
            value = float(visit(tree))
            return value if math.isfinite(value) else None
        except (ValueError, TypeError, KeyError, ArithmeticError):
            return None
