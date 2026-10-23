# SPDX-FileCopyrightText: datarecord Contributors
#
# SPDX-License-Identifier: MIT

import ast
import re
from collections.abc import Iterator
from pathlib import Path


def _code_strings(path: Path) -> Iterator[tuple[int, str]]:
    """Every string constant in `path` that is not a bare expression statement (a docstring)."""
    tree = ast.parse(path.read_text())
    docs = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docs
        ):
            yield node.lineno, node.value


def test_core_names_no_entity():
    """Only a tool's schema declares `entity` or `entity_type`; core treats every dim alike."""
    import datarecord

    package = Path(datarecord.__file__).parent
    hits = [
        f"{path.relative_to(package)}:{line}: {text!r}"
        for path in sorted(package.rglob("*.py"))
        if "tools" not in path.relative_to(package).parts
        for line, text in _code_strings(path)
        if re.search(r"\bentity(_type)?\b", text)
    ]
    assert hits == [], "core code spells a tool's dim or property by name"
