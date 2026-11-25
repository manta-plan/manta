# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""`${{ ... }}` expressions in playbook documents, parsed and evaluated without `eval`.

A value either is a whole expression, or contains none: text around an expression is
refused, so an expression always evaluates to a value of its own type.
"""

import operator
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from lark import Lark, Token, Transformer, UnexpectedCharacters, UnexpectedToken, v_args

ROOTS = frozenset({"inputs"})
"""What a reference can start from."""

EXPRESSION_START = "${{"

_WHOLE = re.compile(r"^\$\{\{(?P<body>(?:(?!\}\}).)*)\}\}$", re.DOTALL)
_GRAMMAR = r"""
?start: disjunction
?disjunction: conjunction ("||" conjunction)*
?conjunction: comparison ("&&" comparison)*
?comparison: unary (COMPARE unary)?
?unary: "!" unary -> negation
      | "(" disjunction ")"
      | STRING -> string
      | NUMBER -> number
      | KEYWORD -> keyword
      | NAME ("." NAME)* -> ref

COMPARE: "==" | "!=" | "<=" | ">=" | "<" | ">"
STRING: /'(?:[^']|'')*'/
NUMBER: /-?\d+(?:\.\d+)?/
KEYWORD.2: /(?:true|false|null)\b/
NAME: /[A-Za-z_]\w*/

%ignore /\s+/
"""
_KEYWORDS: dict[str, object] = {"true": True, "false": False, "null": None}
_COMPARISONS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}
_ORDERINGS = frozenset({"<", "<=", ">", ">="})


class ExpressionError(ValueError):
    """Raised for an expression that cannot be parsed or evaluated."""


@dataclass(frozen=True)
class Const:
    value: object


@dataclass(frozen=True)
class Ref:
    root: str
    path: tuple[str, ...] = ()

    def __str__(self) -> str:
        return ".".join((self.root, *self.path))


@dataclass(frozen=True)
class Not:
    operand: "Node"


@dataclass(frozen=True)
class Logical:
    op: str
    operands: tuple["Node", ...]


@dataclass(frozen=True)
class Compare:
    op: str
    left: "Node"
    right: "Node"


Node = Const | Ref | Not | Logical | Compare


@v_args(inline=True)
class _Build(Transformer[Token, Node]):
    def disjunction(self, *operands: Node) -> Logical:
        return Logical("||", operands)

    def conjunction(self, *operands: Node) -> Logical:
        return Logical("&&", operands)

    def comparison(self, left: Node, op: Token, right: Node) -> Compare:
        return Compare(str(op), left, right)

    def negation(self, operand: Node) -> Not:
        return Not(operand)

    def string(self, token: Token) -> Const:
        return Const(token[1:-1].replace("''", "'"))

    def number(self, token: Token) -> Const:
        return Const(float(token) if "." in token else int(token))

    def keyword(self, token: Token) -> Const:
        return Const(_KEYWORDS[token])

    def ref(self, root: Token, *path: Token) -> Ref:
        return Ref(str(root), tuple(map(str, path)))


_PARSER = Lark(_GRAMMAR, parser="lalr", transformer=_Build())


def _parse_body(body: str) -> Node:
    try:
        node: Node = _PARSER.parse(body)
    except UnexpectedCharacters as exc:
        raise ExpressionError(
            f"Cannot read {body[exc.pos_in_stream :].strip()!r} in {body!r}"
        ) from exc
    except UnexpectedToken as exc:
        if exc.token.type == "$END":
            raise ExpressionError(f"Unexpected end of {body!r}") from exc
        raise ExpressionError(f"Unexpected {exc.token.value!r} in {body!r}") from exc
    for ref in refs(node):
        if ref.root not in ROOTS:
            raise ExpressionError(
                f"{ref.root!r} in {body!r} is not something an expression can read; "
                f"use one of {sorted(ROOTS)}"
            )
    return node


def is_expression(value: object) -> bool:
    """Whether `value` is text holding an expression, whole or not."""
    return isinstance(value, str) and EXPRESSION_START in value


def parse(text: str) -> Node:
    """Parse a whole `${{ ... }}` expression."""
    match = _WHOLE.match(text.strip())
    if match is None:
        raise ExpressionError(
            f"{text!r} mixes an expression with other text; a value must be one whole "
            f"`${{{{ ... }}}}` expression or contain none"
        )
    return _parse_body(match.group("body"))


def check_expression(text: str) -> str:
    """Return `text` if it is one whole expression that parses."""
    parse(text)
    return text


def refs(node: Node) -> set[Ref]:
    """Every reference `node` reads."""
    match node:
        case Const():
            return set()
        case Ref():
            return {node}
        case Not(operand):
            return refs(operand)
        case Logical(_, operands):
            return set().union(*map(refs, operands))
        case Compare(_, left, right):
            return refs(left) | refs(right)


def _lookup(ref: Ref, scope: Mapping[str, Any]) -> object:
    if ref.root not in scope:
        raise ExpressionError(f"{ref} cannot be read here: nothing provides {ref.root!r}")
    value = scope[ref.root]
    for name in ref.path:
        if not isinstance(value, Mapping) or name not in value:
            raise ExpressionError(f"{ref} does not exist")
        value = value[name]
    return value


def _compare(op: str, left: object, right: object) -> bool:
    numbers = all(isinstance(x, int | float) and not isinstance(x, bool) for x in (left, right))
    texts = all(isinstance(x, str) for x in (left, right))
    if op in _ORDERINGS and not (numbers or texts):
        raise ExpressionError(f"Cannot order {left!r} {op} {right!r}")
    return _COMPARISONS[op](left, right)


def evaluate(node: Node, scope: Mapping[str, Any]) -> object:
    """The value of `node`, reading references from `scope` (root name to value)."""
    match node:
        case Const(value):
            return value
        case Ref():
            return _lookup(node, scope)
        case Not(operand):
            return not evaluate(operand, scope)
        case Logical("&&", operands):
            return all(evaluate(operand, scope) for operand in operands)
        case Logical(_, operands):
            return any(evaluate(operand, scope) for operand in operands)
        case Compare(op, left, right):
            return _compare(op, evaluate(left, scope), evaluate(right, scope))


def map_expressions(value: object, function: Callable[[Node], object]) -> object:
    """`value` with every expression in it, at any depth, replaced by `function(node)`."""
    if isinstance(value, dict):
        return {key: map_expressions(item, function) for key, item in value.items()}
    if isinstance(value, list):
        return [map_expressions(item, function) for item in value]
    if isinstance(value, Node):
        return function(value)
    if is_expression(value):
        return function(parse(value))
    return value


def check_expressions_in(value: object) -> object:
    """Return `value` if every expression in it parses."""
    map_expressions(value, lambda node: node)
    return value


def substitute(value: object, scope: Mapping[str, Any]) -> object:
    """`value` with every expression in it evaluated against `scope`."""
    return map_expressions(value, lambda node: evaluate(node, scope))
